"""Normalized text generation for Vietnamese administrative documents.

Design goals:
- Generic for Vietnamese administrative documents, not for a single document type.
- Python does deterministic cleanup, line wrapping, and safety validation.
- LLM only returns enum-based suggestions; no probability/confidence floats.
- LLM reviews sentence/paragraph-like segments, not isolated raw lines only.
- Partial reports are saved so failures do not hide intermediate results.

Input:
    data/extracted_text/{document_id}/page_*.txt

Output:
    data/normalized_text/{document_id}.txt
    data/normalized_text/{document_id}.normalized_report.json
    data/normalized_text/{document_id}.segments.json
    data/normalized_text/{document_id}.llm_review.json
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from openai import OpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed
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

OCR_BATCH_SIZE = int(os.getenv("OCR_BATCH_SIZE", "4"))
OCR_MAX_PROMPT_CHARS = int(os.getenv("OCR_MAX_PROMPT_CHARS", "4000"))
OCR_SEGMENT_MAX_LINES = int(os.getenv("OCR_SEGMENT_MAX_LINES", "8"))
OCR_SEGMENT_MAX_CHARS = int(os.getenv("OCR_SEGMENT_MAX_CHARS", "1200"))
OCR_TEXT_SNIPPET_CHARS = int(os.getenv("OCR_TEXT_SNIPPET_CHARS", "700"))
OCR_MERGE_MAX_BLOCK_LINES = int(os.getenv("OCR_MERGE_MAX_BLOCK_LINES", "16"))
OCR_JSON_RETRY_ATTEMPTS = int(os.getenv("OCR_JSON_RETRY_ATTEMPTS", "3"))
OCR_JSON_RETRY_WAIT_SECONDS = int(os.getenv("OCR_JSON_RETRY_WAIT_SECONDS", "2"))
OCR_ENABLE_LLM_REVIEW = os.getenv("OCR_ENABLE_LLM_REVIEW", "true").lower() == "true"
OCR_ENABLE_SEMANTIC_VALIDATION = os.getenv("OCR_ENABLE_SEMANTIC_VALIDATION", "true").lower() == "true"
OCR_SEMANTIC_BATCH_SIZE = int(os.getenv("OCR_SEMANTIC_BATCH_SIZE", "6"))
OCR_SAVE_REPORTS = os.getenv("OCR_SAVE_REPORTS", "true").lower() == "true"


# =========================================================
# LOGGING / DATA STRUCTURES
# =========================================================

def _log(step: str) -> None:
    print(f"[NORMALIZED-ADMIN-SESSION] {step}", flush=True)


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


@dataclass
class SegmentReview:
    segment_id: int
    decision: str
    risk: str
    fixes: list[dict[str, Any]]
    notes: str = ""


# =========================================================
# JSON PARSER
# =========================================================

def _strip_markdown_fence(content: str) -> str:
    s = str(content or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^\s*```(?:json|JSON)?\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s).strip()
    return s


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
    s = _cut_accidental_logs(_strip_markdown_fence(raw))
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
    return any([
        starts_numbered_marker(text), starts_decimal_marker(text), starts_lettered_marker(text),
        starts_roman_marker(text), starts_article_marker(text), starts_major_admin_marker(text), starts_bullet(text)
    ])


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
    """Minimal generic garbage detector.

    This function is intentionally weak.
    It only catches format-level garbage that does not require document-specific knowledge.
    Semantic noise removal is handled by an LLM validation pass with neighboring context.
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
    if prev.endswith((",", "-", "–", "(", "/")):
        score += 4
    if not prev.endswith((".", ";", ":", "?", "!", "…”", "”")):
        score += 3
    if starts_lowercase(curr):
        score += 3
    if curr.lower().startswith(("và ", "hoặc ", "của ", "theo ", "trong ", "để ", "về ", "với ", "từ ", "đến ", "cho ", "do ", "nhằm ")):
        score += 2
    if prev.endswith((".", "?", "!", "…”", "”")):
        score -= 5
    return score >= 4


def apply_safe_rule_corrections(line: str) -> str:
    s = normalize_basic_spacing(line)
    replacements = [
        (r"\bSo\s*:\s*", "Số: "),
        (r"\bSố\s*:\s*", "Số: "),
        (r"\bngay\s+(\d{1,2})\s+tháng\b", r"ngày \1 tháng"),
        (r"\bthang\s+(\d{1,2})\b", r"tháng \1"),
        (r"\bnam\s+(\d{4})\b", r"năm \1"),
        (r"\bcăn cử\b", "căn cứ"),
        (r"\bthâm quyền\b", "thẩm quyền"),
        (r"\bthành phó\b", "thành phố"),
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

def load_raw_extracted_text(document_id: str) -> str:
    base_path = EXTRACTED_TEXT_DIR / document_id
    _log(f"Checking extracted path: {base_path}")
    page_files = sorted(base_path.glob("page_*.txt"))
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

JSON_OUTPUT_RULES = """
/no_think
Output constraints:
- Return exactly one valid JSON object.
- Do not use markdown code fences.
- Do not write reasoning or analysis.
- Do not include <think>...</think>.
- Do not add comments, logs, or text outside JSON.
- Do not use probability, confidence, score, or numeric certainty fields.
- Use only the enum values allowed by the schema.
- End immediately after the final closing brace }.
""".strip()

SEGMENT_REVIEW_PROMPT = """
You are reviewing OCR text segments from Vietnamese administrative documents.

Task:
For each segment, decide whether Python may safely apply small OCR fixes.
Return enum-based JSON only. Do not use probability scores.

Return format:
{
  "reviews": [
    {
      "segment_id": 1,
      "decision": "KEEP" | "APPLY_SMALL_FIXES" | "MANUAL_REVIEW" | "REMOVE_NOISE",
      "risk": "LOW" | "MEDIUM" | "HIGH",
      "fixes": [
        {
          "kind": "SPELLING" | "DIACRITIC" | "OCR_ARTIFACT" | "PUNCTUATION" | "SPACING",
          "scope": "WORD" | "SHORT_PHRASE",
          "from": "exact source substring",
          "to": "replacement substring"
        }
      ],
      "notes": "short note"
    }
  ]
}

Rules:
- Return exactly one review object for every input segment_id.
- Use KEEP when no safe fix is needed.
- Use APPLY_SMALL_FIXES only for exact short substring fixes inside the segment.
- Use MANUAL_REVIEW when the segment may be wrong but correction would require guessing.
- Use REMOVE_NOISE only for obvious OCR/page/signature garbage; never remove valid legal content.
- Do not rewrite a full line, full sentence, paragraph, name, date, number, document code, article number, or organization name.
- Each fix.from must appear exactly in the segment text.
- Keep fixes short: one word or a short phrase only.
- Do not add missing content.
- Do not change legal meaning.

Focus on:
- Vietnamese diacritic/spelling OCR errors.
- Broken punctuation or spacing.
- OCR artifacts.
- Sentence-level context: segments usually end at punctuation or paragraph boundary.
""".strip()

SEGMENT_REVIEW_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "ocr_segment_review",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "reviews": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "segment_id": {"type": "integer"},
                            "decision": {"type": "string", "enum": ["KEEP", "APPLY_SMALL_FIXES", "MANUAL_REVIEW", "REMOVE_NOISE"]},
                            "risk": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
                            "fixes": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "kind": {"type": "string", "enum": ["SPELLING", "DIACRITIC", "OCR_ARTIFACT", "PUNCTUATION", "SPACING"]},
                                        "scope": {"type": "string", "enum": ["WORD", "SHORT_PHRASE"]},
                                        "from": {"type": "string"},
                                        "to": {"type": "string"},
                                    },
                                    "required": ["kind", "scope", "from", "to"],
                                },
                            },
                            "notes": {"type": "string"},
                        },
                        "required": ["segment_id", "decision", "risk", "fixes", "notes"],
                    },
                }
            },
            "required": ["reviews"],
        },
    },
}


def make_client() -> OpenAI:
    return OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY, timeout=LLM_TIMEOUT_SECONDS)


def _retry_json():
    return retry(
        stop=stop_after_attempt(OCR_JSON_RETRY_ATTEMPTS),
        wait=wait_fixed(OCR_JSON_RETRY_WAIT_SECONDS),
        retry=retry_if_exception_type(Exception),
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


def build_review_prompt(segments: list[SegmentRecord]) -> str:
    payload = {
        "segments": [
            {
                "segment_id": s.segment_id,
                "kind": s.kind,
                "lines": [s.start_line_id, s.end_line_id],
                "text": clip_text(s.text, OCR_TEXT_SNIPPET_CHARS),
            }
            for s in segments
        ]
    }
    prompt = JSON_OUTPUT_RULES + "\n\n" + SEGMENT_REVIEW_PROMPT + "\nINPUT JSON:\n" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(prompt) > OCR_MAX_PROMPT_CHARS:
        raise ValueError(f"Prompt too long: {len(prompt)} chars > {OCR_MAX_PROMPT_CHARS}")
    return prompt


def call_llm_json(client: OpenAI, prompt: str, response_format: dict[str, Any] | None = None, document_id: str | None = None, stage: str = "llm", batch_index: int | None = None) -> dict[str, Any]:
    @_retry_json()
    def _call() -> dict[str, Any]:
        _log(f"LLM JSON call prompt chars={len(prompt)}")
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
        if LLM_USE_RESPONSE_FORMAT and response_format is not None:
            kwargs["response_format"] = response_format
        resp = client.chat.completions.create(**kwargs)
        content = resp.choices[0].message.content or ""
        try:
            return extract_json_object(content)
        except Exception as exc:
            if document_id:
                suffix = f".batch_{batch_index:03d}" if batch_index is not None else ""
                save_json_always(
                    work_dir(document_id) / "llm_failures" / f"{stage}{suffix}.{int(time.time() * 1000)}.json",
                    {
                        "stage": stage,
                        "batch_index": batch_index,
                        "error": str(exc),
                        "raw_response": content,
                        "prompt_preview": prompt[:2500],
                    },
                )
            raise
    return _call()


VALID_DECISIONS = {"KEEP", "APPLY_SMALL_FIXES", "MANUAL_REVIEW", "REMOVE_NOISE"}
VALID_RISKS = {"LOW", "MEDIUM", "HIGH"}
VALID_FIX_KINDS = {"SPELLING", "DIACRITIC", "OCR_ARTIFACT", "PUNCTUATION", "SPACING"}
VALID_SCOPES = {"WORD", "SHORT_PHRASE"}


def parse_segment_reviews(obj: dict[str, Any], segments: list[SegmentRecord]) -> list[SegmentReview]:
    seg_ids = {s.segment_id for s in segments}
    out: list[SegmentReview] = []
    seen: set[int] = set()
    raw = obj.get("reviews", [])
    if not isinstance(raw, list):
        raw = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            sid = int(item.get("segment_id"))
        except (TypeError, ValueError):
            continue
        if sid not in seg_ids or sid in seen:
            continue
        decision = str(item.get("decision", "KEEP")).strip().upper()
        risk = str(item.get("risk", "HIGH")).strip().upper()
        if decision not in VALID_DECISIONS:
            decision = "MANUAL_REVIEW"
        if risk not in VALID_RISKS:
            risk = "HIGH"
        fixes: list[dict[str, Any]] = []
        for fix in item.get("fixes", []) if isinstance(item.get("fixes", []), list) else []:
            if not isinstance(fix, dict):
                continue
            kind = str(fix.get("kind", "")).upper()
            scope = str(fix.get("scope", "")).upper()
            src = str(fix.get("from", ""))
            dst = str(fix.get("to", ""))
            if kind in VALID_FIX_KINDS and scope in VALID_SCOPES and src:
                fixes.append({"kind": kind, "scope": scope, "from": src, "to": dst})
        out.append(SegmentReview(sid, decision, risk, fixes, str(item.get("notes", ""))))
        seen.add(sid)
    for seg in segments:
        if seg.segment_id not in seen:
            out.append(SegmentReview(seg.segment_id, "KEEP", "LOW", [], "LLM omitted this segment; default KEEP."))
    return sorted(out, key=lambda r: r.segment_id)


def review_segments_with_llm(client: OpenAI, segments: list[SegmentRecord], document_id: str | None = None) -> list[SegmentReview]:
    if not OCR_ENABLE_LLM_REVIEW:
        return [SegmentReview(s.segment_id, "KEEP", "LOW", [], "LLM disabled.") for s in segments]
    out: list[SegmentReview] = []
    total_batches = (len(segments) + OCR_BATCH_SIZE - 1) // OCR_BATCH_SIZE
    for batch_index, i in enumerate(range(0, len(segments), OCR_BATCH_SIZE), start=1):
        batch = segments[i:i + OCR_BATCH_SIZE]
        try:
            obj = call_llm_json(
                client,
                build_review_prompt(batch),
                response_format=SEGMENT_REVIEW_RESPONSE_FORMAT,
                document_id=document_id,
                stage="segment_review",
                batch_index=batch_index,
            )
            batch_reviews = parse_segment_reviews(obj, batch)
            out.extend(batch_reviews)
        except Exception as exc:
            _log(f"Segment review batch failed; default KEEP. Error: {exc}")
            batch_reviews = [SegmentReview(s.segment_id, "KEEP", "LOW", [], f"Batch failed: {exc}") for s in batch]
            out.extend(batch_reviews)

        if document_id:
            save_json_always(work_dir(document_id) / "batch_reports" / f"segment_review_{batch_index:03d}.json", [asdict(x) for x in batch_reviews])
            save_json_always(work_dir(document_id) / "llm_review.partial.json", [asdict(x) for x in sorted(out, key=lambda r: r.segment_id)])
            update_progress(
                document_id,
                status="reviewing_segments",
                completed_review_batches=batch_index,
                total_review_batches=total_batches,
            )

    return sorted(out, key=lambda r: r.segment_id)



# =========================================================
# SEMANTIC VALIDATION FOR OCR FIXES
# =========================================================

MEANING_EXPLANATION_PROMPT = """
You are validating OCR correction alternatives in Vietnamese administrative text.

Task:
For each fix_id, explain the contextual meaning of the source phrase and each possible replacement candidate.
Do not decide by probability. Do not apply fixes. Return JSON only.

Return format:
{
  "meanings": [
    {
      "fix_id": "segment_id:index",
      "source_meaning": "meaning of source phrase in this sentence/paragraph",
      "candidate_meanings": [
        {
          "replacement": "candidate replacement",
          "target_meaning": "meaning of this replacement in context",
          "meaning_change": "NONE" | "ORTHOGRAPHIC_ONLY" | "POSSIBLE_CHANGE" | "CLEAR_CHANGE" | "UNKNOWN",
          "requires_guessing": "YES" | "NO",
          "explanation": "short explanation"
        }
      ]
    }
  ]
}

Rules:
- Consider the entire segment context, but prioritize phrase_window and neighboring words.
- A candidate is safe only when it corrects spelling/diacritics/OCR form while preserving the meaning of the phrase, not just the isolated word.
- If a candidate adds missing content, changes legal meaning, changes entity names, changes dates/numbers/codes, or guesses intent, mark requires_guessing = YES.
- If the source is a fragment or ambiguous syllable, mark requires_guessing = YES unless the segment proves it is only OCR/diacritic restoration.
- If the replacement adds words not present in the source, mark meaning_change = CLEAR_CHANGE.
- If unsure, use UNKNOWN or POSSIBLE_CHANGE.

Reject-style examples:
- In "dau tranh", "đấu" may fit "đấu tranh"; "đau" changes meaning and must not be selected.
- In "dé tổng hợp", "để" fits the phrase; "đề" changes the phrase meaning and must not be selected.
- In "hang tuần", "hằng" fits the phrase; "hàng" changes the phrase meaning and must not be selected.
- In "day mạnh", "đẩy" fits the phrase; "đầy" changes the phrase meaning and must not be selected.
- In "ran đe", "răn" fits the phrase; other forms change the phrase meaning.
- Replacing "t" with "thực" expands a fragment into missing content; requires_guessing = YES.
- Replacing "tri tuệ" with "sở hữu trí tuệ" adds words/content; meaning_change = CLEAR_CHANGE.
- Removing a possible administrative label such as "điện:" changes document content unless context proves it is noise.
""".strip()

SIMILARITY_EVALUATION_PROMPT = """
You are choosing the best OCR correction candidate while preserving meaning in Vietnamese administrative text.

Task:
Using the source phrase, candidate replacements, and prior meaning explanation, choose the best replacement using enums.
Return JSON only.

Return format:
{
  "evaluations": [
    {
      "fix_id": "segment_id:index",
      "best_replacement": "candidate replacement or original source",
      "similarity": "EXACT_SAME" | "ORTHOGRAPHIC_EQUIVALENT" | "SAME_ADMIN_TERM" | "AMBIGUOUS" | "MEANING_CHANGED" | "UNRELATED",
      "apply_decision": "ALLOW" | "REJECT" | "MANUAL_REVIEW",
      "reason": "short reason"
    }
  ]
}

Rules:
- ALLOW only when the chosen replacement preserves the same phrase-level meaning and only fixes OCR/spelling/diacritics.
- Use phrase_window and neighboring words to choose between competing Vietnamese words.
- If the safest option is to keep the original source, set best_replacement to the original source and apply_decision = REJECT.
- REJECT if all candidates add words/content, change legal meaning, change names/numbers/dates/codes, or change scope.
- MANUAL_REVIEW if the context is insufficient or ambiguous.
- Do not use numeric scores.

Reject examples:
- In "dau tranh", choose "đấu" only if it is available and context clearly supports "đấu tranh"; do not choose "đau".
- In "dé tổng hợp", choose "để" if available; do not choose "đề".
- In "hang tuần", choose "hằng" if available; do not choose "hàng".
- In "day mạnh", choose "đẩy" if available; do not choose "đầy".
- In "ran đe", choose "răn" if available.
- "t" -> "thực" is content expansion, not ALLOW.
- "tri tuệ" -> "sở hữu trí tuệ" adds words/content, not ALLOW.
- "điện:" -> "" removes possible document content, not ALLOW unless validated as noise elsewhere.
- Single ambiguous syllables should be MANUAL_REVIEW unless context proves one candidate is orthographic equivalence.
""".strip()

MEANING_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "ocr_meaning_explanation",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "meanings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "fix_id": {"type": "string"},
                            "source_meaning": {"type": "string"},
                            "candidate_meanings": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "replacement": {"type": "string"},
                                        "target_meaning": {"type": "string"},
                                        "meaning_change": {"type": "string", "enum": ["NONE", "ORTHOGRAPHIC_ONLY", "POSSIBLE_CHANGE", "CLEAR_CHANGE", "UNKNOWN"]},
                                        "requires_guessing": {"type": "string", "enum": ["YES", "NO"]},
                                        "explanation": {"type": "string"},
                                    },
                                    "required": ["replacement", "target_meaning", "meaning_change", "requires_guessing", "explanation"],
                                },
                            },
                        },
                        "required": ["fix_id", "source_meaning", "candidate_meanings"],
                    },
                }
            },
            "required": ["meanings"],
        },
    },
}

SIMILARITY_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "ocr_similarity_evaluation",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "evaluations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "fix_id": {"type": "string"},
                            "best_replacement": {"type": "string"},
                            "similarity": {"type": "string", "enum": ["EXACT_SAME", "ORTHOGRAPHIC_EQUIVALENT", "SAME_ADMIN_TERM", "AMBIGUOUS", "MEANING_CHANGED", "UNRELATED"]},
                            "apply_decision": {"type": "string", "enum": ["ALLOW", "REJECT", "MANUAL_REVIEW"]},
                            "reason": {"type": "string"},
                        },
                        "required": ["fix_id", "best_replacement", "similarity", "apply_decision", "reason"],
                    },
                }
            },
            "required": ["evaluations"],
        },
    },
}

ALTERNATIVE_GENERATION_PROMPT = """
You are generating possible OCR correction replacements for Vietnamese administrative text.

Task:
For each source phrase marked as a possible OCR/spelling/diacritic error, propose multiple possible replacement candidates.
Use the full segment context. Return JSON only.

Return format:
{
  "alternatives": [
    {
      "fix_id": "segment_id:index",
      "source": "original source phrase",
      "candidates": [
        {
          "replacement": "candidate replacement",
          "candidate_type": "KEEP_ORIGINAL" | "DIACRITIC_RESTORE" | "SPELLING_FIX" | "OCR_SHAPE_FIX" | "PUNCTUATION_FIX" | "UNSURE",
          "context_fit": "GOOD" | "POSSIBLE" | "BAD",
          "changes_meaning": "YES" | "NO" | "UNCLEAR",
          "reason": "short reason"
        }
      ]
    }
  ]
}

Rules:
- Always include the original source as one candidate with candidate_type KEEP_ORIGINAL.
- Use phrase_window, left_words, and right_words more strongly than the isolated source token.
- Include the previous model suggestion only if it is plausible in the phrase context.
- Propose at most 5 candidates per source.
- Prefer Vietnamese administrative/legal context.
- Do not add new content that is not recoverable from the source.
- Do not guess names, dates, numbers, legal codes, agencies, or document identifiers.
- Ambiguous short syllables such as "dau", "day", "de", "dé", "hang", "t", "iy" must include KEEP_ORIGINAL and may include multiple possibilities.
- If no candidate is clearly safe, keep only KEEP_ORIGINAL or mark candidates as UNSURE/POSSIBLE.

Phrase examples:
- phrase_window "dau tranh" should include "đấu" as a candidate; "đau" is bad in that phrase.
- phrase_window "dé tổng hợp" should include "để"; "đề" is bad in that phrase.
- phrase_window "hang tuần" should include "hằng"; "hàng" is bad in that phrase.
- phrase_window "day mạnh" should include "đẩy"; "đầy" is bad in that phrase.
- phrase_window "ran đe" should include "răn"; "ran" or "ràn" is bad in that phrase.
""".strip()

ALTERNATIVE_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "ocr_alternative_generation",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "alternatives": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "fix_id": {"type": "string"},
                            "source": {"type": "string"},
                            "candidates": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "replacement": {"type": "string"},
                                        "candidate_type": {"type": "string", "enum": ["KEEP_ORIGINAL", "DIACRITIC_RESTORE", "SPELLING_FIX", "OCR_SHAPE_FIX", "PUNCTUATION_FIX", "UNSURE"]},
                                        "context_fit": {"type": "string", "enum": ["GOOD", "POSSIBLE", "BAD"]},
                                        "changes_meaning": {"type": "string", "enum": ["YES", "NO", "UNCLEAR"]},
                                        "reason": {"type": "string"},
                                    },
                                    "required": ["replacement", "candidate_type", "context_fit", "changes_meaning", "reason"],
                                },
                            },
                        },
                        "required": ["fix_id", "source", "candidates"],
                    },
                }
            },
            "required": ["alternatives"],
        },
    },
}




SIMPLE_FIX_VALIDATION_PROMPT = """
You validate OCR fixes in Vietnamese administrative text.

Return exactly one valid JSON object.

Input:
- id: fix id
- text: full segment context
- src: exact source substring
- hint: previous suggested replacement, may be wrong

Task:
For each item, decide whether src should be replaced.

Return format:
{
  "results": [
    {
      "id": "same id",
      "action": "APPLY" | "REJECT" | "MANUAL",
      "to": "replacement or original src",
      "reason": "CONTEXT_MATCH" | "KEEP_ORIGINAL" | "MEANING_CHANGE" | "TOO_AMBIGUOUS" | "UNSAFE_EXPANSION" | "PROTECTED_CONTENT" | "NOT_FOUND"
    }
  ]
}

Rules:
- Return exactly one result for every input item.
- APPLY only when the replacement preserves phrase-level meaning.
- If unsure, use MANUAL.
- If keeping original is safest, use REJECT and set to = src.
- Do not add missing content.
- Do not change names, dates, numbers, document codes, article numbers, or organization names.
- Do not rewrite full sentences.
- Prefer context over isolated word form.
- The hint may be wrong; do not blindly follow it.
- If src is not found exactly in text, use REJECT and reason NOT_FOUND.

Important examples:
- "dé tổng hợp" should be "để", not "đề".
- "hang tuần" should be "hằng", not "hàng".
- "day mạnh" should be "đẩy", not "đầy".
- "ran đe" should be "răn".
- "dau tranh" should be "đấu tranh", not "đau tranh".
- "t" -> "thực" is unsafe expansion.
- "tri tuệ" -> "sở hữu trí tuệ" adds content and must be rejected.
- Removing possible administrative labels such as "điện:" is unsafe unless a separate noise validation proves it is noise.
""".strip()


SIMPLE_FIX_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "simple_ocr_fix_validation",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "id": {"type": "string"},
                            "action": {"type": "string", "enum": ["APPLY", "REJECT", "MANUAL"]},
                            "to": {"type": "string"},
                            "reason": {
                                "type": "string",
                                "enum": [
                                    "CONTEXT_MATCH",
                                    "KEEP_ORIGINAL",
                                    "MEANING_CHANGE",
                                    "TOO_AMBIGUOUS",
                                    "UNSAFE_EXPANSION",
                                    "PROTECTED_CONTENT",
                                    "NOT_FOUND",
                                ],
                            },
                        },
                        "required": ["id", "action", "to", "reason"],
                    },
                }
            },
            "required": ["results"],
        },
    },
}


def build_simple_fix_prompt(candidates: list[dict[str, Any]]) -> str:
    payload = {
        "items": [
            {
                "id": c["fix_id"],
                "text": c["segment_text"],
                "src": c["source"],
                "hint": c["replacement"],
            }
            for c in candidates
        ]
    }
    prompt = JSON_OUTPUT_RULES + "\n\n" + SIMPLE_FIX_VALIDATION_PROMPT + "\nINPUT JSON:\n" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(prompt) > OCR_MAX_PROMPT_CHARS:
        raise ValueError(f"Prompt too long: {len(prompt)} chars > {OCR_MAX_PROMPT_CHARS}")
    return prompt



NOISE_VALIDATION_PROMPT = """
You are validating whether OCR/PDF extracted segments are removable noise in a Vietnamese administrative document.

Task:
For each candidate segment marked REMOVE_NOISE by a previous model, inspect the segment with neighboring context.
Return JSON only.

Return format:
{
  "noise_evaluations": [
    {
      "segment_id": 1,
      "content_role": "DOCUMENT_CONTENT" | "LAYOUT_METADATA" | "SCAN_STAMP" | "OCR_GARBAGE" | "UNCLEAR",
      "remove_decision": "REMOVE" | "KEEP" | "MANUAL_REVIEW",
      "reason": "short reason"
    }
  ]
}

Rules:
- REMOVE only if the segment is clearly not part of the administrative document content.
- KEEP if it is a title, subject, recipient, legal basis, numbered/lettered item, body text, footer, signature, date, or document metadata.
- MANUAL_REVIEW if uncertain.
- Use neighboring context to decide whether the text is a scan stamp, portal watermark, broken OCR junk, or real content.
- Do not use document-type-specific assumptions.
- Do not remove valid administrative content just because it has OCR errors.
""".strip()

NOISE_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "ocr_noise_validation",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "noise_evaluations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "segment_id": {"type": "integer"},
                            "content_role": {"type": "string", "enum": ["DOCUMENT_CONTENT", "LAYOUT_METADATA", "SCAN_STAMP", "OCR_GARBAGE", "UNCLEAR"]},
                            "remove_decision": {"type": "string", "enum": ["REMOVE", "KEEP", "MANUAL_REVIEW"]},
                            "reason": {"type": "string"},
                        },
                        "required": ["segment_id", "content_role", "remove_decision", "reason"],
                    },
                }
            },
            "required": ["noise_evaluations"],
        },
    },
}


def build_noise_validation_prompt(items: list[dict[str, Any]]) -> str:
    payload = {"items": items}
    prompt = (
        JSON_OUTPUT_RULES
        + "\n\n"
        + NOISE_VALIDATION_PROMPT
        + "\nINPUT JSON:\n"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )
    if len(prompt) > OCR_MAX_PROMPT_CHARS:
        raise ValueError(f"Prompt too long: {len(prompt)} chars > {OCR_MAX_PROMPT_CHARS}")
    return prompt


def collect_noise_candidates(segments: list[SegmentRecord], reviews: list[SegmentReview]) -> list[dict[str, Any]]:
    review_by_id = {r.segment_id: r for r in reviews}
    segments_sorted = sorted(segments, key=lambda s: s.segment_id)
    by_id = {s.segment_id: s for s in segments_sorted}
    candidates: list[dict[str, Any]] = []

    for seg in segments_sorted:
        review = review_by_id.get(seg.segment_id)
        if not review or review.decision != "REMOVE_NOISE":
            continue

        prev_seg = by_id.get(seg.segment_id - 1)
        next_seg = by_id.get(seg.segment_id + 1)

        candidates.append({
            "segment_id": seg.segment_id,
            "segment_kind": seg.kind,
            "segment_text": clip_text(seg.text, OCR_TEXT_SNIPPET_CHARS),
            "previous_segment": clip_text(prev_seg.text, 280) if prev_seg else None,
            "next_segment": clip_text(next_seg.text, 280) if next_seg else None,
            "model_notes": review.notes,
            "model_risk": review.risk,
        })

    return candidates


def semantic_validate_noise_segments(
    client: OpenAI,
    segments: list[SegmentRecord],
    reviews: list[SegmentReview],
    document_id: str | None = None,
) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]:
    """Validate REMOVE_NOISE decisions with a separate LLM context pass.

    This avoids hard-coding watermark/portal/stamp patterns in Python.
    """
    candidates = collect_noise_candidates(segments, reviews)
    allowed: dict[int, dict[str, Any]] = {}
    report: list[dict[str, Any]] = []

    if not candidates:
        return allowed, report

    for batch_index, batch in enumerate(chunk_list(candidates, OCR_SEMANTIC_BATCH_SIZE), start=1):
        try:
            obj = call_llm_json(
                client,
                build_noise_validation_prompt(batch),
                response_format=NOISE_RESPONSE_FORMAT,
                document_id=document_id,
                stage="noise_validation",
                batch_index=batch_index,
            )
            raw = obj.get("noise_evaluations", []) if isinstance(obj, dict) else []
            evals = {int(e.get("segment_id")): e for e in raw if isinstance(e, dict) and str(e.get("segment_id", "")).isdigit()}

            for c in batch:
                sid = int(c["segment_id"])
                e = evals.get(sid, {})
                role = str(e.get("content_role", "UNCLEAR")).upper()
                decision = str(e.get("remove_decision", "MANUAL_REVIEW")).upper()
                reason = str(e.get("reason", ""))

                can_remove = decision == "REMOVE" and role in {"SCAN_STAMP", "OCR_GARBAGE", "LAYOUT_METADATA"}
                item = {
                    **c,
                    "content_role": role,
                    "remove_decision": decision,
                    "can_remove": can_remove,
                    "reason": reason,
                }
                report.append(item)
                if can_remove:
                    allowed[sid] = item
        except Exception as exc:
            for c in batch:
                report.append({**c, "remove_decision": "MANUAL_REVIEW", "can_remove": False, "reason": f"noise validation failed: {exc}"})

        if document_id:
            save_json_always(work_dir(document_id) / "noise_validation.partial.json", report)
            update_progress(document_id, status="validating_noise", completed_noise_batches=batch_index)

    return allowed, report



def has_cjk(text: str) -> bool:
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
    if re.search(r"\d", src) or re.search(r"\d", dst):
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


def collect_fix_candidates(segments: list[SegmentRecord], reviews: list[SegmentReview]) -> list[dict[str, Any]]:
    seg_by_id = {s.segment_id: s for s in segments}
    candidates: list[dict[str, Any]] = []
    for review in reviews:
        if review.decision != "APPLY_SMALL_FIXES":
            continue
        if review.risk == "HIGH":
            continue
        seg = seg_by_id.get(review.segment_id)
        if not seg:
            continue
        for idx, fix in enumerate(review.fixes):
            src = str(fix.get("from", ""))
            dst = str(fix.get("to", ""))
            ok, reason = generic_fix_shape_is_safe(src, dst)
            fix_id = f"{review.segment_id}:{idx}"
            phrase_context = extract_phrase_context(seg.text, src, window_words=3)
            candidates.append({
                "fix_id": fix_id,
                "segment_id": review.segment_id,
                "fix_index": idx,
                "segment_kind": seg.kind,
                "segment_text": clip_text(seg.text, OCR_TEXT_SNIPPET_CHARS),
                "source": src,
                "replacement": dst,
                "phrase_context": phrase_context,
                "phrase_window": phrase_context.get("phrase_window", src),
                "left_words": phrase_context.get("left_words", []),
                "right_words": phrase_context.get("right_words", []),
                "kind": fix.get("kind", ""),
                "scope": fix.get("scope", ""),
                "precheck": "PASS" if ok else "REJECT",
                "precheck_reason": reason,
            })
    return candidates


def _candidate_context_payload(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "fix_id": c["fix_id"],
        "segment_text": c["segment_text"],
        "source": c["source"],
        "phrase_context": c.get("phrase_context", {}),
        "phrase_window": c.get("phrase_window", c["source"]),
        "left_words": c.get("left_words", []),
        "right_words": c.get("right_words", []),
        "previous_suggestion": c["replacement"],
        "kind": c["kind"],
        "scope": c["scope"],
    }


def build_alternative_prompt(candidates: list[dict[str, Any]]) -> str:
    items = [_candidate_context_payload(c) for c in candidates]
    payload = {"items": items}
    prompt = JSON_OUTPUT_RULES + "\n\n" + ALTERNATIVE_GENERATION_PROMPT + "\nINPUT JSON:\n" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(prompt) > OCR_MAX_PROMPT_CHARS:
        raise ValueError(f"Prompt too long: {len(prompt)} chars > {OCR_MAX_PROMPT_CHARS}")
    return prompt


def build_meaning_prompt(candidates: list[dict[str, Any]], alternatives: dict[str, dict[str, Any]]) -> str:
    items = []
    for c in candidates:
        alt = alternatives.get(c["fix_id"], {})
        item = _candidate_context_payload(c)
        item["candidates"] = alt.get("candidates", [
            {"replacement": c["source"], "candidate_type": "KEEP_ORIGINAL", "context_fit": "POSSIBLE", "changes_meaning": "NO", "reason": "Original source."},
            {"replacement": c["replacement"], "candidate_type": "UNSURE", "context_fit": "POSSIBLE", "changes_meaning": "UNCLEAR", "reason": "Previous suggestion."},
        ])
        items.append(item)

    payload = {"items": items}
    prompt = JSON_OUTPUT_RULES + "\n\n" + MEANING_EXPLANATION_PROMPT + "\nINPUT JSON:\n" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(prompt) > OCR_MAX_PROMPT_CHARS:
        raise ValueError(f"Prompt too long: {len(prompt)} chars > {OCR_MAX_PROMPT_CHARS}")
    return prompt


def build_similarity_prompt(candidates: list[dict[str, Any]], alternatives: dict[str, dict[str, Any]], meanings: dict[str, dict[str, Any]]) -> str:
    items = []
    for c in candidates:
        alt = alternatives.get(c["fix_id"], {})
        item = _candidate_context_payload(c)
        item["candidates"] = alt.get("candidates", [
            {"replacement": c["source"], "candidate_type": "KEEP_ORIGINAL", "context_fit": "POSSIBLE", "changes_meaning": "NO", "reason": "Original source."},
            {"replacement": c["replacement"], "candidate_type": "UNSURE", "context_fit": "POSSIBLE", "changes_meaning": "UNCLEAR", "reason": "Previous suggestion."},
        ])
        item["meaning"] = meanings.get(c["fix_id"], {})
        items.append(item)

    payload = {"items": items}
    prompt = JSON_OUTPUT_RULES + "\n\n" + SIMILARITY_EVALUATION_PROMPT + "\nINPUT JSON:\n" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(prompt) > OCR_MAX_PROMPT_CHARS:
        raise ValueError(f"Prompt too long: {len(prompt)} chars > {OCR_MAX_PROMPT_CHARS}")
    return prompt


def chunk_list(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i:i + size] for i in range(0, len(items), max(1, size))]


def semantic_validate_candidate_fixes(client: OpenAI, segments: list[SegmentRecord], reviews: list[SegmentReview], document_id: str | None = None) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """One-request semantic validation for OCR fixes.

    LLM suggests APPLY / REJECT / MANUAL; Python still performs the final
    deterministic safety checks before allowing any replacement.
    """
    candidates = collect_fix_candidates(segments, reviews)
    report: list[dict[str, Any]] = []
    allowed: dict[str, dict[str, Any]] = {}

    if not OCR_ENABLE_SEMANTIC_VALIDATION:
        for c in candidates:
            report.append({
                **c,
                "semantic_validation": "DISABLED",
                "apply_decision": "MANUAL_REVIEW",
                "reason": "semantic validation disabled",
            })
        return allowed, report

    for batch_index, batch in enumerate(chunk_list(candidates, OCR_SEMANTIC_BATCH_SIZE), start=1):
        passed: list[dict[str, Any]] = []

        for c in batch:
            if c["precheck"] != "PASS":
                report.append({
                    **c,
                    "apply_decision": "REJECT",
                    "reason": c["precheck_reason"],
                })
            else:
                passed.append(c)

        if not passed:
            continue

        try:
            obj = call_llm_json(
                client,
                build_simple_fix_prompt(passed),
                response_format=SIMPLE_FIX_RESPONSE_FORMAT,
                document_id=document_id,
                stage="semantic_validation",
                batch_index=batch_index,
            )

            raw_results = obj.get("results", []) if isinstance(obj, dict) else []
            results = {
                str(item.get("id")): item
                for item in raw_results
                if isinstance(item, dict)
            }

            for c in passed:
                fid = c["fix_id"]
                result = results.get(fid)

                if not result:
                    report.append({
                        **c,
                        "evaluation": {},
                        "best_replacement": c["source"],
                        "original_suggestion": c["replacement"],
                        "best_shape_check": "REJECT",
                        "best_shape_reason": "LLM omitted this fix id",
                        "apply_decision": "MANUAL_REVIEW",
                        "reason": "LLM omitted this fix id",
                    })
                    continue

                action = str(result.get("action", "MANUAL")).upper()
                replacement = str(result.get("to", c["source"]))
                reason = str(result.get("reason", "TOO_AMBIGUOUS")).upper()

                if action not in {"APPLY", "REJECT", "MANUAL"}:
                    action = "MANUAL"
                if reason not in {
                    "CONTEXT_MATCH",
                    "KEEP_ORIGINAL",
                    "MEANING_CHANGE",
                    "TOO_AMBIGUOUS",
                    "UNSAFE_EXPANSION",
                    "PROTECTED_CONTENT",
                    "NOT_FOUND",
                }:
                    reason = "TOO_AMBIGUOUS"

                shape_ok, shape_reason = generic_fix_shape_is_safe(c["source"], replacement)

                can_apply = (
                    action == "APPLY"
                    and reason == "CONTEXT_MATCH"
                    and replacement != c["source"]
                    and c["source"] in c["segment_text"]
                    and shape_ok
                )

                if can_apply:
                    apply_decision = "ALLOW"
                elif action == "REJECT":
                    apply_decision = "REJECT"
                else:
                    apply_decision = "MANUAL_REVIEW"

                item = {
                    **c,
                    "evaluation": result,
                    "best_replacement": replacement,
                    "original_suggestion": c["replacement"],
                    "best_shape_check": "PASS" if shape_ok else "REJECT",
                    "best_shape_reason": shape_reason,
                    "apply_decision": apply_decision,
                    "reason": reason,
                }
                report.append(item)

                if can_apply:
                    allowed[fid] = item

        except Exception as exc:
            for c in passed:
                report.append({
                    **c,
                    "apply_decision": "REJECT",
                    "reason": f"semantic validation failed: {exc}",
                })

        if document_id:
            save_json_always(work_dir(document_id) / "semantic_validation.partial.json", report)
            update_progress(document_id, status="validating_semantic_fixes", completed_semantic_batches=batch_index)

    return allowed, report

def assert_semantic_validation_ready(
    reviews: list[SegmentReview],
    semantic_report: list[dict[str, Any]],
) -> None:
    """Fail early if spelling fixes exist but semantic validation produced no report."""
    has_fix_candidates = any(
        r.decision == "APPLY_SMALL_FIXES" and r.risk != "HIGH" and bool(r.fixes)
        for r in reviews
    )
    if OCR_ENABLE_SEMANTIC_VALIDATION and has_fix_candidates and not semantic_report:
        raise RuntimeError(
            "OCR_ENABLE_SEMANTIC_VALIDATION=true but semantic_validation report is empty while fix candidates exist."
        )


def is_short_safe_fix(src: str, dst: str) -> bool:
    ok, _ = generic_fix_shape_is_safe(src, dst)
    return ok


def apply_reviews_to_segments(
    segments: list[SegmentRecord],
    reviews: list[SegmentReview],
    semantic_allowed: dict[str, dict[str, Any]] | None = None,
    noise_allowed: dict[int, dict[str, Any]] | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    semantic_allowed = semantic_allowed or {}
    noise_allowed = noise_allowed or {}
    by_id = {r.segment_id: r for r in reviews}
    final_segments: list[str] = []
    report: list[dict[str, Any]] = []

    for seg in segments:
        text = seg.text
        review = by_id.get(seg.segment_id, SegmentReview(seg.segment_id, "KEEP", "LOW", [], "Missing review."))
        applied: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        note = ""

        if review.decision == "REMOVE_NOISE":
            noise_eval = noise_allowed.get(seg.segment_id)
            if noise_eval and noise_eval.get("can_remove"):
                report.append({
                    "segment_id": seg.segment_id,
                    "line_ids": seg.line_ids,
                    "kind": seg.kind,
                    "decision": review.decision,
                    "risk": review.risk,
                    "applied": True,
                    "removed": True,
                    "noise_validation": noise_eval,
                    "notes": review.notes,
                    "before": seg.text,
                    "after": "",
                })
                continue
            note = "REMOVE_NOISE rejected because context-aware noise validation did not approve removal."

        if review.decision == "APPLY_SMALL_FIXES":
            for idx, fix in enumerate(review.fixes):
                src = str(fix.get("from", ""))
                original_dst = str(fix.get("to", ""))
                fix_id = f"{seg.segment_id}:{idx}"
                semantic = semantic_allowed.get(fix_id)

                if not semantic:
                    rejected.append({
                        **fix,
                        "fix_id": fix_id,
                        "applied": False,
                        "reason": "Rejected: missing semantic approval.",
                    })
                    continue

                replacement = str(semantic.get("best_replacement", original_dst))

                if src not in text:
                    rejected.append({
                        **fix,
                        "fix_id": fix_id,
                        "applied": False,
                        "reason": "Rejected: source substring not found in segment text.",
                        "semantic": semantic,
                    })
                    continue

                if not is_short_safe_fix(src, replacement):
                    rejected.append({
                        **fix,
                        "fix_id": fix_id,
                        "applied": False,
                        "reason": "Rejected: replacement failed Python shape check.",
                        "semantic": semantic,
                    })
                    continue

                text = text.replace(src, replacement, 1)
                applied.append({
                    **fix,
                    "fix_id": fix_id,
                    "from": src,
                    "to": replacement,
                    "original_suggestion": original_dst,
                    "applied": True,
                    "semantic": semantic,
                })

        text = "\n".join(apply_safe_rule_corrections(line) for line in text.splitlines())
        final_segments.append(text)
        report.append({
            "segment_id": seg.segment_id,
            "line_ids": seg.line_ids,
            "kind": seg.kind,
            "decision": review.decision,
            "risk": review.risk,
            "applied_fixes": applied,
            "rejected_fixes": rejected,
            "notes": note or review.notes,
            "before": seg.text,
            "after": text,
        })

    return final_segments, report

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
        elif normalize_for_compare(s) and normalize_for_compare(s) in comparable_norm:
            status = "FUZZY_FOUND"
            fuzzy += 1
        else:
            status = "MISSING"
            missing += 1

        if status != "EXACT_FOUND":
            results.append({
                **asdict(line),
                "status": status,
                "normalized_for_compare": normalize_for_compare(s),
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


def build_applied_fixes_summary(
    review_report: list[dict[str, Any]],
    semantic_report: list[dict[str, Any]],
    noise_report: list[dict[str, Any]],
) -> dict[str, Any]:
    applied_fixes: list[dict[str, Any]] = []
    rejected_fixes: list[dict[str, Any]] = []
    removed_noise: list[dict[str, Any]] = []
    manual_review: list[dict[str, Any]] = []

    semantic_by_id = {
        str(item.get("fix_id")): item
        for item in semantic_report
        if isinstance(item, dict) and item.get("fix_id") is not None
    }

    for item in review_report:
        if item.get("removed"):
            removed_noise.append({
                "segment_id": item.get("segment_id"),
                "before": item.get("before"),
                "noise_validation": item.get("noise_validation"),
            })

        for fix in item.get("applied_fixes", []) or []:
            fid = str(fix.get("fix_id"))
            applied_fixes.append({
                "segment_id": item.get("segment_id"),
                "from": fix.get("from"),
                "to": fix.get("to"),
                "fix_id": fid,
                "semantic": fix.get("semantic") or semantic_by_id.get(fid),
            })

        for fix in item.get("rejected_fixes", []) or []:
            fid = str(fix.get("fix_id"))
            rejected_fixes.append({
                "segment_id": item.get("segment_id"),
                "from": fix.get("from"),
                "to": fix.get("to"),
                "fix_id": fid,
                "reason": fix.get("reason"),
                "semantic": semantic_by_id.get(fid),
            })

        if item.get("decision") == "MANUAL_REVIEW":
            manual_review.append({
                "segment_id": item.get("segment_id"),
                "kind": item.get("kind"),
                "before": item.get("before"),
                "notes": item.get("notes"),
            })

    return {
        "applied_count": len(applied_fixes),
        "rejected_count": len(rejected_fixes),
        "removed_noise_count": len(removed_noise),
        "manual_review_count": len(manual_review),
        "applied_fixes": applied_fixes[:200],
        "rejected_fixes": rejected_fixes[:300],
        "removed_noise": removed_noise[:100],
        "manual_review": manual_review[:100],
        "noise_validation_count": len(noise_report),
        "semantic_validation_count": len(semantic_report),
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
    start = time.time()
    ensure_dirs(document_id)

    normalized_path = NORMALIZED_TEXT_DIR / f"{document_id}.txt"

    update_progress(document_id, status="started", output_path=str(normalized_path), work_dir=str(work_dir(document_id)))
    _log(f"START normalized_text pipeline: {document_id}")
    _log("Effective runtime config / env:")
    print(json.dumps(get_effective_env(), ensure_ascii=False, indent=2), flush=True)

    try:
        raw_text = load_raw_extracted_text(document_id)
        save_text(work_dir(document_id) / "raw_extracted_text.txt", raw_text)
        update_progress(document_id, status="loaded_raw_text")

        prepared = prepare_lines(raw_text)
        _log(f"Prepared lines: {len(prepared)}")
        save_session_json(document_id, "prepared_lines.json", [asdict(x) for x in prepared])
        update_progress(document_id, status="prepared_lines", prepared_line_count=len(prepared))

        merged_lines = merge_visual_wrapped_lines(prepared)
        _log(f"Merged visual wrapped lines: {len(merged_lines)}")
        save_session_json(document_id, "merged_lines.json", [asdict(x) for x in merged_lines])
        save_partial_normalized(document_id, "01_after_merge.txt", "\n".join(x.text for x in merged_lines).strip() + "\n")
        update_progress(document_id, status="merged_lines", merged_line_count=len(merged_lines))

        segments = build_sentence_segments(merged_lines)
        _log(f"Built sentence/paragraph segments: {len(segments)}")
        save_session_json(document_id, "segments.json", [asdict(x) for x in segments])
        update_progress(document_id, status="built_segments", segment_count=len(segments))

        client = make_client()

        reviews = review_segments_with_llm(client, segments, document_id=document_id)
        save_session_json(document_id, "llm_review.json", [asdict(x) for x in reviews])
        update_progress(document_id, status="reviewed_segments", review_count=len(reviews))

        semantic_allowed, semantic_report = semantic_validate_candidate_fixes(
            client,
            segments,
            reviews,
            document_id=document_id,
        )
        save_session_json(document_id, "semantic_validation.json", semantic_report)
        save_session_json(document_id, "semantic_allowed.json", semantic_allowed)
        update_progress(
            document_id,
            status="validated_semantic_fixes",
            semantic_validation_count=len(semantic_report),
            semantic_allowed_count=len(semantic_allowed),
        )

        assert_semantic_validation_ready(reviews, semantic_report)

        noise_allowed, noise_report = semantic_validate_noise_segments(
            client,
            segments,
            reviews,
            document_id=document_id,
        )
        save_session_json(document_id, "noise_validation.json", noise_report)
        save_session_json(document_id, "noise_allowed.json", noise_allowed)
        update_progress(
            document_id,
            status="validated_noise",
            noise_validation_count=len(noise_report),
            noise_allowed_count=len(noise_allowed),
        )

        fixed_segments, review_report = apply_reviews_to_segments(
            segments,
            reviews,
            semantic_allowed=semantic_allowed,
            noise_allowed=noise_allowed,
        )
        save_session_json(document_id, "normalized_report.json", review_report)

        joined_fixed = "\n".join(fixed_segments)
        save_partial_normalized(document_id, "02_after_apply_reviews.txt", joined_fixed.strip() + "\n")
        update_progress(document_id, status="applied_reviews", fixed_segment_count=len(fixed_segments))

        normalized_text = final_merge_and_cleanup(joined_fixed)
        save_partial_normalized(document_id, "03_final_normalized_preview.txt", normalized_text)

        validation = validate_loss_signal(prepared, normalized_text)
        save_session_json(document_id, "validation.json", validation)

        applied_summary = build_applied_fixes_summary(review_report, semantic_report, noise_report)
        save_session_json(document_id, "applied_fixes_summary.json", applied_summary)

        normalized_path.parent.mkdir(parents=True, exist_ok=True)
        normalized_path.write_text(normalized_text, encoding="utf-8")

        # Backward-compatible copies in result directory.
        # These are controlled by OCR_SAVE_REPORTS.
        save_json(NORMALIZED_TEXT_DIR / f"{document_id}.prepared_lines.json", [asdict(x) for x in prepared])
        save_json(NORMALIZED_TEXT_DIR / f"{document_id}.merged_lines.json", [asdict(x) for x in merged_lines])
        save_json(NORMALIZED_TEXT_DIR / f"{document_id}.segments.json", [asdict(x) for x in segments])
        save_json(NORMALIZED_TEXT_DIR / f"{document_id}.llm_review.json", [asdict(x) for x in reviews])
        save_json(NORMALIZED_TEXT_DIR / f"{document_id}.semantic_validation.json", semantic_report)
        save_json(NORMALIZED_TEXT_DIR / f"{document_id}.noise_validation.json", noise_report)
        save_json(NORMALIZED_TEXT_DIR / f"{document_id}.normalized_report.json", review_report)
        save_json(NORMALIZED_TEXT_DIR / f"{document_id}.applied_fixes_summary.json", applied_summary)
        save_json(NORMALIZED_TEXT_DIR / f"{document_id}.validation.json", validation)

        duration = round(time.time() - start, 2)

        if validation["count"]:
            _log(f"Validation warning: possibly missing meaningful lines = {validation['count']}")

        update_progress(
            document_id,
            status="done",
            output_path=str(normalized_path),
            work_dir=str(work_dir(document_id)),
            duration_seconds=duration,
            validation_summary=validation.get("summary", {}),
            applied_fixes_summary={
                "applied_count": applied_summary.get("applied_count", 0),
                "rejected_count": applied_summary.get("rejected_count", 0),
                "removed_noise_count": applied_summary.get("removed_noise_count", 0),
                "manual_review_count": applied_summary.get("manual_review_count", 0),
            },
        )

        _log(f"Saved normalized text: {normalized_path}")
        _log(f"Saved session work dir: {work_dir(document_id)}")
        _log(f"DONE in {duration:.2f}s")
        return normalized_path

    except Exception as exc:
        update_progress(
            document_id,
            status="failed",
            error=str(exc),
            output_path=str(normalized_path),
            work_dir=str(work_dir(document_id)),
            duration_seconds=round(time.time() - start, 2),
        )
        raise