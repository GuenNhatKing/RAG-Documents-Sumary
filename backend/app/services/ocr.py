from __future__ import annotations

import io
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import pytesseract
from PIL import Image


DATA_DIR = Path("data")
EXTRACTED_TEXT_DIR = DATA_DIR / "extracted_text"
EXTRACT_WORK_DIR = DATA_DIR / "extract_work"

OCR_LANG = "vie+eng"
OCR_DPI = 300
SAVE_DEBUG_FILES = os.getenv("SAVE_DEBUG_FILES", "false").lower() == "true"
MIN_NATIVE_TEXT_CHARS = 500

SIGNATURE_NOISE_KEYWORDS = (
    "Người ký:",
    "CỔNG THÔNG TIN ĐIỆN TỬ",
    "Ký bởi:",
    "Thời gian ký:",
    "Email:",
)


@dataclass
class PageExtractReport:
    page: int
    method: str
    native_chars: int
    ocr_chars: int
    selected_chars: int
    reason: str
    output_path: str | None = None
    error: str | None = None


def _log(message: str) -> None:
    print(f"[EXTRACT-TEXT] {message}", flush=True)


def _work_dir(document_id: str) -> Path:
    return EXTRACT_WORK_DIR / document_id


def _ensure_dirs(document_id: str) -> None:
    (EXTRACTED_TEXT_DIR / document_id).mkdir(parents=True, exist_ok=True)
    for sub in ["pages", "errors"]:
        (_work_dir(document_id) / sub).mkdir(parents=True, exist_ok=True)


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _update_progress(document_id: str, **data: Any) -> None:
    payload = dict(data)
    payload["document_id"] = document_id
    payload["updated_at"] = time.time()
    _save_json(_work_dir(document_id) / "progress.json", payload)


def _page_text_path(document_id: str, page_num: int) -> Path:
    return EXTRACTED_TEXT_DIR / document_id / f"page_{page_num + 1:03d}.txt"


def _save_page_text(document_id: str, page_num: int, text: str) -> Path | None:
    text = text.strip()
    if not text:
        return None

    out_path = _page_text_path(document_id, page_num)
    _save_text(out_path, text)
    return out_path


def _has_signature_noise(text: str) -> bool:
    return any(keyword in text for keyword in SIGNATURE_NOISE_KEYWORDS)


def _should_try_ocr(native_text: str) -> tuple[bool, str]:
    if len(native_text.strip()) < MIN_NATIVE_TEXT_CHARS:
        return True, "native_text_too_short"

    if _has_signature_noise(native_text):
        return True, "signature_noise_detected"

    return False, "native_text_enough"


def _ocr_page(page: fitz.Page) -> str:
    pix = page.get_pixmap(dpi=OCR_DPI)
    img_data = pix.tobytes("png")
    image = Image.open(io.BytesIO(img_data))
    return pytesseract.image_to_string(image, lang=OCR_LANG).strip()


def _choose_text(native_text: str, ocr_text: str, reason: str) -> tuple[str, str]:
    native_text = native_text.strip()
    ocr_text = ocr_text.strip()

    if not ocr_text:
        return native_text, "native_text_selected_ocr_empty"

    if not native_text:
        return ocr_text, "ocr_selected_native_empty"

    if _has_signature_noise(native_text) and len(ocr_text) >= len(native_text) * 0.5:
        return ocr_text, "ocr_selected_signature_noise"

    if len(ocr_text) > len(native_text):
        return ocr_text, "ocr_selected_longer_text"

    return native_text, f"native_text_selected_{reason}"


def extract_text(file_path: str, document_id: str) -> None:
    """Extract text from PDF into page_XXX.txt files.

    Final output:
        data/extracted_text/{document_id}/page_001.txt

    Work/session output:
        data/extract_work/{document_id}/progress.json
        data/extract_work/{document_id}/pages/page_001.json
        data/extract_work/{document_id}/errors/page_001.json
        data/extract_work/{document_id}/report.json
    """
    start = time.time()
    path = Path(file_path)
    ext = path.suffix.lower()

    _ensure_dirs(document_id)

    if ext != ".pdf":
        _update_progress(
            document_id,
            status="skipped",
            reason=f"unsupported_format:{ext}",
            file_path=str(path),
        )
        _log(f"Bỏ qua định dạng không hỗ trợ: {ext}")
        return

    reports: list[PageExtractReport] = []

    _update_progress(
        document_id,
        status="started",
        file_path=str(path),
    )

    doc = fitz.open(path)

    try:
        total_pages = len(doc)

        _update_progress(
            document_id,
            status="processing",
            total_pages=total_pages,
            completed_pages=0,
        )

        for page_num in range(total_pages):
            page_index = page_num + 1
            _log(f"Extract page {page_index}/{total_pages}")

            try:
                page = doc[page_num]
                native_text = page.get_text().strip()

                should_ocr, reason = _should_try_ocr(native_text)

                ocr_text = ""
                if should_ocr:
                    ocr_text = _ocr_page(page)

                if should_ocr:
                    selected_text, method = _choose_text(native_text, ocr_text, reason)
                else:
                    selected_text, method = native_text, "native_text"

                out_path = _save_page_text(document_id, page_num, selected_text)

                report = PageExtractReport(
                    page=page_index,
                    method=method,
                    native_chars=len(native_text),
                    ocr_chars=len(ocr_text),
                    selected_chars=len(selected_text),
                    reason=reason,
                    output_path=str(out_path) if out_path else None,
                )

                reports.append(report)

                if SAVE_DEBUG_FILES:
                    _save_json(
                        _work_dir(document_id) / "pages" / f"page_{page_index:03d}.json",
                        asdict(report),
                    )

                _update_progress(
                    document_id,
                    status="processing",
                    total_pages=total_pages,
                    completed_pages=page_index,
                    current_page=page_index,
                )

            except Exception as exc:
                report = PageExtractReport(
                    page=page_index,
                    method="failed",
                    native_chars=0,
                    ocr_chars=0,
                    selected_chars=0,
                    reason="page_extract_failed",
                    error=str(exc),
                )

                reports.append(report)

                if SAVE_DEBUG_FILES:
                    _save_json(
                        _work_dir(document_id) / "errors" / f"page_{page_index:03d}.json",
                        asdict(report),
                    )

                _log(f"Page {page_index} failed: {exc}")

        if SAVE_DEBUG_FILES:
            _save_json(
                _work_dir(document_id) / "report.json",
                [asdict(report) for report in reports],
            )

        _update_progress(
            document_id,
            status="done",
            total_pages=total_pages,
            completed_pages=len(reports),
            duration_seconds=round(time.time() - start, 2),
            output_dir=str(EXTRACTED_TEXT_DIR / document_id),
            work_dir=str(_work_dir(document_id)),
        )

        _log(f"Done. Output dir: {EXTRACTED_TEXT_DIR / document_id}")
        _log(f"Work dir: {_work_dir(document_id)}")

    except Exception as exc:
        _update_progress(
            document_id,
            status="failed",
            error=str(exc),
            duration_seconds=round(time.time() - start, 2),
            output_dir=str(EXTRACTED_TEXT_DIR / document_id),
            work_dir=str(_work_dir(document_id)),
        )
        raise

    finally:
        doc.close()