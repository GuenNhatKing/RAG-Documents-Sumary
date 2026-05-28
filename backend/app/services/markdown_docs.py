from __future__ import annotations

import json, os, re, time
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from openai import OpenAI, APITimeoutError, APIConnectionError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

# =========================================================
# CONFIG - small by design
# =========================================================
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
NORMALIZED_DIR = Path(os.getenv("NORMALIZED_TEXT_DIR", str(DATA_DIR / "normalized_text")))
MARKDOWN_DIR = Path(os.getenv("MARKDOWN_DOCS_DIR", str(DATA_DIR / "markdown_docs")))
WORK_DIR = Path(os.getenv("MD_WORK_DIR", str(DATA_DIR / "markdown_work")))

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "ollama")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen3:4b-q4_K_M")
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "300"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1024"))
LLM_NUM_CTX = int(os.getenv("LLM_NUM_CTX", "4096"))
LLM_THINK = os.getenv("LLM_THINK", "false").lower() == "true"
LLM_KEEP_ALIVE = os.getenv("LLM_KEEP_ALIVE", "30m")
LLM_USE_RESPONSE_FORMAT = os.getenv("LLM_USE_RESPONSE_FORMAT", "true").lower() == "true"

MD_MAX_PROMPT_CHARS = int(os.getenv("MD_MAX_PROMPT_CHARS", "7500"))
MD_SECTION_MAX_BLOCKS = int(os.getenv("MD_SECTION_MAX_BLOCKS", "28"))
MD_SECTION_MAX_CHARS = int(os.getenv("MD_SECTION_MAX_CHARS", "5000"))
MD_BLOCK_TEXT_CHARS = int(os.getenv("MD_BLOCK_TEXT_CHARS", "140"))
MD_MAX_HEADING_LEVEL = int(os.getenv("MD_MAX_HEADING_LEVEL", "4"))
MD_SAVE_REPORTS = os.getenv("MD_SAVE_REPORTS", "true").lower() == "true"
SAVE_DEBUG_FILES = os.getenv("SAVE_DEBUG_FILES", "false").lower() == "true"
MD_ALLOW_PARTIAL = os.getenv("MD_ALLOW_PARTIAL", "true").lower() == "true"
MD_JSON_RETRY_ATTEMPTS = int(os.getenv("MD_JSON_RETRY_ATTEMPTS", "3"))
MD_JSON_RETRY_WAIT_SECONDS = int(os.getenv("MD_JSON_RETRY_WAIT_SECONDS", "2"))

# Batched pipeline config
MD_LLM_MAX_CHUNK_CHARS = int(os.getenv("MD_LLM_MAX_CHUNK_CHARS", "1500"))
MD_LLM_MAX_BLOCKS_PER_CHUNK = int(os.getenv("MD_LLM_MAX_BLOCKS_PER_CHUNK", "12"))
MD_LLM_MAX_CHUNKS_PER_CALL = int(os.getenv("MD_LLM_MAX_CHUNKS_PER_CALL", "4"))
MD_LLM_CONTEXT_BEFORE_CHARS = int(os.getenv("MD_LLM_CONTEXT_BEFORE_CHARS", "100"))
MD_LLM_CONTEXT_AFTER_CHARS = int(os.getenv("MD_LLM_CONTEXT_AFTER_CHARS", "100"))
MD_SUMMARY_MAX_WORDS = int(os.getenv("MD_SUMMARY_MAX_WORDS", "40"))
MD_ENABLE_GLOBAL_REVIEW = os.getenv("MD_ENABLE_GLOBAL_REVIEW", "true").lower() == "true"
MD_ENABLE_AUDIT_LOG = os.getenv("MD_ENABLE_AUDIT_LOG", "true").lower() == "true"
MD_MERGE_CONSERVATIVE = os.getenv("MD_MERGE_CONSERVATIVE", "true").lower() == "true"
MD_PIPELINE_MODE = os.getenv("MD_PIPELINE_MODE", "safe")  # fast/safe/debug

# =========================================================
# DATA
# =========================================================
@dataclass
class LineRecord:
    line_id: int
    text: str

@dataclass
class BlockRecord:
    block_id: int
    line_ids: list[int]
    text: str
    first_line: str
    start_line_id: int
    end_line_id: int
    features: dict[str, Any]

@dataclass
class SectionRecord:
    section_id: int
    block_ids: list[int]
    start_block_id: int
    end_block_id: int
    start_line_id: int
    end_line_id: int
    anchor_text: str
    reason: str
    char_count: int

@dataclass
class BlockRole:
    block_id: int
    role: str
    summary: str = ""

@dataclass
class NodeCandidate:
    block_id: int
    rough_level: str
    role: str

@dataclass
class OutlineNode:
    block_id: int
    line_id: int
    level: int
    first_line: str
    line_ids: list[int]
    role: str = "UNKNOWN"
    section_id: int | None = None

# =========================================================
# FILE / LOG
# =========================================================
_log_file = None  # Will be set per pipeline run
_log_lock = threading.Lock()


def _log(msg: str) -> None:
    print(f"[MD-INCREMENTAL] {msg}", flush=True)
    with _log_lock:
        if _log_file:
            _log_file.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
            _log_file.flush()


def _log_stage(stage: str, **kwargs: Any) -> None:
    """Structured log with stage name and key-value metrics."""
    extras = " ".join(f"{k}={v}" for k, v in kwargs.items())
    msg = f"[MD-INCREMENTAL] [{stage}] {extras}"
    print(msg, flush=True)
    with _log_lock:
        if _log_file:
            _log_file.write(f"[{time.strftime('%H:%M:%S')}] [{stage}] {extras}\n")
            _log_file.flush()


def _log_llm_call(stage: str, section_id: int | None, prompt_chars: int,
                  response_chars: int, duration_s: float, success: bool,
                  error: str = "") -> None:
    """Log LLM call metrics for performance analysis."""
    status = "OK" if success else "FAIL"
    sec_str = f"section={section_id}" if section_id is not None else "single"
    msg = f"LLM {stage} {sec_str} prompt={prompt_chars} response={response_chars} {duration_s:.1f}s {status}"
    if error:
        msg += f" error={error[:120]}"
    full = f"[MD-INCREMENTAL] [LLM] {msg}"
    print(full, flush=True)
    with _log_lock:
        if _log_file:
            _log_file.write(f"[{time.strftime('%H:%M:%S')}] [LLM] {msg}\n")
            _log_file.flush()

def work_dir(document_id: str) -> Path:
    return WORK_DIR / document_id

def ensure_dirs(document_id: str) -> None:
    MARKDOWN_DIR.mkdir(parents=True, exist_ok=True)
    for sub in ["section_reports", "partial_markdown", "llm_failures"]:
        (work_dir(document_id) / sub).mkdir(parents=True, exist_ok=True)

def save_json(path: Path, data: Any) -> None:
    if not MD_SAVE_REPORTS:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _save_debug_json(path: Path, data: Any) -> None:
    """Always save, regardless of SAVE_DEBUG_FILES. Used for llm_failures only."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def save_text(path: Path, text: str) -> None:
    if not MD_SAVE_REPORTS:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

def effective_config() -> dict[str, Any]:
    return {
        "DATA_DIR": str(DATA_DIR), "NORMALIZED_TEXT_DIR": str(NORMALIZED_DIR),
        "MARKDOWN_DOCS_DIR": str(MARKDOWN_DIR), "MD_WORK_DIR": str(WORK_DIR),
        "LLM_BASE_URL": LLM_BASE_URL, "LLM_API_KEY": "***" if LLM_API_KEY else "",
        "LLM_MODEL": LLM_MODEL, "LLM_NUM_CTX": LLM_NUM_CTX, "LLM_THINK": LLM_THINK,
        "LLM_MAX_TOKENS": LLM_MAX_TOKENS, "LLM_TIMEOUT_SECONDS": LLM_TIMEOUT_SECONDS,
        "LLM_USE_RESPONSE_FORMAT": LLM_USE_RESPONSE_FORMAT, "LLM_KEEP_ALIVE": LLM_KEEP_ALIVE,
        "MD_MAX_PROMPT_CHARS": MD_MAX_PROMPT_CHARS,
        "MD_SECTION_MAX_BLOCKS": MD_SECTION_MAX_BLOCKS, "MD_SECTION_MAX_CHARS": MD_SECTION_MAX_CHARS,
        "MD_BLOCK_TEXT_CHARS": MD_BLOCK_TEXT_CHARS, "MD_MAX_HEADING_LEVEL": MD_MAX_HEADING_LEVEL,
        "MD_ALLOW_PARTIAL": MD_ALLOW_PARTIAL, "MD_SAVE_REPORTS": MD_SAVE_REPORTS,
        "MD_JSON_RETRY_ATTEMPTS": MD_JSON_RETRY_ATTEMPTS,
        "MD_JSON_RETRY_WAIT_SECONDS": MD_JSON_RETRY_WAIT_SECONDS,
        "MD_PIPELINE_MODE": MD_PIPELINE_MODE,
        "MD_LLM_MAX_CHUNK_CHARS": MD_LLM_MAX_CHUNK_CHARS,
        "MD_LLM_MAX_CHUNKS_PER_CALL": MD_LLM_MAX_CHUNKS_PER_CALL,
        "MD_ENABLE_GLOBAL_REVIEW": MD_ENABLE_GLOBAL_REVIEW,
        "MD_MERGE_CONSERVATIVE": MD_MERGE_CONSERVATIVE,
    }

def update_progress(doc_id: str, **data: Any) -> None:
    """Write progress.json safely.

    doc_id is the source of truth. Callers may still pass document_id inside
    **data; it will be overwritten, so Python will not receive duplicate
    values for the same formal argument.
    """
    payload = dict(data or {})
    payload["document_id"] = doc_id
    save_json(work_dir(doc_id) / "progress.json", payload)

# =========================================================
# TEXT UTILS
# =========================================================
def read_lines(path: Path) -> list[LineRecord]:
    lines: list[LineRecord] = []
    for i, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        s = raw.strip()
        if s:
            lines.append(LineRecord(len(lines) + 1, s))
    return lines

def clip(text: Any, n: int) -> str:
    s = " ".join(str(text or "").split())
    if len(s) <= n:
        return s
    if n <= 20:
        return s[:n]
    h = n // 2
    return s[:h].rstrip() + " ... " + s[-h:].lstrip()

def cj(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))

# =========================================================
# ROBUST JSON
# =========================================================
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

def extract_json_object(content: str) -> dict[str, Any]:
    raw = (content or "").strip()
    raw = _THINK_RE.sub("", raw).strip()
    raw = re.sub(r"^```(?:json|JSON)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw).strip()
    for marker in ["\nINFO:", "\nERROR:", "\nWARNING:", "\nTraceback", "\n[GIN]"]:
        p = raw.find(marker)
        if p != -1:
            raw = raw[:p].strip()

    def balanced(s: str) -> str | None:
        start = s.find("{")
        while start != -1:
            depth = 0; ins = False; esc = False
            for i in range(start, len(s)):
                ch = s[i]
                if ins:
                    if esc: esc = False
                    elif ch == "\\": esc = True
                    elif ch == '"': ins = False
                    continue
                if ch == '"': ins = True
                elif ch == "{": depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0: return s[start:i+1]
            start = s.find("{", start + 1)
        return None

    def sanitize(s: str) -> str:
        out=[]; ins=False; esc=False
        allowed=set('{}[]:,.+-0123456789 \t\r\n')|set('truefalsenullTRUEFALSENULL')
        for ch in s:
            if ins:
                out.append(ch)
                if esc: esc=False
                elif ch=='\\': esc=True
                elif ch=='"': ins=False
            elif ch=='"':
                ins=True; out.append(ch)
            elif ch in allowed:
                out.append(ch)
        return ''.join(out)

    variants = [raw]
    b = balanced(raw)
    if b: variants.append(b)
    if raw.find("{") != -1: variants.append(raw[raw.find("{"):])
    tried=set()
    for v in variants:
        for x in [v, re.sub(r",(\s*[}\]])", r"\1", v), sanitize(v), re.sub(r",(\s*[}\]])", r"\1", sanitize(v))]:
            x=x.strip()
            if not x or x in tried: continue
            tried.add(x)
            try:
                obj=json.loads(x)
                if isinstance(obj, dict): return obj
            except json.JSONDecodeError:
                pass
    raise ValueError(f"LLM did not return parseable JSON. Raw preview:\n{raw[:2000]}")

# =========================================================
# ADMIN FEATURES
# =========================================================
VI_LOWER = "a-zàáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ"

def starts_lower(s: str) -> bool: return bool(re.match(rf"^[{VI_LOWER}]", s.strip()))
def dash_bullet(s: str) -> bool: return bool(re.match(r"^[-–•+]\s+", s.strip()))
def numbered(s: str) -> bool: return bool(re.match(r"^\d+[.)]\s+", s.strip()))
def decimal(s: str) -> bool: return bool(re.match(r"^\d+(?:\.\d+)+[.)]?\s+", s.strip()))
def lettered(s: str) -> bool: return bool(re.match(r"^[A-Za-zÀ-ỹĐđ][.)]\s+", s.strip(), re.I))
def roman(s: str) -> bool: return bool(re.match(r"^[IVXLCDM]+[.)]\s+", s.strip(), re.I))
def article(s: str) -> bool: return bool(re.match(r"^Điều\s+\d+[.:]?\s+", s.strip(), re.I))
def chapter(s: str) -> bool: return bool(re.match(r"^(PHẦN|CHƯƠNG|MỤC|TIỂU\s+MỤC)\s+", s.strip(), re.I))

def marker_kind(s: str) -> str:
    x = s.strip()

    m = re.match(r"^(PHẦN|CHƯƠNG|MỤC|TIỂU\s+MỤC)", x, re.I)
    if m:
        return m.group(1).upper().replace(" ", "_")

    if article(x): return "ARTICLE"
    if decimal(x): return "DECIMAL"
    if numbered(x): return "NUMBER"
    if lettered(x): return "LETTER"
    if roman(x): return "ROMAN"
    if dash_bullet(x): return "BULLET"
    return ""

def any_marker(s: str) -> bool:
    return any(f(s) for f in [dash_bullet, decimal, numbered, lettered, roman, article, chapter])

def upper_ratio(s: str) -> float:
    letters = re.findall(r"[A-Za-zÀ-ỹĐđ]", s)
    if not letters: return 0.0
    return sum(1 for c in letters if c.upper()==c and c.lower()!=c) / len(letters)

def title_like(s: str) -> bool:
    s=s.strip(); words=s.split()
    return bool(s and not any_marker(s) and len(words)<=12 and upper_ratio(s)>=0.65 and not re.search(r"[.!?…]$", s))

def metadata_like(s: str) -> bool:
    s=s.strip()
    if not s or any_marker(s): return False
    return bool(re.match(r"^(số|so)\s*[:：]", s, re.I) or re.search(r"\bngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4}\b", s, re.I) or re.search(r"độc\s+lập\s*-\s*tự\s+do\s*-\s*hạnh\s+phúc", s, re.I))

def subject_like(s: str) -> bool:
    return bool(re.match(r"^(Về|Về việc|Ban hành|Phê duyệt|Triển khai|Kế hoạch|Hướng dẫn)\b", s.strip(), re.I))

def footer_section_like(s: str) -> bool:
    return bool(re.match(r"^(nơi nhận|nơi gửi|kính gửi|lưu|phụ lục)\s*[:：]?$", s.strip(), re.I))

def signature_like(s: str) -> bool:
    return bool(re.search(r"\b(KT\.|TM\.|TL\.|TUQ\.|THỦ TRƯỞNG|BỘ TRƯỞNG|CHỦ TỊCH|PHÓ|TỔNG GIÁM ĐỐC)\b", s.strip(), re.I))

def noise_like(s: str) -> bool:
    s = s.strip()
    alnum = re.findall(r"[A-Za-zÀ-ỹĐđ0-9]", s)
    return bool(
        not s
        or (len(alnum) <= 1 and len(s) <= 8)
        or re.match(r"^={2,}\s*PAGE\s+\d+", s, re.I)
        or re.match(r"^\d+\s*$", s)
    )

def continuation(s: str) -> bool:
    s=s.strip()
    return bool(starts_lower(s) or re.match(r"^\d{1,2}\s+(ngày|tháng|năm)\b", s, re.I) or (len(s)<=35 and not any_marker(s) and not re.search(r"[.!?;:]$", s)))

def prev_invites(prev: str) -> bool:
    s=prev.strip()
    if s.endswith((",",";","-","–")): return True
    if s.endswith(":"): return False
    return bool(not re.search(r"[.!?…]$", s) and len(s.split())>=6 and not title_like(s))

def line_features(s: str) -> dict[str, Any]:
    return {"marker_kind": marker_kind(s), "title_like": title_like(s), "subject_like": subject_like(s), "metadata_like": metadata_like(s), "footer_section_like": footer_section_like(s), "signature_like": signature_like(s), "noise_like": noise_like(s), "starts_marker": any_marker(s), "starts_bullet": dash_bullet(s)}

def new_block(prev: str|None, cur: str, current: list[str]) -> bool:
    if noise_like(cur): return True
    if prev is None: return True
    if len(current)>=12 or len(" ".join(current))+len(cur)>2200: return True
    if title_like(cur) or footer_section_like(cur) or signature_like(cur) or any_marker(cur): return True
    if continuation(cur) or prev_invites(prev): return False
    return True

def make_block(block_id: int, ls: list[LineRecord]) -> BlockRecord:
    text="\n".join(x.text for x in ls); first=ls[0].text
    return BlockRecord(block_id, [x.line_id for x in ls], text, first, ls[0].line_id, ls[-1].line_id, {"line_count":len(ls), "char_count":len(text), "word_count":len(text.split()), "first_line_features":line_features(first)})

def build_blocks(lines: list[LineRecord]) -> list[BlockRecord]:
    blocks=[]; cur=[]
    for line in lines:
        if noise_like(line.text):
            if cur: blocks.append(make_block(len(blocks)+1, cur)); cur=[]
            blocks.append(make_block(len(blocks)+1, [line])); continue
        if not cur: cur=[line]; continue
        if new_block(cur[-1].text, line.text, [x.text for x in cur]):
            blocks.append(make_block(len(blocks)+1, cur)); cur=[line]
        else: cur.append(line)
    if cur: blocks.append(make_block(len(blocks)+1, cur))
    return blocks

# =========================================================
# SECTIONS
# =========================================================
def anchor(block: BlockRecord, idx: int, total: int) -> tuple[str, str]:
    f=block.features["first_line_features"]; pos=idx/max(total,1); s=block.first_line
    if f["noise_like"]: return "", ""
    if f["title_like"] and pos<0.15: return "DOCUMENT_TITLE", "title_like_near_start"
    if f["subject_like"] and pos<0.25: return "DOCUMENT_SUBJECT", "subject_like_near_start"
    if chapter(s): return "MAJOR_STRUCTURAL", marker_kind(s)
    if article(s) or numbered(s) or decimal(s): return "MAIN_UNIT", marker_kind(s)
    if f["footer_section_like"] and pos>0.45: return "FOOTER_SECTION", "footer_section"
    if f["signature_like"] and pos>0.55: return "SIGNATURE_BLOCK", "signature_block"
    return "", ""

def build_sections(blocks: list[BlockRecord]) -> list[SectionRecord]:
    sections=[]; cur=[]; reason="first_section"; total=len(blocks)
    def flush():
        nonlocal cur, reason
        if not cur: return
        sections.append(SectionRecord(len(sections)+1, [b.block_id for b in cur], cur[0].block_id, cur[-1].block_id, cur[0].start_line_id, cur[-1].end_line_id, cur[0].first_line, reason, sum(b.features["char_count"] for b in cur)))
        cur=[]
    for i,b in enumerate(blocks):
        chars=sum(x.features["char_count"] for x in cur)
        a,why=anchor(b,i,total)
        start = False
        if not cur: start=True; reason=why or "first_section"
        elif len(cur)>=MD_SECTION_MAX_BLOCKS or chars+b.features["char_count"]>MD_SECTION_MAX_CHARS: start=True; why="size_limit"
        elif a in {"DOCUMENT_TITLE","MAJOR_STRUCTURAL","MAIN_UNIT","FOOTER_SECTION","SIGNATURE_BLOCK"}: start=True
        if start and cur:
            flush(); reason=why or "anchor"; cur=[b]
        else:
            cur.append(b)
    flush()
    return sections


# =========================================================
# STRUCTURAL SIGNALS + SEMANTIC CHUNKING
# =========================================================

def _parse_numbering(s: str) -> tuple[str | None, int]:
    """Extract numbering string and its level from text.

    Returns (numbering_str, level) or (None, 0).
    Level: 1=chapter/article, 2=numbered, 3=decimal sub, 4=lettered sub.
    """
    s = s.strip()
    # Chapter markers
    m = re.match(r"^(PHẦN|CHƯƠNG|MỤC|TIỂU\s+MỤC)", s, re.I)
    if m:
        return m.group(0), 1
    # Article: Điều 1.
    m = re.match(r"^(Điều\s+\d+[.:]?\s*)", s, re.I)
    if m:
        return m.group(1).strip(), 2
    # Decimal: 1.1.1 or 1.1.1)
    m = re.match(r"^(\d+(?:\.\d+)+[.)]?\s*)", s)
    if m:
        depth = m.group(1).count(".")
        return m.group(1).strip(), min(depth + 1, 4)
    # Numbered: 1. or 1)
    m = re.match(r"^(\d+[.)]\s*)", s)
    if m:
        return m.group(1).strip(), 2
    # Roman: I. or IV)
    m = re.match(r"^([IVXLCDM]+[.)]\s*)", s, re.I)
    if m:
        return m.group(1).strip(), 3
    # Lettered: A. or a)
    m = re.match(r"^([A-Za-zÀ-ỹĐđ][.)]\s*)", s, re.I)
    if m:
        return m.group(1).strip(), 4
    return None, 0


def extract_structural_signals(blocks: list[BlockRecord]) -> list[dict[str, Any]]:
    """Detect structural signals for each block as evidence (not decisions).

    These signals are used to build chunks, inform LLM, and validate LLM output.
    """
    result: list[dict[str, Any]] = []
    for i, b in enumerate(blocks):
        s = b.first_line
        f = b.features
        fl = f.get("first_line_features", {})
        numbering_str, numbering_level = _parse_numbering(s)
        result.append({
            "block_id": b.block_id,
            "numbering": numbering_str,
            "numbering_level": numbering_level,
            "marker_kind": marker_kind(s),
            "bullet": dash_bullet(s),
            "article": article(s),
            "chapter": chapter(s),
            "all_caps": title_like(s),
            "short_line": f.get("char_count", 999) < 80,
            "ends_period": bool(re.search(r"[.!?…]\s*$", s.strip())),
            "continuation": continuation(s),
            "incomplete_prev": prev_invites(blocks[i - 1].first_line) if i > 0 else False,
            "noise_like": noise_like(s),
            "metadata_like": metadata_like(s),
            "footer_like": footer_section_like(s),
            "signature_like": signature_like(s),
            "subject_like": subject_like(s),
            "line_count": f.get("line_count", 1),
            "char_count": f.get("char_count", 0),
        })
    return result


def _chunk_signals_summary(signals: list[dict]) -> dict[str, Any]:
    """Aggregate signals for a chunk from its block signals."""
    if not signals:
        return {}
    has_numbering = any(s["numbering"] for s in signals)
    numbering_level = min((s["numbering_level"] for s in signals if s["numbering_level"] > 0), default=0)
    return {
        "has_numbering": has_numbering,
        "numbering_level": numbering_level,
        "has_article": any(s["article"] for s in signals),
        "has_chapter": any(s["chapter"] for s in signals),
        "is_all_caps": any(s["all_caps"] for s in signals),
        "is_short": all(s["short_line"] for s in signals),
        "ends_period": signals[-1]["ends_period"] if signals else False,
        "is_continuation": signals[0]["continuation"] if signals else False,
        "char_count": sum(s["char_count"] for s in signals),
        "block_count": len(signals),
    }


def _should_start_new_chunk(
    current_signals: list[dict],
    current_chars: int,
    new_signal: dict,
    new_block_idx: int,
) -> bool:
    """Decide if a new block should start a new chunk."""
    if not current_signals:
        return False
    # Size limit
    if current_chars + new_signal["char_count"] > MD_LLM_MAX_CHUNK_CHARS:
        return True
    if len(current_signals) >= MD_LLM_MAX_BLOCKS_PER_CHUNK:
        return True
    # Structural anchor triggers new chunk
    if new_signal["noise_like"] or new_signal["metadata_like"]:
        return True
    if new_signal["footer_like"] or new_signal["signature_like"]:
        return True
    # Same-level marker change triggers new chunk
    if new_signal["numbering"] and current_signals:
        # Find the first numbering in current chunk
        chunk_numbering_level = min(
            (s["numbering_level"] for s in current_signals if s["numbering_level"] > 0),
            default=0,
        )
        if new_signal["numbering_level"] > 0 and chunk_numbering_level > 0:
            # Same or higher level marker → start new chunk
            if new_signal["numbering_level"] <= chunk_numbering_level:
                return True
    # Chapter/subject always starts new chunk
    if new_signal["chapter"] or new_signal["subject_like"]:
        return True
    # All-caps title-like near start → new chunk
    if new_signal["all_caps"] and current_signals and not current_signals[0]["all_caps"]:
        return True
    return False


def build_semantic_chunks(
    blocks: list[BlockRecord],
    signals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Group blocks into semantic chunks for batched LLM recognition.

    Each chunk contains consecutive blocks that belong together logically.
    A new chunk starts when a structural boundary is detected.
    """
    if not blocks:
        return []

    chunks: list[dict[str, Any]] = []
    current_blocks: list[int] = []  # block_ids
    current_signals: list[dict] = []
    current_texts: list[str] = []
    current_chars = 0

    def flush():
        nonlocal current_blocks, current_signals, current_texts, current_chars
        if not current_blocks:
            return
        chunk_id = f"c{len(chunks) + 1}"
        # First block's first line as candidate header
        first_block = next(b for b in blocks if b.block_id == current_blocks[0])
        candidate_header = first_block.first_line
        text = "\n".join(current_texts)
        chunk_signals = _chunk_signals_summary(current_signals)

        # Context before: last block before this chunk
        before_idx = blocks.index(first_block) - 1
        context_before = ""
        if before_idx >= 0:
            context_before = clip(blocks[before_idx].text, MD_LLM_CONTEXT_BEFORE_CHARS)

        chunks.append({
            "chunk_id": chunk_id,
            "source_block_ids": list(current_blocks),
            "text": text,
            "candidate_header": candidate_header,
            "python_signals": chunk_signals,
            "context_before": context_before,
            "context_after": "",  # filled after all chunks built
        })
        current_blocks = []
        current_signals = []
        current_texts = []
        current_chars = 0

    for i, (block, sig) in enumerate(zip(blocks, signals)):
        if _should_start_new_chunk(current_signals, current_chars, sig, i):
            flush()
        current_blocks.append(block.block_id)
        current_signals.append(sig)
        current_texts.append(block.text)
        current_chars += sig["char_count"]

    flush()

    # Fill context_after
    for i, chunk in enumerate(chunks):
        if i + 1 < len(chunks):
            chunk["context_after"] = clip(
                chunks[i + 1]["candidate_header"], MD_LLM_CONTEXT_AFTER_CHARS
            )

    return chunks


# =========================================================
# LLM PROMPTS + SCHEMAS
# =========================================================
JSON_RULES = "/no_think\nReturn exactly one valid JSON object. No markdown. No reasoning. No <think>. No extra fields."

RECOGNITION_PROMPT = """Analyze these chunks from a Vietnamese administrative document.
For each chunk, classify its role, decide if it should become a Markdown heading,
and provide a short summary.

Allowed roles: TITLE, HEADING, BODY, NOISE, REVIEW
Allowed decisions: KEEP, MERGE_PREVIOUS, MARK_NOISE, REVIEW

Rules:
- TITLE: document title, usually all-caps or near the top.
- HEADING: section heading with numbering (1., 1.1, I., A., etc.) or structural marker.
- BODY: regular content paragraph.
- NOISE: page header/footer, OCR noise, page number, separator.
- REVIEW: use when unsure.
- KEEP: chunk is fine as-is.
- MERGE_PREVIOUS: chunk should be merged with the previous chunk (e.g., continuation).
- MARK_NOISE: chunk is noise and should be removed from output.
- REVIEW: need human review.
- is_node=true only for TITLE and HEADING chunks.
- level=1 for document title, level=2 for major sections, level=3 for articles/numbered units, level=4 for lettered sub-units.
- summary: 1 sentence, max 40 Vietnamese words, describing what the chunk is about.
- risk_flags: list any concerns (possible_heading, possible_body, possible_continuation, possible_noise, unclear_level, header_content_mismatch, numbering_level_mismatch).
- If unsure about anything, choose REVIEW.

Return format:
{
  "chunks": [
    {
      "chunk_id": "c1",
      "source_block_ids": [1, 2, 3],
      "role": "HEADING",
      "is_node": true,
      "header": "1. Tang cuong cong tac lanh dao",
      "level": 2,
      "summary": "Section yeu cau tang cuong lanh dao, chi dao va phoi hop.",
      "decision": "KEEP",
      "risk_flags": [],
      "reason": "Chunk starts with a clear numbered heading."
    }
  ],
  "document_warnings": []
}""".strip()

RECOGNITION_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "recognition_response",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "chunks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "chunk_id": {"type": "string"},
                            "source_block_ids": {"type": "array", "items": {"type": "integer"}},
                            "role": {"type": "string"},
                            "is_node": {"type": "boolean"},
                            "header": {"type": "string"},
                            "level": {"type": "integer"},
                            "summary": {"type": "string"},
                            "decision": {"type": "string"},
                            "risk_flags": {"type": "array", "items": {"type": "string"}},
                            "reason": {"type": "string"},
                        },
                        "required": ["chunk_id", "source_block_ids", "role", "is_node", "header", "level", "summary", "decision", "risk_flags", "reason"],
                    },
                },
                "document_warnings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "type": {"type": "string"},
                            "chunk_ids": {"type": "array", "items": {"type": "string"}},
                            "risk_flags": {"type": "array", "items": {"type": "string"}},
                            "reason": {"type": "string"},
                        },
                        "required": ["type", "chunk_ids", "risk_flags", "reason"],
                    },
                },
            },
            "required": ["chunks", "document_warnings"],
        },
    },
}

GLOBAL_REVIEW_PROMPT = """Review this document structure from a Vietnamese administrative document.
You are given headers, levels, summaries, and Python-detected warnings.

Your job: confirm or flag issues. You can only suggest:
- KEEP: confirmed correct
- REVIEW: needs human review
- MERGE_PREVIOUS: merge this header's chunk with the previous one
- MARK_NOISE: this chunk is noise

You CANNOT create new headers, rewrite headers, delete content, or reorder sections.

Return format:
{
  "reviews": [
    {
      "chunk_id": "c1",
      "suggestion": "KEEP",
      "reason": "Document title is correctly identified."
    }
  ],
  "document_notes": []
}""".strip()

GLOBAL_REVIEW_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "global_review_response",
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
                            "chunk_id": {"type": "string"},
                            "suggestion": {"type": "string"},
                            "reason": {"type": "string"},
                        },
                        "required": ["chunk_id", "suggestion", "reason"],
                    },
                },
                "document_notes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "type": {"type": "string"},
                            "chunk_ids": {"type": "array", "items": {"type": "string"}},
                            "reason": {"type": "string"},
                        },
                        "required": ["type", "chunk_ids", "reason"],
                    },
                },
            },
            "required": ["reviews", "document_notes"],
        },
    },
}

def block_payload(b: BlockRecord) -> dict[str,Any]:
    f=b.features["first_line_features"]
    return {"block_id":b.block_id,"lines":[b.start_line_id,b.end_line_id],"first":clip(b.first_line,120),"text":clip(b.text,MD_BLOCK_TEXT_CHARS),"features":f}

def ensure_prompt(prompt: str) -> str:
    if len(prompt) > MD_MAX_PROMPT_CHARS:
        raise ValueError(f"Prompt too long: {len(prompt)} chars > {MD_MAX_PROMPT_CHARS}")
    return prompt

def outline_prompt(blocks: list[BlockRecord], section: SectionRecord) -> str:
    payload = {
        "section": asdict(section),
        "blocks": [block_payload(b) for b in blocks],
    }
    prompt = ensure_prompt(JSON_RULES + "\n" + OUTLINE_PROMPT + "\n" + cj(payload))
    return prompt

class EmptyLLMResponseError(Exception):
    """LLM returned empty or whitespace-only content."""
    pass


class LLMJSONParseError(Exception):
    """LLM returned content but it could not be parsed as JSON."""
    pass


def client() -> OpenAI: return OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY, timeout=LLM_TIMEOUT_SECONDS)
def retry_json(): return retry(stop=stop_after_attempt(MD_JSON_RETRY_ATTEMPTS), wait=wait_exponential(multiplier=1, min=2, max=30), retry=retry_if_exception_type((EmptyLLMResponseError, LLMJSONParseError, APITimeoutError, APIConnectionError, TimeoutError, ConnectionError, OSError)), reraise=True)

def call_json(c: OpenAI, prompt: str, docid: str, stage: str, secid: int|None, fmt: dict|None) -> dict[str,Any]:
    """Call LLM and return parsed JSON.

    If response_format causes empty response (common with small models),
    automatically retries without response_format.
    """
    @retry_json()
    def _call():
        kw={"model":LLM_MODEL,"messages":[{"role":"user","content":prompt}],"temperature":0,"top_p":0.9,"max_tokens":LLM_MAX_TOKENS,"extra_body":{"think":LLM_THINK,"keep_alive":LLM_KEEP_ALIVE,"options":{"num_ctx":LLM_NUM_CTX,"temperature":0,"top_p":0.9,"top_k":20}}}
        use_fmt = LLM_USE_RESPONSE_FORMAT and fmt
        if use_fmt: kw["response_format"]=fmt
        t0 = time.time()
        resp=c.chat.completions.create(**kw)
        content=resp.choices[0].message.content or ""
        elapsed = time.time() - t0
        if not content.strip() and use_fmt:
            _log(f"LLM empty with response_format for {stage} section={secid}, retrying without")
            kw.pop("response_format", None)
            t0 = time.time()
            resp=c.chat.completions.create(**kw)
            content=resp.choices[0].message.content or ""
            elapsed = time.time() - t0
        if not content.strip():
            _log_llm_call(stage, secid, len(prompt), 0, elapsed, False, "empty_response")
            _save_debug_json(work_dir(docid)/"llm_failures"/f"section_{secid or 0:03d}.{stage}.{int(time.time()*1000)}.json", {"error":"LLM returned empty response","raw_response":"","prompt_preview":prompt[:2500]})
            raise EmptyLLMResponseError(f"LLM returned empty response for {stage} section={secid}")
        try:
            result = extract_json_object(content)
            _log_llm_call(stage, secid, len(prompt), len(content), elapsed, True)
            return result
        except EmptyLLMResponseError:
            raise
        except Exception as e:
            _log_llm_call(stage, secid, len(prompt), len(content), elapsed, False, str(e))
            _save_debug_json(work_dir(docid)/"llm_failures"/f"section_{secid or 0:03d}.{stage}.{int(time.time()*1000)}.json", {"error":str(e),"raw_response":content[:5000],"prompt_preview":prompt[:2500]})
            raise LLMJSONParseError(f"Could not parse JSON from {stage} section={secid}: {str(e)[:100]}")
    return _call()


# =========================================================
# BATCHED LLM RECOGNITION PIPELINE
# =========================================================

# Allowed enum values for normalization
_ALLOWED_ROLES = {"TITLE", "HEADING", "BODY", "NOISE", "REVIEW"}
_ROLE_NORMALIZE = {
    "heading": "HEADING", "header": "HEADING", "subheading": "HEADING",
    "section_heading": "HEADING", "sub_heading": "HEADING",
    "title": "TITLE", "document_title": "TITLE",
    "paragraph": "BODY", "content": "BODY", "body": "BODY", "text": "BODY",
    "body_detail": "BODY", "preamble": "BODY", "background": "BODY",
    "noise": "NOISE", "footer": "NOISE", "page_number": "NOISE",
    "header_footer": "NOISE", "separator": "NOISE", "page_header": "NOISE",
    "review": "REVIEW", "unknown": "REVIEW",
}
_ALLOWED_DECISIONS = {"KEEP", "MERGE_PREVIOUS", "MARK_NOISE", "REVIEW"}
_DECISION_NORMALIZE = {
    "keep": "KEEP", "stay": "KEEP", "no_change": "KEEP",
    "merge": "MERGE_PREVIOUS", "merge_with_previous": "MERGE_PREVIOUS",
    "merge_previous": "MERGE_PREVIOUS", "merge_with_prev": "MERGE_PREVIOUS",
    "noise": "MARK_NOISE", "mark_noise": "MARK_NOISE", "remove": "MARK_NOISE",
    "review": "REVIEW",
}
_ALLOWED_RISK_FLAGS = {
    "possible_heading", "possible_body", "possible_continuation",
    "possible_noise", "unclear_level", "header_content_mismatch",
    "numbering_level_mismatch",
}


def normalize_llm_output(raw_result: dict[str, Any]) -> dict[str, Any]:
    """Normalize LLM output enums. Small models may return near-correct values."""
    normalized = dict(raw_result)
    chunks = normalized.get("chunks", [])
    for chunk in chunks:
        # Normalize role
        raw_role = str(chunk.get("role", "REVIEW")).strip().lower()
        chunk["role"] = _ROLE_NORMALIZE.get(raw_role, "REVIEW")
        # Normalize decision
        raw_decision = str(chunk.get("decision", "REVIEW")).strip().lower()
        chunk["decision"] = _DECISION_NORMALIZE.get(raw_decision, "REVIEW")
        # Normalize level
        try:
            level = int(chunk.get("level", 3))
        except (ValueError, TypeError):
            level = 3
        if chunk["role"] == "TITLE":
            level = 1
        elif chunk["role"] == "NOISE":
            level = 0
        chunk["level"] = max(1 if chunk["role"] != "NOISE" else 0, min(MD_MAX_HEADING_LEVEL, level))
        # Normalize risk_flags
        raw_flags = chunk.get("risk_flags", [])
        if isinstance(raw_flags, list):
            chunk["risk_flags"] = [f for f in raw_flags if isinstance(f, str) and f in _ALLOWED_RISK_FLAGS]
        else:
            chunk["risk_flags"] = []
        # Normalize is_node
        chunk["is_node"] = bool(chunk.get("is_node", False))
        if chunk["role"] in ("TITLE", "HEADING"):
            chunk["is_node"] = True
        elif chunk["role"] in ("BODY", "NOISE"):
            chunk["is_node"] = False
    return normalized


def _chunk_has_numbering(chunk: dict) -> bool:
    """Check if chunk's candidate_header starts with a clear numbering pattern."""
    header = chunk.get("candidate_header", "").strip()
    return bool(_parse_numbering(header)[0])


def _chunk_looks_like_heading(chunk: dict) -> bool:
    """Check if chunk looks like a heading based on signals."""
    signals = chunk.get("python_signals", {})
    s = chunk.get("candidate_header", "").strip()
    if signals.get("has_numbering"):
        return True
    if signals.get("is_all_caps"):
        return True
    if signals.get("has_article") or signals.get("has_chapter"):
        return True
    if title_like(s):
        return True
    if len(s.split()) <= 12 and not signals.get("ends_period"):
        return True
    return False


def compute_trust_score(
    chunk: dict,
    llm_decision: str,
    signals: dict[str, Any],
) -> tuple[str, str]:
    """Compute trust level from structural evidence. Returns (trust, reason).

    Trust levels: "accept", "flag_review", "reject"
    """
    has_numbering = signals.get("has_numbering", False)
    numbering_level = signals.get("numbering_level", 0)
    is_continuation = signals.get("is_continuation", False)
    chunk_has_heading_look = _chunk_looks_like_heading(chunk)

    # LLM returns REVIEW → always flag
    if llm_decision == "REVIEW":
        return "flag_review", "LLM chose REVIEW"

    # MERGE_PREVIOUS: conservative check
    if llm_decision == "MERGE_PREVIOUS":
        if has_numbering:
            return "reject", "Chunk has clear numbering — reject merge"
        if chunk_has_heading_look:
            return "reject", "Chunk looks like heading — reject merge"
        return "accept", "Merge approved: no numbering, not heading-like"

    # MARK_NOISE: check noise signals
    if llm_decision == "MARK_NOISE":
        if signals.get("noise_like"):
            return "accept", "Noise signal matches LLM decision"
        return "flag_review", "LLM says noise but no noise signal"

    # KEEP: generally trust LLM
    if llm_decision == "KEEP":
        return "accept", "KEEP with no conflicts"

    return "flag_review", f"Unknown decision: {llm_decision}"


def validate_llm_decisions(
    chunks: list[dict],
    signals_map: dict[int, dict],
    normalized: dict[str, Any],
) -> list[dict[str, Any]]:
    """Validate each LLM decision against structural signals.

    Returns list of validated items with trust scores and final decisions.
    """
    validated: list[dict[str, Any]] = []
    llm_chunks = {c["chunk_id"]: c for c in normalized.get("chunks", [])}

    for chunk in chunks:
        cid = chunk["chunk_id"]
        llm = llm_chunks.get(cid, {})
        llm_decision = llm.get("decision", "REVIEW")
        llm_role = llm.get("role", "REVIEW")

        # Get signals for blocks in this chunk
        chunk_signals = [signals_map.get(bid, {}) for bid in chunk["source_block_ids"]]
        agg = _chunk_signals_summary(chunk_signals)

        trust, reason = compute_trust_score(chunk, llm_decision, agg)

        final_decision = llm_decision
        applied = False

        if trust == "accept":
            applied = True
        elif trust == "reject":
            final_decision = "KEEP"  # downgrade to KEEP
            applied = True
            reason += " → downgraded to KEEP"
        else:  # flag_review
            final_decision = "REVIEW"
            applied = False

        # For HEADING: check numbering consistency
        level_correction = None
        if llm_role == "HEADING" and agg.get("has_numbering") and agg.get("numbering_level", 0) > 0:
            expected_level = agg["numbering_level"]
            llm_level = llm.get("level", 3)
            if llm_level != expected_level:
                level_correction = expected_level
                reason += f" → level corrected {llm_level}→{expected_level} (numbering match)"

        validated.append({
            "chunk_id": cid,
            "source_block_ids": chunk["source_block_ids"],
            "llm_raw": {"role": llm.get("role"), "decision": llm.get("decision"), "level": llm.get("level")},
            "normalized_role": llm_role,
            "normalized_decision": llm_decision,
            "final_decision": final_decision,
            "final_role": llm_role,
            "final_level": level_correction or llm.get("level", 3),
            "is_node": llm.get("is_node", False),
            "header": llm.get("header", ""),
            "summary": llm.get("summary", ""),
            "risk_flags": llm.get("risk_flags", []),
            "trust": trust,
            "reason": reason,
            "applied": applied,
        })

    return validated


def _build_chunk_payload_for_llm(chunk: dict) -> dict:
    """Build a compact payload for a single chunk to send to LLM."""
    sig = chunk.get("python_signals", {})
    # Only send essential signals to save prompt space
    compact_sig = {
        "has_numbering": sig.get("has_numbering", False),
        "numbering_level": sig.get("numbering_level", 0),
        "is_all_caps": sig.get("is_all_caps", False),
        "is_short": sig.get("is_short", False),
        "ends_period": sig.get("ends_period", False),
        "is_continuation": sig.get("is_continuation", False),
        "char_count": sig.get("char_count", 0),
    }
    return {
        "chunk_id": chunk["chunk_id"],
        "source_block_ids": chunk["source_block_ids"],
        "candidate_header": clip(chunk["candidate_header"], 80),
        "text": clip(chunk["text"], 150),
        "python_signals": compact_sig,
        "context_before": clip(chunk.get("context_before", ""), 30),
        "context_after": clip(chunk.get("context_after", ""), 30),
    }


def llm_recognize_chunks(
    c: OpenAI,
    docid: str,
    chunks: list[dict],
) -> dict[str, Any]:
    """Send chunks to LLM for batched recognition.

    Splits into multiple calls if chunks exceed MD_LLM_MAX_CHUNKS_PER_CALL.
    Returns merged normalized result.
    """
    if not chunks:
        return {"chunks": [], "document_warnings": []}

    # Split into batches
    batch_size = MD_LLM_MAX_CHUNKS_PER_CALL
    batches = [chunks[i:i + batch_size] for i in range(0, len(chunks), batch_size)]

    all_chunks: list[dict] = []
    all_warnings: list[dict] = []

    for batch_idx, batch in enumerate(batches):
        payload = {"chunks": [_build_chunk_payload_for_llm(ch) for ch in batch]}
        prompt = ensure_prompt(JSON_RULES + "\n" + RECOGNITION_PROMPT + "\n" + cj(payload))

        t0 = time.time()
        try:
            raw = call_json(c, prompt, docid, "recognition", batch_idx, RECOGNITION_FORMAT)
            elapsed = time.time() - t0
            _log_llm_call("recognition", batch_idx, len(prompt), 0, elapsed, True)
        except Exception as e:
            elapsed = time.time() - t0
            _log_llm_call("recognition", batch_idx, len(prompt), 0, elapsed, False, str(e))
            _log(f"Recognition batch {batch_idx} failed: {e}")
            # Fallback: create REVIEW entries for all chunks in this batch
            for ch in batch:
                all_chunks.append({
                    "chunk_id": ch["chunk_id"],
                    "source_block_ids": ch["source_block_ids"],
                    "role": "REVIEW",
                    "is_node": False,
                    "header": ch["candidate_header"],
                    "level": 3,
                    "summary": "LLM recognition failed — needs manual review.",
                    "decision": "REVIEW",
                    "risk_flags": [],
                    "reason": f"LLM call failed: {str(e)[:100]}",
                })
            continue

        # Normalize
        normalized = normalize_llm_output(raw)
        all_chunks.extend(normalized.get("chunks", []))
        all_warnings.extend(normalized.get("document_warnings", []))

    return {"chunks": all_chunks, "document_warnings": all_warnings}


def llm_global_review(
    c: OpenAI,
    docid: str,
    validated: list[dict],
    warnings: list[dict],
) -> dict[str, Any]:
    """Run global review: LLM sees all headers + levels + summaries."""
    headers = []
    for v in validated:
        headers.append({
            "chunk_id": v["chunk_id"],
            "header": clip(v.get("header", ""), 80),
            "level": v.get("final_level", 3),
            "role": v.get("final_role", "REVIEW"),
            "summary": clip(v.get("summary", ""), 50),
        })

    payload = {
        "document_headers": headers,
        "total_chunks": len(validated),
    }
    prompt = ensure_prompt(JSON_RULES + "\n" + GLOBAL_REVIEW_PROMPT + "\n" + cj(payload))

    t0 = time.time()
    try:
        raw = call_json(c, prompt, docid, "global_review", None, GLOBAL_REVIEW_FORMAT)
        elapsed = time.time() - t0
        _log_llm_call("global_review", None, len(prompt), 0, elapsed, True)
        return raw
    except Exception as e:
        elapsed = time.time() - t0
        _log_llm_call("global_review", None, len(prompt), 0, elapsed, False, str(e))
        _log(f"Global review failed: {e}")
        return {"reviews": [], "document_notes": []}


def apply_safe_decisions(
    chunks: list[dict],
    validated: list[dict],
    byid: dict[int, BlockRecord],
) -> list[OutlineNode]:
    """Convert validated decisions into OutlineNodes.

    Only applied decisions become nodes. MERGE_PREVIOUS modifies previous chunk's blocks.
    """
    # First pass: collect which blocks are merged into previous
    merged_into: dict[int, int] = {}  # block_id -> previous chunk's first block_id
    for v in validated:
        if v["final_decision"] == "MERGE_PREVIOUS" and v["applied"]:
            # Find previous chunk's last block_id
            chunk_idx = next(
                (i for i, vv in enumerate(validated) if vv["chunk_id"] == v["chunk_id"]),
                -1,
            )
            if chunk_idx > 0:
                prev = validated[chunk_idx - 1]
                prev_last_block = prev["source_block_ids"][-1] if prev["source_block_ids"] else None
                if prev_last_block is not None:
                    for bid in v["source_block_ids"]:
                        merged_into[bid] = prev_last_block

    # Second pass: build OutlineNodes from applied HEADING/TITLE decisions
    nodes: list[OutlineNode] = []
    for v in validated:
        if not v["applied"]:
            continue
        if not v.get("is_node", False):
            continue
        if v["final_decision"] == "MARK_NOISE":
            continue
        # Use first block of the chunk as the heading node
        first_bid = v["source_block_ids"][0] if v["source_block_ids"] else None
        if first_bid is None or first_bid in merged_into:
            continue
        block = byid.get(first_bid)
        if block is None:
            continue

        level = max(1, min(MD_MAX_HEADING_LEVEL, v.get("final_level", 3)))
        role = v.get("final_role", "BODY")

        nodes.append(OutlineNode(
            block_id=block.block_id,
            line_id=block.start_line_id,
            level=level,
            first_line=block.first_line,
            line_ids=block.line_ids,
            role=role,
            section_id=None,
        ))

    return sorted(nodes, key=lambda n: n.line_id)


def apply_global_review_safely(
    review: dict[str, Any],
    nodes: list[OutlineNode],
    byid: dict[int, BlockRecord],
) -> list[OutlineNode]:
    """Apply global review suggestions safely.

    Only KEEP, MARK_NOISE are auto-applied. MERGE_PREVIOUS needs conservative check.
    """
    reviews = review.get("reviews", [])
    if not reviews:
        return nodes

    nodes_by_block = {n.block_id: n for n in nodes}
    changes = 0

    for r in reviews:
        suggestion = str(r.get("suggestion", "KEEP")).strip().upper()
        suggestion = _DECISION_NORMALIZE.get(suggestion.lower(), suggestion)

        if suggestion == "MARK_NOISE":
            # Find and remove the node
            cid = r.get("chunk_id", "")
            # Match by chunk_id format: extract block info if possible
            # For now, log the suggestion
            _log(f"Global review MARK_NOISE for {cid}: {r.get('reason', '')}")
            changes += 1

        elif suggestion == "REVIEW":
            _log(f"Global review flags REVIEW for {r.get('chunk_id', '')}: {r.get('reason', '')}")
            changes += 1

    if changes > 0:
        _log(f"Global review: {changes} suggestions processed")

    return nodes


def export_metadata(
    document_id: str,
    chunks: list[dict],
    validated: list[dict],
) -> Path:
    """Export metadata.json with section info."""
    sections = []
    for v in validated:
        sections.append({
            "chunk_id": v["chunk_id"],
            "source_block_ids": v["source_block_ids"],
            "header": v.get("header", ""),
            "level": v.get("final_level", 3),
            "role": v.get("final_role", "REVIEW"),
            "decision": v.get("final_decision", "REVIEW"),
            "summary": v.get("summary", ""),
        })
    data = {"document_id": document_id, "sections": sections}
    path = work_dir(document_id) / "metadata.json"
    save_json(path, data)
    return path


def export_audit_log(
    document_id: str,
    validated: list[dict],
    llm_calls: list[dict],
    warnings: list[dict],
) -> Path:
    """Export audit.json with full decision trail."""
    entries = []
    rejected = []
    for v in validated:
        entry = {
            "chunk_id": v["chunk_id"],
            "llm_raw": v.get("llm_raw", {}),
            "normalized": {
                "role": v.get("normalized_role"),
                "decision": v.get("normalized_decision"),
            },
            "final_decision": v.get("final_decision"),
            "trust": v.get("trust"),
            "trust_reason": v.get("reason", ""),
            "applied": v.get("applied", False),
        }
        if v.get("applied"):
            entries.append(entry)
        else:
            rejected.append({**entry, "rejected_reason": v.get("reason", "")})

    data = {
        "document_id": document_id,
        "entries": entries,
        "rejected": rejected,
        "llm_calls": llm_calls,
        "document_warnings": warnings,
    }
    path = work_dir(document_id) / "audit.json"
    save_json(path, data)
    return path


# =========================================================
# PARSE + FALLBACKS
# =========================================================
ROLES={"DOCUMENT_TITLE","DOCUMENT_SUBJECT","METADATA","PREAMBLE","BACKGROUND","LEGAL_BASIS","SECTION_INTRO","MAIN_CONTENT_UNIT","SUB_CONTENT_UNIT","BODY_DETAIL","LIST_ITEM","ADDRESSEE_ITEM","FOOTER_SECTION","FOOTER_ITEM","SIGNATURE_BLOCK","APPENDIX_SECTION","NOISE","UNKNOWN"}
NON_NODE={"METADATA","PREAMBLE","BODY_DETAIL","LIST_ITEM","ADDRESSEE_ITEM","FOOTER_ITEM","SIGNATURE_BLOCK","NOISE","UNKNOWN"}
ROUGH_LEVEL={"ROOT":1,"MAJOR":2,"MAIN":3,"SUB":4}
ROLE_LEVEL={"DOCUMENT_TITLE":1,"DOCUMENT_SUBJECT":2,"FOOTER_SECTION":2,"APPENDIX_SECTION":2,"SECTION_INTRO":2,"MAIN_CONTENT_UNIT":3,"SUB_CONTENT_UNIT":4}

def py_role(b: BlockRecord, i: int, total: int, in_footer=False) -> str:
    f=b.features["first_line_features"]; pos=i/max(total,1); s=b.first_line
    if f["noise_like"]: return "NOISE"
    if f["footer_section_like"] and pos>0.45: return "FOOTER_SECTION"
    if in_footer: return "FOOTER_ITEM" if dash_bullet(s) or b.features["line_count"]<=2 else "BODY_DETAIL"
    if f["signature_like"] and pos>0.55: return "SIGNATURE_BLOCK"
    if f["metadata_like"] and pos<0.25: return "METADATA"
    if f["title_like"] and pos<0.2: return "DOCUMENT_TITLE"
    if f["subject_like"] and pos<0.35: return "DOCUMENT_SUBJECT"
    if chapter(s) or article(s) or numbered(s) or decimal(s) or roman(s): return "MAIN_CONTENT_UNIT"
    if lettered(s): return "SUB_CONTENT_UNIT"
    if dash_bullet(s): return "LIST_ITEM"
    if s.strip().endswith(":"): return "SECTION_INTRO"
    return "BODY_DETAIL"

def parse_roles(obj, byid, blocks):
    out={}; raw=obj.get("roles",[])
    if isinstance(raw,list):
        for it in raw:
            if not isinstance(it,dict): continue
            try: bid=int(it.get("block_id"))
            except Exception: continue
            if bid not in byid: continue
            role=str(it.get("role","UNKNOWN")).strip().upper()
            out[bid]=BlockRole(bid, role if role in ROLES else "UNKNOWN")
    in_footer=False
    total=len(blocks)
    for i,b in enumerate(blocks):
        base=out.get(b.block_id, BlockRole(b.block_id,"UNKNOWN")).role
        pr=py_role(b,i,total,in_footer)
        if pr in {"NOISE","FOOTER_SECTION","FOOTER_ITEM","SIGNATURE_BLOCK","MAIN_CONTENT_UNIT","SUB_CONTENT_UNIT"}: base=pr
        elif pr=="METADATA" and base in {"UNKNOWN","DOCUMENT_TITLE","MAIN_CONTENT_UNIT"}: base=pr
        elif pr=="DOCUMENT_TITLE" and base in {"UNKNOWN","METADATA","MAIN_CONTENT_UNIT"}: base=pr
        elif pr=="DOCUMENT_SUBJECT" and base in {"UNKNOWN","BODY_DETAIL","MAIN_CONTENT_UNIT"}: base=pr
        elif base=="UNKNOWN": base=pr
        if base=="FOOTER_SECTION": in_footer=True
        out[b.block_id]=BlockRole(b.block_id, base)
    return out

def parse_outline(
    obj: dict[str, Any],
    blocks: list[BlockRecord],
    byid: dict[int, BlockRecord],
    section_id: int,
) -> tuple[dict[int, BlockRole], list[NodeCandidate], list[OutlineNode]]:
    """Parse one-shot outline response.

    LLM returns role + node decision + level in one JSON object.
    Python still overrides strong structural signals and provides fallback nodes.
    """
    block_map = {b.block_id: b for b in blocks}
    total = len(blocks)

    roles: dict[int, BlockRole] = {}
    cands: list[NodeCandidate] = []
    nodes: list[OutlineNode] = []

    raw = obj.get("blocks", [])
    # Handle LLM returning object instead of array
    if isinstance(raw, dict):
        # Convert {"blocks": {block_id: {...}}} to [{"block_id": ..., ...}]
        converted = []
        for key, val in raw.items():
            if isinstance(val, dict):
                try:
                    val["block_id"] = int(key)
                except (ValueError, TypeError):
                    pass
                converted.append(val)
        raw = converted
    if not isinstance(raw, list):
        raw = []

    raw_by_id: dict[int, dict[str, Any]] = {}

    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            bid = int(item.get("block_id"))
        except Exception:
            continue
        if bid in block_map:
            raw_by_id[bid] = item

    in_footer = False

    for i, block in enumerate(blocks):
        raw_item = raw_by_id.get(block.block_id, {})

        role = str(raw_item.get("role", "UNKNOWN")).strip().upper()
        if role not in ROLES:
            role = "UNKNOWN"

        py = py_role(block, i, total, in_footer)

        if py in {
            "NOISE",
            "FOOTER_SECTION",
            "FOOTER_ITEM",
            "SIGNATURE_BLOCK",
            "MAIN_CONTENT_UNIT",
            "SUB_CONTENT_UNIT",
        }:
            role = py
        elif py == "METADATA" and role in {"UNKNOWN", "DOCUMENT_TITLE", "MAIN_CONTENT_UNIT"}:
            role = py
        elif py == "DOCUMENT_TITLE" and role in {"UNKNOWN", "METADATA", "MAIN_CONTENT_UNIT"}:
            role = py
        elif py == "DOCUMENT_SUBJECT" and role in {"UNKNOWN", "BODY_DETAIL", "MAIN_CONTENT_UNIT"}:
            role = py
        elif role == "UNKNOWN":
            role = py

        if role == "FOOTER_SECTION":
            in_footer = True

        roles[block.block_id] = BlockRole(block.block_id, role)

        is_node = bool(raw_item.get("is_node", False))

        if role not in NON_NODE:
            if is_node or role in ROLE_LEVEL or marker_kind(block.first_line):
                rough = (
                    "ROOT" if role == "DOCUMENT_TITLE"
                    else "MAJOR" if role in {
                        "DOCUMENT_SUBJECT",
                        "FOOTER_SECTION",
                        "APPENDIX_SECTION",
                        "SECTION_INTRO",
                    }
                    else "SUB" if role == "SUB_CONTENT_UNIT"
                    else "MAIN"
                )

                cands.append(NodeCandidate(block.block_id, rough, role))

                try:
                    level = int(raw_item.get("level", ROLE_LEVEL.get(role, ROUGH_LEVEL.get(rough, 3))))
                except Exception:
                    level = ROLE_LEVEL.get(role, ROUGH_LEVEL.get(rough, 3))

                tmp = OutlineNode(
                    block_id=block.block_id,
                    line_id=block.start_line_id,
                    level=level,
                    first_line=block.first_line,
                    line_ids=block.line_ids,
                    role=role,
                    section_id=section_id,
                )

                level = structural_level(tmp) or level
                level = max(1, min(MD_MAX_HEADING_LEVEL, level))

                nodes.append(OutlineNode(
                    block_id=block.block_id,
                    line_id=block.start_line_id,
                    level=level,
                    first_line=block.first_line,
                    line_ids=block.line_ids,
                    role=role,
                    section_id=section_id,
                ))

    cands = sorted(cands, key=lambda c: byid[c.block_id].start_line_id)
    nodes = sorted(nodes, key=lambda n: n.line_id)
    return roles, cands, nodes


def py_candidates(blocks, roles):
    out=[]
    for b in blocks:
        role=roles.get(b.block_id,BlockRole(b.block_id,"UNKNOWN")).role
        if role in NON_NODE: continue
        rough="ROOT" if role=="DOCUMENT_TITLE" else "MAJOR" if role in {"DOCUMENT_SUBJECT","FOOTER_SECTION","APPENDIX_SECTION","SECTION_INTRO"} else "SUB" if role=="SUB_CONTENT_UNIT" else "MAIN"
        out.append(NodeCandidate(b.block_id,rough,role))
    return out

def parse_candidates(obj, roles, byid):
    out=[]; seen=set(); raw=obj.get("nodes",[])
    if isinstance(raw,list):
        for it in raw:
            if not isinstance(it,dict): continue
            try: bid=int(it.get("block_id"))
            except Exception: continue
            if bid in seen or bid not in byid: continue
            role=roles.get(bid,BlockRole(bid,"UNKNOWN")).role
            if role in NON_NODE: continue
            rough=str(it.get("rough_level","")).upper().strip()
            if rough not in ROUGH_LEVEL: rough={1:"ROOT",2:"MAJOR",3:"MAIN",4:"SUB"}.get(ROLE_LEVEL.get(role,0),"")
            if rough in ROUGH_LEVEL:
                out.append(NodeCandidate(bid,rough,role)); seen.add(bid)
    return sorted(out,key=lambda c:byid[c.block_id].start_line_id)

def structural_level(n: OutlineNode) -> int|None:
    k=marker_kind(n.first_line)
    if n.role=="DOCUMENT_TITLE": return 1
    if n.role in {"DOCUMENT_SUBJECT","FOOTER_SECTION","APPENDIX_SECTION"}: return 2
    if k in {"PHẦN","CHƯƠNG"}: return 2
    if k in {"MỤC","TIỂU_MỤC","ARTICLE","NUMBER","DECIMAL","ROMAN"}: return 3
    if k=="LETTER": return 4
    return None

def nodes_from_candidates(cands, byid, secid, levels=None):
    levels=levels or {}; nodes=[]
    for c in cands:
        b=byid[c.block_id]; lv=int(levels.get(c.block_id) or ROUGH_LEVEL.get(c.rough_level) or ROLE_LEVEL.get(c.role) or 3)
        tmp=OutlineNode(c.block_id,b.start_line_id,lv,b.first_line,b.line_ids,c.role,secid)
        lv=structural_level(tmp) or lv
        nodes.append(OutlineNode(c.block_id,b.start_line_id,max(1,min(MD_MAX_HEADING_LEVEL,lv)),b.first_line,b.line_ids,c.role,secid))
    return sorted(nodes,key=lambda n:n.line_id)

def parse_levels(obj,cands,byid,secid):
    raw=obj.get("levels",[]); levels={}
    if isinstance(raw,list):
        for it in raw:
            if not isinstance(it,dict): continue
            try: bid=int(it.get("block_id")); lv=int(it.get("level"))
            except Exception: continue
            if 1<=lv<=MD_MAX_HEADING_LEVEL: levels[bid]=lv
    return nodes_from_candidates(cands,byid,secid,levels)

def structural_postprocess(nodes, byid):
    out={n.block_id:n for n in nodes}
    # Add obvious structural headings that LLM missed.
    for b in sorted(byid.values(), key=lambda x:x.start_line_id):
        if b.block_id in out: continue
        k=marker_kind(b.first_line)
        if k in {"ARTICLE","NUMBER","DECIMAL","ROMAN","LETTER"} or chapter(b.first_line) or footer_section_like(b.first_line):
            role="SUB_CONTENT_UNIT" if k=="LETTER" else "MAIN_CONTENT_UNIT"
            if footer_section_like(b.first_line): role="FOOTER_SECTION"
            tmp=OutlineNode(b.block_id,b.start_line_id,3,b.first_line,b.line_ids,role,None)
            lv=structural_level(tmp) or 3
            out[b.block_id]=OutlineNode(b.block_id,b.start_line_id,lv,b.first_line,b.line_ids,role,None)
    has_h1=any(n.level==1 for n in out.values())
    fixed=[]
    for n in sorted(out.values(), key=lambda x:x.line_id):
        lv=structural_level(n) or n.level
        if has_h1 and n.role in {"FOOTER_SECTION","APPENDIX_SECTION"}: lv=max(2,lv)
        fixed.append(OutlineNode(n.block_id,n.line_id,max(1,min(4,lv)),n.first_line,n.line_ids,n.role,n.section_id))
    return fixed

def hierarchical_validation(nodes):
    # local parent-child sibling normalization, no whole-document LLM
    stack=[]; parent_children={None:[]}
    for n in sorted(nodes,key=lambda x:x.line_id):
        while stack and stack[-1].level>=n.level: stack.pop()
        pid=stack[-1].block_id if stack else None
        parent_children.setdefault(pid,[]).append(n); stack.append(n)
    byid={n.block_id:n for n in nodes}
    for kids in parent_children.values():
        kinds=[marker_kind(k.first_line) for k in kids]
        if kinds.count("LETTER")>=2:
            for k in kids:
                if marker_kind(k.first_line)=="LETTER": byid[k.block_id]=OutlineNode(k.block_id,k.line_id,4,k.first_line,k.line_ids,"SUB_CONTENT_UNIT",k.section_id)
        if sum(1 for x in kinds if x in {"NUMBER","ARTICLE","ROMAN","DECIMAL"})>=2:
            for k in kids:
                if marker_kind(k.first_line) in {"NUMBER","ARTICLE","ROMAN","DECIMAL"}: byid[k.block_id]=OutlineNode(k.block_id,k.line_id,3,k.first_line,k.line_ids,"MAIN_CONTENT_UNIT",k.section_id)
    return sorted(byid.values(),key=lambda x:x.line_id)

# =========================================================
# SECTION PROCESSING
# =========================================================
def process_section(
    c: OpenAI,
    docid: str,
    section: SectionRecord,
    blocks: list[BlockRecord],
    byid: dict[int, BlockRecord],
) -> dict[str, Any]:
    secblocks = [byid[i] for i in section.block_ids if i in byid]

    status = "done"
    err = ""

    try:
        obj = call_json(
            c,
            outline_prompt(secblocks, section),
            docid,
            "outline",
            section.section_id,
            OUTLINE_FORMAT,
        )

        roles, cands, nodes = parse_outline(
            obj=obj,
            blocks=secblocks,
            byid=byid,
            section_id=section.section_id,
        )

    except Exception as e:
        status = "done_with_fallback"
        err = f"outline: {e}"
        _log(f"Section {section.section_id} outline fallback: {e}")

        roles = parse_roles({}, {}, secblocks)
        cands = py_candidates(secblocks, roles)
        nodes = nodes_from_candidates(cands, byid, section.section_id)

    if not cands:
        cands = py_candidates(secblocks, roles)

    if not nodes:
        nodes = nodes_from_candidates(cands, byid, section.section_id)

    # structural_postprocess removed here — runs once after merge at line 968

    return {
        "section_id": section.section_id,
        "status": status,
        "error": err,
        "roles": list(roles.values()),
        "candidates": cands,
        "outline": nodes,
    }

# =========================================================
# RENDER
# =========================================================
def render_markdown(lines: list[LineRecord], nodes: list[OutlineNode]) -> str:
    byline = {n.line_id: n for n in nodes}
    out: list[str] = []

    for line in lines:
        n = byline.get(line.line_id)

        if n:
            if out and out[-1] != "":
                out.append("")
            out.append("#" * n.level + " " + line.text)
            out.append("")
        else:
            out.append(line.text)

    return "\n".join(out).rstrip() + "\n"

def render_section(lines, sec, nodes):
    return render_markdown([l for l in lines if sec.start_line_id<=l.line_id<=sec.end_line_id], [n for n in nodes if sec.start_line_id<=n.line_id<=sec.end_line_id])

def validate_lossless(lines: list[LineRecord], md: str) -> dict[str, Any]:
    plain_lines = {
        re.sub(r"^#{1,6}\s+", "", line).strip()
        for line in md.splitlines()
        if line.strip()
    }

    missing = [
        asdict(line)
        for line in lines
        if line.text.strip() and line.text.strip() not in plain_lines
    ]

    return {
        "input_line_count": len(lines),
        "rendered_line_count": len(plain_lines),
        "missing_count": len(missing),
        "missing_lines": missing[:300],
    }

def build_tree_nodes(nodes: list[OutlineNode]) -> list[dict[str, Any]]:
    stack: list[OutlineNode] = []
    out: list[dict[str, Any]] = []

    for n in sorted(nodes, key=lambda x: x.line_id):
        level = max(1, min(MD_MAX_HEADING_LEVEL, n.level))
        n = OutlineNode(
            n.block_id,
            n.line_id,
            level,
            n.first_line,
            n.line_ids,
            n.role,
            n.section_id,
        )

        while stack and stack[-1].level >= n.level:
            stack.pop()

        parent = stack[-1] if stack else None

        out.append({
            "block_id": n.block_id,
            "line_id": n.line_id,
            "level": n.level,
            "parent_block_id": parent.block_id if parent else None,
            "parent_line_id": parent.line_id if parent else None,
            "text": n.first_line,
        })

        stack.append(n)

    return out

# =========================================================
# MAIN
# =========================================================
def generate_markdown_doc(document_id: str, normalized_path: str|Path|None=None) -> Path:
    """Main pipeline: normalized text → Markdown via batched LLM recognition.

    Flow:
    1. Python segment → lines, blocks
    2. Python detect signals → structural signals per block
    3. Python build chunks → semantic chunks with context
    4. LLM recognize → batched classification (1-2 calls)
    5. Python normalize → enum normalization
    6. Python validate → trust scoring, safe apply
    7. LLM global review → review headers + summaries (1 call)
    8. Python apply review → safe apply global review
    9. Build tree → structural_postprocess + hierarchical_validation
    10. Render markdown → render_markdown
    11. Export metadata/audit
    """
    global _log_file
    start = time.time()
    ensure_dirs(document_id)
    inp = Path(normalized_path) if normalized_path else NORMALIZED_DIR / f"{document_id}.txt"
    outp = MARKDOWN_DIR / f"{document_id}.md"
    if not inp.exists():
        raise FileNotFoundError(f"Normalized text not found: {inp}")
    log_path = work_dir(document_id) / "pipeline.log"
    _log_file = open(log_path, "a", encoding="utf-8")
    llm_calls_log: list[dict] = []

    try:
        _log_stage("START", input=str(inp), output=str(outp), model=LLM_MODEL, mode=MD_PIPELINE_MODE)
        _log_stage("CONFIG", **effective_config())
        root = work_dir(document_id)

        # Step 1: Python segment
        t0 = time.time()
        lines = read_lines(inp)
        blocks = build_blocks(lines)
        byid = {b.block_id: b for b in blocks}
        _log_stage("PARSE", lines=len(lines), blocks=len(blocks), duration=f"{time.time()-t0:.2f}s")
        if SAVE_DEBUG_FILES:
            save_json(root/"lines.json", [asdict(x) for x in lines])
            save_json(root/"blocks.json", [asdict(x) for x in blocks])

        # Step 2: Python detect signals
        t0 = time.time()
        block_signals = extract_structural_signals(blocks)
        signals_map = {s["block_id"]: s for s in block_signals}
        _log_stage("SIGNALS", count=len(block_signals), duration=f"{time.time()-t0:.2f}s")
        if SAVE_DEBUG_FILES:
            save_json(root/"signals.json", block_signals)

        # Step 3: Python build chunks
        t0 = time.time()
        chunks = build_semantic_chunks(blocks, block_signals)
        _log_stage("CHUNKS", count=len(chunks), duration=f"{time.time()-t0:.2f}s")
        if SAVE_DEBUG_FILES:
            save_json(root/"chunks.json", chunks)

        update_progress(document_id, status="processing",
                        stage="llm_recognition", total_chunks=len(chunks))

        # Step 4: LLM recognize (batched)
        t_llm_start = time.time()
        c = client()
        recognition_result = llm_recognize_chunks(c, document_id, chunks)
        llm_calls_log.append({"stage": "recognition", "chunks": len(chunks)})
        _log_stage("LLM_RECOGNITION", chunks=len(recognition_result.get("chunks", [])),
                    warnings=len(recognition_result.get("document_warnings", [])),
                    duration=f"{time.time()-t_llm_start:.2f}s")

        # Step 5: Normalize (already done inside llm_recognize_chunks)
        # Step 6: Python validate
        t0 = time.time()
        validated = validate_llm_decisions(chunks, signals_map, recognition_result)
        _log_stage("VALIDATE", total=len(validated),
                    applied=sum(1 for v in validated if v["applied"]),
                    rejected=sum(1 for v in validated if not v["applied"]),
                    duration=f"{time.time()-t0:.2f}s")
        if SAVE_DEBUG_FILES:
            save_json(root/"validated.json", validated)

        update_progress(document_id, status="processing",
                        stage="global_review", validated=len(validated))

        # Step 7: LLM global review
        t_review_start = time.time()
        if MD_ENABLE_GLOBAL_REVIEW:
            review_result = llm_global_review(
                c, document_id, validated, recognition_result.get("document_warnings", [])
            )
            llm_calls_log.append({"stage": "global_review"})
            _log_stage("GLOBAL_REVIEW", reviews=len(review_result.get("reviews", [])),
                        duration=f"{time.time()-t_review_start:.2f}s")
        else:
            review_result = {"reviews": [], "document_notes": []}

        t_llm_total = time.time() - t_llm_start

        # Step 8: Apply safe decisions → OutlineNodes
        t0 = time.time()
        nodes = apply_safe_decisions(chunks, validated, byid)
        _log_stage("APPLY_DECISIONS", nodes=len(nodes), duration=f"{time.time()-t0:.2f}s")

        # Step 8b: Apply global review
        if MD_ENABLE_GLOBAL_REVIEW:
            nodes = apply_global_review_safely(review_result, nodes, byid)

        # Step 9: Build tree (structural_postprocess + hierarchical_validation)
        t0 = time.time()
        nodes = structural_postprocess(nodes, byid)
        checked = hierarchical_validation(nodes)
        checked = sorted({n.block_id: n for n in checked}.values(), key=lambda n: n.line_id)
        _log_stage("TREE", raw_nodes=len(nodes), final_nodes=len(checked),
                    duration=f"{time.time()-t0:.2f}s")
        if SAVE_DEBUG_FILES:
            save_json(root/"merged_outline.json", [asdict(x) for x in nodes])
            save_json(root/"hierarchy_checked_outline.json", [asdict(x) for x in checked])
            save_json(root/"tree_nodes.json", build_tree_nodes(checked))

        # Step 10: Render markdown
        t0 = time.time()
        md = render_markdown(lines, checked)
        validation = validate_lossless(lines, md)
        _log_stage("RENDER", md_chars=len(md), md_lines=len(md.splitlines()),
                    missing=validation["missing_count"], duration=f"{time.time()-t0:.2f}s")
        if SAVE_DEBUG_FILES:
            save_json(root/"lossless_validation.json", validation)
            save_text(root/"final.md", md)
        outp.write_text(md, encoding="utf-8")

        # Step 11: Export metadata + audit
        if MD_SAVE_REPORTS:
            export_metadata(document_id, chunks, validated)
        if MD_ENABLE_AUDIT_LOG:
            export_audit_log(document_id, validated, llm_calls_log,
                             recognition_result.get("document_warnings", []))

        total_duration = round(time.time() - start, 2)
        llm_call_count = len(llm_calls_log)
        _log_stage("PIPELINE_COMPLETE", document_id=document_id,
                    duration=f"{total_duration:.2f}s", llm_duration=f"{t_llm_total:.2f}s",
                    llm_calls=llm_call_count, chunks=len(chunks),
                    outline_nodes=len(checked), md_chars=len(md),
                    missing_lines=validation["missing_count"])

        update_progress(document_id, status="done", output_path=str(outp),
                        duration_seconds=total_duration, llm_calls=llm_call_count)
        _log(f"DONE in {total_duration:.2f}s ({llm_call_count} LLM calls) → {outp}")
        return outp

    except Exception as exc:
        duration = round(time.time() - start, 2)
        _log_stage("PIPELINE_FAILED", document_id=document_id,
                    duration=f"{duration:.2f}s", error=str(exc)[:200])
        update_progress(document_id, status="failed",
                        output_path=str(outp), duration_seconds=duration)
        raise
    finally:
        if _log_file:
            _log_file.close()
            _log_file = None
