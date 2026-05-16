import os
import io
from pathlib import Path
import fitz  # PyMuPDF
import pytesseract
from PIL import Image

def _save_page_text(doc_id: str, page_num: int, text: str) -> None:
    """Save extracted text for a single page."""
    if not text.strip():
        return
    out_dir = Path("data/extracted_text") / doc_id
    out_dir.mkdir(parents=True, exist_ok=True)
    # Dùng 03d để format tên file giúp sắp xếp chuẩn xác (page_001, page_002...)
    out_path = out_dir / f"page_{page_num + 1:03d}.txt"
    out_path.write_text(text, encoding="utf-8")

def extract_text(file_path: str, document_id: str) -> None:
    """
    Extract text from PDF using a smart hybrid approach.
    Bypasses digital signature noise and processes scan pages correctly.
    """
    ext = Path(file_path).suffix.lower()

    if ext == ".pdf":
        doc = fitz.open(file_path)
        for page_num in range(len(doc)):
            page = doc[page_num]
            native_text = page.get_text().strip()

            # Ngưỡng 500 ký tự và bắt keyword rác của chữ ký số
            is_scanned_or_signed = (
                len(native_text) < 500 or
                "Người ký:" in native_text or
                "CỔNG THÔNG TIN ĐIỆN TỬ" in native_text
            )

            if is_scanned_or_signed:
                pix = page.get_pixmap(dpi=300)
                img_data = pix.tobytes("png")
                ocr_text = pytesseract.image_to_string(Image.open(io.BytesIO(img_data)), lang='vie+eng').strip()
                # Ưu tiên text dài hơn (bao phủ toàn trang)
                text = ocr_text if len(ocr_text) > len(native_text) else native_text
            else:
                text = native_text

            _save_page_text(document_id, page_num, text)
        doc.close()
    else:
        print(f"Bỏ qua định dạng không hỗ trợ: {ext}")