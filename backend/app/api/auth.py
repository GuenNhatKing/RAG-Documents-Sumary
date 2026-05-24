
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status

router = APIRouter()
from fastapi.security import OAuth2PasswordBearer

auth_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
from pydantic import BaseModel
from pathlib import Path
import jwt

# RSA key handling
KEY_DIR = Path(__file__).resolve().parent.parent / "keys"
PRIVATE_KEY_PATH = KEY_DIR / "private.pem"
PUBLIC_KEY_PATH = KEY_DIR / "public.pem"
if not KEY_DIR.exists():
    KEY_DIR.mkdir(parents=True)
if not PRIVATE_KEY_PATH.exists() or not PUBLIC_KEY_PATH.exists():
    from Crypto.PublicKey import RSA
    key = RSA.generate(2048)
    PRIVATE_KEY_PATH.write_bytes(key.export_key('PEM'))
    PUBLIC_KEY_PATH.write_bytes(key.publickey().export_key('PEM'))
PRIVATE_KEY = PRIVATE_KEY_PATH.read_text()
PUBLIC_KEY = PUBLIC_KEY_PATH.read_text()
ALGORITHM = "RS256"

class TokenData(BaseModel):
    username: str | None = None
    role: str | None = None

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    role: str  # nguoi_dung, admin, quan_ly, can_bo

# Database-backed user handling – imported below
from sqlalchemy.orm import Session
from ..database import SessionLocal
from ..models import User
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], default="pbkdf2_sha256", deprecated="auto")

def get_user(db: Session, username: str):
    return db.query(User).filter(User.username == username).first()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_user(db: Session, username: str, password: str, role: str):
    db_user = User(username=username, hashed_password=get_password_hash(password), role=role)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=30))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, PRIVATE_KEY, algorithm=ALGORITHM)

@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    db_user = get_user(db, req.username)
    if not db_user or not verify_password(req.password, db_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    access_token = create_access_token({"sub": db_user.username, "role": db_user.role})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/public-key")
def get_public_key():
    return {"public_key": PUBLIC_KEY}

@router.post("/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    # Only regular users can register via API
    if req.role != "nguoi_dung":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Privileged roles cannot be registered via API")
    if get_user(db, req.username):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already exists")
    create_user(db, req.username, req.password, req.role)
    return {"msg": "User created"}

async def get_current_user(token: str = Depends(auth_scheme)):
    try:
        payload = jwt.decode(token, PUBLIC_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if username is None or role is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        token_data = TokenData(username=username, role=role)
        return token_data
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate token")