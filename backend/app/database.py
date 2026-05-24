from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base

# Luôn đặt database.db trong thư mục /backend/ bất kể server chạy từ đâu
_DB_DIR = Path(__file__).resolve().parent.parent  # /work/backend/
_DB_PATH = _DB_DIR / "database.db"
SQLALCHEMY_DATABASE_URL = f"sqlite:///{_DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
