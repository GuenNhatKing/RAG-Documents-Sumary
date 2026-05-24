# CHỈ DẪN VẬN HÀNH DÀNH CHO AI AGENT

Bạn được trang bị 3 công cụ MCP cốt lõi: `filesystem`, `agentmemory`, và `semble`. Hãy tuân thủ nghiêm ngặt quy trình phối hợp sau:

## 1. Quy tắc tìm kiếm & Định vị mã nguồn (Dùng `semble`)

- Tuyệt đối KHÔNG dùng lệnh `grep` hoặc đọc bừa bãi toàn bộ file lớn để tìm thông tin. Việc này gây lãng phí 98% token hệ thống.
- BẮT BUỘC dùng công cụ `search` của `semble` để tìm phân đoạn code bằng ngôn ngữ tự nhiên.
- Dùng `find_related` của `semble` khi muốn mở rộng tìm kiếm các hàm/class có liên quan xung quanh vị trí vừa tìm thấy.

## 2. Quy tắc Đọc & Chỉnh sửa file (Dùng `filesystem`)

- Sau khi `semble` định vị được chính xác file và dòng code cần xử lý, hãy dùng các công cụ của `filesystem` (như `read_file`, `write_file`, `view_code_item`) để làm việc với tệp tin trong thư mục `/work`.
- Luôn kiểm tra lại cú pháp sau khi ghi file để đảm bảo mã nguồn không bị lỗi.

## 3. Quy tắc Quản lý bộ nhớ & Bài học kinh nghiệm (Dùng `agentmemory`)

- Trước khi bắt đầu một task lớn, hãy truy vấn `agentmemory` xem trước đây bạn hoặc các Agent khác đã từng xử lý lỗi tương tự hoặc có lưu ý gì đặc biệt về kiến trúc của dự án này chưa.
- Sau khi hoàn thành một task khó, sửa xong một bug phức tạp, hoặc khi cấu hình thành công một tính năng mới: Bạn BẮT BUỘC phải dùng `agentmemory` để lưu lại bài học kinh nghiệm (Ví dụ: "Cách fix lỗi tràn bộ nhớ khi cấu hình Podman..."). Điều này giúp các Agent ở phiên làm việc sau không dẫm lại vết xe đổ.

## Quy trình xử lý Task tiêu chuẩn (Workflow)

Bước 1: Tra cứu bộ nhớ cũ (`agentmemory`)
   ↓
Bước 2: Tìm vị trí đoạn code cần xử lý (`semble search`)
   ↓
Bước 3: Đọc và tiến hành sửa đổi file (`filesystem: write_file`)
   ↓
Bước 4: Lưu lại kiến thức mới vừa học được vào bộ nhớ (`agentmemory`)
