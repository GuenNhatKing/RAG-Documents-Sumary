"""Master Tree service.

Stores summaries of all processed documents for cross-document search.
File: data/master_tree.json
Structure: {doc_id: {filename, summary, node_count, created_at}}
"""

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

from openai import OpenAI
from app.env import load_backend_env
from app.services.pageindex.utils import (
    generate_doc_description,
    create_clean_structure_for_description,
    structure_to_list,
    ConfigLoader,
)

load_backend_env()

MASTER_TREE_PATH = Path("data/master_tree.json")

_client = OpenAI(
    api_key=os.getenv("RAG_API_KEY") or os.getenv("LLM_API_KEY"),
    base_url=os.getenv("RAG_BASE_URL") or os.getenv("LLM_BASE_URL"),
)


def _get_extra_body() -> dict | None:
    """Trả về extra_body để bật/tắt chế độ suy nghĩ của mô hình tùy thuộc vào LLM_THINK."""
    rag_base_url = os.getenv("RAG_BASE_URL")
    if rag_base_url and "groq.com" in rag_base_url:
        return None
    llm_think = os.getenv("LLM_THINK", "true").lower()
    if llm_think == "false":
        return {"think": False}
    return None

LLM_MODEL = os.getenv("RAG_MODEL") or os.getenv("LLM_MODEL")


def _log(msg: str):
    print(f"[MASTER_TREE] {msg}", flush=True)


def load_master_tree() -> Dict[str, Any]:
    """Load master tree from disk. Returns empty dict if not exists."""
    if not MASTER_TREE_PATH.exists():
        return {}
    try:
        with open(MASTER_TREE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_master_tree(tree: Dict[str, Any]):
    """Save master tree to disk."""
    MASTER_TREE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MASTER_TREE_PATH, "w", encoding="utf-8") as f:
        json.dump(tree, f, ensure_ascii=False, indent=2)


def add_doc_to_master_tree(
    doc_id: str,
    filename: str,
    semantic_tree: Any,
):
    """Generate summary from semantic tree and add to master tree."""
    _log(f"Adding doc {doc_id} to master tree...")

    # Extract structure from tree data
    if isinstance(semantic_tree, dict) and "structure" in semantic_tree:
        structure = semantic_tree["structure"]
    else:
        structure = semantic_tree

    # Generate description using PageIndex utility
    try:
        clean_structure = create_clean_structure_for_description(structure)
        config_loader = ConfigLoader()
        opt = config_loader.load({})
        summary = generate_doc_description(clean_structure, model=opt.model)
    except Exception as e:
        _log(f"Warning: generate_doc_description failed: {e}")
        # Fallback: use first node title as summary
        nodes = structure_to_list(structure) if structure else []
        summary = nodes[0].get("title", filename) if nodes else filename

    # Count nodes
    nodes = structure_to_list(structure) if structure else []
    node_count = len(nodes)

    # Extract top headings (depth=0 node titles)
    top_titles = []
    if isinstance(structure, list):
        top_titles = [node.get("title", "") for node in structure if node.get("title")]
    elif isinstance(structure, dict):
        top_titles = [structure.get("title", "")] if structure.get("title") else []
    
    clean_top_titles = [t.strip() for t in top_titles if t.strip()]
    top_headings = ", ".join(clean_top_titles[:8]) # Limit to top 8 headings

    # Load and update
    tree = load_master_tree()
    tree[doc_id] = {
        "filename": filename,
        "summary": summary.strip(),
        "node_count": node_count,
        "top_headings": top_headings,
        "created_at": datetime.now().isoformat(),
    }
    save_master_tree(tree)
    _log(f"Doc {doc_id} added. Total docs: {len(tree)}")


def remove_doc_from_master_tree(doc_id: str):
    """Remove a document from the master tree."""
    tree = load_master_tree()
    if doc_id in tree:
        del tree[doc_id]
        save_master_tree(tree)
        _log(f"Doc {doc_id} removed. Total docs: {len(tree)}")


def search_master_tree(query: str) -> List[Dict[str, str]]:
    """Search master tree for documents relevant to the query.

    Returns list of {doc_id, filename, summary} sorted by relevance.
    """
    tree = load_master_tree()
    if not tree:
        return []

    # Build catalog for LLM
    catalog_lines = []
    for doc_id, info in tree.items():
        entry = f"- [{doc_id}] {info['filename']}: {info['summary']}"
        if "top_headings" in info and info["top_headings"]:
            entry += f" (Chủ đề chính: {info['top_headings']})"
        catalog_lines.append(entry)
    catalog = "\n".join(catalog_lines)

    prompt = f"""You are a document search assistant. Given a catalog of documents and a user query, find the most relevant documents.

DOCUMENT CATALOG:
{catalog}

USER QUERY: {query}

Reply EXACTLY in JSON (no markdown, no code blocks):
{{
    "relevant_docs": ["doc_id_1", "doc_id_2"]
}}

Rules:
- Return doc_ids that are relevant to the query, ordered by relevance (most relevant first).
- If no documents are relevant, return {{"relevant_docs": []}}.
- Only include doc_ids from the catalog above.
"""

    try:
        extra_body = _get_extra_body()
        response = _client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.0,
            extra_body=extra_body if extra_body else None,
        )
        content = response.choices[0].message.content
        if not content:
            return []

        # Clean response
        cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()
        result = json.loads(cleaned)
        doc_ids = result.get("relevant_docs", [])

        # Build results with info
        results = []
        for did in doc_ids:
            if did in tree:
                results.append({
                    "doc_id": did,
                    "filename": tree[did]["filename"],
                    "summary": tree[did]["summary"],
                })
        return results

    except Exception as e:
        _log(f"Search error: {e}")
        # Fallback: return all docs (let user pick)
        return [
            {"doc_id": did, "filename": info["filename"], "summary": info["summary"]}
            for did, info in tree.items()
        ]


def add_vector_doc_to_master_tree(
    doc_id: str,
    filename: str,
    markdown_text: str,
):
    """Generate summary from full markdown text and add vector doc to master tree."""
    _log(f"Adding vector doc {doc_id} to master tree...")
    
    from app.services.llm import generate_summary
    try:
        summary = generate_summary(markdown_text, length="medium")
    except Exception as e:
        _log(f"Warning: generate_summary failed: {e}")
        summary = filename
        
    # Extract top headings from markdown headings (lines starting with # or ##)
    top_titles = []
    for line in markdown_text.splitlines():
        if line.startswith("# ") or line.startswith("## "):
            title = line.lstrip("#").strip()
            if title:
                top_titles.append(title)
                if len(top_titles) >= 8:
                    break
                    
    top_headings = ", ".join(top_titles)
    
    # Load and update
    tree = load_master_tree()
    tree[doc_id] = {
        "filename": filename,
        "summary": summary.strip(),
        "node_count": len(top_titles),
        "top_headings": top_headings,
        "created_at": datetime.now().isoformat(),
    }
    save_master_tree(tree)
    _log(f"Vector doc {doc_id} added. Total docs: {len(tree)}")
