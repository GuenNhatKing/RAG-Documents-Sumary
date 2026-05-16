# PHASE 3 REPORT — OPENROUTER AGENTIC CHAT

[x] End-to-End API Gateway: Xây dựng endpoint POST /chat/ask trong app/api/chat.py, ghép nối hoàn hảo luồng Semantic Retrieval (Phase 2) với LLM Generation (Phase 3), thiết kế định dạng đầu ra JSON chuẩn mực bao gồm answer và danh sách sources tách biệt.

[x] Resilient LLM Engine: Thiết lập service giao tiếp OpenRouter API tại app/services/llm.py, bọc lớp bảo hiểm Exponential Backoff Retry bằng thư viện tenacity để hệ thống tự động xoay sở, chịu tải và phục hồi trước các sự cố mạng (429, 503) mà không gây crash ứng dụng.

[x] Ironclad Zero-Hallucination Prompt: Áp dụng kỹ thuật Prompt Engineering "kín cổng cao tường" bằng tiếng Anh, thiết lập các chốt chặn (Guardrails) ép AI tuân thủ tuyệt đối: chỉ trả lời dựa trên ngữ cảnh, bắt buộc trích dẫn in-line, và trả về chuỗi Fallback chuẩn hóa ("Tài liệu không đề cập...") khi thiếu dữ liệu.

[x] Independent Source Auditing: Triển khai thuật toán kiểm duyệt trích dẫn độc lập bằng Regex. Tự động quét, bóc tách và khử trùng lặp các thẻ [Nguồn: ..., Dòng: ...] trực tiếp từ "ngữ cảnh thô" (Raw Context) bằng Python, triệt tiêu hoàn toàn rủi ro AI "tự bịa" hoặc làm sai lệch nguồn gốc dữ liệu.

[x] Dynamic Model Configuration: Đồng bộ hóa toàn bộ kiến trúc (bao gồm cả rag.py và llm.py) sang cơ chế nạp cấu hình động qua biến môi trường OPENROUTER_MODEL, cho phép nâng cấp tức thời lõi suy luận lên các model tối tân (như Llama 3.3 70B) chỉ qua một thao tác sửa .env.
