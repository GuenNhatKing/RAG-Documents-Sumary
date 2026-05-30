import os
import json
import numpy as np
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer

# Cache model locally in data/models
MODEL_NAME = "all-MiniLM-L6-v2"
_model = None

def get_model() -> SentenceTransformer:
    """Lazy-load the SentenceTransformer model to save memory on startup."""
    global _model
    if _model is None:
        model_dir = os.path.join("data", "models")
        os.makedirs(model_dir, exist_ok=True)
        # Suppress symlink warning on Windows if not running as admin
        os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
        # Suppress HF unauthenticated Hub request warnings and disable telemetry
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        import warnings
        warnings.filterwarnings("ignore", message=".*unauthenticated requests.*")
        warnings.filterwarnings("ignore", category=UserWarning, module="huggingface_hub")
        _model = SentenceTransformer(MODEL_NAME, cache_folder=model_dir)
    return _model


def get_embeddings(texts: List[str]) -> List[List[float]]:
    """Generate dense embeddings for a list of texts."""
    model = get_model()
    embeddings = model.encode(texts, convert_to_numpy=True)
    return embeddings.tolist()


def get_embedding(text: str) -> List[float]:
    """Generate dense embedding for a single text."""
    model = get_model()
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding.tolist()


def chunk_markdown(text: str, max_chunk_size: int = 1000, overlap: int = 150) -> List[Dict[str, Any]]:
    """Chunks markdown text while preserving line numbers and supporting overlap."""
    lines = text.split("\n")
    chunks = []
    current_chunk = []
    current_len = 0
    start_line = 1
    
    for idx, line in enumerate(lines, 1):
        line_len = len(line)
        
        # If adding this line exceeds the max size, and we already have some text
        if current_len + line_len > max_chunk_size and current_chunk:
            chunk_text = "\n".join(current_chunk)
            end_line = start_line + len(current_chunk) - 1
            chunks.append({
                "text": chunk_text,
                "line_num": start_line,
                "end_line_num": end_line
            })
            
            # Backtrack to build the overlap
            overlap_lines = []
            overlap_len = 0
            for l in reversed(current_chunk):
                if overlap_len + len(l) < overlap:
                    overlap_lines.insert(0, l)
                    overlap_len += len(l) + 1
                else:
                    break
            
            current_chunk = overlap_lines + [line]
            current_len = sum(len(l) for l in current_chunk) + len(current_chunk) - 1
            start_line = idx - len(overlap_lines)
        else:
            current_chunk.append(line)
            current_len += line_len + 1  # Include newline character in size calculation
            
    # Add final chunk
    if current_chunk:
        chunk_text = "\n".join(current_chunk)
        end_line = start_line + len(current_chunk) - 1
        chunks.append({
            "text": chunk_text,
            "line_num": start_line,
            "end_line_num": end_line
        })
        
    return chunks


def keyword_overlap_score(query: str, text: str) -> float:
    """Calculates the percentage of unique query words that appear in the chunk text."""
    import re
    words = re.findall(r'\w+', query.lower())
    query_words = set(w for w in words if len(w) >= 2)
    if not query_words:
        return 0.0
    text_lower = text.lower()
    match_count = sum(1 for w in query_words if w in text_lower)
    return match_count / len(query_words)


def search_similar_chunks(query: str, chunks: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
    """Searches and ranks chunks using hybrid scoring (cosine similarity + 0.5 * keyword overlap)."""
    if not chunks:
        return []
        
    query_vector = get_embedding(query)
    
    # Pure Python helpers for cosine similarity to avoid NumPy Windows thread crashes
    def dot_product(v1, v2):
        return sum(x * y for x, y in zip(v1, v2))

    def magnitude(v):
        return sum(x * x for x in v) ** 0.5

    def cosine_similarity(v1, v2):
        mag1 = magnitude(v1)
        mag2 = magnitude(v2)
        if mag1 == 0 or mag2 == 0:
            return 0.0
        return dot_product(v1, v2) / (mag1 * mag2)

    results = []
    for chunk in chunks:
        vec_str = chunk.get("vector")
        if not vec_str:
            continue
            
        try:
            if isinstance(vec_str, str):
                vec = json.loads(vec_str)
            else:
                vec = vec_str
            
            cos = cosine_similarity(vec, query_vector)
            kw = keyword_overlap_score(query, chunk["text"])
            hybrid = cos + 0.5 * kw
            
            chunk_data = chunk.copy()
            if "vector" in chunk_data:
                del chunk_data["vector"]
            chunk_data["score"] = hybrid
            results.append(chunk_data)
        except Exception:
            pass
            
    # Sort and take top_k
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]

