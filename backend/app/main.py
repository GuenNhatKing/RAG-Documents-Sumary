from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pathlib import Path
import json
import shutil
import os
import uuid
import traceback
import asyncio
import functools

from .env import load_backend_env

load_backend_env()

from sqlalchemy import func
from .models import Document, Base, DocumentStatus, ChatSession, ChatMessage, User
from .database import SessionLocal, engine
from celery import Celery

from .services.normalized_text import generate_normalized_text
from .services.markdown_docs import generate_markdown_doc
from .services.semantic_trees import generate_semantic_tree
from .services.ocr import extract_text
from .services.ocr_to_markdown import process_to_markdown
from .services.master_tree import remove_doc_from_master_tree
from .api.auth import get_current_user, TokenData

from .api import upload

app = FastAPI()

# =========================================================
# AUTH HELPER
# =========================================================
auth_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

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
from app.api import chat, auth
app.include_router(chat.router, prefix="/chat", tags=["Chat"])
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
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
# LIST DOCUMENTS ENDPOINT (auth required, role-filtered)
# =========================================================
@app.get("/documents")
def list_documents(
    page: int = 1,
    page_size: int = 20,
    current_user: TokenData = Depends(get_current_user),
):
    db = SessionLocal()
    try:
        query = db.query(Document).order_by(Document.created_at.desc())
        # nguoi_dung only see processed documents
        if current_user.role not in ("admin", "can_bo"):
            query = query.filter(Document.status == DocumentStatus.PROCESSED)
        total = query.count()
        docs = query.offset((page - 1) * page_size).limit(page_size).all()
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    "id": d.id,
                    "filename": d.filename,
                    "status": d.status.value if hasattr(d.status, 'value') else d.status,
                    "total_pages": d.total_pages,
                    "created_at": d.created_at.isoformat(),
                    "markdown_path": d.markdown_path,
                    "json_tree_path": d.json_tree_path,
                }
                for d in docs
            ],
        }
    finally:
        db.close()


# =========================================================
# TASK 4.1 - UPLOAD FILE ENDPOINT (Đã sửa lỗi raw_file_path & UUID)
# =========================================================
@app.post("/upload")
async def upload_file(file: UploadFile = File(...), current_user: TokenData = Depends(get_current_user)):
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
async def extract_text_api(document_id: str, current_user: TokenData = Depends(get_current_user)):
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()

        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        doc.status = DocumentStatus.PROCESSING
        db.commit()

        file_path = doc.raw_file_path
        loop = asyncio.get_event_loop()
        md_path = await loop.run_in_executor(
            None,
            functools.partial(process_to_markdown, file_path, document_id)
        )

        doc.status = DocumentStatus.PENDING_REVIEW
        doc.markdown_path = str(md_path)
        db.commit()

        return {
            "status": "ok",
            "document_id": document_id,
            "markdown_path": str(md_path),
            "message": "OCR pipeline hoàn tất. Markdown đã sẵn sàng để review."
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        traceback.print_exc()
        if doc:
            doc.status = DocumentStatus.ERROR
            db.commit()
        raise HTTPException(status_code=500, detail=f"OCR pipeline thất bại: {str(e)}")
    finally:
        db.close()


@app.get("/documents/{document_id}/extract-progress")
async def get_extract_progress(document_id: str, current_user: TokenData = Depends(get_current_user)):
    from .services.progress_store import get as get_progress
    cached = get_progress(document_id)
    if cached:
        return cached

    from .services.ocr import EXTRACT_WORK_DIR
    from .services.semantic_trees import TREE_WORK_DIR
    for base in (EXTRACT_WORK_DIR, Path("data") / "md_work", TREE_WORK_DIR):
        p = base / document_id / "progress.json"
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                return data
            except Exception:
                pass
    return {"status": "unknown", "current_page": 0, "total_pages": 0}


# =========================================================
# GENERATE MARKDOWN ENDPOINT (Phase A - dừng ở .md, chờ review)
# =========================================================
@app.post("/documents/{document_id}/generate-md")
async def generate_md_api(document_id: str, current_user: TokenData = Depends(get_current_user)):
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        if not doc.markdown_path or not Path(doc.markdown_path).exists():
            raise HTTPException(
                status_code=400,
                detail="Chưa có markdown. Gọi /extract-text trước để chạy OCR pipeline."
            )

        doc.status = DocumentStatus.PENDING_REVIEW
        db.commit()

        return {
            "status": "ok",
            "document_id": document_id,
            "markdown_path": doc.markdown_path,
            "message": "Markdown đã sẵn sàng để review."
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Markdown generation failed: {str(e)}")
    finally:
        db.close()


# =========================================================
# GET DOCUMENT MARKDOWN (Review endpoint)
# =========================================================
@app.get("/documents/{doc_id}/markdown")
def get_document_markdown(doc_id: str, current_user: TokenData = Depends(get_current_user)):
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        md_path = Path(doc.markdown_path) if doc.markdown_path else None
        if not md_path or not md_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Markdown not found for doc_id={doc_id}",
            )

        markdown = md_path.read_text(encoding="utf-8")

        return {
            "doc_id": doc_id,
            "markdown": markdown,
        }
    finally:
        db.close()


# =========================================================
# GET DOCUMENT RAW FILE (PDF gốc)
# =========================================================
@app.get("/documents/{doc_id}/raw")
def get_document_raw(doc_id: str, current_user: TokenData = Depends(get_current_user)):
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        raw_path = Path(doc.raw_file_path)
        if not raw_path.exists():
            raise HTTPException(status_code=404, detail="Raw file not found on disk")

        media_type = "application/pdf" if raw_path.suffix.lower() == ".pdf" else "application/octet-stream"
        return FileResponse(
            path=str(raw_path),
            filename=doc.filename,
            media_type=media_type,
            headers={"Content-Disposition": f'inline; filename="{doc.filename}"'},
        )
    finally:
        db.close()


# =========================================================
# EDIT DOCUMENT MARKDOWN (Cán bộ sửa .md trước khi confirm)
# =========================================================
@app.patch("/documents/{doc_id}/markdown")
def edit_document_markdown(doc_id: str, body: dict, current_user: TokenData = Depends(get_current_user)):
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        if doc.status not in (DocumentStatus.PENDING_REVIEW, DocumentStatus.PROCESSED):
            raise HTTPException(
                status_code=400,
                detail=f"Document status is '{doc.status.value}', expected 'pending_review' or 'processed'"
            )

        new_markdown = body.get("markdown")
        if not new_markdown:
            raise HTTPException(status_code=400, detail="Missing 'markdown' field")

        md_path = Path(doc.markdown_path) if doc.markdown_path else (
            Path("data/markdown_docs") / f"{doc_id}.md"
        )
        md_path.write_text(new_markdown, encoding="utf-8")

        doc.markdown_path = str(md_path)
        db.commit()

        return {"status": "ok", "doc_id": doc_id, "message": "Markdown updated"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")
    finally:
        db.close()


# =========================================================
# CONFIRM MARKDOWN & BUILD SEMANTIC TREE (Phase B - cán bộ xác nhận)
# =========================================================
@app.post("/documents/{document_id}/confirm-md")
async def confirm_md_api(document_id: str, current_user: TokenData = Depends(get_current_user)):
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        if doc.status not in (DocumentStatus.PENDING_REVIEW, DocumentStatus.PROCESSED):
            raise HTTPException(
                status_code=400,
                detail=f"Document status is '{doc.status.value}', expected 'pending_review' or 'processed'"
            )

        doc.status = DocumentStatus.PROCESSING
        db.commit()

        # Build semantic tree từ .md đã được review
        tree_path = await generate_semantic_tree(document_id)

        doc.status = DocumentStatus.PROCESSED
        doc.json_tree_path = str(tree_path)
        db.commit()

        return {
            "status": "ok",
            "document_id": document_id,
            "tree_path": str(tree_path),
            "message": "Document fully processed."
        }

    except Exception as e:
        db.rollback()
        if doc:
            doc.status = DocumentStatus.ERROR
            db.commit()
        raise HTTPException(status_code=500, detail=f"Confirm failed: {str(e)}")
    finally:
        db.close()


# =========================================================
# BUILD TREE ENDPOINT (Legacy - kept for backward compatibility)
# =========================================================
@app.post("/documents/{document_id}/build-tree")
async def build_tree(document_id: str, current_user: TokenData = Depends(get_current_user)):
    try:
        normalized_path = generate_normalized_text(document_id)

        markdown_path = generate_markdown_doc(
            document_id=document_id,
            normalized_path=normalized_path,
        )

        tree_path = await generate_semantic_tree(document_id)

        return {
            "status": "ok",
            "document_id": document_id,
            "normalized_path": str(normalized_path),
            "markdown_path": str(markdown_path),
            "tree_path": str(tree_path),
        }

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Required file not found: {str(e)}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input or configuration: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tree generation failed: {str(e)}")


# =========================================================
# GET DOCUMENT DETAIL (auth required)
# =========================================================
@app.get("/documents/{doc_id}")
def get_document_detail(doc_id: str, current_user: TokenData = Depends(get_current_user)):
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        return {
            "id": doc.id,
            "filename": doc.filename,
            "status": doc.status.value if hasattr(doc.status, 'value') else doc.status,
            "total_pages": doc.total_pages,
            "created_at": doc.created_at.isoformat(),
            "markdown_path": doc.markdown_path,
            "json_tree_path": doc.json_tree_path,
            "raw_file_path": doc.raw_file_path,
        }
    finally:
        db.close()


# =========================================================
# RENAME DOCUMENT (admin/can_bo only)
# =========================================================
@app.patch("/documents/{doc_id}/filename")
def rename_document(doc_id: str, body: dict, current_user: TokenData = Depends(get_current_user)):
    if current_user.role not in ("admin", "can_bo"):
        raise HTTPException(status_code=403, detail="Not authorized")
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        new_name = body.get("filename", "").strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="Missing 'filename' field")
        doc.filename = new_name
        db.commit()
        return {"status": "ok", "doc_id": doc_id, "filename": new_name}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Rename failed: {str(e)}")
    finally:
        db.close()


# =========================================================
# DELETE DOCUMENT (admin/can_bo only)
# =========================================================
@app.delete("/documents/{doc_id}")
def delete_document(doc_id: str, current_user: TokenData = Depends(get_current_user)):
    if current_user.role not in ("admin", "can_bo"):
        raise HTTPException(status_code=403, detail="Not authorized to delete documents")
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        # Delete files from disk
        for path_str in [doc.raw_file_path, doc.markdown_path, doc.json_tree_path]:
            if path_str:
                p = Path(path_str)
                if p.exists():
                    p.unlink()

        # Delete normalized_text file (and any sidecar JSONs)
        for pattern in [f"{doc_id}.txt", f"{doc_id}.*.json"]:
            for f in Path("data/normalized_text").glob(pattern):
                f.unlink(missing_ok=True)

        # Delete markdown_docs and semantic_trees files (fallback if not in DB paths)
        Path(f"data/markdown_docs/{doc_id}.md").unlink(missing_ok=True)
        Path(f"data/semantic_trees/{doc_id}.json").unlink(missing_ok=True)

        # Delete all work/data directories for this document
        for subdir in [
            "extracted_text",
            "extract_work",
            "normalized_work",
            "markdown_work",
        ]:
            d = Path(f"data/{subdir}/{doc_id}")
            if d.exists():
                shutil.rmtree(d)

        # Delete chat sessions for this document (and their messages via ORM cascade)
        sessions = db.query(ChatSession).filter(ChatSession.doc_id == doc_id).all()
        for s in sessions:
            db.delete(s)

        # Remove from master tree
        try:
            remove_doc_from_master_tree(doc_id)
        except Exception:
            pass

        # Delete document DB record
        db.delete(doc)
        db.commit()
        return {"detail": "Document deleted"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")
    finally:
        db.close()


# =========================================================
# STATS ENDPOINT (admin only)
# =========================================================
@app.get("/stats")
def get_stats(current_user: TokenData = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    db = SessionLocal()
    try:
        total_docs = db.query(Document).count()
        docs_by_status = {}
        for s in DocumentStatus:
            count = db.query(Document).filter(Document.status == s).count()
            docs_by_status[s.value] = count

        total_users = db.query(User).count()
        users_by_role = {}
        for role_name in ["admin", "can_bo", "nguoi_dung"]:
            count = db.query(User).filter(User.role == role_name).count()
            users_by_role[role_name] = count

        total_sessions = db.query(ChatSession).count()
        total_messages = db.query(ChatMessage).filter(ChatMessage.role == "user").count()

        # Sessions by role
        sessions_by_role: dict[str, int] = {}
        session_rows = (
            db.query(User.role, func.count(ChatSession.id))
            .outerjoin(ChatSession, ChatSession.user_id == User.id)
            .group_by(User.role)
            .all()
        )
        for role_name, cnt in session_rows:
            if cnt > 0:
                sessions_by_role[role_name] = cnt

        # Questions by role (messages with role="user" joined through session)
        questions_by_role: dict[str, int] = {}
        question_rows = (
            db.query(User.role, func.count(ChatMessage.id))
            .outerjoin(ChatSession, ChatSession.user_id == User.id)
            .outerjoin(ChatMessage, (ChatMessage.session_id == ChatSession.id) & (ChatMessage.role == "user"))
            .group_by(User.role)
            .all()
        )
        for role_name, cnt in question_rows:
            if cnt > 0:
                questions_by_role[role_name] = cnt

        # Feature usage: global Q&A vs document Q&A
        global_session_ids = (
            db.query(ChatSession.id)
            .filter(ChatSession.doc_id == "__global__")
            .subquery()
        )
        global_questions = (
            db.query(func.count(ChatMessage.id))
            .filter(ChatMessage.role == "user", ChatMessage.session_id.in_(global_session_ids))
            .scalar()
        )
        doc_questions = total_messages - global_questions

        feature_usage = {
            "Hỏi đáp": global_questions,
            "Hỏi tài liệu": doc_questions,
        }

        return {
            "total_docs": total_docs,
            "docs_by_status": docs_by_status,
            "total_users": total_users,
            "users_by_role": users_by_role,
            "total_sessions": total_sessions,
            "total_questions": total_messages,
            "sessions_by_role": sessions_by_role,
            "questions_by_role": questions_by_role,
            "feature_usage": feature_usage,
        }
    finally:
        db.close()


# =========================================================
# CELERY WORKER TEST
# =========================================================
@celery_app.task
def add(x: int, y: int) -> int:
    return x + y