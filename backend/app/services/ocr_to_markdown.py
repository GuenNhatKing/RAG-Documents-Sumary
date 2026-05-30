from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from .deepdoc.pipeline import pdf_to_markdown, image_file_to_markdown
from .progress_store import update as update_progress


def _article(s: str) -> bool:
    return bool(re.match(r"^Điều\s+\d+[.:]?\s*", s.strip(), re.I))


def _decimal(s: str) -> bool:
    return bool(re.match(r"^\d+(?:\.\d+)+[.)]?\s*", s.strip()))


def _numbered(s: str) -> bool:
    return bool(re.match(r"^\d+[.)]\s*", s.strip()))


def _lettered(s: str) -> bool:
    return bool(re.match(r"^[A-Za-zÀ-ỹĐđ][.)]\s*", s.strip()))


def _roman(s: str) -> bool:
    return bool(re.match(r"^[IVXLCDM]+[.)]\s*", s.strip()))


def _marker_kind(s: str) -> str:
    x = s.strip()
    m = re.match(r"^(PHẦN|CHƯƠNG|MỤC|TIỂU\s+MỤC)", x, re.I)
    if m:
        return m.group(1).upper().replace(" ", "_")
    if _article(x):
        return "ARTICLE"
    if _decimal(x):
        return "DECIMAL"
    if _numbered(x):
        return "NUMBER"
    if _lettered(x):
        return "LETTER"
    if _roman(x):
        return "ROMAN"
    return "PLAIN"


def _detect_heading_level(text: str) -> int | None:
    k = _marker_kind(text)
    if k in {"PHẦN", "CHƯƠNG"}:
        return 1
    if k in {"MỤC", "TIỂU_MỤC", "ARTICLE"}:
        return 2
    if k in {"NUMBER", "DECIMAL", "ROMAN"}:
        return 3
    if k == "LETTER":
        return 4
    return None


def _is_document_title(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    if t.isupper() and len(t) > 10:
        keywords = ["LUẬT", "NGHỊ ĐỊNH", "THÔNG TƯ", "QUYẾT ĐỊNH", "CHỈ THỊ", "HIẾN PHÁP"]
        return any(kw in t for kw in keywords)
    return False


def _correct_heading_levels(markdown: str) -> str:
    lines = markdown.split("\n")
    result: list[str] = []
    first_heading = True
    in_code_block = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("```"):
            in_code_block = not in_code_block
            result.append(line)
            continue

        if not stripped.startswith("#"):
            result.append(line)
            continue

        # Only process heading lines
        m = re.match(r"^(#{1,4})\s+(.*)", stripped)
        if not m:
            result.append(line)
            continue

        text = m.group(2).strip()
        correct_level = _detect_heading_level(text)

        if correct_level is None:
            if first_heading and _is_document_title(text):
                result.append(text)
            else:
                result.append(line)
        else:
            result.append("#" * correct_level + " " + text)
            first_heading = False
            continue

        first_heading = False

    return "\n".join(result)


DATA_DIR = Path("data")
MARKDOWN_DIR = DATA_DIR / "markdown_docs"
WORK_DIR = DATA_DIR / "md_work"


def _log(message: str) -> None:
    print(f"[OCR-TO-MD] {message}", flush=True)


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _update_progress(document_id: str, **data: Any) -> None:
    payload = dict(data)
    payload["document_id"] = document_id
    payload["updated_at"] = time.time()
    _save_json(WORK_DIR / document_id / "progress.json", payload)
    update_progress(document_id, **data)


def process_to_markdown(file_path: str, document_id: str) -> Path:
    """Run full OCR pipeline (layout + OCR + table → markdown) and save .md file.

    Input:  PDF or image file path
    Output: data/markdown_docs/{document_id}.md
    """
    start = time.time()
    path = Path(file_path)
    ext = path.suffix.lower()

    _log(f"Processing {path.name} (doc_id={document_id})")

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    MARKDOWN_DIR.mkdir(parents=True, exist_ok=True)

    _update_progress(document_id, status="started")

    image_exts = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}

    try:
        if ext == ".pdf":
            def _on_page(current: int, total: int):
                _update_progress(document_id, status="processing", current_page=current, total_pages=total)
                _log(f"Page {current}/{total}")
            pages = pdf_to_markdown(str(path), progress_callback=_on_page)
            full_md = "\n\n".join(p["markdown"] for p in pages)
            _log(f"Processed {len(pages)} pages")
        elif ext in image_exts:
            md = image_file_to_markdown(str(path))
            full_md = md
            pages = [{"page": 1, "markdown": md}]
            _log("Processed 1 image")
        else:
            raise ValueError(f"Unsupported format: {ext}")

        out_path = MARKDOWN_DIR / f"{document_id}.md"
        corrected = _correct_heading_levels(full_md)
        if corrected != full_md:
            _log("Corrected heading levels for Vietnamese legal document structure")
        out_path.write_text(corrected, encoding="utf-8")
        _log(f"Saved markdown to {out_path}")

        _update_progress(
            document_id,
            status="done",
            pages=len(pages),
            output_path=str(out_path),
            duration_seconds=round(time.time() - start, 2),
        )

        return out_path

    except Exception as e:
        _update_progress(
            document_id,
            status="failed",
            error=str(e),
            duration_seconds=round(time.time() - start, 2),
        )
        raise
