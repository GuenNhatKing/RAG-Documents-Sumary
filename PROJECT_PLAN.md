# KẾ HOẠCH DỰ ÁN

## HỆ THỐNG QUẢN LÝ, SỐ HÓA VÀ TRUY XUẤT TÀI LIỆU THÔNG MINH SỬ DỤNG AI RAG

---

## 1. TỔNG QUAN DỰ ÁN

### 1.1 Tên hệ thống

Hệ thống quản lý, số hóa và truy xuất tài liệu thông minh sử dụng Agentic Vectorless RAG.

### 1.2 Mục tiêu dự án

Xây dựng hệ thống hỗ trợ:

- Số hóa tài liệu hành chính/pháp lý (PDF, DOCX, Image).
- Xây dựng \"Mục lục thông minh\" (Semantic Tree) tự động bằng PageIndex.
- Tìm kiếm theo cơ chế suy luận (Reasoning-based Retrieval).
- Hỏi đáp tài liệu có trích dẫn nguồn chính xác cấp độ trang.
- Tóm tắt và tổng hợp thông tin từ văn bản phức tạp.

### 1.3 Tổng quan kiến trúc

|Thành phần|Kiến trúc/Công nghệ|
|---|---|
|AI Search|Vectorless RAG|
|Indexing|Semantic Tree (JSON format) qua thư viện PageIndex|
|LLM & Reasoning|Local LLM API|
|Backend|FastAPI|
|Frontend|NextJS + TailwindCSS|
|Queue|Celery + Redis|
|Database Metadata|SQLite + SQLAlchemy ORM (Chỉ lưu user & metadata tài liệu)|
|Storage|Local / MinIO (Lưu PDF và file JSON Tree)|

---

## 2. PHẠM VI DỰ ÁN

### 2.1 Số hóa & Build Tree tự động

Cho phép Upload PDF/DOCX/Ảnh scan.

Hệ thống tự động:

- Dùng thư viện pageindex phân tích cấu trúc tài liệu.
- Gọi LLM thông qua Local LLM để hỗ trợ semantic parsing.
- Tạo ra file Cây Ngữ Nghĩa (Semantic Tree) định dạng JSON lưu vào thư mục data/semantic_trees/.

### 2.2 Tìm kiếm Agentic & Trích dẫn

Người dùng hỏi:

\"Điều kiện cấp phép xây dựng?\"

Hệ thống:

- Duyệt JSON Tree (Reasoning).
- Lấy đúng nội dung Leaf node.
- Trả lời bằng Local LLM LLM kèm citation:

[Nguồn: Luat-Xay-Dung.pdf, Trang 12]

---

## 3. KIẾN TRÚC HỆ THỐNG

### 3.1 Kiến trúc tổng thể

                ┌─────────────────┐
                │   Frontend UI   │
                └────────┬────────┘
                         │
                ┌────────▼────────┐
                │ FastAPI Backend │
                └────┬───────┬────┘
                     │       │
       ┌─────────────▼─┐   ┌─▼─────────────┐
       │ File Ingestion│   │ RAG Service   │
       │ (PageIndex)   │   │ (Tree Search) │
       └──────┬────────┘   └──────┬────────┘
              │                   │
       ┌──────▼────────┐   ┌──────▼────────┐
       │   JSON Tree   │◄──┤ Local LLM    │
       │   Storage     │   │ LLM Gateway   │
       └───────────────┘   └───────────────┘

---

## 4. GIAO TIẾP FRONTEND ↔ BACKEND

### 4.1 Ingestion Flow (Build Tree)

Upload PDF
    -> Lưu file
    -> Gọi script run_pageindex.py
    -> Lưu JSON tree vào data/semantic_trees/
    -> Update status vào DB

### 4.2 RAG Flow (Chat)

User Query
    -> Load JSON Tree
    -> Reasoning Tree Search
    -> Context Builder
    -> Local LLM API
    -> Trả về Answer + Citations

---

## 5. THIẾT KẾ DATABASE & ORM

Sử dụng SQLAlchemy để đảm bảo tính trừu tượng hóa.

Logic nghiệp vụ sẽ không phụ thuộc vào loại DB cụ thể.

- Database Engine: SQLite (Lưu trữ dạng file database.db).
- ORM Layer: SQLAlchemy 2.0+.
- Migrations: Sử dụng Alembic (tùy chọn) để quản lý sự thay đổi schema.

Lưu ý:

- Không dùng DB để lưu Index/Chunking/Vector.
- SQLite chỉ lưu metadata và thông tin người dùng.

### 5.1 users

|Field|Type|Note|
|---|---|---|
|id|UUID|Primary Key|
|username|VARCHAR|Unique|
|password_hash|TEXT||
|role|VARCHAR||
|created_at|TIMESTAMP||

### 5.2 documents

|Field|Type|Note|
|---|---|---|
|id|UUID|Primary Key|
|filename|VARCHAR||
|total_pages|INTEGER|Tổng số trang (phục vụ Reasoning)|
|uploaded_by|UUID|Foreign Key -> users.id|
|json_tree_path|TEXT||
|status|ENUM|pending, processed, error|
|created_at|TIMESTAMP||

(Xóa bỏ bảng page_index khỏi thiết kế cũ)

---

## 6. CÁC BƯỚC SETUP MÔI TRƯỜNG

### 6.1 Cài đặt bắt buộc

- Python 3.11+
- NodeJS 22+
- SQLite3 (Tích hợp sẵn trong Python, KHÔNG cần cài đặt thêm server DB)

### 6.2 Environment Variables

    DATABASE_URL=sqlite:///./database.db
    REDIS_URL=redis://localhost:6379/0
    Local LLM_API_KEY=your_Local LLM_api_key_here
    Local LLM_MODEL=Local LLM/free
    JWT_SECRET=your_jwt_secret_here
    