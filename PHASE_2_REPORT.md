# PHASE 2 REPORT — RECURSIVE REASONING RETRIEVAL

[x] Agentic Tree Traversal: Xây dựng hàm reasoning_search_tree trong app/services/rag.py, sử dụng LLM để suy luận và điều hướng trực tiếp trên cấu trúc thư mục JSON (đọc Title/Summary) để tìm node_id, loại bỏ hoàn toàn Vector Search và Embeddings.

[x] Bulletproof Normalization: Triển khai đệ quy an toàn _normalize_tree_node, tự động xử lý các cấu trúc JSON bất đồng nhất (List vs Dict, id vs node_id), bảo toàn tuyệt đối cấu trúc phân cấp (Hierarchy) để LLM không bị mất phương hướng.

[x] Semantic Chunking & Extraction: Hoàn thiện build_context_from_markdown, áp dụng thuật toán cắt text theo ngữ nghĩa bằng cách xác định chính xác ranh giới dòng (line_num start/end) từ file .md duy nhất tại data/markdown_docs/<doc_id>.md.

[x] Context Formatting & Citation: Tự động gộp ngữ cảnh, khử trùng lặp (deduplication) và bắt buộc dán nhãn trích dẫn gốc [Nguồn: <doc_id>.md, Dòng: X-Y] ngay trên đầu mỗi đoạn text trích xuất.
