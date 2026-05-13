from fastapi import FastAPI, UploadFile, File, HTTPException
from pathlib import Path
import shutil
from .models import Document, Base
from .database import SessionLocal, engine
from celery import Celery
import os

# Initialize FastAPI application
app = FastAPI()
Base.metadata.create_all(bind=engine)

@app.get("/ping")
async def ping():
    return {"status": "ok"}

# Initialize Celery application
# REDIS_URL is expected to be set in the environment (from .env)
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery_app = Celery(__name__, broker=redis_url, backend=redis_url)

# Example task to verify worker startup (optional)

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    # Save uploaded file to the project data directory
    upload_dir = Path("data/raw")
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / file.filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    # Record in database with pending status
    db = SessionLocal()
    try:
        doc = Document(filename=file.filename, storage_path=str(file_path), status="pending")
        db.add(doc)
        db.commit()
        db.refresh(doc)
    finally:
        db.close()
    return {"filename": file.filename, "id": doc.id}
@celery_app.task
def add(x: int, y: int) -> int:
    return x + y
