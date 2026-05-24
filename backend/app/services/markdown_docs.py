from __future__ import annotations

import json, os, re, time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from openai import OpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

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
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "240"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1024"))
LLM_NUM_CTX = int(os.getenv("LLM_NUM_CTX", "4096"))
LLM_THINK = os.getenv("LLM_THINK", "false").lower() == "true"
LLM_KEEP_ALIVE = os.getenv("LLM_KEEP_ALIVE", "30m")
LLM_USE_RESPONSE_FORMAT = os.getenv("LLM_USE_RESPONSE_FORMAT", "true").lower() == "true"

MD_BATCH_SIZE = int(os.getenv("MD_BATCH_SIZE", "4"))
MD_MAX_PROMPT_CHARS = int(os.getenv("MD_MAX_PROMPT_CHARS", "4000"))
MD_SECTION_MAX_BLOCKS = int(os.getenv("MD_SECTION_MAX_BLOCKS", "28"))
MD_SECTION_MAX_CHARS = int(os.getenv("MD_SECTION_MAX_CHARS", "5000"))
MD_BLOCK_TEXT_CHARS = int(os.getenv("MD_BLOCK_TEXT_CHARS", "140"))
MD_MAX_HEADING_LEVEL = int(os.getenv("MD_MAX_HEADING_LEVEL", "4"))
MD_SAVE_REPORTS = os.getenv("MD_SAVE_REPORTS", "true").lower() == "true"
MD_ALLOW_PARTIAL = os.getenv("MD_ALLOW_PARTIAL", "true").lower() == "true"
MD_JSON_RETRY_ATTEMPTS = int(os.getenv("MD_JSON_RETRY_ATTEMPTS", "3"))
MD_JSON_RETRY_WAIT_SECONDS = int(os.getenv("MD_JSON_RETRY_WAIT_SECONDS", "2"))

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
def _log(msg: str) -> None:
    print(f"[MD-ADMIN-INCREMENTAL] {msg}", flush=True)

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

def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

def effective_config() -> dict[str, Any]:
    return {
        "DATA_DIR": str(DATA_DIR), "NORMALIZED_TEXT_DIR": str(NORMALIZED_DIR),
        "MARKDOWN_DOCS_DIR": str(MARKDOWN_DIR), "MD_WORK_DIR": str(WORK_DIR),
        "LLM_BASE_URL": LLM_BASE_URL, "LLM_API_KEY": "***" if LLM_API_KEY else "",
        "LLM_MODEL": LLM_MODEL, "LLM_NUM_CTX": LLM_NUM_CTX, "LLM_THINK": LLM_THINK,
        "LLM_MAX_TOKENS": LLM_MAX_TOKENS, "LLM_TIMEOUT_SECONDS": LLM_TIMEOUT_SECONDS,
        "MD_BATCH_SIZE": MD_BATCH_SIZE, "MD_MAX_PROMPT_CHARS": MD_MAX_PROMPT_CHARS,
        "MD_SECTION_MAX_BLOCKS": MD_SECTION_MAX_BLOCKS, "MD_SECTION_MAX_CHARS": MD_SECTION_MAX_CHARS,
        "MD_BLOCK_TEXT_CHARS": MD_BLOCK_TEXT_CHARS, "MD_ALLOW_PARTIAL": MD_ALLOW_PARTIAL,
        "MD_SAVE_REPORTS": MD_SAVE_REPORTS,
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
def extract_json_object(content: str) -> dict[str, Any]:
    raw = (content or "").strip()
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
# LLM
# =========================================================
JSON_RULES = "/no_think\nReturn exactly one valid JSON object. No markdown. No reasoning. No <think>. No extra fields."

OUTLINE_PROMPT = """Analyze blocks from a Vietnamese administrative document.

Return format:
{
  "blocks": [
    {
      "block_id": 1,
      "role": "DOCUMENT_TITLE",
      "is_node": true,
      "level": 1
    }
  ]
}

Allowed roles:
DOCUMENT_TITLE,DOCUMENT_SUBJECT,METADATA,PREAMBLE,BACKGROUND,LEGAL_BASIS,
SECTION_INTRO,MAIN_CONTENT_UNIT,SUB_CONTENT_UNIT,BODY_DETAIL,LIST_ITEM,
ADDRESSEE_ITEM,FOOTER_SECTION,FOOTER_ITEM,SIGNATURE_BLOCK,APPENDIX_SECTION,
NOISE,UNKNOWN.

Rules:
- Return exactly one object for every input block_id.
- Classify semantic function of every input block.
- Set is_node=true only for blocks that should become Markdown headings.
- Do not select metadata, footer item, list item, body detail, signature, noise.
- Use level 1 for document title.
- Use level 2 for subject, major section, appendix section, footer section.
- Use level 3 for article, numbered unit, roman unit, decimal unit.
- Use level 4 for lettered sub-unit.
- Similar sibling markers must use the same level.
- If unsure about role, choose UNKNOWN and is_node=false.
- Do not rewrite block text.
""".strip()

OUTLINE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "outline_response",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "blocks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "block_id": {"type": "integer"},
                            "role": {"type": "string"},
                            "is_node": {"type": "boolean"},
                            "level": {"type": "integer"},
                        },
                        "required": ["block_id", "role", "is_node", "level"],
                    },
                }
            },
            "required": ["blocks"],
        },
    },
}

def block_payload(b: BlockRecord) -> dict[str,Any]:
    f=b.features["first_line_features"]
    return {"block_id":b.block_id,"lines":[b.start_line_id,b.end_line_id],"first":clip(b.first_line,120),"text":clip(b.text,MD_BLOCK_TEXT_CHARS),"features":f}

def ensure_prompt(prompt: str) -> str:
    if len(prompt)>MD_MAX_PROMPT_CHARS: raise ValueError(f"Prompt too long: {len(prompt)} chars > {MD_MAX_PROMPT_CHARS}")
    return prompt

def outline_prompt(blocks: list[BlockRecord], section: SectionRecord) -> str:
    payload = {
        "section": asdict(section),
        "blocks": [block_payload(b) for b in blocks],
    }
    return ensure_prompt(JSON_RULES + "\n" + OUTLINE_PROMPT + "\n" + cj(payload))

def client() -> OpenAI: return OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY, timeout=LLM_TIMEOUT_SECONDS)
def retry_json(): return retry(stop=stop_after_attempt(MD_JSON_RETRY_ATTEMPTS), wait=wait_fixed(MD_JSON_RETRY_WAIT_SECONDS), retry=retry_if_exception_type(Exception), reraise=True)

def call_json(c: OpenAI, prompt: str, docid: str, stage: str, secid: int|None, fmt: dict|None) -> dict[str,Any]:
    @retry_json()
    def _call():
        _log(f"LLM JSON stage={stage} section={secid} chars={len(prompt)}")
        kw={"model":LLM_MODEL,"messages":[{"role":"user","content":prompt}],"temperature":0,"top_p":0.1,"max_tokens":LLM_MAX_TOKENS,"extra_body":{"think":LLM_THINK,"keep_alive":LLM_KEEP_ALIVE,"options":{"num_ctx":LLM_NUM_CTX,"temperature":0,"top_p":0.1,"top_k":1}}}
        if LLM_USE_RESPONSE_FORMAT and fmt: kw["response_format"]=fmt
        resp=c.chat.completions.create(**kw)
        content=resp.choices[0].message.content or ""
        try: return extract_json_object(content)
        except Exception as e:
            save_json(work_dir(docid)/"llm_failures"/f"section_{secid or 0:03d}.{stage}.{int(time.time()*1000)}.json", {"error":str(e),"raw_response":content,"prompt_preview":prompt[:2500]})
            raise
    return _call()

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

    nodes = structural_postprocess(nodes, byid)

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
    start=time.time(); ensure_dirs(document_id)
    inp=Path(normalized_path) if normalized_path else NORMALIZED_DIR/f"{document_id}.txt"
    outp=MARKDOWN_DIR/f"{document_id}.md"
    if not inp.exists(): raise FileNotFoundError(f"Normalized text not found: {inp}")
    _log(f"Input: {inp}"); _log(f"Output: {outp}"); _log(f"Model: {LLM_MODEL}")
    print(json.dumps(effective_config(),ensure_ascii=False,indent=2),flush=True)
    lines=read_lines(inp); blocks=build_blocks(lines); byid={b.block_id:b for b in blocks}; sections=build_sections(blocks)
    _log(f"Loaded {len(lines)} lines; built {len(blocks)} blocks; built {len(sections)} sections")
    root=work_dir(document_id)
    save_json(root/"lines.json", [asdict(x) for x in lines]); save_json(root/"blocks.json", [asdict(x) for x in blocks]); save_json(root/"sections.json", [asdict(x) for x in sections])
    c=client(); results=[]; completed=[]; failed=[]
    update_progress(document_id, status="processing", total_sections=len(sections), completed_sections=[], failed_sections=[])
    for sec in sections:
        _log(f"Section {sec.section_id}/{len(sections)} blocks={len(sec.block_ids)} reason={sec.reason}")
        try: res=process_section(c,document_id,sec,blocks,byid)
        except Exception as e:
            _log(f"Section {sec.section_id} hard fallback: {e}")
            secblocks=[byid[i] for i in sec.block_ids if i in byid]
            roles=parse_roles({}, {}, secblocks); cands=py_candidates(secblocks,roles); nodes=structural_postprocess(nodes_from_candidates(cands,byid,sec.section_id),byid)
            res={"section_id":sec.section_id,"status":"failed_but_rendered","error":str(e),"roles":list(roles.values()),"candidates":cands,"outline":nodes}
        results.append(res)
        save_json(root/"section_reports"/f"section_{sec.section_id:03d}.result.json", {"section":asdict(sec),"status":res["status"],"error":res["error"],"roles":[asdict(x) for x in res["roles"]],"candidates":[asdict(x) for x in res["candidates"]],"outline":[asdict(x) for x in res["outline"]]})
        save_text(root/"partial_markdown"/f"section_{sec.section_id:03d}.md", render_section(lines,sec,res["outline"]))
        completed.append(sec.section_id) if res["status"] in {"done","done_with_fallback","failed_but_rendered"} else failed.append({"section_id":sec.section_id,"error":res["error"]})
        update_progress(document_id, status="processing", total_sections=len(sections), completed_sections=completed, failed_sections=failed, current_section=sec.section_id, updated_at=time.time())
        if res["status"]=="failed" and not MD_ALLOW_PARTIAL: raise RuntimeError(res["error"])
    merged=[]
    for r in results: merged.extend(r["outline"])
    merged=structural_postprocess(merged,byid); checked=structural_postprocess(hierarchical_validation(merged),byid); checked=sorted({n.block_id:n for n in checked}.values(),key=lambda n:n.line_id)
    save_json(root/"merged_outline.json", [asdict(x) for x in merged]); save_json(root/"hierarchy_checked_outline.json", [asdict(x) for x in checked]); save_json(root/"tree_nodes.json", build_tree_nodes(checked))
    md=render_markdown(lines,checked); save_json(root/"lossless_validation.json", validate_lossless(lines,md)); save_text(root/"final.md", md); outp.write_text(md,encoding="utf-8")
    update_progress(document_id, status="done", total_sections=len(sections), completed_sections=completed, failed_sections=failed, output_path=str(outp), duration_seconds=round(time.time()-start, 2))
    _log(f"Saved Markdown: {outp}"); _log(f"DONE in {time.time()-start:.2f}s")
    return outp