from sqlalchemy import Column, String, DateTime, Integer, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
import uuid
import datetime
import enum

Base = declarative_base()

class DocumentStatus(enum.Enum):
    """Lifecycle của tài liệu trong Vectorless RAG"""
    PENDING = "pending"
    PROCESSING = "processing"
    PENDING_REVIEW = "pending_review"  # .md đã tạo, chờ cán bộ xác nhận
    PROCESSED = "processed"
    ERROR = "error"

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False)

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"


class Document(Base):
    __tablename__ = "documents"

    # UUID primary key — khớp với cấu trúc thư mục (data/<doc_id>/...)
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String, nullable=False)

    # Đường dẫn file gốc (PDF upload)
    raw_file_path = Column(String, nullable=False)

    # Đường dẫn file JSON cấu trúc cây (Task 1.3)
    json_tree_path = Column(String, nullable=True)

    # Đường dẫn thư mục chứa text từng trang (Task 1.2)
    extracted_text_path = Column(String, nullable=True)

    # Đường dẫn file Markdown đã tạo
    markdown_path = Column(String, nullable=True)

    # Tổng số trang PDF
    total_pages = Column(Integer, default=0, nullable=False)

    # Trạng thái xử lý (Enum)
    status = Column(SAEnum(DocumentStatus), default=DocumentStatus.PENDING, nullable=False)

    # Thời điểm tạo bản ghi
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, filename='{self.filename}', status='{self.status.value}')>"


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    doc_id = Column(String, ForeignKey("documents.id"), nullable=False)
    title = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<ChatSession(id={self.id}, doc_id='{self.doc_id}')>"


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    sources = Column(Text, nullable=True)  # JSON string of sources
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    session = relationship("ChatSession", back_populates="messages")

    def __repr__(self) -> str:
        return f"<ChatMessage(id={self.id}, role='{self.role}', session_id='{self.session_id}')>"