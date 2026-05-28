from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from .deepdoc.pipeline import pdf_to_markdown, image_file_to_markdown


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
            pages = pdf_to_markdown(str(path))
            full_md = "\n\n---\n\n".join(
                f"# Trang {p['page']}\n\n{p['markdown']}" for p in pages
            )
            _log(f"Processed {len(pages)} pages")
        elif ext in image_exts:
            md = image_file_to_markdown(str(path))
            full_md = md
            pages = [{"page": 1, "markdown": md}]
            _log("Processed 1 image")
        else:
            raise ValueError(f"Unsupported format: {ext}")

        out_path = MARKDOWN_DIR / f"{document_id}.md"
        out_path.write_text(full_md, encoding="utf-8")
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
