from sqlalchemy import Column, String, DateTime, Integer, Enum as SAEnum
from sqlalchemy.ext.declarative import declarative_base
import uuid
import datetime
import enum

Base = declarative_base()

class DocumentStatus(enum.Enum):
    """Lifecycle của tài liệu trong Vectorless RAG"""
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    ERROR = "error"

class Document(Base):
    __tablename__ = "documents"

    # Giữ nguyên ID dạng UUID để khớp với cấu trúc thư mục hiện tại
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String, nullable=False)
    
    # --- CẬP NHẬT MỚI CHO TASK 1.4 ---
    
    # Đường dẫn file gốc (trước đây là storage_path)
    raw_file_path = Column(String, nullable=False) 
    
    # Đường dẫn file JSON cấu trúc cây (Task 1.3)
    # Ví dụ: data/semantic_trees/<uuid>.json
    json_tree_path = Column(String, nullable=True) 
    
    # Đường dẫn thư mục chứa text từng trang (Task 1.2)
    # Ví dụ: data/extracted_text/<uuid>/
    extracted_text_path = Column(String, nullable=True)
    
    # Thông tin bổ trợ để Agent dễ điều hướng
    total_pages = Column(Integer, default=0, nullable=False)
    
    # Chuyển đổi status từ String sang Enum để chặt chẽ hơn
    status = Column(SAEnum(DocumentStatus), default=DocumentStatus.PENDING, nullable=False)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, filename='{self.filename}', status='{self.status.value}')>"