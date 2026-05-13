# AI RAG SYSTEM ROADMAP (VECTORLESS RAG)

## Tổng quan

Triển khai hệ thống Agentic Vectorless Retrieval-Augmented Generation (RAG) sử dụng:

- PageIndex (Semantic Tree)
- Gemini 1.5 Flash

Kiến trúc này loại bỏ hoàn toàn:

- Vector Database
- Embedding Similarity Search
- pgvector
- pg_trgm

Thay vào đó, hệ thống sử dụng:

- Semantic Tree Traversal
- Recursive Reasoning
- Page-Level Retrieval
- LLM-based Navigation

để điều hướng tài liệu theo cấu trúc phân cấp thực tế.

---

# PHASE 0 — KHỞI TẠO MÔI TRƯỜNG

## Task 0.1 — Khởi tạo Backend Core

### Input

Project rỗng.

### Output

Khởi tạo cấu trúc backend FastAPI bao gồm:

- FastAPI
- SQLAlchemy
- Redis
- Celery
- Gemini SDK
- PageIndex
- OCR libraries

### requirements.txt

```txt
fastapi
uvicorn
sqlalchemy
alembic
google-generativeai
tenacity
pageindex
redis
celery
pymupdf
pdfplumber
python-docx
pytesseract
pillow
```

### Done Condition

- `pip install -r requirements.txt` chạy thành công.
- `uvicorn app.main:app --reload` hoạt động.
- Redis kết nối thành công.
- Celery worker start thành công.

---

# PHASE 1 — DOCUMENT INGESTION & SEMANTIC TREE

---

## Task 1.1 — Xây dựng Upload Pipeline

### Input

File upload:

- PDF
- DOCX
- PNG/JPG scan

### Output

File được lưu vào:

```text
data/raw/
```

Ví dụ:

```text
data/raw/luat-xay-dung.pdf
```

### Done Condition

- Upload API hoạt động.
- File được lưu chính xác.
- DB tạo document record trạng thái `pending`.

---

## Task 1.2 — OCR & Extract Text Pipeline

### Input

Raw document từ:

```text
data/raw/
```

### Output

Extract toàn bộ text từng trang và lưu vào:

```text
data/extracted_text/<document_id>/
```

Ví dụ:

```text
page_001.txt
page_002.txt
```

### Important Rules

- Mỗi trang là 1 file riêng.
- Không gộp toàn bộ text thành 1 file lớn.
- Hỗ trợ page-level retrieval.

### Done Condition

- PDF scan OCR thành công.
- Extract text chính xác.
- Có thể đọc riêng từng trang.

---

## Task 1.3 — Build `run_pageindex.py`

### Input

PDF path.

### Output

Generate Semantic Tree JSON bằng thư viện `pageindex`.

Lưu tại:

```text
data/semantic_trees/<document_id>.json
```

### Semantic Tree Requirements

Mỗi node phải có:

- id
- title
- summary
- page_start
- page_end
- children

### Done Condition

- PDF lớn được convert thành semantic hierarchy.
- JSON tree phản ánh cấu trúc tài liệu thực tế.
- Root → Section → Subsection → Leaf nodes đầy đủ.

---

## Task 1.4 — Update Database Schema

### Input

SQLAlchemy `Document` model.

### Output

Schema mới:

```python
class Document(Base):
    id
    filename
    raw_file_path
    json_tree_path
    extracted_text_path
    total_pages
    status
    created_at
```

### Status Lifecycle

```text
pending
processing
processed
error
```

### Important Rules

KHÔNG sử dụng:

- pgvector
- pg_trgm
- embeddings
- vector columns

### Done Condition

- Migration chạy thành công.
- SQLite/PostgreSQL hoạt động bình thường.
- Không có vector dependency.

---

# PHASE 2 — RECURSIVE REASONING RETRIEVAL

---

## Task 2.1 — Tree Navigation Engine

### File

```text
app/services/rag.py
```

### Input

- User query
- Semantic Tree JSON

### Output

Function:

```python
reasoning_search_tree(tree, query)
```

### Recursive Reasoning Flow

#### Step 1 — Root-Level Reasoning

Gemini chỉ đọc:

- Root nodes
- Chapter titles
- Summaries

KHÔNG load toàn bộ tree.

Gemini xác định chapter liên quan.

---

#### Step 2 — Subtree Traversal

Chỉ load subtree liên quan.

Ví dụ:

```text
Chương 2 → Mục 2.1
```

---

#### Step 3 — Leaf Retrieval

Chỉ khi tới leaf node mới load:

```text
data/extracted_text/page_xxx.txt
```

---

### Important Rules

- Tuyệt đối không cosine similarity.
- Không embedding search.
- Không ANN search.
- Không semantic vector retrieval.

### Done Condition

- System tìm đúng section bằng reasoning.
- Chỉ load context cần thiết.
- Token usage thấp.

---

## Task 2.2 — Context Builder

### Input

Leaf nodes từ retrieval engine.

### Output

Formatted context:

```text
[Nguồn: Luat-Xay-Dung.pdf, Trang 12]
```

### Responsibilities

- Merge contexts
- Remove duplicates
- Sort relevance
- Compress token
- Prevent overflow

### Important Rules

- Context phải deterministic.
- Citation bắt buộc.
- Không hallucinated source.

### Done Condition

- Gemini nhận context sạch.
- Không vượt token limit.
- Citation mapping chính xác.

---

# PHASE 3 — GEMINI AGENTIC CHAT

---

## Task 3.1 — LLM Generation Service

### File

```text
app/services/llm.py
```

### Input

- System Prompt
- Context Builder output
- User query

### Output

Final answer generation bằng:

```text
gemini-1.5-flash
```

### Important Rules

LLM:

- CHỈ được trả lời từ provided context.
- KHÔNG tự suy diễn ngoài context.
- Bắt buộc citation.

### Done Condition

- Hallucination giảm tối đa.
- Citation luôn tồn tại.
- Output ổn định.

---

## Task 3.2 — POST `/chat/ask`

### Input

```json
{
  "pdf_name": "string",
  "question": "string"
}
```

### Output

```json
{
  "answer": "string",
  "sources": [
    {
      "page": 12,
      "file": "luat.pdf"
    }
  ]
}
```

### Done Condition

- HTTP 200 thành công.
- Citation đúng trang.
- Response time ổn định.

---

## Task 3.3 — Retry & Error Handling

### Input

- 429 errors
- 503 errors
- Network timeout

### Output

Retry wrappers bằng:

```python
tenacity
```

### Retry Strategy

- exponential backoff
- retry_if_exception_type
- max retry limit

### Done Condition

- Auto retry hoạt động.
- Graceful degradation.
- Không crash worker.

---

# PHASE 4 — FRONTEND & UI

---

## Task 4.1 — Upload UI

### Features

- Drag & Drop
- Upload progress
- Retry upload
- Processing status

### Auto Flow

Upload thành công sẽ tự động:

- OCR
- Extract text
- Build tree

### Done Condition

- UI realtime update trạng thái.
- Người dùng thấy:
  - pending
  - processing
  - processed
  - error

---

## Task 4.2 — Chat UI

### Features

- Streaming response
- Citation rendering
- Chat history

### Citation Behavior

Click:

```text
[Trang 12]
```

sẽ mở PDF đúng trang.

### Done Condition

- Citation clickable.
- PDF jump hoạt động.
- UX ổn định.

---

# PHASE 5 — TESTING & STABILITY

---

## Task 5.1 — Unit Tests

Coverage yêu cầu:

```text
>= 80%
```

### Required Test Areas

- OCR
- Tree generation
- Recursive traversal
- Context builder
- Citation mapping
- Gemini wrapper
- Retry logic

---

## Task 5.2 — Integration Tests

Test toàn bộ flow:

```text
Upload PDF
→ OCR
→ Semantic Tree
→ Recursive Retrieval
→ Gemini
→ Final Answer
```

### Done Condition

- Full pipeline hoạt động.
- Không token overflow.
- Citation chính xác.

---

# ACCEPTANCE CRITERIA

Hệ thống phải đảm bảo:

- ZERO vector similarity search.
- ZERO embeddings retrieval.
- ZERO pgvector.
- ZERO pg_trgm.

Pipeline hoàn chỉnh:

```text
PDF Upload
→ OCR
→ Extract Text
→ Semantic Tree
→ Recursive Reasoning
→ Context Builder
→ Gemini Answer
→ Citation Output
```

Hệ thống phải:

- Explainable
- Token-efficient
- Hierarchical reasoning
- Citation-accurate
- Production-ready