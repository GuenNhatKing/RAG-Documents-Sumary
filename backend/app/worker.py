from .main import celery_app
from .database import SessionLocal
from .models import Document
from .services.ocr import extract_text

@celery_app.task(name="app.worker.process_document")
def process_document(doc_id: str):
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            return
        doc.status = "processing"
        db.commit()
        extract_text(doc.storage_path, doc.id)
        doc.status = "processed"
        db.commit()
    except Exception as e:
        if doc:
            doc.status = f"failed: {str(e)}"
            db.commit()
    finally:
        db.close()
