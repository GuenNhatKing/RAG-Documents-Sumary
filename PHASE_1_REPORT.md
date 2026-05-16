# PHASE 1 REPORT — DOCUMENT INGESTION & SEMANTIC TREE

[x] Upload Pipeline: Xây dựng API tiếp nhận PDF/DOCX, lưu trữ vật lý tại data/raw/ với định danh UUID.

[x] Page-level Extraction: Trích xuất Text thô từng trang thành các file riêng biệt (page_001.txt, page_002.txt) tại `data/extracted_text/<doc_id>/`.

[x] Semantic Tree Construction: Tích hợp PageIndex để tạo cấu trúc phân cấp (Hierarchy) lưu dưới dạng JSON tại `data/semantic_trees/`.

[x] Vectorless DB Schema: Cập nhật SQLAlchemy model, loại bỏ hoàn toàn các cột Embedding/Vector, quản lý bằng hệ thống File Path.

[x] Alembic Migration: Thực thi thành công initial_vectorless_schema, đồng bộ hóa Database giữa các Container thông qua volume /work/database.db.
