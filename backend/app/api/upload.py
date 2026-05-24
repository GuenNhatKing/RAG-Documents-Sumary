from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.security import OAuth2PasswordBearer
from pathlib import Path
import shutil

router = APIRouter()

auth_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# Simple token verification – reuse existing utils if any
def get_current_user(token: str = Depends(auth_scheme)):
    # For demo purposes we just accept any token; real implementation should verify JWT
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return token

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploaded_files"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

@router.post("/files/upload")
async def upload_file(file: UploadFile = File(...), token: str = Depends(get_current_user)):
    dest = UPLOAD_DIR / file.filename
    with dest.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"filename": file.filename, "status": "uploaded"}

@router.get("/files/list")
async def list_files(token: str = Depends(get_current_user)):
    return [p.name for p in UPLOAD_DIR.iterdir() if p.is_file()]
