from .main import celery_app
from .database import SessionLocal
from .models import Document, DocumentStatus  # Import thêm DocumentStatus Enum
from .services.ocr import extract_text

@celery_app.task(name="app.worker.process_document")
def process_document(doc_id: str):
    db = SessionLocal()
    doc = None
    try:
        # 1. Tìm tài liệu trong DB bằng UUID String
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            return f"Document {doc_id} not found"
            
        # 2. Cập nhật trạng thái sang PROCESSING (Dùng Enum chuẩn)
        doc.status = DocumentStatus.PROCESSING
        db.commit()
        
        # 3. Gọi hàm OCR với trường chuẩn 'raw_file_path'
        extract_text(doc.raw_file_path, doc.id)
        
        # 4. Hoàn thành OCR, chuyển trạng thái sang PROCESSED
        doc.status = DocumentStatus.PROCESSED
        db.commit()
        return f"Document {doc_id} processed successfully"

    except Exception as e:
        db.rollback()  # Thu hồi lệnh nếu có lỗi xảy ra trong phiên
        if doc:
            # 5. Lỗi thì chuyển sang Enum ERROR (Không gán chuỗi text tự do vào đây)
            doc.status = DocumentStatus.ERROR
            db.commit()
        raise e  # Re-raise lỗi để Celery log lại hệ thống dashboard
        
    finally:
        db.close()