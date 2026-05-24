from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import shutil
import os
import uuid

from .env import load_backend_env

load_backend_env()

from .models import Document, Base, DocumentStatus
from .database import SessionLocal, engine
from celery import Celery

from .services.normalized_text import generate_normalized_text
from .services.markdown_docs import generate_markdown_doc
from .services.semantic_trees import generate_semantic_tree
from .services.ocr import extract_text 

app = FastAPI()

# =========================================================
# CORS MIDDLEWARE (Cấu hình mở cổng kết nối Frontend Next.js)
# =========================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Cho phép tất cả các nguồn hoặc điền cụ thể ["http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================================
# REGISTER ROUTERS
# =========================================================
from app.api import chat
app.include_router(chat.router, prefix="/chat", tags=["Chat"])

# Khởi tạo cấu trúc bảng trong Database nếu chưa tồn tại
Base.metadata.create_all(bind=engine)

# =========================================================
# CELERY CONFIGURATION
# =========================================================
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery_app = Celery(__name__, broker=redis_url, backend=redis_url)


# =========================================================
# HEALTH CHECK ENDPOINT
# =========================================================
@app.get("/ping")
async def ping():
    return {"status": "ok"}


# =========================================================
# TASK 4.1 - UPLOAD FILE ENDPOINT (Đã sửa lỗi raw_file_path & UUID)
# =========================================================
@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    db = SessionLocal()
    try:
        # 1. Chủ động sinh UUID dạng chuỗi để làm khóa chính đồng bộ hệ thống
        doc_id = str(uuid.uuid4())
        ext = Path(file.filename).suffix  # Lấy đuôi file (ví dụ: .pdf)
        new_filename = f"{doc_id}{ext}"
        
        # 2. Chuẩn bị thư mục lưu trữ file thô (Raw PDF)
        upload_dir = Path("data/raw")
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / new_filename

        # 3. Ghi file từ luồng mạng xuống ổ cứng máy chủ
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 4. Lưu bản ghi vào Database (Đồng bộ chính xác tên trường và kiểu Enum)
        doc = Document(
            id=doc_id,
            filename=file.filename,
            raw_file_path=str(file_path),
            status=DocumentStatus.PENDING
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        return {
            "id": doc.id, 
            "original_filename": file.filename, 
            "saved_filename": new_filename
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database or Storage error: {str(e)}")
    finally:
        db.close()


# =========================================================
# TASK 4.1 - EXTRACT TEXT ENDPOINT (Đã sửa str ID & raw_file_path)
# =========================================================
@app.post("/documents/{document_id}/extract-text")
async def extract_text_api(document_id: str):
    db = SessionLocal()
    try:
        # Tìm tài liệu bằng UUID String
        doc = db.query(Document).filter(Document.id == document_id).first()

        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        # Cập nhật trạng thái sang Đang xử lý
        doc.status = DocumentStatus.PROCESSING
        db.commit()

        # Gọi hàm xử lý OCR / Trích xuất text từ file gốc
        file_path = doc.raw_file_path
        extract_text(file_path, document_id)

        # Trích xuất thành công, chuyển trạng thái tài liệu
        doc.status = DocumentStatus.PROCESSED
        db.commit()

        return {
            "status": "ok",
            "document_id": document_id,
            "output_dir": f"data/extracted_text/{document_id}"
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"OCR Extraction failed: {str(e)}")
    finally:
        db.close()


# =========================================================
# TASK 4.1 - BUILD SEMANTIC TREE ENDPOINT
# =========================================================
@app.post("/documents/{document_id}/build-tree")
async def build_tree(document_id: str):
    try:
        # =============================
        # PHASE 1 - NORMALIZED TEXT
        # =============================
        normalized_path = generate_normalized_text(document_id)

        # =============================
        # PHASE 2 - MARKDOWN DOCS
        # =============================
        markdown_path = generate_markdown_doc(
            document_id=document_id,
            normalized_path=normalized_path,
        )

        # =============================
        # PHASE 3 - SEMANTIC TREE
        # =============================
        tree_path = await generate_semantic_tree(document_id)

        return {
            "status": "ok",
            "document_id": document_id,
            "normalized_path": str(normalized_path),
            "markdown_path": str(markdown_path),
            "tree_path": str(tree_path),
        }

    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail=f"Required file not found: {str(e)}",
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid input or configuration: {str(e)}",
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Tree generation failed: {str(e)}",
        )

@app.get("/documents/{doc_id}/markdown")
def get_document_markdown(doc_id: str):
    markdown_path = (
        Path("/work/backend/data/markdown_docs") / f"{doc_id}.md"
    )

    if not markdown_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Markdown not found for doc_id={doc_id}",
        )

    markdown = markdown_path.read_text(
        encoding="utf-8"
    )

    return {
        "doc_id": doc_id,
        "markdown": markdown,
    }

# =========================================================
# CELERY WORKER TEST
# =========================================================
@celery_app.task
def add(x: int, y: int) -> int:
    return x + y