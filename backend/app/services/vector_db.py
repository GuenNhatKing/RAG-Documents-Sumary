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


def search_similar_chunks(query: str, chunks: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
    """Searches and ranks chunks using cosine similarity on generated embeddings."""
    if not chunks:
        return []
        
    query_vector = get_embedding(query)
    
    chunk_vectors = []
    valid_chunks = []
    
    for chunk in chunks:
        vec_str = chunk.get("vector")
        if vec_str:
            try:
                vec = json.loads(vec_str)
                chunk_vectors.append(vec)
                valid_chunks.append(chunk)
            except Exception:
                pass
                
    if not chunk_vectors:
        return []
        
    # Compute similarity matrix
    q = np.array(query_vector)
    c = np.array(chunk_vectors)
    
    dot_products = np.dot(c, q)
    q_norm = np.linalg.norm(q)
    c_norms = np.linalg.norm(c, axis=1)
    
    c_norms[c_norms == 0] = 1e-9
    if q_norm == 0:
        q_norm = 1e-9
        
    similarities = dot_products / (q_norm * c_norms)
    
    # Sort and take top_k
    indices = np.argsort(similarities)[::-1][:top_k]
    
    results = []
    for idx in indices:
        chunk_data = valid_chunks[idx].copy()
        # Remove raw vector from response to save bandwidth
        if "vector" in chunk_data:
            del chunk_data["vector"]
        chunk_data["score"] = float(similarities[idx])
        results.append(chunk_data)
        
    return results
