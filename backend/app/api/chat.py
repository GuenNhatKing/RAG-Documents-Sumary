import json
import os
import re
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session

from app.services.rag import reasoning_search_tree, build_context_from_markdown
from app.services.llm import generate_final_answer
from app.database import SessionLocal
from app.models import ChatSession, ChatMessage, User
from app.api.auth import get_current_user, TokenData

router = APIRouter()


# ============================================================
# DATABASE DEPENDENCY
# ============================================================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================
# HELPER
# ============================================================
def _get_user_id(current_user: TokenData, db: Session) -> str:
    user = db.query(User).filter(User.username == current_user.username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user.id


def _check_ownership(session: ChatSession, user_id: str):
    if session.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")


# ============================================================
# PYDANTIC SCHEMAS
# ============================================================
class ChatRequest(BaseModel):
    doc_id: str
    question: str
    session_id: Optional[str] = None


class SourceDetail(BaseModel):
    lines: str
    file: str


class ChatResult(BaseModel):
    answer: str
    sources: List[SourceDetail]


class ChatResponse(BaseModel):
    result: ChatResult


class CreateSessionRequest(BaseModel):
    doc_id: str
    title: Optional[str] = None


class SessionResponse(BaseModel):
    id: str
    user_id: Optional[str]
    doc_id: str
    title: Optional[str]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    sources: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


# ============================================================
# SESSION CRUD (protected)
# ============================================================
@router.post("/sessions", response_model=SessionResponse)
def create_session(
    req: CreateSessionRequest,
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    user_id = _get_user_id(current_user, db)
    session = ChatSession(doc_id=req.doc_id, title=req.title, user_id=user_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return SessionResponse(
        id=session.id,
        user_id=session.user_id,
        doc_id=session.doc_id,
        title=session.title,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
    )


@router.get("/sessions", response_model=List[SessionResponse])
def list_sessions(
    doc_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    user_id = _get_user_id(current_user, db)
    query = db.query(ChatSession).filter(ChatSession.user_id == user_id).order_by(ChatSession.updated_at.desc())
    if doc_id:
        query = query.filter(ChatSession.doc_id == doc_id)
    sessions = query.all()
    return [
        SessionResponse(
            id=s.id,
            user_id=s.user_id,
            doc_id=s.doc_id,
            title=s.title,
            created_at=s.created_at.isoformat(),
            updated_at=s.updated_at.isoformat(),
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    user_id = _get_user_id(current_user, db)
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    _check_ownership(session, user_id)
    return SessionResponse(
        id=session.id,
        user_id=session.user_id,
        doc_id=session.doc_id,
        title=session.title,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
    )


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    user_id = _get_user_id(current_user, db)
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    _check_ownership(session, user_id)
    db.delete(session)
    db.commit()
    return {"detail": "Session deleted"}


@router.get("/sessions/{session_id}/messages", response_model=List[MessageResponse])
def get_messages(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    user_id = _get_user_id(current_user, db)
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    _check_ownership(session, user_id)
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return [
        MessageResponse(
            id=m.id,
            session_id=m.session_id,
            role=m.role,
            content=m.content,
            sources=m.sources,
            created_at=m.created_at.isoformat(),
        )
        for m in messages
    ]


# ============================================================
# CHAT ASK (protected, with session persistence)
# ============================================================
@router.post("/ask", response_model=ChatResponse)
async def ask_document(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    json_path = f"/work/backend/data/semantic_trees/{request.doc_id}.json"
    markdown_path = f"/work/backend/data/markdown_docs/{request.doc_id}.md"

    if not os.path.exists(json_path) or not os.path.exists(markdown_path):
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu (JSON hoặc MD).")

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            tree_data = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi đọc file JSON: {e}")

    try:
        node_list = reasoning_search_tree(tree_data, request.question)
        if not node_list:
            context = ""
        else:
            context = build_context_from_markdown(tree_data, node_list, markdown_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi RAG Retrieval: {e}")

    sources = []
    if context:
        pattern = r"\[Nguồn:\s*(.*?),\s*Dòng:\s*(.*?)\]"
        matches = re.findall(pattern, context)
        unique_matches = list(set(matches))
        for match in unique_matches:
            sources.append(SourceDetail(file=match[0], lines=match[1]))

    try:
        answer = generate_final_answer(context, request.question)
    except Exception as e:
         raise HTTPException(status_code=503, detail=f"Lỗi gọi LLM: {e}")

    if request.session_id:
        user_id = _get_user_id(current_user, db)
        session = db.query(ChatSession).filter(ChatSession.id == request.session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        _check_ownership(session, user_id)

        user_msg = ChatMessage(session_id=request.session_id, role="user", content=request.question)
        db.add(user_msg)

        sources_json = json.dumps([{"file": s.file, "lines": s.lines} for s in sources]) if sources else None
        assistant_msg = ChatMessage(session_id=request.session_id, role="assistant", content=answer, sources=sources_json)
        db.add(assistant_msg)

        if not session.title:
            session.title = request.question[:100]

        db.commit()

    return ChatResponse(result=ChatResult(answer=answer, sources=sources))
