"""Normalized text generation for Vietnamese administrative documents.

Hybrid Pipeline (3 steps):
1. underthesea: Tokenization and OCR error detection
2. SymSpell: Generate correction suggestions via edit distance
3. LLM (Qwen3): Context-aware referee to choose correct words

Design goals:
- Generic for Vietnamese administrative documents, not for a single document type.
- Python does deterministic cleanup, line wrapping, and safety validation.
- LLM only used for ambiguous corrections; SymSpell handles clear cases directly.
- Partial reports are saved so failures do not hide intermediate results.

Input:
    data/extracted_text/{document_id}/page_*.txt

Output:
    data/normalized_text/{document_id}.txt
    data/normalized_text/{document_id}.normalized_report.json
    data/normalized_text/{document_id}.segments.json
    data/normalized_text/{document_id}.hybrid_report.json
"""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from openai import OpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from underthesea import word_tokenize
from symspellpy import SymSpell, Verbosity
from app.env import load_backend_env


load_backend_env()


# =========================================================
# CONFIG - keep it small
# =========================================================

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
EXTRACTED_TEXT_DIR = Path(os.getenv("EXTRACTED_TEXT_DIR", str(DATA_DIR / "extracted_text")))
NORMALIZED_TEXT_DIR = Path(os.getenv("NORMALIZED_TEXT_DIR", str(DATA_DIR / "normalized_text")))
NORMALIZED_WORK_DIR = Path(os.getenv("NORMALIZED_WORK_DIR", str(DATA_DIR / "normalized_work")))

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "ollama")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen3:4b-q4_K_M")
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "180"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1024"))
LLM_NUM_CTX = int(os.getenv("LLM_NUM_CTX", "4096"))
LLM_THINK = os.getenv("LLM_THINK", "false").lower() == "true"
LLM_KEEP_ALIVE = os.getenv("LLM_KEEP_ALIVE", "30m")
LLM_USE_RESPONSE_FORMAT = os.getenv("LLM_USE_RESPONSE_FORMAT", "true").lower() == "true"

OCR_BATCH_SIZE = int(os.getenv("OCR_BATCH_SIZE", "2"))
OCR_MAX_PROMPT_CHARS = int(os.getenv("OCR_MAX_PROMPT_CHARS", "3000"))
OCR_SEGMENT_MAX_LINES = int(os.getenv("OCR_SEGMENT_MAX_LINES", "8"))
OCR_SEGMENT_MAX_CHARS = int(os.getenv("OCR_SEGMENT_MAX_CHARS", "1200"))
OCR_TEXT_SNIPPET_CHARS = int(os.getenv("OCR_TEXT_SNIPPET_CHARS", "700"))
OCR_MERGE_MAX_BLOCK_LINES = int(os.getenv("OCR_MERGE_MAX_BLOCK_LINES", "16"))
OCR_JSON_RETRY_ATTEMPTS = int(os.getenv("OCR_JSON_RETRY_ATTEMPTS", "3"))
OCR_JSON_RETRY_WAIT_SECONDS = int(os.getenv("OCR_JSON_RETRY_WAIT_SECONDS", "2"))
OCR_ENABLE_LLM_REVIEW = os.getenv("OCR_ENABLE_LLM_REVIEW", "true").lower() == "true"
OCR_ENABLE_SEMANTIC_VALIDATION = os.getenv("OCR_ENABLE_SEMANTIC_VALIDATION", "true").lower() == "true"
OCR_SEMANTIC_BATCH_SIZE = int(os.getenv("OCR_SEMANTIC_BATCH_SIZE", "3"))
OCR_SAVE_REPORTS = os.getenv("OCR_SAVE_REPORTS", "false").lower() == "true"
SAVE_DEBUG_FILES = os.getenv("SAVE_DEBUG_FILES", "false").lower() == "true"


# =========================================================
# LOGGING / DATA STRUCTURES
# =========================================================

_log_file = None  # Will be set per pipeline run


def _log(step: str) -> None:
    print(f"[NORMALIZED-SESSION] {step}", flush=True)
    if _log_file:
        _log_file.write(f"[{time.strftime('%H:%M:%S')}] {step}\n")
        _log_file.flush()


def _log_stage(stage: str, **kwargs: Any) -> None:
    """Structured log with stage name and key-value metrics."""
    extras = " ".join(f"{k}={v}" for k, v in kwargs.items())
    msg = f"[NORMALIZED-SESSION] [{stage}] {extras}"
    print(msg, flush=True)
    if _log_file:
        _log_file.write(f"[{time.strftime('%H:%M:%S')}] [{stage}] {extras}\n")
        _log_file.flush()


def _log_llm_call(stage: str, batch_index: int | None, prompt_chars: int,
                  response_chars: int, duration_s: float, success: bool,
                  error: str = "") -> None:
    """Log LLM call metrics for performance analysis."""
    status = "OK" if success else "FAIL"
    batch_str = f"batch={batch_index}" if batch_index is not None else "single"
    msg = f"LLM {stage} {batch_str} prompt={prompt_chars} response={response_chars} {duration_s:.1f}s {status}"
    if error:
        msg += f" error={error[:120]}"
    full = f"[NORMALIZED-SESSION] [LLM] {msg}"
    print(full, flush=True)
    if _log_file:
        _log_file.write(f"[{time.strftime('%H:%M:%S')}] [LLM] {msg}\n")
        _log_file.flush()


def work_dir(document_id: str) -> Path:
    return NORMALIZED_WORK_DIR / document_id


def ensure_dirs(document_id: str) -> None:
    NORMALIZED_TEXT_DIR.mkdir(parents=True, exist_ok=True)
    for sub in ["partial_normalized", "llm_failures", "batch_reports"]:
        (work_dir(document_id) / sub).mkdir(parents=True, exist_ok=True)


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def update_progress(document_id: str, **data: Any) -> None:
    payload = dict(data or {})
    payload["document_id"] = document_id
    payload["updated_at"] = time.time()
    # Use direct JSON writing here so progress is still written even if OCR_SAVE_REPORTS=false.
    path = work_dir(document_id) / "progress.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass
class LineRecord:
    line_id: int
    text: str
    page: int | None = None


@dataclass
class SegmentRecord:
    segment_id: int
    line_ids: list[int]
    text: str
    kind: str
    start_line_id: int
    end_line_id: int


# =========================================================
# JSON PARSER
# =========================================================

def _strip_markdown_fence(content: str) -> str:
    s = str(content or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^\s*```(?:json|JSON)?\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s).strip()
    return s


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_think_blocks(content: str) -> str:
    """Remove think blocks that qwen3 models sometimes emit."""
    return _THINK_RE.sub("", content).strip()


def _cut_accidental_logs(content: str) -> str:
    markers = ["\nINFO:", "\nERROR:", "\nWARNING:", "\nTraceback", "\n[GIN]", "\n127.0.0.1:"]
    end = len(content)
    for marker in markers:
        pos = content.find(marker)
        if pos != -1:
            end = min(end, pos)
    return content[:end].strip()


def _remove_trailing_commas(content: str) -> str:
    return re.sub(r",(\s*[}\]])", r"\1", content)


def _extract_first_balanced_object(content: str) -> str | None:
    start = content.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escape = False
        for idx in range(start, len(content)):
            ch = content[idx]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return content[start:idx + 1]
        start = content.find("{", start + 1)
    return None


def _sanitize_json_outside_strings(content: str) -> str:
    out: list[str] = []
    in_string = False
    escape = False
    allowed_outside = set('{}[]:,.+-0123456789 \t\r\n')
    allowed_literals = set("truefalsenullTRUEFALSENULL")
    for ch in content:
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
        elif ch in allowed_outside or ch in allowed_literals:
            out.append(ch)
        else:
            continue
    return "".join(out)


def _try_json_object(content: str) -> dict[str, Any] | None:
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def extract_json_object(content: str) -> dict[str, Any]:
    raw = content or ""
    s = _cut_accidental_logs(_strip_think_blocks(_strip_markdown_fence(raw)))
    candidates = [s]
    balanced = _extract_first_balanced_object(s)
    if balanced:
        candidates.append(balanced)
    first = s.find("{")
    if first != -1:
        candidates.append(s[first:])

    tried: set[str] = set()
    for c in candidates:
        for v in [c, _remove_trailing_commas(c), _sanitize_json_outside_strings(c), _remove_trailing_commas(_sanitize_json_outside_strings(c))]:
            v = v.strip()
            if not v or v in tried:
                continue
            tried.add(v)
            obj = _try_json_object(v)
            if obj is not None:
                return obj
    raise ValueError(f"LLM did not return parseable JSON. Raw preview:\n{raw[:1500]}")


# =========================================================
# GENERIC ADMIN TEXT RULES
# =========================================================

VI_LOWER = "a-zàáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ"


def normalize_basic_spacing(line: str) -> str:
    s = str(line or "").replace("\ufeff", "").strip()
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)
    s = re.sub(r"([,.;:!?])(?=\S)", r"\1 ", s)
    s = re.sub(r"\s*/\s*", "/", s)
    s = re.sub(r"\s+-\s+", " - ", s)
    return s.strip()


def uppercase_ratio(text: str) -> float:
    letters = re.findall(r"[A-Za-zÀ-ỹĐđ]", text)
    if not letters:
        return 0.0
    uppers = [c for c in letters if c.upper() == c and c.lower() != c]
    return len(uppers) / len(letters)


def starts_lowercase(text: str) -> bool:
    return bool(re.match(rf"^[{VI_LOWER}]", text.strip()))


def starts_numbered_marker(text: str) -> bool:
    return bool(re.match(r"^\d+[.)]\s+", text.strip()))


def starts_decimal_marker(text: str) -> bool:
    return bool(re.match(r"^\d+(?:\.\d+)+[.)]?\s+", text.strip()))


def starts_lettered_marker(text: str) -> bool:
    return bool(re.match(r"^[A-Za-zÀ-ỹĐđ][.)]\s+", text.strip(), flags=re.IGNORECASE))


def starts_roman_marker(text: str) -> bool:
    return bool(re.match(r"^[IVXLCDM]+[.)]\s+", text.strip(), flags=re.IGNORECASE))


def starts_article_marker(text: str) -> bool:
    return bool(re.match(r"^Điều\s+\d+[.:]?\s+", text.strip(), flags=re.IGNORECASE))


def starts_major_admin_marker(text: str) -> bool:
    return bool(re.match(r"^(PHẦN|CHƯƠNG|MỤC|TIỂU\s+MỤC)\s+([IVXLCDM]+|\d+|THỨ\s+\w+)", text.strip(), flags=re.IGNORECASE))


def starts_bullet(text: str) -> bool:
    return bool(re.match(r"^[-–•+]\s+", text.strip()))


def starts_structural_marker(text: str) -> bool:
    # Use generator for true short-circuit evaluation (avoids calling all 7 checks)
    return any(fn(text) for fn in (
        starts_numbered_marker, starts_decimal_marker, starts_lettered_marker,
        starts_roman_marker, starts_article_marker, starts_major_admin_marker, starts_bullet
    ))


def looks_title_like_line(text: str) -> bool:
    s = text.strip()
    if not s or starts_structural_marker(s):
        return False
    if len(s.split()) <= 12 and uppercase_ratio(s) >= 0.65 and not re.search(r"[.!?…]$", s):
        return True
    return False


def looks_metadata_like_line(text: str) -> bool:
    s = text.strip()
    if not s or starts_structural_marker(s):
        return False
    patterns = [
        r"^(số|so)\s*[:：]",
        r"\bngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4}\b",
        r"độc\s+lập\s*-\s*tự\s+do\s*-\s*hạnh\s+phúc",
        r"^(cộng\s+hòa\s+xã\s+hội\s+chủ\s+nghĩa\s+việt\s+nam)$",
    ]
    return any(re.search(p, s, flags=re.IGNORECASE) for p in patterns)


def looks_footer_or_signature_line(text: str) -> bool:
    s = text.strip()
    return bool(re.match(r"^(Nơi nhận|Kính gửi|Lưu|KT\.|TM\.|TL\.|TUQ\.|PHỤ LỤC)\b", s, flags=re.IGNORECASE))


def is_probable_garbage_line(line: str) -> bool:
    """Generic garbage detector for OCR artifacts in Vietnamese admin documents.

    Catches format-level garbage AND common OCR noise patterns observed in real data.
    Semantic noise removal is still handled by LLM validation for borderline cases.
    """
    s = line.strip()
    if not s:
        return True

    # Page markers and standalone page numbers are layout artifacts, not document content.
    if re.match(r"^={2,}\s*PAGE\s+\d+\s*={2,}\s*\d*\s*$", s, flags=re.IGNORECASE):
        return True
    if re.match(r"^\d+\s*$", s):
        return True

    # Lines made almost entirely of punctuation/symbols.
    letters_or_digits = re.findall(r"[A-Za-zÀ-ỹĐđ0-9]", s)
    if len(letters_or_digits) == 0 and len(s) <= 12:
        return True

    # Very short symbol-heavy fragments, e.g. ", _".
    symbol_count = len(re.findall(r"[^A-Za-zÀ-ỹĐđ0-9\s]", s))
    if len(s) <= 8 and symbol_count >= max(2, len(letters_or_digits) + 1):
        return True

    # OCR noise: lines with trailing ". . . . ." or ".. .. .." patterns (common OCR garbage)
    if re.search(r"(\.\s){3,}\.?\s*$", s):
        return True

    # OCR noise: lines with mostly dots, commas, or repeated punctuation
    # High ratio of dots/commas relative to text length.
    dots_and_commas = s.count(".") + s.count(",")
    if len(s) > 5 and dots_and_commas / len(s) > 0.4:
        return True

    # OCR noise: lines that are mostly single letters or short fragments separated by spaces (e.g. "T a i l i e u")
    # Pattern: alternating single chars and spaces with very few real words.
    if re.match(r"^([A-Za-zÀ-ỹĐđ]\s){4,}[A-Za-zÀ-ỹĐđ]$", s):
        return True

    # OCR noise: lines that are just punctuation markers repeated (e.g. "........", "--------", "________")
    if re.match(r"^([.\-=_*]{2,}\s*)+$", s):
        return True

    # OCR noise: very short lines with no letters or digits at all but longer than 12 chars (symbol-only spam)
    if len(letters_or_digits) == 0 and len(s) > 12:
        return True

    return False




def line_ends_sentence(text: str) -> bool:
    return bool(re.search(r"[.!?…;]$", text.strip()))


def is_hard_structural_line(text: str) -> bool:
    s = text.strip()
    return (
        is_probable_garbage_line(s)
        or looks_title_like_line(s)
        or looks_metadata_like_line(s)
        or looks_footer_or_signature_line(s)
        or starts_structural_marker(s)
    )


def should_merge_lines(prev_line: str, curr_line: str) -> bool:
    prev = normalize_basic_spacing(prev_line)
    curr = normalize_basic_spacing(curr_line)
    if not prev or not curr:
        return False
    if is_hard_structural_line(curr):
        return False
    score = 0
    # Strong merge signals
    if prev.endswith((",", "-", "–", "(", "/", ":")):
        score += 4
    if prev.endswith(";"):
        score += 3  # semicolon is list separator in admin docs, not sentence end
    # Previous line has no sentence-ending punctuation
    if not prev.endswith((".", "?", "!", "…\"")):
        score += 3
    # Current line starts lowercase → continuation
    if starts_lowercase(curr):
        score += 3
    # Current line starts with continuation words
    if curr.lower().startswith(("và ", "hoặc ", "của ", "theo ", "trong ", "để ", "về ", "với ", "từ ", "đến ", "cho ", "do ", "nhằm ")):
        score += 2
    # Sentence-ending punctuation → strong break signal
    if prev.endswith((".", "?", "!")):
        score -= 5
    # Quoted sentence end → break
    if prev.endswith(("…\"",)):
        score -= 4
    return score >= 4


def apply_safe_rule_corrections(line: str) -> str:
    s = normalize_basic_spacing(line)
    replacements = [
        (r"\bSo\s*:\s*", "Số: "),
        (r"\bSố\s*:\s*", "Số: "),
        (r"\bngay\s+(\d{1,2})\s+tháng\b", r"ngày \1 tháng"),
        (r"\bthang\s+(\d{1,2})\b", r"tháng \1"),
        (r"\bnam\s+(\d{4})\b", r"năm \1"),
        (r"^[_]+\s+", ""),
        (r",\s*\.\s*", ", "),
        (r"\.\s+\.\s+\.", "..."),
    ]
    for pattern, repl in replacements:
        s = re.sub(pattern, repl, s, flags=re.IGNORECASE)
    return normalize_basic_spacing(s)


def split_combined_admin_headers(line: str) -> list[str]:
    s = normalize_basic_spacing(line)
    patterns = [
        (r"^(.*?)\s+(CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM)\s+(.*)$", [r"\1", r"\2", r"\3"]),
        (r"^(CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM)\s+(Độc lập\s*-\s*Tự do\s*-\s*Hạnh phúc)$", [r"\1", r"\2"]),
    ]
    for pattern, parts in patterns:
        m = re.match(pattern, s, flags=re.IGNORECASE)
        if m:
            out = [m.expand(part).strip() for part in parts if m.expand(part).strip()]
            # Only split if it does not create a huge arbitrary prefix.
            if len(out) >= 2 and all(len(x) <= 120 for x in out):
                return out
    return [s]


# =========================================================
# PREPARE / MERGE / SEGMENT
# =========================================================

def _natural_sort_key(path: Path) -> int:
    """Extract numeric part from page_N.txt for natural sorting."""
    m = re.search(r"(\d+)", path.stem)
    return int(m.group(1)) if m else 0


def load_raw_extracted_text(document_id: str) -> str:
    base_path = EXTRACTED_TEXT_DIR / document_id
    _log(f"Checking extracted path: {base_path}")
    page_files = sorted(base_path.glob("page_*.txt"), key=_natural_sort_key)
    _log(f"Found pages: {len(page_files)}")
    if not page_files:
        raise FileNotFoundError(f"Không tìm thấy file tại {base_path}")
    pages: list[str] = []
    for idx, page_file in enumerate(page_files, start=1):
        content = page_file.read_text(encoding="utf-8")
        pages.append(f"=== PAGE {idx} ===\n{content}")
    return "\n\n".join(pages)


def prepare_lines(raw_text: str) -> list[LineRecord]:
    lines: list[LineRecord] = []
    page = None
    line_id = 1
    for raw_line in raw_text.splitlines():
        s = normalize_basic_spacing(raw_line)
        if not s:
            continue
        m = re.match(r"^={2,}\s*PAGE\s+(\d+)\s*={2,}", s, flags=re.IGNORECASE)
        if m:
            page = int(m.group(1))
            continue
        for part in split_combined_admin_headers(s):
            part = apply_safe_rule_corrections(part)
            if is_probable_garbage_line(part):
                continue
            lines.append(LineRecord(line_id=line_id, text=part, page=page))
            line_id += 1
    return lines


def merge_visual_wrapped_lines(lines: list[LineRecord]) -> list[LineRecord]:
    merged: list[LineRecord] = []
    for line in lines:
        if not merged:
            merged.append(line)
            continue
        prev = merged[-1]
        if should_merge_lines(prev.text, line.text):
            merged[-1] = LineRecord(prev.line_id, normalize_basic_spacing(prev.text + " " + line.text), prev.page)
        else:
            merged.append(line)
    # Reassign line IDs after merge for stable normalized output.
    return [LineRecord(i + 1, x.text, x.page) for i, x in enumerate(merged)]


def is_strict_document_metadata_line(text: str, position_ratio: float = 1.0) -> bool:
    """Detect only strong document metadata, not body lines that merely contain dates."""
    s = text.strip()
    if not s:
        return False

    lower = s.lower()

    if re.match(r"^số\s*[:：]", lower):
        return True

    if re.search(r"cộng\s+hòa\s+xã\s+hội\s+chủ\s+nghĩa\s+việt\s+nam", lower):
        return True

    if re.search(r"độc\s+lập\s*-\s*tự\s+do\s*-\s*hạnh\s+phúc", lower):
        return True

    if position_ratio < 0.20 and re.search(r"\b\w+,\s*ngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4}\b", lower):
        return True

    if re.match(r"^(người\s*k[ýyỳ]|email|e-mail|cơ quan|thời gian ký|thoi gian ky)\s*:", lower):
        return True

    return False


def classify_segment_kind(
    lines: list[LineRecord],
    previous_kind: str | None = None,
    position_ratio: float = 1.0,
) -> str:
    first = lines[0].text if lines else ""

    if looks_title_like_line(first):
        return "STRUCTURAL_TITLE"

    if starts_structural_marker(first):
        return "STRUCTURAL_UNIT"

    if looks_footer_or_signature_line(first):
        return "FOOTER_OR_SIGNATURE"

    if is_strict_document_metadata_line(first, position_ratio=position_ratio):
        return "METADATA"

    if previous_kind in {"STRUCTURAL_UNIT", "BODY_CONTINUATION", "PARAGRAPH_OR_SENTENCE", "LINE"}:
        if not starts_structural_marker(first) and not looks_title_like_line(first) and not is_strict_document_metadata_line(first, position_ratio):
            if (
                starts_lowercase(first)
                or not re.search(r"[.!?…:]$", first.strip())
                or re.match(r"^\d{1,2}\s+năm\b", first.strip(), flags=re.IGNORECASE)
            ):
                return "BODY_CONTINUATION"

    if len(lines) == 1:
        return "LINE"

    return "PARAGRAPH_OR_SENTENCE"


def build_sentence_segments(lines: list[LineRecord]) -> list[SegmentRecord]:
    segments: list[SegmentRecord] = []
    current: list[LineRecord] = []
    total = max(len(lines), 1)

    def flush() -> None:
        nonlocal current
        if not current:
            return
        text = "\n".join(x.text for x in current)
        previous_kind = segments[-1].kind if segments else None
        position_ratio = (current[0].line_id - 1) / total
        kind = classify_segment_kind(current, previous_kind=previous_kind, position_ratio=position_ratio)
        segments.append(SegmentRecord(
            segment_id=len(segments) + 1,
            line_ids=[x.line_id for x in current],
            text=text,
            kind=kind,
            start_line_id=current[0].line_id,
            end_line_id=current[-1].line_id,
        ))
        current = []

    for line in lines:
        if is_hard_structural_line(line.text):
            flush()
            current = [line]
            flush()
            continue

        current.append(line)
        current_text = " ".join(x.text for x in current)
        if line_ends_sentence(line.text) or len(current) >= OCR_SEGMENT_MAX_LINES or len(current_text) >= OCR_SEGMENT_MAX_CHARS:
            flush()

    flush()
    return segments


# =========================================================
# LLM REVIEW USING ENUMS

# =========================================================
# LLM OUTPUT RULES
# =========================================================

JSON_OUTPUT_RULES = (
    "/no_think\n"
    "Output constraints:\n"
    "- Return exactly one valid JSON object.\n"
    "- Do not use markdown code fences.\n"
    "- Do not write reasoning or analysis.\n"
    "- Do not include <think> blocks.\n"
    "- Do not add comments, logs, or text outside JSON.\n"
    "- End immediately after the final closing brace }."
)

# =========================================================
# LLM CLIENT & JSON CALLS (kept for compatibility)
# =========================================================

def make_client() -> OpenAI:
    return OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY, timeout=LLM_TIMEOUT_SECONDS)


class EmptyLLMResponseError(Exception):
    """LLM returned empty or whitespace-only content."""
    pass


class LLMJSONParseError(Exception):
    """LLM returned content but it could not be parsed as JSON."""
    pass


def _retry_json():
    return retry(
        stop=stop_after_attempt(OCR_JSON_RETRY_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((EmptyLLMResponseError, LLMJSONParseError)),
        reraise=True,
    )


def clip_text(text: str, max_chars: int) -> str:
    s = " ".join(str(text or "").split())
    if len(s) <= max_chars:
        return s
    if max_chars <= 20:
        return s[:max_chars]
    half = max_chars // 2
    return s[:half].rstrip() + " ... " + s[-half:].lstrip()


def call_llm_json(client: OpenAI, prompt: str, response_format: dict[str, Any] | None = None, document_id: str | None = None, stage: str = "", batch_index: int | None = None) -> dict[str, Any]:
    """Call LLM and return parsed JSON."""

    @_retry_json()
    def _call():
        kwargs: dict[str, Any] = {
            "model": LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "top_p": 0.1,
            "max_tokens": LLM_MAX_TOKENS,
            "extra_body": {
                "think": LLM_THINK,
                "keep_alive": LLM_KEEP_ALIVE,
                "options": {"num_ctx": LLM_NUM_CTX, "temperature": 0, "top_p": 0.1, "top_k": 1},
            },
        }
        if LLM_USE_RESPONSE_FORMAT and response_format:
            kwargs["response_format"] = response_format
        t0 = time.time()
        resp = client.chat.completions.create(**kwargs)
        raw = resp.choices[0].message.content or ""
        elapsed = time.time() - t0
        if not raw.strip():
            _log_llm_call(stage, batch_index, len(prompt), 0, elapsed, False, "empty_response")
            raise EmptyLLMResponseError(f"LLM returned empty response for stage={stage}")
        try:
            result = extract_json_object(raw)
            _log_llm_call(stage, batch_index, len(prompt), len(raw), elapsed, True)
            return result
        except EmptyLLMResponseError:
            raise
        except Exception as e:
            _log_llm_call(stage, batch_index, len(prompt), len(raw), elapsed, False, str(e))
            raise LLMJSONParseError(f"Could not parse JSON from LLM stage={stage}: {str(e)[:100]}")

    return _call()


# =========================================================
# HYBRID PIPELINE: heuristic detect + context + LLM review
# =========================================================
#
# Flow:
#   OCR text → normalize → heuristic error detection →
#   context validation → generate candidates → LLM review
#   → Python applies validated corrections
#

def _strip_diacritics(text: str) -> str:
    """Remove Vietnamese diacritics, keep base letters."""
    text = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn").lower()


# Precompiled regex for strange character detection
_RE_NORMALIZE_QUOTES = re.compile(r"[\u201C\u201D\u2018\u2019\u00AB\u00BB]")  # fancy quotes → ASCII
_RE_STRANGE_CHARS = re.compile(
    r"[^\w\s.,;:!?/\\(){}@#$%^&*+=<>~`|\"'\-_–—…àáảãạăắằẵặấầẩẫậèéẻẽẹêếềểễệ"
    r"ìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ"
    r"ÀÁẢÃẠĂẮẰẴẶẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢ"
    r"ÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴĐ]"
)


def clean_strange_chars(text: str) -> str:
    """Remove non-standard characters from text.

    Keeps: Vietnamese letters, digits, common ASCII punctuation, whitespace.
    Normalizes fancy quotes to ASCII.
    Removes: OCR noise like ¬, §, ¶, stray symbols.
    """
    # Normalize fancy quotes to ASCII
    text = _RE_NORMALIZE_QUOTES.sub('"', text)
    # Remove remaining strange characters
    return _RE_STRANGE_CHARS.sub("", text)


def _has_vietnamese_diacritics(text: str) -> bool:
    """Check if text contains Vietnamese diacritic characters."""
    return bool(re.search(
        r"[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ]",
        text.lower()
    ))


_SYMSPELL_INSTANCE: SymSpell | None = None
_BASE_FORM_INDEX: dict[str, list[tuple[str, int]]] | None = None


def _load_symspell_vi() -> SymSpell:
    """Load Vietnamese dictionary for SymSpell (cached singleton)."""
    global _SYMSPELL_INSTANCE
    if _SYMSPELL_INSTANCE is not None:
        return _SYMSPELL_INSTANCE
    sym = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
    dict_path = Path(__file__).resolve().parents[2] / "data" / "vi_frequency_dict.txt"
    if not dict_path.exists():
        _log(f"WARNING: SymSpell dictionary not found at {dict_path}")
        _SYMSPELL_INSTANCE = sym
        return sym
    sym.load_dictionary(str(dict_path), term_index=0, count_index=1, separator="\t")
    _SYMSPELL_INSTANCE = sym
    # Build base_form index: stripped_form -> [(original_word, freq), ...]
    # Index all words (single + compound) for missing-diacritics lookup
    global _BASE_FORM_INDEX
    if _BASE_FORM_INDEX is None:
        _BASE_FORM_INDEX = {}
        for word, count in sym.words.items():
            base = _strip_diacritics(word)
            if base != word.lower():  # only index words that have diacritics
                _BASE_FORM_INDEX.setdefault(base, []).append((word, count))
            # Also add d-đ alias: strip đ -> d for OCR missing-đ detection
            if 'đ' in base:
                alias = base.replace('đ', 'd')
                if alias != base:
                    _BASE_FORM_INDEX.setdefault(alias, []).append((word, count))
        for entries in _BASE_FORM_INDEX.values():
            entries.sort(key=lambda x: -x[1])  # sort by freq descending
    return sym


# =========================================================
# STEP 1: Heuristic error detection
# =========================================================

def detect_errors_heuristic(text: str, sym: SymSpell) -> list[dict[str, Any]]:
    """Detect suspected OCR errors using heuristics.

    Heuristics:
    1. Word has Vietnamese diacritics but NOT in SymSpell dictionary
    2. Word looks like OCR noise (random chars, numbers mixed with letters)
    3. Word is a known OCR error pattern (e.g., single-letter words with diacritics)
    4. Word missing diacritics - base form exists in dictionary (e.g., "phap" -> "pháp")
    5. Word has wrong diacritic position - base form matches dictionary entries

    Returns list of suspected errors with word, position, and reason.
    """
    tokens = word_tokenize(text, format="text")
    words = tokens.split()
    flagged: list[dict[str, Any]] = []
    seen: set[str] = set()

    for word in words:
        # Normalize underthesea underscore tokens (de_nghi -> de nghi)
        clean = word.strip().replace("_", " ")
        if not clean or len(clean) < 2:
            continue
        if clean in seen:
            continue
        seen.add(clean)

        # Skip numbers, pure ASCII, structural markers
        if re.match(r"^[\d\s\W]+$", clean):
            continue
        # Skip pure punctuation
        if not any(c.isalpha() for c in clean):
            continue
        # Skip proper nouns (person names, place names)
        # Vietnamese names: 2-5 words, each starting with uppercase
        # Also skip ALL_CAPS short words that look like abbreviations
        if _is_proper_noun(clean):
            continue

        reasons = []
        clean_lower = clean.lower()

        # Heuristic 1: has diacritics but not in dictionary
        has_diacritics = _has_vietnamese_diacritics(clean)
        in_dict = clean_lower in sym.words

        if has_diacritics and not in_dict:
            reasons.append("NOT_IN_DICT")

        # Heuristic 2: looks like OCR noise (mixed letters/numbers)
        if re.search(r"[a-zA-Z].*\d|\d.*[a-zA-Z]", clean) and not re.match(r"^(ngày|tháng|năm|số|điều|khoản|mục)\s", clean_lower):
            reasons.append("OCR_NOISE")

        # Heuristic 3: single-letter word with diacritics AND low frequency (likely OCR error)
        # Skip common words like 'có' (542K), 'từ' (120K), 'bộ' (31K)
        if len(clean) == 2 and has_diacritics and not in_dict:
            reasons.append("SINGLE_LETTER_DIACRITIC")

        # Heuristic 4: missing diacritics (ASCII-only word, base form in dict)
        # e.g., "phap" not in dict, but "pháp" is in dict via base_form_index
        if not has_diacritics and not in_dict and _BASE_FORM_INDEX:
            base = _strip_diacritics(clean)  # same as clean_lower for ASCII
            if base in _BASE_FORM_INDEX:
                candidates = [w for w, _ in _BASE_FORM_INDEX[base]]
                if candidates:
                    reasons.append("MISSING_DIACRITICS")

        # Heuristic 5: wrong diacritic position (has diacritics, not in dict, base form matches dict entries)
        # e.g., "trành" not in dict, but base "tranh" -> "tranh" is in dict
        if has_diacritics and not in_dict and _BASE_FORM_INDEX:
            base = _strip_diacritics(clean)
            if base in _BASE_FORM_INDEX:
                candidates = [w for w, _ in _BASE_FORM_INDEX[base]]
                if candidates and clean_lower not in candidates:
                    reasons.append("WRONG_DIACRITIC")

        # Heuristic 6: likely wrong word (in dict but very low freq vs top candidate)
        # e.g., "nhiêu" (freq=289) vs "nhiều" (freq=122987) — ratio 426x
        if in_dict and _BASE_FORM_INDEX and not reasons:
            base = _strip_diacritics(clean)
            if base in _BASE_FORM_INDEX:
                entries = _BASE_FORM_INDEX[base]
                word_freq = sym.words.get(clean_lower, 0)
                top_word, top_freq = entries[0] if entries else ("", 0)
                # Flag if: word freq < 2000, top candidate freq >= 10x, and word is not the top candidate
                if word_freq < 2000 and top_freq >= 10 * word_freq and top_word != clean_lower:
                    reasons.append("LIKELY_WRONG")

        if reasons:
            # Find position in original text
            pos = text.find(clean)
            if pos == -1:
                continue
            flagged.append({
                "token": clean,
                "position": pos,
                "base_form": _strip_diacritics(clean),
                "reasons": reasons,
            })

    return flagged


# =========================================================
# STEP 2: Context validation
# =========================================================

def validate_with_context(text: str, flagged: list[dict[str, Any]], sym: SymSpell) -> list[dict[str, Any]]:
    """Validate suspected errors by checking context (surrounding words).

    Context checks:
    1. Word appears multiple times in text - likely correct (not flagged)
    2. Word is part of a known phrase (e.g., "nhân dân" is always correct)
    3. Word is adjacent to structural markers (e.g., "Số:", "Ngày:")

    Returns filtered list of confirmed errors.
    """
    confirmed = []
    text_lower = text.lower()

    for item in flagged:
        token = item["token"]
        token_lower = token.lower()

        # Skip if word appears multiple times (likely correct)
        count = text_lower.count(token_lower)
        if count > 1:
            continue

        # Skip if word is adjacent to structural markers
        pos = item["position"]
        context_before = text[max(0, pos-50):pos].lower()
        context_after = text[pos+len(token):pos+len(token)+50].lower()

        # Structural markers that indicate the word is likely correct
        structural_markers = ["số:", "ngày:", "tháng:", "năm:", "điều:", "khoản:", "mục:", "phần:"]
        if any(marker in context_before for marker in structural_markers):
            continue

        confirmed.append(item)

    return confirmed


# =========================================================
# STEP 3: Generate correction candidates
# =========================================================

def generate_candidates(text: str, flagged: list[dict[str, Any]], sym: SymSpell) -> list[dict[str, Any]]:
    """Generate correction candidates for each flagged word using SymSpell.

    For each flagged word, find the closest valid words in the dictionary.
    Falls back to base_form_index for MISSING_DIACRITICS/WRONG_DIACRITIC errors.
    For adjacent flagged words, try compound-word lookup (e.g., "tham quyen" -> "thẩm quyền").
    Returns list with added "candidates" field.
    """
    for item in flagged:
        reasons = item.get("reasons", [])

        # For missing-diacritics / wrong-diacritic / likely-wrong / single-letter errors, use base_form_index
        # (SymSpell edit distance can't bridge the gap or would give wrong results)
        if any(r in reasons for r in ("MISSING_DIACRITICS", "WRONG_DIACRITIC", "LIKELY_WRONG", "SINGLE_LETTER_DIACRITIC")) and _BASE_FORM_INDEX:
            base = item.get("base_form", "")
            if base in _BASE_FORM_INDEX:
                candidates = [w for w, _ in _BASE_FORM_INDEX[base]
                              if w != item["token"].lower()][:10]
                if candidates:
                    item["candidates"] = candidates
                    continue

        # Standard SymSpell edit-distance lookup
        suggestions = sym.lookup(
            item["token"], Verbosity.CLOSEST, max_edit_distance=2, transfer_casing=True
        )
        # Filter out the word itself and get top 3
        candidates = [s.term for s in suggestions if s.term != item["token"]][:10]
        item["candidates"] = candidates

    # Compound-word merge: for adjacent flagged words, try pairing them
    # Also try pairing a flagged word with the NEXT word in text (even if not flagged)
    if _BASE_FORM_INDEX and len(flagged) >= 1:
        flagged_sorted = sorted(flagged, key=lambda x: x.get("position", 0))
        skip_indices: set[int] = set()
        merged_flagged: list[dict[str, Any]] = []

        for i in range(len(flagged_sorted)):
            if i in skip_indices:
                continue
            cur = flagged_sorted[i]
            cur_base = cur.get("base_form", _strip_diacritics(cur.get("token", "")))
            cur_end = cur.get("position", 0) + len(cur.get("token", ""))

            # Strategy 1: pair with next flagged word
            if i + 1 < len(flagged_sorted):
                nxt = flagged_sorted[i + 1]
                nxt_pos = nxt.get("position", 0)
                gap = text[cur_end:nxt_pos]
                if len(gap) <= 1 and (not gap or gap.isspace()):
                    nxt_base = nxt.get("base_form", _strip_diacritics(nxt.get("token", "")))
                    compound_base = f"{cur_base} {nxt_base}"
                    if compound_base in _BASE_FORM_INDEX:
                        compound_candidates = [w for w, _ in _BASE_FORM_INDEX[compound_base]
                                               if w != compound_base][:5]
                        if compound_candidates:
                            cur["compound_candidates"] = compound_candidates
                            cur["compound_with"] = nxt["token"]
                            cur["compound_position_end"] = nxt_pos + len(nxt.get("token", ""))
                            skip_indices.add(i + 1)
                            merged_flagged.append(cur)
                            continue

            # Strategy 2: pair with next word in text (even if not flagged)
            # Extract next word from text after current word
            remaining = text[cur_end:].lstrip()
            if remaining:
                next_word_match = re.match(r"(\S+)", remaining)
                if next_word_match:
                    next_word = next_word_match.group(1)
                    # Only try if next word looks Vietnamese (not punctuation, not number)
                    if re.match(r"^[a-zA-ZÀ-ỹĐđ]+$", next_word):
                        gap_len = len(text[cur_end:]) - len(text[cur_end:].lstrip())
                        if gap_len <= 2:  # at most 2 spaces
                            next_base = _strip_diacritics(next_word)
                            compound_base = f"{cur_base} {next_base}"
                            if compound_base in _BASE_FORM_INDEX:
                                compound_candidates = [w for w, _ in _BASE_FORM_INDEX[compound_base]
                                                       if w != compound_base][:5]
                                if compound_candidates:
                                    next_pos = cur_end + gap_len
                                    cur["compound_candidates"] = compound_candidates
                                    cur["compound_with"] = next_word
                                    cur["compound_position_end"] = next_pos + len(next_word)
                                    merged_flagged.append(cur)
                                    continue

            # Strategy 3: pair with PREVIOUS word in text (even if not flagged)
            # e.g., "thanh pho" -> "pho" flagged, look back to find "thanh"
            cur_pos = cur.get("position", 0)
            text_before = text[:cur_pos].rstrip()
            if text_before:
                prev_word_match = re.search(r"(\S+)$", text_before)
                if prev_word_match:
                    prev_word = prev_word_match.group(1)
                    if re.match(r"^[a-zA-ZÀ-ỹĐđ]+$", prev_word):
                        gap_len = cur_pos - len(text_before)
                        if gap_len <= 2:
                            prev_base = _strip_diacritics(prev_word)
                            compound_base = f"{prev_base} {cur_base}"
                            if compound_base in _BASE_FORM_INDEX:
                                compound_candidates = [w for w, _ in _BASE_FORM_INDEX[compound_base]
                                                       if w != compound_base][:5]
                                if compound_candidates:
                                    prev_pos = len(text_before)
                                    cur["compound_candidates"] = compound_candidates
                                    cur["compound_with"] = prev_word
                                    cur["compound_position_start"] = prev_pos
                                    cur["compound_position_end"] = cur_pos + len(cur.get("token", ""))
                                    merged_flagged.append(cur)
                                    continue

            merged_flagged.append(cur)

        flagged = merged_flagged

    # Only keep items that have candidates
    return [item for item in flagged if item.get("candidates") or item.get("compound_candidates")]


# =========================================================
# STEP 4: LLM reviews and chooses corrections
# =========================================================

# JSON schema for LLM correction response
CORRECTION_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "correction_response",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "corrections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "word": {"type": "string"},
                            "chosen": {"type": "string"},
                            "reason": {"type": "string"},
                        },
                        "required": ["word", "chosen", "reason"],
                    },
                },
            },
            "required": ["corrections"],
        },
    },
}


def _get_context_snippet(text: str, position: int, word_len: int, before: int = 60, after: int = 60) -> tuple[str, str]:
    """Extract context snippets before and after a word at given position."""
    ctx_before = text[max(0, position - before):position].strip()
    ctx_after = text[position + word_len:position + word_len + after].strip()
    return ctx_before, ctx_after


def _is_proper_noun(token: str) -> bool:
    """Check if token looks like a Vietnamese proper noun (person name, place name).

    Pattern: Title Case (not ALL CAPS), 2-4 words, each starting with uppercase.
    Example: "Tô Lâm", "Nguyễn Văn A", "Hà Nội", "Bộ Công Thương"
    NOT: "VAN PHONG", "CONG HÒA" (these are ALL CAPS OCR errors)
    """
    clean = token.strip()
    if not clean or not clean[0].isupper():
        return False
    # Reject ALL CAPS — these are likely OCR errors, not names
    if clean.isupper():
        return False
    words = clean.split()
    if len(words) < 2 or len(words) > 5:
        return False
    # Each word should start with uppercase
    return all(w[0].isupper() for w in words if w)


def build_llm_review_prompt(text: str, flagged: list[dict[str, Any]]) -> str:
    """Build prompt asking LLM to review suspected errors and choose corrections.

    The LLM sees the full text and a list of suspected errors with context snippets.
    It chooses the best correction for each error based on context.
    """
    if not flagged:
        return ""

    error_lines = []
    for item in flagged[:10]:  # Limit to 10 errors max
        candidates = list(item.get("candidates", []))
        # Add compound candidates (e.g., "tham quyen" -> "thẩm quyền")
        compound_cands = item.get("compound_candidates", [])
        compound_with = item.get("compound_with", "")
        if compound_cands and compound_with:
            candidates.extend([f"[{c}]" for c in compound_cands])  # bracket to indicate compound
        candidates_str = ", ".join(candidates)
        reasons = ", ".join(item.get("reasons", []))
        pos = item.get("position", -1)
        ctx_before, ctx_after = "", ""
        if pos >= 0:
            ctx_before, ctx_after = _get_context_snippet(text, pos, len(item["token"]))
        context_part = ""
        if ctx_before or ctx_after:
            context_part = f' context: "...{ctx_before} [{item["token"]}] {ctx_after}..."'
        error_lines.append(f'- "{item["token"]}" -> candidates: [{candidates_str}] (reasons: {reasons}){context_part}')

    errors_text = "\n".join(error_lines)

    return (
        f"/no_think\n"
        f"Review this Vietnamese text for OCR errors. The following words are suspected errors:\n\n"
        f"{errors_text}\n\n"
        f"Text:\n{text}\n\n"
        f"For each error, pick the best correction from the candidates based on context. "
        f"If a word is actually correct, skip it.\n"
        f"IMPORTANT: Do NOT correct proper nouns (person names, place names). "
        f"If a word starts with uppercase and appears to be a name, skip it even if it has candidates.\n"
        f"Return JSON:\n"
        f'{{"corrections": [{{"word": "error", "chosen": "correction", "reason": "why"}}]}}'
    )


def apply_validated_corrections(text: str, llm_corrections: list[dict[str, Any]], flagged: list[dict[str, Any]], sym: SymSpell) -> str:
    """Apply LLM-chosen corrections with strict validation.

    Rules:
    - Only replace words that are in the flagged list
    - Only replace with words from SymSpell candidates (not LLM-invented words)
    - Case-preserving replacement
    - Handle compound candidates (e.g., [thẩm quyền] replaces "tham quyen")
    - Log each decision for audit
    """
    if not llm_corrections:
        return text

    # Build lookup: word -> allowed candidates (including compound)
    allowed_map: dict[str, list[str]] = {}
    # Map for compound: first_word -> (second_word, compound_candidates, position_end)
    compound_map: dict[str, dict[str, Any]] = {}
    for item in flagged:
        allowed_map[item["token"].lower()] = item.get("candidates", [])
        if item.get("compound_candidates") and item.get("compound_with"):
            allowed_map[item["token"].lower()].extend(
                [f"[{c}]" for c in item["compound_candidates"]]
            )
            compound_map[item["token"].lower()] = {
                "second_word": item["compound_with"],
                "candidates": item["compound_candidates"],
                "end_pos": item.get("compound_position_end"),
                "start_pos": item.get("compound_position_start"),
            }

    result = text
    for corr in llm_corrections:
        word = str(corr.get("word", "")).strip()
        chosen = str(corr.get("chosen", "")).strip()
        reason = str(corr.get("reason", "")).strip()

        if not word or not chosen:
            continue

        # Validate: word must be in flagged list (exact or fuzzy match)
        word_lower = word.lower()
        if word_lower not in allowed_map:
            # Fuzzy: try base_form match (LLM may return slightly different diacritics)
            word_base = _strip_diacritics(word)
            fuzzy_match = None
            for flagged_word in allowed_map:
                if _strip_diacritics(flagged_word) == word_base:
                    fuzzy_match = flagged_word
                    break
            if fuzzy_match:
                word_lower = fuzzy_match
                word = fuzzy_match
            else:
                _log(f"LLM correction REJECTED: '{word}' not in flagged list")
                continue

        # Skip proper nouns — don't correct names even if LLM suggests it
        if _is_proper_noun(word):
            _log(f"LLM correction REJECTED: '{word}' is a proper noun (name/place)")
            continue

        # Validate: chosen must be from SymSpell candidates (including compound)
        allowed = [c.lower() for c in allowed_map[word_lower]]
        is_compound = chosen.startswith("[") and chosen.endswith("]")
        chosen_clean = chosen.strip("[]") if is_compound else chosen
        if chosen_clean.lower() not in allowed and chosen.lower() not in allowed:
            _log(f"LLM correction REJECTED: '{chosen}' not in candidates for '{word}'")
            continue

        if is_compound and word_lower in compound_map:
            # Compound replacement: replace "word1 word2" with compound word
            info = compound_map[word_lower]
            second_word = info["second_word"]
            start_pos = info.get("start_pos")

            if start_pos is not None:
                # Backward compound: prev_word + current_word
                idx = result.lower().find(word_lower)
                if idx == -1:
                    continue
                span_end = idx + len(word)
                actual_span = result[start_pos:span_end]
                corrected = _match_case(actual_span.split()[0] if actual_span.split() else "", chosen_clean)
                result = result[:start_pos] + corrected + result[span_end:]
                _log(f"LLM compound APPLIED: '{actual_span}' -> '{corrected}' (reason: {reason})")
            else:
                # Forward compound: current_word + next_word
                idx = result.find(word)
                if idx == -1:
                    idx = result.lower().find(word_lower)
                if idx == -1:
                    continue
                search_start = idx + len(word)
                idx2 = result.find(second_word, search_start)
                if idx2 == -1:
                    idx2 = result.lower().find(second_word.lower(), search_start)
                if idx2 == -1:
                    continue
                span_end = idx2 + len(second_word)
                actual_span = result[idx:span_end]
                corrected = _match_case(actual_span.split()[0] if actual_span.split() else "", chosen_clean)
                result = result[:idx] + corrected + result[span_end:]
                _log(f"LLM compound APPLIED: '{actual_span}' -> '{corrected}' (reason: {reason})")
        else:
            # Single word replacement
            idx = result.find(word)
            if idx == -1:
                idx = result.lower().find(word_lower)
            if idx == -1:
                continue
            actual_text = result[idx:idx + len(word)]
            corrected = _match_case(actual_text, chosen_clean)
            result = result[:idx] + corrected + result[idx + len(word):]
            _log(f"LLM correction APPLIED: '{word}' -> '{corrected}' (reason: {reason})")

    return result


def llm_review_and_correct(text: str, flagged: list[dict[str, Any]], sym: SymSpell, client: OpenAI) -> str:
    """Ask LLM to review suspected errors and choose corrections.

    The LLM sees the full text context and chooses from candidates.
    Python validates and applies the choices.
    """
    if not flagged:
        return text

    prompt = build_llm_review_prompt(text, flagged)
    if not prompt:
        return text

    try:
        kwargs = {
            "model": LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "top_p": 0.1,
            "max_tokens": min(LLM_MAX_TOKENS, 512),
            "extra_body": {
                "think": LLM_THINK,
                "keep_alive": LLM_KEEP_ALIVE,
                "options": {"num_ctx": LLM_NUM_CTX, "temperature": 0, "top_p": 0.1, "top_k": 1},
            },
        }
        if LLM_USE_RESPONSE_FORMAT:
            kwargs["response_format"] = CORRECTION_RESPONSE_FORMAT

        resp = client.chat.completions.create(**kwargs)
        content = (resp.choices[0].message.content or "").strip()

        if not content:
            _log("LLM returned empty for correction review")
            return text

        # Parse JSON response
        try:
            parsed = extract_json_object(content)
        except Exception:
            _log("LLM correction JSON parse failed")
            return text

        corrections = parsed.get("corrections", [])
        if not isinstance(corrections, list):
            return text

        # Apply with strict validation
        return apply_validated_corrections(text, corrections, flagged, sym)

    except Exception as exc:
        _log(f"LLM correction review failed: {exc}")
        return text


# =========================================================
# STEP 5: Apply SymSpell-only corrections (no LLM needed)
# =========================================================

def _match_case(original: str, correction: str) -> str:
    """Preserve case pattern of original when applying correction.

    Examples:
        _match_case("Dau", "đấu") -> "Đấu"
        _match_case("DAU TRANH", "đấu tranh") -> "ĐẤU TRANH"
        _match_case("dau Tranh", "đấu tranh") -> "đấu Tranh"
    """
    if original.isupper():
        return correction.upper()
    if original.islower():
        return correction
    if original[0].isupper():
        return correction[0].upper() + correction[1:]
    return correction


def apply_symspell_direct(text: str, flagged: list[dict[str, Any]], sym: SymSpell) -> str:
    """Apply SymSpell corrections directly for unambiguous cases.

    If a word has exactly ONE candidate, replace it without LLM.
    If a word has MULTIPLE candidates, leave it for LLM review.
    Preserves original case pattern.
    """
    result = text
    for item in sorted(flagged, key=lambda x: x["position"], reverse=True):
        candidates = item.get("candidates", [])
        if len(candidates) == 1:
            # Unambiguous: replace directly with case preservation
            pos = item["position"]
            corrected = _match_case(item["token"], candidates[0])
            result = result[:pos] + corrected + result[pos + len(item["token"]):]

    return result


# =========================================================
# MAIN HYBRID PIPELINE FUNCTION
# =========================================================

def process_segments_hybrid(
    segments: list[SegmentRecord],
    client: OpenAI,
    document_id: str | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Run the 5-step hybrid pipeline on all segments.

    Flow per segment:
    1. Heuristic detect: underthesea tokenize + SymSpell lookup + OCR patterns
    2. Context validate: check surrounding words, remove false positives
    3. Generate candidates: SymSpell edit distance suggestions
    4. SymSpell direct: apply unambiguous (single-candidate) corrections
    5. LLM review: for ambiguous cases, LLM sees full text and chooses

    Returns (corrected_texts, report).
    """
    sym = _load_symspell_vi()
    corrected: list[str] = []
    report_items: list[dict[str, Any]] = []
    total_segments = len(segments)
    segments_with_errors = 0
    segments_corrected = 0

    for idx, seg in enumerate(segments):
        t0 = time.time()

        # Step 0: Clean strange characters (OCR noise)
        seg_text = clean_strange_chars(seg.text)

        # Step 1: Heuristic error detection
        flagged_raw = detect_errors_heuristic(seg_text, sym)

        # Step 2: Context validation (remove false positives)
        flagged = validate_with_context(seg_text, flagged_raw, sym)

        # Step 3: Generate candidates
        flagged_with_candidates = generate_candidates(seg_text, flagged, sym)

        detect_time = time.time() - t0

        if not flagged_with_candidates:
            corrected.append(seg_text)
            report_items.append({
                "segment_id": seg.segment_id,
                "kind": seg.kind,
                "raw_errors": len(flagged_raw),
                "confirmed_errors": len(flagged),
                "corrected": False,
                "before": seg.text,
                "after": seg_text,
            })
            continue

        segments_with_errors += 1

        # Step 4: Apply unambiguous SymSpell corrections directly
        sym_text = apply_symspell_direct(seg_text, flagged_with_candidates, sym)
        sym_changed = sym_text.strip() != seg_text.strip()

        # Step 5: LLM review for ambiguous cases (multiple candidates)
        ambiguous = [item for item in flagged_with_candidates if len(item.get("candidates", [])) > 1]

        llm_time = 0.0
        if ambiguous:
            t0 = time.time()
            final_text = llm_review_and_correct(sym_text, ambiguous, sym, client)
            llm_time = time.time() - t0
        else:
            final_text = sym_text

        changed = final_text.strip() != seg_text.strip()
        if changed:
            segments_corrected += 1

        corrected.append(final_text)
        report_items.append({
            "segment_id": seg.segment_id,
            "kind": seg.kind,
            "raw_errors": len(flagged_raw),
            "confirmed_errors": len(flagged),
            "with_candidates": len(flagged_with_candidates),
            "unambiguous_applied": sym_changed,
            "ambiguous_for_llm": len(ambiguous),
            "corrected": changed,
            "detect_duration": f"{detect_time:.2f}s",
            "llm_duration": f"{llm_time:.2f}s",
            "before": seg.text,
            "after": final_text,
        })

        if document_id and (idx + 1) % 5 == 0:
            update_progress(
                document_id,
                status="hybrid_correcting",
                completed_segments=idx + 1,
                total_segments=total_segments,
                segments_with_errors=segments_with_errors,
                segments_corrected=segments_corrected,
            )

    summary = {
        "total_segments": total_segments,
        "segments_with_errors": segments_with_errors,
        "segments_corrected": segments_corrected,
        "items": report_items,
    }
    return corrected, summary




def has_cjk(text: str) -> bool:
    """Detect CJK characters to protect non-Vietnamese content."""
    return bool(re.search(r"[\u3400-\u9fff]", str(text or "")))


def generic_fix_shape_is_safe(src: str, dst: str) -> tuple[bool, str]:
    """Generic pre-filter only; no hard-coded word dictionary."""
    src = str(src or "").strip()
    dst = str(dst or "").strip()
    if not src or src == dst:
        return False, "empty or unchanged fix"
    if has_cjk(src) or has_cjk(dst):
        return False, "contains CJK characters"
    if len(src) <= 1:
        return False, "source too short"
    if len(src) > 36 or len(dst) > 44:
        return False, "fix too long"
    if "\n" in src or "\n" in dst:
        return False, "multiline fix rejected"
    if len(src.split()) > 5 or len(dst.split()) > 5:
        return False, "too many tokens"
    if abs(len(src.split()) - len(dst.split())) >= 2:
        return False, "token count changes too much"
    if len(dst) > len(src) * 2 + 6:
        return False, "replacement expands too much"
    src_digits = re.findall(r"\d", src)
    dst_digits = re.findall(r"\d", dst)
    if src_digits != dst_digits:
        return False, "numbers/codes are protected"
    if starts_structural_marker(src) or looks_metadata_like_line(src):
        return False, "structural/metadata text is protected"
    return True, "generic shape is safe"


def extract_phrase_context(segment_text: str, source: str, window_words: int = 3) -> dict[str, Any]:
    """Extract a small phrase window around source.

    Vietnamese OCR corrections often depend on nearby words:
    "dé tổng hợp" -> "để tổng hợp", "hang tuần" -> "hằng tuần".
    """
    text_value = str(segment_text or "")
    source_value = str(source or "").strip()
    if not source_value or source_value not in text_value:
        return {
            "source_phrase": source_value,
            "left_words": [],
            "right_words": [],
            "phrase_window": source_value,
        }

    start = text_value.find(source_value)
    end = start + len(source_value)
    left_text = text_value[:start]
    right_text = text_value[end:]

    word_pattern = r"[A-Za-zÀ-ỹĐđ0-9]+"
    left_words = re.findall(word_pattern, left_text)[-window_words:]
    right_words = re.findall(word_pattern, right_text)[:window_words]

    phrase_window = " ".join(left_words + [source_value] + right_words).strip()
    return {
        "source_phrase": source_value,
        "left_words": left_words,
        "right_words": right_words,
        "phrase_window": phrase_window,
    }


def final_merge_and_cleanup(text: str) -> str:
    raw_lines = [normalize_basic_spacing(line) for line in text.splitlines() if line.strip()]
    records = [LineRecord(i + 1, line) for i, line in enumerate(raw_lines) if not is_probable_garbage_line(line)]
    merged = merge_visual_wrapped_lines(records)
    out = "\n".join(apply_safe_rule_corrections(x.text) for x in merged)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip() + "\n"


def normalize_for_compare(value: str) -> str:
    s = str(value or "").lower()
    s = re.sub(r"[^a-zà-ỹđ0-9]+", " ", s, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", s).strip()


def validate_loss_signal(original_lines: list[LineRecord], normalized_text: str) -> dict[str, Any]:
    """Soft validation using enum levels: EXACT_FOUND / FUZZY_FOUND / MISSING."""
    results: list[dict[str, Any]] = []
    exact = 0
    fuzzy = 0
    missing = 0

    compact_norm = re.sub(r"\s+", " ", normalized_text)
    comparable_norm = normalize_for_compare(normalized_text)

    for line in original_lines:
        s = line.text.strip()
        if len(s) < 12 or is_probable_garbage_line(s):
            continue

        if s in normalized_text or re.sub(r"\s+", " ", s) in compact_norm:
            status = "EXACT_FOUND"
            exact += 1
        else:
            norm_s = normalize_for_compare(s)
            if norm_s and norm_s in comparable_norm:
                status = "FUZZY_FOUND"
                fuzzy += 1
            else:
                status = "MISSING"
                missing += 1

        if status != "EXACT_FOUND":
            results.append({
                **asdict(line),
                "status": status,
                "normalized_for_compare": norm_s,
            })

    return {
        "summary": {
            "EXACT_FOUND": exact,
            "FUZZY_FOUND": fuzzy,
            "MISSING": missing,
        },
        "non_exact_lines": results[:300],
        "possibly_missing_meaningful_lines": [x for x in results if x["status"] == "MISSING"][:200],
        "count": missing,
    }


def build_hybrid_fixes_summary(hybrid_report: dict[str, Any]) -> dict[str, Any]:
    """Build summary from hybrid pipeline report."""
    items = hybrid_report.get("items", [])
    corrected_items = [i for i in items if i.get("corrected")]
    error_items = [i for i in items if i.get("flagged_words", 0) > 0 and not i.get("corrected")]
    return {
        "total_segments": hybrid_report.get("total_segments", 0),
        "segments_with_errors": hybrid_report.get("segments_with_errors", 0),
        "segments_corrected": hybrid_report.get("segments_corrected", 0),
        "corrected_details": corrected_items[:100],
        "uncorrected_errors": error_items[:50],
    }


# =========================================================
# PUBLIC ENTRYPOINT
# =========================================================

def save_json(path: Path, data: Any) -> None:
    if not OCR_SAVE_REPORTS:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_json_always(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_session_json(document_id: str, name: str, data: Any) -> None:
    save_json_always(work_dir(document_id) / name, data)


def save_partial_normalized(document_id: str, name: str, text: str) -> None:
    save_text(work_dir(document_id) / "partial_normalized" / name, text)


def get_effective_env() -> dict[str, Any]:
    return {
        "LLM_MODEL": LLM_MODEL,
        "LLM_NUM_CTX": LLM_NUM_CTX,
        "LLM_THINK": LLM_THINK,
        "LLM_MAX_TOKENS": LLM_MAX_TOKENS,
        "OCR_BATCH_SIZE": OCR_BATCH_SIZE,
        "OCR_MAX_PROMPT_CHARS": OCR_MAX_PROMPT_CHARS,
        "OCR_SEGMENT_MAX_LINES": OCR_SEGMENT_MAX_LINES,
        "OCR_SEGMENT_MAX_CHARS": OCR_SEGMENT_MAX_CHARS,
        "OCR_TEXT_SNIPPET_CHARS": OCR_TEXT_SNIPPET_CHARS,
        "OCR_ENABLE_LLM_REVIEW": OCR_ENABLE_LLM_REVIEW,
        "OCR_ENABLE_SEMANTIC_VALIDATION": OCR_ENABLE_SEMANTIC_VALIDATION,
        "OCR_SEMANTIC_BATCH_SIZE": OCR_SEMANTIC_BATCH_SIZE,
        "NORMALIZED_WORK_DIR": str(NORMALIZED_WORK_DIR),
        "NORMALIZED_TEXT_DIR": str(NORMALIZED_TEXT_DIR),
    }


def generate_normalized_text(document_id: str) -> Path:
    """Generate normalized text with session-style progress saving.

    Final output:
        data/normalized_text/{document_id}.txt

    Session/work output:
        data/normalized_work/{document_id}/progress.json
        data/normalized_work/{document_id}/raw_extracted_text.txt
        data/normalized_work/{document_id}/prepared_lines.json
        data/normalized_work/{document_id}/merged_lines.json
        data/normalized_work/{document_id}/segments.json
        data/normalized_work/{document_id}/llm_review.json
        data/normalized_work/{document_id}/semantic_validation.json
        data/normalized_work/{document_id}/noise_validation.json
        data/normalized_work/{document_id}/normalized_report.json
        data/normalized_work/{document_id}/applied_fixes_summary.json
        data/normalized_work/{document_id}/validation.json
        data/normalized_work/{document_id}/partial_normalized/*.txt
        data/normalized_work/{document_id}/llm_failures/*.json
        data/normalized_work/{document_id}/batch_reports/*.json
    """
    global _log_file
    start = time.time()
    ensure_dirs(document_id)

    normalized_path = NORMALIZED_TEXT_DIR / f"{document_id}.txt"

    # Open log file for this pipeline run
    log_path = work_dir(document_id) / "pipeline.log"
    _log_file = open(log_path, "a", encoding="utf-8")

    update_progress(document_id, status="started", output_path=str(normalized_path), work_dir=str(work_dir(document_id)))
    _log(f"START normalized_text pipeline: {document_id}")
    _log_stage("CONFIG", **get_effective_env())

    try:
        t0 = time.time()
        raw_text = load_raw_extracted_text(document_id)
        if SAVE_DEBUG_FILES:
            save_text(work_dir(document_id) / "raw_extracted_text.txt", raw_text)
        _log_stage("LOAD_RAW", chars=len(raw_text), duration=f"{time.time()-t0:.2f}s")
        update_progress(document_id, status="loaded_raw_text")

        t0 = time.time()
        prepared = prepare_lines(raw_text)
        _log_stage("PREPARE", lines=len(prepared), duration=f"{time.time()-t0:.2f}s")
        if SAVE_DEBUG_FILES:
            save_session_json(document_id, "prepared_lines.json", [asdict(x) for x in prepared])
        update_progress(document_id, status="prepared_lines", prepared_line_count=len(prepared))

        t0 = time.time()
        merged_lines = merge_visual_wrapped_lines(prepared)
        reduction = len(prepared) - len(merged_lines)
        _log_stage("MERGE", before=len(prepared), after=len(merged_lines), reduction=reduction, duration=f"{time.time()-t0:.2f}s")
        if SAVE_DEBUG_FILES:
            save_session_json(document_id, "merged_lines.json", [asdict(x) for x in merged_lines])
            save_partial_normalized(document_id, "01_after_merge.txt", "\n".join(x.text for x in merged_lines).strip() + "\n")
        update_progress(document_id, status="merged_lines", merged_line_count=len(merged_lines))

        t0 = time.time()
        segments = build_sentence_segments(merged_lines)
        _log_stage("SEGMENT", segments=len(segments), duration=f"{time.time()-t0:.2f}s")
        if SAVE_DEBUG_FILES:
            save_session_json(document_id, "segments.json", [asdict(x) for x in segments])
        update_progress(document_id, status="built_segments", segment_count=len(segments))

        t0 = time.time()
        client = make_client()

        fixed_segments, hybrid_report = process_segments_hybrid(segments, client, document_id=document_id)
        hybrid_duration = time.time() - t0
        _log_stage("HYBRID_PIPELINE",
            total_segments=hybrid_report.get("total_segments", 0),
            with_errors=hybrid_report.get("segments_with_errors", 0),
            corrected=hybrid_report.get("segments_corrected", 0),
            duration=f"{hybrid_duration:.2f}s")
        if SAVE_DEBUG_FILES:
            save_session_json(document_id, "hybrid_report.json", hybrid_report)
        update_progress(document_id, status="hybrid_completed",
            total_segments=hybrid_report.get("total_segments", 0),
            segments_with_errors=hybrid_report.get("segments_with_errors", 0),
            segments_corrected=hybrid_report.get("segments_corrected", 0))

        joined_fixed = "\n".join(fixed_segments)
        if SAVE_DEBUG_FILES:
            save_partial_normalized(document_id, "02_after_hybrid.txt", joined_fixed.strip() + "\n")

        t0 = time.time()
        normalized_text = final_merge_and_cleanup(joined_fixed)
        _log_stage("FINAL_MERGE", chars=len(normalized_text), duration=f"{time.time()-t0:.2f}s")
        if SAVE_DEBUG_FILES:
            save_partial_normalized(document_id, "03_final_normalized_preview.txt", normalized_text)

        t0 = time.time()
        validation = validate_loss_signal(prepared, normalized_text)
        _log_stage("VALIDATE_LOSS", exact=validation["summary"]["EXACT_FOUND"], fuzzy=validation["summary"]["FUZZY_FOUND"], missing=validation["summary"]["MISSING"], duration=f"{time.time()-t0:.2f}s")
        if SAVE_DEBUG_FILES:
            save_session_json(document_id, "validation.json", validation)

        hybrid_fixes_summary = build_hybrid_fixes_summary(hybrid_report)
        if SAVE_DEBUG_FILES:
            save_session_json(document_id, "hybrid_fixes_summary.json", hybrid_fixes_summary)

        normalized_path.parent.mkdir(parents=True, exist_ok=True)
        normalized_path.write_text(normalized_text, encoding="utf-8")

        if OCR_SAVE_REPORTS:
            save_json(NORMALIZED_TEXT_DIR / f"{document_id}.prepared_lines.json", [asdict(x) for x in prepared])
            save_json(NORMALIZED_TEXT_DIR / f"{document_id}.merged_lines.json", [asdict(x) for x in merged_lines])
            save_json(NORMALIZED_TEXT_DIR / f"{document_id}.segments.json", [asdict(x) for x in segments])
            save_json(NORMALIZED_TEXT_DIR / f"{document_id}.hybrid_report.json", hybrid_report)
            save_json(NORMALIZED_TEXT_DIR / f"{document_id}.hybrid_fixes_summary.json", hybrid_fixes_summary)
            save_json(NORMALIZED_TEXT_DIR / f"{document_id}.validation.json", validation)

        duration = round(time.time() - start, 2)

        # Final summary log
        _log_stage("PIPELINE_COMPLETE",
            document_id=document_id,
            duration=f"{duration:.2f}s",
            input_lines=len(prepared),
            output_lines=len(normalized_text.splitlines()),
            output_chars=len(normalized_text),
            segments_with_errors=hybrid_fixes_summary.get("segments_with_errors", 0),
            segments_corrected=hybrid_fixes_summary.get("segments_corrected", 0),
            loss_exact=validation["summary"]["EXACT_FOUND"],
            loss_fuzzy=validation["summary"]["FUZZY_FOUND"],
            loss_missing=validation["summary"]["MISSING"],
        )

        if validation["count"]:
            _log(f"Validation warning: possibly missing meaningful lines = {validation['count']}")

        update_progress(
            document_id,
            status="done",
            output_path=str(normalized_path),
            work_dir=str(work_dir(document_id)),
            duration_seconds=duration,
            validation_summary=validation.get("summary", {}),
            hybrid_fixes_summary={
                "total_segments": hybrid_fixes_summary.get("total_segments", 0),
                "segments_with_errors": hybrid_fixes_summary.get("segments_with_errors", 0),
                "segments_corrected": hybrid_fixes_summary.get("segments_corrected", 0),
            },
        )

        _log(f"DONE in {duration:.2f}s → {normalized_path}")
        return normalized_path

    except Exception as exc:
        duration = round(time.time() - start, 2)
        _log_stage("PIPELINE_FAILED", document_id=document_id, duration=f"{duration:.2f}s", error=str(exc)[:200])
        update_progress(
            document_id,
            status="failed",
            error=str(exc),
            output_path=str(normalized_path),
            work_dir=str(work_dir(document_id)),
            duration_seconds=duration,
        )
        raise
    finally:
        if _log_file:
            _log_file.close()
            _log_file = None
