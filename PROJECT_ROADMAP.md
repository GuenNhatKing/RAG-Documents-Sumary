# PROJECT ROADMAP

## Tổng quan

Triển khai hệ thống Agentic Vectorless Retrieval-Augmented Generation (RAG) sử dụng:

- PageIndex (Semantic Tree)
- OpenRouter API

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

## PHASE 0 — KHỞI TẠO MÔI TRƯỜNG

### Task 0.1 — Khởi tạo Backend Core

**Input:**

Project rỗng.

**Output:**

Khởi tạo cấu trúc backend FastAPI bao gồm:

- FastAPI
- SQLAlchemy
- Redis
- Celery
- OpenRouter Integration
- PageIndex
- OCR libraries

#### requirements.txt

fastapi
uvicorn
sqlalchemy
alembic
requests
tenacity
pageindex
redis
celery
pymupdf
pdfplumber
python-docx
pytesseract
pillow

**Done Condition (Task 0.1):**

- pip install -r requirements.txt chạy thành công.
- uvicorn app.main:app --reload hoạt động.
- Redis kết nối thành công.
- Celery worker start thành công.

---

## PHASE 1 — DOCUMENT INGESTION & SEMANTIC TREE

### Task 1.1 — Xây dựng Upload Pipeline

**Input:**

File upload:

- PDF
- DOCX
- PNG/JPG scan

**Output:**

File được lưu vào:

data/raw/

Ví dụ:

data/raw/luat-xay-dung.pdf

**Done Condition (Task 1.1):**

- Upload API hoạt động.
- File được lưu chính xác.
- DB tạo document record trạng thái pending.

---

### Task 1.2 — OCR & Extract Text Pipeline

**Input:**

Raw document từ:

data/raw/

**Output:**

Extract toàn bộ text từng trang và lưu vào:

`data/extracted_text/<document_id>/`

Ví dụ:

page_001.txt
page_002.txt

**Important Rules:**

- Mỗi trang là 1 file riêng.
- Không gộp toàn bộ text thành 1 file lớn.
- Hỗ trợ page-level retrieval.

**Done Condition (Task 1.2):**

- PDF scan OCR thành công.
- Extract text chính xác.
- Có thể đọc riêng từng trang.

---

### Task 1.3 — Build run_pageindex.py

**Input:**

PDF path.

**Output:**

Generate Semantic Tree JSON bằng thư viện pageindex.

Lưu tại:

`data/semantic_trees/<document_id>.json`

**Semantic Tree Requirements:**

Mỗi node phải có:

- id
- title
- summary
- page_start
- page_end
- children

**Done Condition (Task 1.3):**

- PDF lớn được convert thành semantic hierarchy.
- JSON tree phản ánh cấu trúc tài liệu thực tế.
- Root → Section → Subsection → Leaf nodes đầy đủ.

---

### Task 1.4 — Update Database Schema

**Input:**

SQLAlchemy Document model.

**Output:**

Schema mới:

class Document(Base):
    id
    filename
    raw_file_path
    json_tree_path
    extracted_text_path
    total_pages
    status
    created_at

**Status Lifecycle:**

- pending
- processing
- processed
- error

**Important Rules:**

KHÔNG sử dụng:

- pgvector
- pg_trgm
- embeddings
- vector columns

**Done Condition (Task 1.4):**

- Migration chạy thành công.
- SQLite/PostgreSQL hoạt động bình thường.
- Không có vector dependency.

---

## PHASE 2 — RECURSIVE REASONING RETRIEVAL

### Task 2.1 — Tree Navigation Engine

**File:**

app/services/rag.py

**Input:**

- User query
- Semantic Tree JSON (Cấu trúc phân cấp với thuộc tính line_num)

**Output:**

Function:

`reasoning_search_tree(tree, query)`

**Recursive Reasoning Flow:**

#### Step 1 — Root-Level Reasoning

OpenRouter LLM chỉ đọc:

- Root nodes
- Chapter/Section titles
- Summaries (summary hoặc prefix_summary)

KHÔNG load toàn bộ tree hay text thô.
LLM xác định chapter/section liên quan nhất với câu hỏi.

---

##### Step 2 — Subtree Traversal

Chỉ load subtree liên quan.

Ví dụ:

Chương 2 → Mục 2.1

---

##### Step 3 — Leaf Retrieval & Line Boundary Detection

Khi LLM chốt được các target Node IDs, hệ thống thực hiện Semantic Chunking:

- Tìm dòng bắt đầu (Start Line = `line_num` của node hiện tại).
- Tìm dòng kết thúc (End Line = `line_num` của node kế tiếp liền kề - 1).

**Important Rules:**

- Tuyệt đối không cosine similarity.
- Không embedding search.
- Không ANN search.
- Không semantic vector retrieval.

**Done Condition (Task 2.1):**

- System tìm đúng section bằng reasoning.
- Phân định ranh giới dòng (line boundaries) chính xác.
- Token usage cực thấp.

---

### Task 2.2 — Context Builder

**File:**

app/services/rag.py (Function: `build_context_from_markdown`)

**Input:**

- Danh sách Target Node IDs cùng ranh giới dòng (Start/End).
- File Markdown gốc: `data/markdown_docs/[doc_id].md`

**Output:**

Formatted context string:

[Nguồn: e651cdac-b5a5-4ffe-bb0b-e7564f1d1a53.md, Dòng: 22-23]
Nội dung trích xuất...

**Responsibilities:**

- Trích xuất chính xác theo Line Index.
- Merge contexts (Gộp các đoạn text nếu LLM chọn nhiều Node).
- Remove overlapping ranges (Khử trùng lặp nếu các dòng giao nhau).
- Compress token & Prevent overflow (Cắt gọn nội dung lố, lấy đúng "ngăn kéo" thông tin).

**Important Rules:**

- Context phải deterministic (Trích xuất 100 lần kết quả y như nhau).
- Citation (Đánh dấu nguồn & số dòng) là bắt buộc ở đầu mỗi đoạn.
- Không hallucinated source (Chỉ trích xuất text có thật từ file MD).

**Done Condition (Task 2.2):**

- Trích xuất đúng đoạn hội thoại/điều khoản mà không bị lẹm sang phần khác.
- OpenRouter nhận context "sạch" và cực kỳ cô đọng.
- Citation mapping chính xác tới từng số dòng.

---

## PHASE 3 — OPENROUTER AGENTIC CHAT

### Task 3.1 — LLM Generation Service

**File:**

app/services/llm.py

**Input:**

- System Prompt
- Context Builder output
- User query

**Output:**

Final answer generation bằng:

openrouter/free

**Important Rules:**

LLM:

- CHỈ được trả lời từ provided context.
- KHÔNG tự suy diễn ngoài context.
- Bắt buộc citation.

**Done Condition (Task 3.1):**

- Hallucination giảm tối đa.
- Citation luôn tồn tại.
- Output ổn định.

---

### Task 3.2 — POST /chat/ask

**Input:**

    {
      \"doc_id\": \"string\",
      \"question\": \"string\"
    }

**Output:**

    {
      \"result\": {
        \"answer\": \"string\",
        \"sources\": [
          {
            \"lines\": \"22-23\",
            \"file\": \"e651cdac-b5a5-4ffe-bb0b-e7564f1d1a53.md\"
          }
        ]
      }
    }

**Done Condition (Task 3.2):**

- HTTP 200 thành công.
- Citation đúng dòng.
- Response time ổn định.

---

### Task 3.3 — Retry & Error Handling

**Input:**

- 429 errors
- 503 errors
- Network timeout

**Output:**

Retry wrappers bằng:

tenacity

**Retry Strategy:**

- exponential backoff
- retry_if_exception_type
- max retry limit

**Done Condition (Task 3.3):**

- Auto retry hoạt động.
- Graceful degradation.
- Không crash worker.

---

## PHASE 4 — FRONTEND & UI

### Task 4.1 — Upload UI

**Features:**

- Drag & Drop
- Upload progress
- Retry upload
- Processing status

**Auto Flow:**

Upload thành công sẽ tự động:

- OCR
- Extract text
- Build tree

**Done Condition (Task 4.1):**

- UI realtime update trạng thái.
- Người dùng thấy:
  - pending
  - processing
  - processed
  - error

---

### Task 4.2 — Chat UI

**Features:**

- Streaming response
- Citation rendering
- Chat history

**Citation Behavior:**

Click:

[Trang 12]

sẽ mở PDF đúng trang.

**Done Condition (Task 4.2):**

- Citation clickable.
- PDF jump hoạt động.
- UX ổn định.

---

## PHASE 5 — TESTING & STABILITY

### Task 5.1 — Unit Tests

Coverage yêu cầu:

>= 80%

**Required Test Areas:**

- OCR
- Tree generation
- Recursive traversal
- Context builder
- Citation mapping
- OpenRouter wrapper
- Retry logic

---

### Task 5.2 — Integration Tests

Test toàn bộ flow:

Upload PDF
→ OCR
→ Semantic Tree
→ Recursive Retrieval
→ OpenRouter
→ Final Answer

**Done Condition (Task 5.2):**

- Full pipeline hoạt động.
- Không token overflow.
- Citation chính xác.

---

## ACCEPTANCE CRITERIA

Hệ thống phải đảm bảo:

- ZERO vector similarity search.
- ZERO embeddings retrieval.
- ZERO pgvector.
- ZERO pg_trgm.

Pipeline hoàn chỉnh:

PDF Upload
→ OCR
→ Extract Text
→ Semantic Tree
→ Recursive Reasoning
→ Context Builder
→ OpenRouter Answer
→ Citation Output

Hệ thống phải:

- Explainable
- Token-efficient
- Hierarchical reasoning
- Citation-accurate
- Production-ready

---

## ENVIRONMENT VARIABLES

  DATABASE_URL=sqlite:///./database.db
  REDIS_URL=redis://localhost:6379/0
  OPENROUTER_API_KEY=your_openrouter_api_key_here
  JWT_SECRET=your_jwt_secret_here
