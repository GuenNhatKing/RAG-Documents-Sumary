from fastapi import FastAPI, UploadFile, File, HTTPException
from pathlib import Path
import shutil
import os

from dotenv import load_dotenv
load_dotenv()

from .models import Document, Base
from .database import SessionLocal, engine
from celery import Celery

from .services.pageindex_service import generate_semantic_tree
from .services.ocr import extract_text 


app = FastAPI()

# Register chat router
from app.api import chat
app.include_router(chat.router, prefix="/chat", tags=["Chat"])
Base.metadata.create_all(bind=engine)


# =========================================================
# CELERY
# =========================================================
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery_app = Celery(__name__, broker=redis_url, backend=redis_url)


# =========================================================
# HEALTH CHECK
# =========================================================
@app.get("/ping")
async def ping():
    return {"status": "ok"}


# =========================================================
# UPLOAD FILE
# =========================================================
@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    db = SessionLocal()
    try:
        # 1. Tạo record trong database trước để lấy ID (storage_path tạm để trống)
        doc = Document(
            filename=file.filename,
            storage_path="", 
            status="pending"
        )
        db.add(doc)
        db.commit()
        db.refresh(doc) # Lúc này doc đã có ID tự tăng

        # 2. Lấy phần mở rộng của file (extension) và tạo tên mới
        ext = Path(file.filename).suffix # Lấy đuôi file, ví dụ: .pdf, .docx
        new_filename = f"{doc.id}{ext}"
        
        # 3. Chuẩn bị thư mục và đường dẫn file
        upload_dir = Path("data/raw")
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / new_filename

        # 4. Ghi file xuống ổ cứng với tên mới
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 5. Cập nhật lại đường dẫn thực tế vào database
        doc.storage_path = str(file_path)
        db.commit()
        db.refresh(doc)

    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()

    return {
        "id": doc.id, 
        "original_filename": file.filename, 
        "saved_filename": new_filename
    }


# =========================================================
# EXTRACT TEXT
# =========================================================
@app.post("/documents/{document_id}/extract-text")
async def extract_text_api(document_id: str):
    db = SessionLocal()

    try:
        doc = db.query(Document).filter(Document.id == document_id).first()

        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        file_path = doc.storage_path

        extract_text(file_path, document_id)

        doc.status = "extracted"
        db.commit()

        return {
            "status": "ok",
            "document_id": document_id,
            "output_dir": f"data/extracted_text/{document_id}"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        db.close()


# =========================================================
# BUILD SEMANTIC TREE
# =========================================================
@app.post("/documents/{document_id}/build-tree")
async def build_tree(document_id: str):
    try:
        out_path = await generate_semantic_tree(document_id)

        return {
            "status": "ok",
            "tree_path": str(out_path)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# CELERY TEST
# =========================================================
@celery_app.task
def add(x: int, y: int) -> int:
    return x + y