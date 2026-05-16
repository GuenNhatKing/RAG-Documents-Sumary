import json
import os
import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

from app.services.rag import reasoning_search_tree, build_context_from_markdown
from app.services.llm import generate_final_answer

router = APIRouter()

class ChatRequest(BaseModel):
    doc_id: str
    question: str

class SourceDetail(BaseModel):
    lines: str
    file: str

class ChatResult(BaseModel):
    answer: str
    sources: List[SourceDetail]

class ChatResponse(BaseModel):
    result: ChatResult

@router.post("/ask", response_model=ChatResponse)
async def ask_document(request: ChatRequest):
    json_path = f"/work/backend/data/semantic_trees/{request.doc_id}.json"
    markdown_path = f"/work/data/markdown_docs/{request.doc_id}.md"

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

    return ChatResponse(
        result=ChatResult(
            answer=answer,
            sources=sources
        )
    )
