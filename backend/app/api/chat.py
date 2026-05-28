import json
import os
import re
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session

from app.services.rag import reasoning_search_tree, build_context_from_markdown
from app.services.llm import generate_final_answer, generate_summary
from app.database import SessionLocal
from app.models import ChatSession, ChatMessage, User
from app.api.auth import get_current_user, TokenData

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _get_user_id(current_user: TokenData, db: Session) -> str:
    user = db.query(User).filter(User.username == current_user.username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user.id


def _check_ownership(session: ChatSession, user_id: str):
    if session.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")


# ============================================================
# SCHEMAS
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


class SearchRequest(BaseModel):
    query: str


class DocResult(BaseModel):
    doc_id: str
    filename: str
    summary: str


class GlobalAskRequest(BaseModel):
    question: str
    session_id: Optional[str] = None


class GlobalAskResponse(BaseModel):
    answer: str
    sources: List[SourceDetail]
    relevant_docs: List[DocResult]


class SummarizeRequest(BaseModel):
    doc_id: str
    length: str  # "short" | "medium" | "long"
    session_id: Optional[str] = None


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
        id=session.id, user_id=session.user_id, doc_id=session.doc_id,
        title=session.title, created_at=session.created_at.isoformat(),
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
    return [
        SessionResponse(id=s.id, user_id=s.user_id, doc_id=s.doc_id, title=s.title,
                        created_at=s.created_at.isoformat(), updated_at=s.updated_at.isoformat())
        for s in query.all()
    ]


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(session_id: str, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_user)):
    user_id = _get_user_id(current_user, db)
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    _check_ownership(session, user_id)
    return SessionResponse(id=session.id, user_id=session.user_id, doc_id=session.doc_id, title=session.title,
                           created_at=session.created_at.isoformat(), updated_at=session.updated_at.isoformat())


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_user)):
    user_id = _get_user_id(current_user, db)
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    _check_ownership(session, user_id)
    db.delete(session)
    db.commit()
    return {"detail": "Session deleted"}


@router.get("/sessions/{session_id}/messages", response_model=List[MessageResponse])
def get_messages(session_id: str, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_user)):
    user_id = _get_user_id(current_user, db)
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    _check_ownership(session, user_id)
    messages = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.asc()).all()
    return [MessageResponse(id=m.id, session_id=m.session_id, role=m.role, content=m.content,
                            sources=m.sources, created_at=m.created_at.isoformat())
            for m in messages]


# ============================================================
# SINGLE DOC ASK (protected)
# ============================================================
@router.post("/ask", response_model=ChatResponse)
async def ask_document(request: ChatRequest, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_user)):
    json_path = f"/work/backend/data/semantic_trees/{request.doc_id}.json"
    markdown_path = f"/work/backend/data/markdown_docs/{request.doc_id}.md"

    if not os.path.exists(json_path) or not os.path.exists(markdown_path):
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu.")

    with open(json_path, 'r', encoding='utf-8') as f:
        tree_data = json.load(f)

    node_list = reasoning_search_tree(tree_data, request.question)
    context = build_context_from_markdown(tree_data, node_list, markdown_path) if node_list else ""

    sources = []
    if context:
        seen_files: set[str] = set()
        for match in re.findall(r"\[Nguồn:\s*(.*?),\s*Dòng:\s*(.*?)\]", context):
            filename = match[0].strip()
            if filename not in seen_files:
                seen_files.add(filename)
                sources.append(SourceDetail(file=filename, lines=match[1].strip()))

    answer = generate_final_answer(context, request.question)

    if request.session_id:
        user_id = _get_user_id(current_user, db)
        session = db.query(ChatSession).filter(ChatSession.id == request.session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        _check_ownership(session, user_id)
        db.add(ChatMessage(session_id=request.session_id, role="user", content=request.question))
        sources_json = json.dumps([{"file": s.file, "lines": s.lines} for s in sources]) if sources else None
        db.add(ChatMessage(session_id=request.session_id, role="assistant", content=answer, sources=sources_json))
        if not session.title:
            session.title = request.question[:100]
        db.commit()

    return ChatResponse(result=ChatResult(answer=answer, sources=sources))


# ============================================================
# MASTER TREE SEARCH (protected)
# ============================================================
@router.post("/search", response_model=List[DocResult])
def search_docs(req: SearchRequest, current_user: TokenData = Depends(get_current_user)):
    from app.services.master_tree import search_master_tree
    results = search_master_tree(req.query)
    return [DocResult(**r) for r in results]


# ============================================================
# GLOBAL ASK — cross-document (protected)
# ============================================================
@router.post("/ask-global", response_model=GlobalAskResponse)
def ask_global(req: GlobalAskRequest, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_user)):
    from app.services.master_tree import search_master_tree

    relevant_docs = search_master_tree(req.question)
    if not relevant_docs:
        return GlobalAskResponse(answer="Không tìm thấy tài liệu nào liên quan.", sources=[], relevant_docs=[])

    # Build context from top docs
    context_parts = []
    for doc_info in relevant_docs[:3]:
        doc_id = doc_info["doc_id"]
        json_path = f"/work/backend/data/semantic_trees/{doc_id}.json"
        markdown_path = f"/work/backend/data/markdown_docs/{doc_id}.md"
        if not os.path.exists(json_path) or not os.path.exists(markdown_path):
            continue
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                tree_data = json.load(f)
            node_list = reasoning_search_tree(tree_data, req.question)
            if node_list:
                ctx = build_context_from_markdown(tree_data, node_list, markdown_path)
                if ctx:
                    context_parts.append(f"=== Tài liệu: {doc_info['filename']} ===\n{ctx}")
        except Exception:
            continue

    combined_context = "\n\n".join(context_parts)

    sources = []
    if combined_context:
        seen_files: set[str] = set()
        for match in re.findall(r"\[Nguồn:\s*(.*?),\s*Dòng:\s*(.*?)\]", combined_context):
            filename = match[0].strip()
            if filename not in seen_files:
                seen_files.add(filename)
                sources.append(SourceDetail(file=filename, lines=match[1].strip()))

    try:
        answer = generate_final_answer(combined_context, req.question)
    except Exception:
        answer = "Lỗi khi tạo câu trả lời."

    # Save messages to session if session_id provided
    if req.session_id:
        user_id = _get_user_id(current_user, db)
        session = db.query(ChatSession).filter(ChatSession.id == req.session_id).first()
        if session and session.user_id == user_id:
            db.add(ChatMessage(session_id=req.session_id, role="user", content=req.question))
            sources_json = json.dumps([{"file": s.file, "lines": s.lines} for s in sources]) if sources else None
            relevant_json = json.dumps([{"doc_id": d["doc_id"], "filename": d["filename"]} for d in relevant_docs[:3]])
            db.add(ChatMessage(
                session_id=req.session_id, role="assistant", content=answer,
                sources=sources_json,
            ))
            if not session.title:
                session.title = req.question[:100]
            db.commit()

    return GlobalAskResponse(
        answer=answer,
        sources=sources,
        relevant_docs=[DocResult(**d) for d in relevant_docs],
    )


# ============================================================
# SUMMARIZE — document summarization (protected)
# ============================================================
@router.post("/summarize", response_model=ChatResponse)
def summarize_document(req: SummarizeRequest, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_user)):
    """Summarize a document with user-selected length: short, medium, or long."""
    markdown_path = f"/work/backend/data/markdown_docs/{req.doc_id}.md"

    if not os.path.exists(markdown_path):
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu.")

    # Read full markdown content for summarization
    with open(markdown_path, "r", encoding="utf-8") as f:
        full_text = f.read()

    if not full_text.strip():
        raise HTTPException(status_code=400, detail="Tài liệu trống.")

    # Validate length parameter
    valid_lengths = {"short", "medium", "long"}
    length = req.length if req.length in valid_lengths else "medium"

    # Generate summary
    answer = generate_summary(full_text, length)

    # Save messages to session if session_id provided
    if req.session_id:
        user_id = _get_user_id(current_user, db)
        session = db.query(ChatSession).filter(ChatSession.id == req.session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        _check_ownership(session, user_id)

        length_labels = {"short": "Ngắn", "medium": "Vừa", "long": "Chi tiết"}
        user_msg = f"[Tóm tắt văn bản - Độ dài: {length_labels.get(length, 'Vừa')}]"
        db.add(ChatMessage(session_id=req.session_id, role="user", content=user_msg))
        db.add(ChatMessage(session_id=req.session_id, role="assistant", content=answer))
        if not session.title:
            session.title = f"Tóm tắt tài liệu"
        db.commit()

    return ChatResponse(result=ChatResult(answer=answer, sources=[]))
