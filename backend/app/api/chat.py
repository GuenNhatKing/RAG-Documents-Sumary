import json
import os
import re
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session

from app.services.rag import reasoning_search_tree, build_context_from_markdown
from app.services.llm import generate_final_answer, generate_summary, generate_conversational_response
import unicodedata
from app.database import SessionLocal
from app.models import ChatSession, ChatMessage, User
from app.api.auth import get_current_user, TokenData

router = APIRouter()


def is_general_conversational(text: str) -> bool:
    s = text.lower().strip()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = s.replace('đ', 'd')
    s = re.sub(r'[^\w\s]', '', s)
    s = ' '.join(s.split())
    
    greetings = {
        "chao", "xin chao", "chao ban", "chao ad", "chao tro ly", "chao robot", 
        "hello", "hi", "hey", "good morning", "good afternoon", "good evening",
        "cam on", "cam on ban", "cam on ad", "cam on tro ly", "thank you", "thanks",
        "tam biet", "tam biet ban", "bye", "goodbye",
        "ban la ai", "ban ten la gi", "who are you", "what is your name",
        "ban co khoe khong", "khoe khong", "how are you"
    }
    if s in greetings:
        return True
        
    patterns = [
        r'^chao\b',
        r'^xin chao\b',
        r'^hello\b',
        r'^hi\b',
        r'^hey\b',
        r'^cam on\b',
        r'^thank\b',
    ]
    
    doc_keywords = ["tai lieu", "van ban", "tom tat", "doc", "tim", "hoi", "trang", "dong", "noi dung", "nguon"]
    has_doc_keyword = any(kw in s for kw in doc_keywords)
    if has_doc_keyword:
        return False
        
    for p in patterns:
        if re.search(p, s):
            return True
            
    return False


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
    from app.models import Document, DocumentStatus
    doc = db.query(Document).filter(Document.id == request.doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu.")

    markdown_path = doc.markdown_path
    json_path = doc.json_tree_path
    is_vector_db = (doc.status == DocumentStatus.VECTOR_PROCESSED)

    if is_vector_db:
        if not markdown_path or not os.path.exists(markdown_path):
            raise HTTPException(status_code=404, detail="Tài liệu chưa được xử lý (thiếu markdown).")
    else:
        if not markdown_path or not json_path or not os.path.exists(json_path) or not os.path.exists(markdown_path):
            raise HTTPException(status_code=404, detail="Tài liệu chưa được xử lý.")

    tree_data = None
    if not is_vector_db:
        with open(json_path, 'r', encoding='utf-8') as f:
            tree_data = json.load(f)

    session = None
    search_query = request.question
    if request.session_id:
        user_id = _get_user_id(current_user, db)
        session = db.query(ChatSession).filter(ChatSession.id == request.session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        _check_ownership(session, user_id)
        history = db.query(ChatMessage).filter(ChatMessage.session_id == request.session_id).order_by(ChatMessage.created_at.asc()).all()
        from app.services.llm import condense_query
        search_query = condense_query(request.question, history)

    if is_general_conversational(request.question):
        answer = generate_conversational_response(request.question)
        sources = []
    else:
        if is_vector_db:
            from app.models import DocumentChunk
            from app.services.vector_db import search_similar_chunks
            
            chunks_in_db = db.query(DocumentChunk).filter(DocumentChunk.doc_id == request.doc_id).all()
            chunks_dicts = [
                {
                    "text": c.text,
                    "line_num": c.line_num,
                    "vector": c.vector
                }
                for c in chunks_in_db
            ]
            
            # Retrieve top 5 similar chunks
            matched_chunks = search_similar_chunks(search_query, chunks_dicts, top_k=5)
            
            # Build context
            context_parts = []
            sources = []
            seen_files = set()
            filename = doc.filename
            
            for chunk in matched_chunks:
                start_l = chunk["line_num"]
                end_l = start_l + len(chunk["text"].split("\n")) - 1
                source_tag = f"[Nguồn: {filename}, Dòng: {start_l}-{end_l}]"
                context_parts.append(f"{source_tag}\n{chunk['text'].strip()}")
                
                # Check lines citation format
                line_range = f"{start_l}-{end_l}"
                sources.append(SourceDetail(file=filename, lines=line_range))
                
            context = "\n\n---\n\n".join(context_parts) if context_parts else ""
        else:
            node_list = reasoning_search_tree(tree_data, search_query)
            context = build_context_from_markdown(tree_data, node_list, markdown_path) if node_list else ""

            sources = []
            if context:
                seen_files: set[str] = set()
                for match in re.findall(r"\[Nguồn:\s*(.*?),\s*Dòng:\s*(.*?)\]", context):
                    filename = match[0].strip()
                    if filename not in seen_files:
                        seen_files.add(filename)
                        sources.append(SourceDetail(file=filename, lines=match[1].strip()))

        answer = generate_final_answer(context, search_query)

    if session:
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
    session = None
    search_query = req.question
    if req.session_id:
        user_id = _get_user_id(current_user, db)
        session = db.query(ChatSession).filter(ChatSession.id == req.session_id).first()
        if session and session.user_id == user_id:
            history = db.query(ChatMessage).filter(ChatMessage.session_id == req.session_id).order_by(ChatMessage.created_at.asc()).all()
            from app.services.llm import condense_query
            search_query = condense_query(req.question, history)

    if is_general_conversational(req.question):
        answer = generate_conversational_response(req.question)
        sources = []
        relevant_docs = []
    else:
        relevant_docs = search_master_tree(search_query)
        if not relevant_docs:
            return GlobalAskResponse(answer="Không tìm thấy tài liệu nào liên quan.", sources=[], relevant_docs=[])

        # Build context from top docs
        context_parts = []
        from app.models import Document
        import concurrent.futures

        # Query documents from Database in main thread for thread-safety
        docs_to_process = []
        for doc_info in relevant_docs[:3]:
            doc_id = doc_info["doc_id"]
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if doc and doc.markdown_path and os.path.exists(doc.markdown_path):
                # Allow if either VECTOR_PROCESSED or both tree_path and tree file exists
                if doc.status == DocumentStatus.VECTOR_PROCESSED or (doc.json_tree_path and os.path.exists(doc.json_tree_path)):
                    docs_to_process.append({
                        "doc_id": doc_id,
                        "filename": doc_info["filename"],
                        "status": doc.status,
                        "json_path": doc.json_tree_path,
                        "markdown_path": doc.markdown_path,
                        "question": search_query
                    })

        def process_doc_thread(doc_item: dict) -> Optional[str]:
            try:
                from app.models import DocumentStatus
                if doc_item["status"] == DocumentStatus.VECTOR_PROCESSED:
                    from app.models import DocumentChunk
                    from app.services.vector_db import search_similar_chunks
                    
                    # Create a new session for the thread to avoid concurrent DB access on same session
                    thread_db = SessionLocal()
                    try:
                        chunks_in_db = thread_db.query(DocumentChunk).filter(DocumentChunk.doc_id == doc_item["doc_id"]).all()
                        chunks_dicts = [
                            {
                                "text": c.text,
                                "line_num": c.line_num,
                                "vector": c.vector
                            }
                            for c in chunks_in_db
                        ]
                        matched_chunks = search_similar_chunks(doc_item["question"], chunks_dicts, top_k=5)
                        
                        context_parts = []
                        filename = doc_item["filename"]
                        for chunk in matched_chunks:
                            start_l = chunk["line_num"]
                            end_l = start_l + len(chunk["text"].split("\n")) - 1
                            source_tag = f"[Nguồn: {filename}, Dòng: {start_l}-{end_l}]"
                            context_parts.append(f"{source_tag}\n{chunk['text'].strip()}")
                        
                        if context_parts:
                            return f"=== Tài liệu: {filename} ===\n" + "\n\n---\n\n".join(context_parts)
                    finally:
                        thread_db.close()
                else:
                    with open(doc_item["json_path"], 'r', encoding='utf-8') as f:
                        tree_data = json.load(f)
                    node_list = reasoning_search_tree(tree_data, doc_item["question"])
                    if node_list:
                        ctx = build_context_from_markdown(tree_data, node_list, doc_item["markdown_path"])
                        if ctx:
                            return f"=== Tài liệu: {doc_item['filename']} ===\n{ctx}"
            except Exception as e:
                print(f"Error processing doc {doc_item['filename']} in thread: {e}", flush=True)
            return None

        if docs_to_process:
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(docs_to_process)) as executor:
                # executor.map preserves the original order of items
                thread_results = list(executor.map(process_doc_thread, docs_to_process))
                for res in thread_results:
                    if res:
                        context_parts.append(res)

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
            answer = generate_final_answer(combined_context, search_query)
        except Exception:
            answer = "Lỗi khi tạo câu trả lời."

    # Save messages to session if session_id provided
    if session:
        db.add(ChatMessage(session_id=req.session_id, role="user", content=req.question))
        sources_json = json.dumps([{"file": s.file, "lines": s.lines} for s in sources]) if sources else None
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
    from app.models import Document
    doc = db.query(Document).filter(Document.id == req.doc_id).first()
    if not doc or not doc.markdown_path:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu.")
    markdown_path = doc.markdown_path

    if not os.path.exists(markdown_path):
        raise HTTPException(status_code=404, detail="Không tìm thấy file markdown.")

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
