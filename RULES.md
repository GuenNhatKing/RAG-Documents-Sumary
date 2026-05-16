# QUY TẮC KIẾN TRÚC & THỰC THI CHO AI AGENT

## 0. CORE PRINCIPLES

## 0.1 AI Agent KHÔNG được tự suy đoán kiến trúc

TRƯỚC KHI CODE, BẮT BUỘC:

- Đọc toàn bộ codebase hiện tại.
- Đọc `RULES.md`.
- Đọc `PROJECT_PLAN.md`.
- Đọc `PROJECT_ROADMAP.md`.
- Đọc `NOTE.md`.
- Hiểu chính xác workflow của:
  - `pageindex`
  - recursive reasoning retrieval
  - semantic tree traversal
  - extracted text pipeline

BẮT BUỘC hiểu:

- semantic tree hierarchy
- node traversal flow
- recursive retrieval
- page-level retrieval
- citation mapping
- context builder flow

KHÔNG:

- tự đổi architecture
- tự đổi retrieval flow
- tự đổi semantic tree structure
- tự đổi storage structure
- tự đổi naming convention
- tự tạo abstraction mới
- tự thêm vector database
- tự thêm embedding retrieval
- tự thay framework indexing

Nếu requirement chưa rõ:

- PHẢI dừng
- PHẢI clarify ambiguity trước khi code

---

## 0.2 Repository luôn phải ở trạng thái chạy được

MỌI THỜI ĐIỂM:

- backend phải boot được
- frontend phải build được
- celery worker phải start được
- imports không lỗi
- tests phải pass
- migrations không fail

CẤM:

- commit broken state
- commit unfinished critical logic
- commit TODO architecture
- commit partially migrated architecture

---

## 0.3 Thứ tự ưu tiên tuyệt đối

  Correctness
  > Retrieval Accuracy
  > Citation Accuracy
  > Stability
  > Deterministic Retrieval
  > Testability
  > Maintainability
  > Performance
  > Optimization

---

## 1. QUY TẮC KIẾN TRÚC VECTORLESS RAG (CRITICAL)

## 1.1 CẤM Vector Database

TUYỆT ĐỐI KHÔNG được dùng:

- Pinecone
- ChromaDB
- FAISS
- Milvus
- Weaviate
- Qdrant
- Elasticsearch vector search
- pgvector
- embedding retrieval
- semantic vector search
- ANN search

CẤM:

- generate embeddings để retrieval
- cosine similarity retrieval
- dense retrieval
- hybrid retrieval
- vector indexing
- reranking bằng embeddings

---

## 1.2 CẤM PostgreSQL / SQLite Search Features

KHÔNG được dùng:

- TSVECTOR
- ts_rank
- PostgreSQL Full Text Search
- pg_trgm
- trigram similarity
- BM25 extensions
- search_vector columns
- SQLite FTS retrieval

Database KHÔNG phải search engine.

Database CHỈ lưu metadata.

---

## 1.3 Retrieval Architecture BẮT BUỘC: VECTORLESS RAG

Hệ thống BẮT BUỘC sử dụng:

- `pageindex`
- semantic tree traversal
- recursive reasoning
- page-level retrieval

Nguồn chính thức:

- [PageIndex on GitHub](https://github.com/VectifyAI/PageIndex)

TRƯỚC KHI CODE:

- BẮT BUỘC đọc `PAGE_INDEX_README.md`
- BẮT BUỘC hiểu:
  - semantic tree
  - node hierarchy
  - subtree traversal
  - leaf extraction
  - retrieval flow
  - recursive reasoning

QUAN TRỌNG:

- "PageIndex" KHÔNG có nghĩa là lưu từng page vào database.
- "PageIndex" là framework semantic indexing dạng tree hierarchy.

---

## 1.4 Retrieval Flow chuẩn (BẮT BUỘC)

  Upload PDF/DOCX/Image
   ↓
  Store Raw File
   ↓
  OCR / Text Extraction
   ↓
  Store Extracted Page Text
   ↓
  pageindex processing
   ↓
  Semantic Tree JSON
   ↓
  Store Semantic Tree
   ↓
  Root-Level Reasoning
   ↓
  Subtree Traversal
   ↓
  Leaf Node Retrieval
   ↓
  Context Builder
   ↓
  Gemini Answer Generation
   ↓
  Citation Output

CẤM:

- custom retrieval pipeline khác flow trên
- bypass semantic tree
- direct OCR full retrieval
- vector retrieval fallback
- full document prompt injection
- load toàn bộ semantic tree vào một prompt lớn

---

## 1.5 Retrieval Unit = Leaf Node

CẤM:

- random chunking
- semantic chunking
- token chunking
- sliding window
- fixed chunk size retrieval

Ví dụ CẤM:

  500 tokens/chunk

BẮT BUỘC:

- retrieval theo leaf nodes trong semantic tree

Lý do:

- deterministic retrieval
- semantic hierarchy preservation
- explainability
- traceability
- citation accuracy

---

## 1.6 Recursive Reasoning là bắt buộc

Retrieval PHẢI theo cơ chế:

  Root Nodes
  → Relevant Chapter
  → Relevant Section
  → Leaf Node
  → Extracted Text

LLM KHÔNG được:

- đọc toàn bộ tree
- đọc toàn bộ document
- đọc toàn bộ extracted text

Mục tiêu:

- giảm token usage
- tăng retrieval accuracy
- tăng explainability
- tránh context overflow

---

## 1.7 Semantic Tree là Source of Truth

Semantic Tree JSON là nguồn dữ liệu chính cho:

- retrieval
- citation
- semantic navigation
- hierarchy traversal
- context building

CẤM:

- infer hierarchy bằng LLM
- generate fake semantic structure
- manual semantic reconstruction
- tự tạo synthetic nodes

---

## 1.8 Extracted Text là Deep Reading Source

Semantic Tree chỉ dùng cho:

- navigation
- reasoning
- hierarchy selection

Extracted text mới là nguồn:

- paragraph retrieval
- detailed reading
- final grounding

BẮT BUỘC:

    `data/extracted_text/<document_id>/page_xxx.txt`

---

## 1.9 Citation là BẮT BUỘC

MỌI câu trả lời AI PHẢI có citation.

Format DUY NHẤT được phép:

  [Nguồn: `<filename>`, Trang `<page_number>`]

Ví dụ:

  [Nguồn: Luat-Xay-Dung.pdf, Trang 12]

Citation phải mapping đúng:

- filename
- page number
- leaf node source

Citation sai = SYSTEM FAILURE.

---

## 1.10 Không có context → từ chối trả lời

Nếu retrieval không đủ context:

BẮT BUỘC trả:

  Không tìm thấy thông tin trong tài liệu.

CẤM:

- hallucination
- suy diễn
- trả lời theo pretrained knowledge
- dùng world knowledge
- fabricate citations

---

## 1.11 LLM không được truy cập internet

LLM chỉ được dùng:

- retrieved context
- user query
- system prompt

CẤM:

- browsing
- internet search
- external web tools
- online retrieval

---

## 1.12 PageIndex output phải persistent

BẮT BUỘC lưu:

- semantic tree JSON
- node metadata
- hierarchy structure
- page mappings

Ví dụ:

    `data/semantic_trees/<document_id>.json`

---

## 1.13 Không modify internal structure của PageIndex

CẤM:

- monkey patch pageindex
- rewrite parser internals
- custom hierarchy rewrite
- patch semantic node structure

Trừ khi:

- có RFC rõ ràng
- được approve trước

---

## 1.14 Nếu PageIndex fail → fail gracefully

KHÔNG:

- fallback fake indexing
- fallback hallucinated hierarchy
- fallback vector retrieval

BẮT BUỘC:

- return processing error
- log error
- mark document status = error

---

## 2. QUY TẮC DATABASE & STORAGE

## 2.1 Database CHỈ lưu metadata

Database chỉ được dùng cho:

- users
- auth
- document metadata
- processing status
- audit logs

CẤM lưu:

- chunks
- vectors
- embeddings
- OCR corpus
- semantic trees
- retrieval index
- extracted text pages

---

## 2.2 Semantic Tree phải lưu thành file vật lý

BẮT BUỘC:

  data/semantic_trees/

Ví dụ:

    `data/semantic_trees/<document_id>.json`

---

## 2.3 Extracted Text phải lưu riêng từng trang

BẮT BUỘC:

    `data/extracted_text/<document_id>/page_001.txt`

CẤM:

- single giant text file
- merged OCR corpus
- database text storage

---

## 2.4 Storage separation bắt buộc

|Data Type|Storage|
|---|---|
|Raw PDF/DOCX/Image|`data/raw/`|
|Semantic Tree JSON|`data/semantic_trees/`|
|Extracted Page Text|`data/extracted_text/`|
|Metadata|SQLite/PostgreSQL|

---

## 3. QUY TẮC BACKEND

## 3.1 Architecture bắt buộc

  API
   ↓
  Service
   ↓
  Repository
   ↓
  Database

---

## 3.2 Không viết business logic trong route

CẤM:

def upload():
  @app.post("/upload")
  def upload():
    # pageindex logic

Đúng:

- route chỉ nhận request/response
- business logic ở service layer

---

## 3.3 Separation of Concerns bắt buộc

|Layer|Responsibility|
|---|---|
|API|HTTP|
|Service|business logic|
|Repository|DB metadata access|
|Model|schema|
|Worker|async jobs|

---

## 3.4 Type hints bắt buộc

Ví dụ:

  def process_document(document_id: UUID) -> ProcessingResult:

---

## 3.5 Không hardcode config

CẤM:

  API_KEY = "abc"

BẮT BUỘC:

- `.env`
- settings layer

---

## 3.6 Queue-based processing bắt buộc

OCR + PageIndex processing PHẢI chạy async bằng:

- Celery
- Redis queue

CẤM:

- synchronous PDF processing trong HTTP request

---

## 4. QUY TẮC TASK EXECUTION

## 4.1 Một task chỉ làm MỘT việc

Ví dụ đúng:

  Create upload validator

Ví dụ sai:

  Build entire ingestion pipeline

---

## 4.2 Mỗi task ≤ 150 LOC

Nếu vượt:

- chia nhỏ task

---

## 4.3 Không sửa nhiều subsystem cùng lúc

CẤM:

- OCR + RAG + Frontend trong cùng task

---

## 4.4 Mỗi task bắt buộc có test

KHÔNG merge nếu:

- không có test

---

## 4.5 Không tự refactor lớn

Nếu chưa hiểu toàn hệ thống:

- KHÔNG rename lớn
- KHÔNG đổi architecture
- KHÔNG tạo abstraction mới

---

## 5. QUY TẮC TESTING

## 5.1 Test ngay sau mỗi task

KHÔNG:

- dồn test cuối phase

---

## 5.2 Không merge nếu test fail

---

## 5.3 Mock LLM trong CI

CẤM:

- gọi Gemini API thật trong pipeline

---

## 5.4 Hallucination tests bắt buộc

Ví dụ:

  Ask nonexistent regulation

Expected:

  Không tìm thấy thông tin trong tài liệu.

---

## 5.5 Citation accuracy tests bắt buộc

PHẢI verify:

- filename đúng
- page number đúng
- node mapping đúng
- extracted text đúng nguồn

---

## 5.6 Recursive traversal tests bắt buộc

PHẢI verify:

- root reasoning
- subtree traversal
- leaf retrieval
- token reduction

---

## 6. QUY TẮC GIT & VERSION CONTROL

## 6.1 Commit sau mỗi task hoàn thành

Workflow bắt buộc:

  Read Task
   ↓
  Implement
   ↓
  Run Tests
   ↓
  Fix Errors
   ↓
  Tests Pass
   ↓
  git diff
   ↓
  Commit

---

## 6.2 Không commit broken state

CẤM commit nếu:

- build fail
- import fail
- test fail
- migration fail
- startup fail

---

## 6.3 Conventional Commits bắt buộc

Format:

  type(scope): message

Ví dụ:

  feat(upload): add upload endpoint
  fix(rag): correct leaf node traversal
  docs(pageindex): add semantic tree documentation

---

## 6.4 Một commit = một concern

CẤM:

- mixed unrelated changes

---

## 6.5 Không commit secrets

CẤM:

- `.env`
- API keys
- passwords
- JWT secrets

BẮT BUỘC:

- `.gitignore`

---

## 6.6 Check git diff trước commit

BẮT BUỘC:

  git diff

Kiểm tra:

- accidental edits
- secrets
- debug code
- unrelated changes

---

## 6.7 Branch strategy bắt buộc

|Branch|Purpose|
|---|---|
|main|stable|
|develop|integration|
|feature/*|features|
|fix/*|bugfixes|

---

## 6.8 CẤM code trực tiếp trên main

---

## 6.9 Repository luôn runnable

Sau mỗi commit:

- backend boot được
- frontend build được
- worker start được
- tests pass

---

## 7. DEFINITION OF DONE

Task chỉ được xem là DONE nếu:

|Requirement|Required|
|---|---|
|Code chạy|✅|
|Tests pass|✅|
|Không có secrets|✅|
|Không có debug code|✅|
|Đúng kiến trúc Vectorless RAG|✅|
|Dùng đúng PageIndex|✅|
|Recursive retrieval đúng|✅|
|Citation đúng|✅|
|Retrieval validated|✅|
|Type hints đầy đủ|✅|
|Error handling đầy đủ|✅|
|Logging đầy đủ|✅|
|Commit đúng format|✅|

---

## 8. QUY TẮC QUAN TRỌNG NHẤT

## 8.1 Retrieval > Prompt

---

## 8.2 Citation Accuracy là bắt buộc

Citation sai = system fail.

---

## 8.3 Stability > Optimization

---

## 8.4 Không optimize quá sớm

MVP trước:

- đúng
- ổn định
- deterministic
- testable

Sau mới:

- optimize
- caching
- scaling

---

## 8.5 Recursive Reasoning là core architecture

Semantic Tree Navigation là nền tảng hệ thống.

KHÔNG được:

- bypass tree traversal
- bypass hierarchy reasoning
- bypass leaf retrieval

---

## 8.6 Không để ambiguity tồn tại

Nếu:

- requirement unclear
- architecture unclear
- retrieval unclear
- PageIndex usage unclear
- semantic tree unclear

→ PHẢI dừng và clarify trước khi code.
