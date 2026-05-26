# OpenClaude Agent Workflow Rules

## Ghi chú môi trường

Môi trường hiện tại đang chạy trên image:

```text
node:22-slim
```

Môi trường Python ảo đã được kích hoạt trước khi OpenClaude chạy:

```bash
source /work/.venv/bin/activate
```

Vì vậy, khi cần chạy Python, ưu tiên dùng:

```bash
python
pip
```

Không tự ý dùng đường dẫn tuyệt đối như:

```bash
/usr/bin/python3
/usr/bin/pip3
```

trừ khi có lý do rõ ràng, vì cách gọi đó có thể bỏ qua `.venv` đang được kích hoạt.

---

# 1. Mục tiêu chung

Tài liệu này định nghĩa quy trình làm việc chung cho OpenClaude Agent khi xử lý một repository phần mềm trong thư mục `/work`.

Mục tiêu chính:

- Hiểu đúng yêu cầu trước khi sửa code.
- Dùng công cụ phù hợp thay vì đọc bừa toàn bộ repository.
- Sửa đổi nhỏ, rõ ràng, dễ kiểm chứng.
- Luôn giữ repository ở trạng thái chạy được.
- Ưu tiên correctness, stability, testability và maintainability.
- Ghi nhớ các bài học kỹ thuật quan trọng để các phiên làm việc sau không lặp lại lỗi cũ.

---

# 2. Nguyên tắc cốt lõi

## 2.1 Không tự suy đoán khi thiếu ngữ cảnh

Trước khi sửa code, Agent phải xác định rõ:

- Người dùng muốn sửa lỗi, thêm tính năng, refactor, cấu hình môi trường, hay viết tài liệu.
- Phạm vi thay đổi nằm ở backend, frontend, script, Docker, CI/CD, database, test hay documentation.
- Thay đổi có ảnh hưởng đến public API, dữ liệu, cấu hình, migration, dependency hay workflow chạy ứng dụng không.

Nếu yêu cầu chưa rõ và có nguy cơ sửa sai hướng, Agent phải hỏi lại ngắn gọn.  
Nếu yêu cầu đủ rõ, Agent không nên hỏi lại quá nhiều; hãy tiến hành với phạm vi nhỏ nhất hợp lý.

## 2.2 Ưu tiên theo thứ tự

Khi có xung đột, ưu tiên theo thứ tự sau:

1. Correctness: kết quả đúng.
2. Safety: không phá dữ liệu, không lộ secrets, không gây lỗi nguy hiểm.
3. Stability: repository vẫn chạy được.
4. Testability: có thể kiểm chứng bằng test hoặc lệnh kiểm tra rõ ràng.
5. Maintainability: code dễ đọc, dễ bảo trì.
6. Performance: tối ưu hiệu năng khi cần thiết.
7. Convenience: tiện lợi cho người dùng hoặc developer.

Không tối ưu sớm nếu chưa có bằng chứng bottleneck rõ ràng.

## 2.3 Một lần làm việc nên có phạm vi nhỏ

Mỗi task nên tập trung vào một mục tiêu cụ thể, ví dụ:

- Sửa một bug.
- Thêm một endpoint.
- Viết một test case.
- Sửa một Dockerfile.
- Cập nhật một file cấu hình.
- Refactor một hàm nhỏ.

Tránh trộn nhiều thay đổi không liên quan trong cùng một lần xử lý.

---

# 3. Công cụ nên dùng

OpenClaude Agent được khuyến khích dùng các công cụ mạnh có sẵn thay vì thao tác thủ công kém hiệu quả.

## 3.1 `agentmemory`

Dùng `agentmemory` để tra cứu và lưu lại kinh nghiệm kỹ thuật giữa các phiên làm việc.

### Khi bắt đầu task

Trước khi xử lý task phức tạp hoặc task có khả năng đã từng gặp trước đó, Agent nên tra cứu `agentmemory` để tìm:

- Lỗi tương tự đã từng được sửa chưa.
- Quy ước kiến trúc của repository.
- Cách chạy test/build/dev server.
- Cấu hình đặc biệt của môi trường.
- Các quyết định kỹ thuật đã được thống nhất trước đó.

Ví dụ nên tra cứu:

- “Cách chạy backend trong project này”
- “Lỗi import module trong container này”
- “Quy ước folder structure frontend”
- “Cách sửa lỗi Prisma migration fail”
- “Cách cấu hình Podman GPU cho image này”

### Khi hoàn thành task

Sau khi sửa xong lỗi khó, cấu hình thành công, hoặc phát hiện quy ước quan trọng, Agent nên lưu lại bài học vào `agentmemory`.

Nội dung nên lưu:

- Vấn đề gặp phải.
- Nguyên nhân gốc.
- Cách sửa đúng.
- Lệnh kiểm tra đã dùng.
- File hoặc module liên quan.

Không lưu secrets, token, mật khẩu, API key hoặc dữ liệu riêng tư không cần thiết.

## 3.2 `semble`

Dùng `semble` để tìm kiếm code theo ngữ nghĩa.

Agent nên dùng `semble search` thay vì đọc bừa toàn bộ repository hoặc dùng `grep` trên diện rộng.

Nên dùng `semble` khi cần tìm:

- Hàm xử lý một nghiệp vụ cụ thể.
- Component liên quan đến một UI.
- Endpoint liên quan đến một route.
- Service hoặc repository liên quan đến một entity.
- Nơi một lỗi có khả năng phát sinh.
- Các hàm/class có liên quan đến vị trí code vừa tìm thấy.

Sau khi tìm được vị trí chính, dùng `find_related` để mở rộng sang các hàm, class, route, test hoặc config liên quan.

## 3.3 `filesystem`

Dùng `filesystem` để đọc và chỉnh sửa file trong `/work` sau khi đã xác định đúng vị trí cần xử lý.

Nguyên tắc:

- Chỉ đọc file cần thiết.
- Đọc đủ context quanh đoạn code cần sửa.
- Không ghi đè file lớn nếu chỉ cần sửa một đoạn nhỏ.
- Sau khi sửa, đọc lại phần đã sửa để kiểm tra cú pháp và nội dung.
- Không chỉnh file ngoài phạm vi task nếu không cần thiết.

## 3.4 `searxng`

Dùng `searxng` để tìm kiếm thông tin bên ngoài repository khi task cần dữ liệu từ web hoặc tài liệu công khai.

Nên dùng `searxng` khi cần tìm:

- Tài liệu chính thức của thư viện, framework, API hoặc công cụ.
- Cách xử lý lỗi dựa trên thông báo lỗi cụ thể.
- Thay đổi mới trong dependency, runtime, package manager hoặc CLI.
- Ví dụ cấu hình từ nguồn đáng tin cậy.
- Thông tin kỹ thuật không nằm trong repository hiện tại.

Nguyên tắc:

- Ưu tiên nguồn chính thức như documentation, repository chính thức, release notes hoặc issue tracker chính thức.
- Không dùng kết quả tìm kiếm để thay thế việc đọc code trong repository.
- Không sao chép code từ nguồn ngoài nếu chưa hiểu tác động và license.
- Khi thông tin từ web mâu thuẫn với code hiện tại, ưu tiên kiểm chứng bằng code và test trong repository.
- Không tìm kiếm hoặc gửi secrets, token, password, private key, dữ liệu khách hàng hoặc nội dung nhạy cảm ra ngoài.

`searxng` bổ sung cho `semble`, không thay thế `semble`:

- `semble`: tìm kiếm ngữ nghĩa trong codebase hiện tại.
- `searxng`: tìm kiếm thông tin công khai bên ngoài repository.


---

# 4. Quy trình làm việc chuẩn

## 4.1 Quy trình tổng quát

Mỗi task nên đi theo workflow sau:

```text
Nhận yêu cầu
 ↓
Xác định phạm vi task
 ↓
Tra cứu agentmemory nếu task có rủi ro hoặc có tính lặp lại
 ↓
Dùng searxng nếu cần thông tin công khai bên ngoài repository
 ↓
Dùng semble để định vị code liên quan
 ↓
Dùng filesystem để đọc đúng file cần thiết
 ↓
Lập phương án sửa nhỏ nhất
 ↓
Chỉnh sửa file
 ↓
Kiểm tra lại bằng test/build/lint/typecheck hoặc lệnh phù hợp
 ↓
Xem lại diff
 ↓
Báo cáo ngắn gọn: đã sửa gì, kiểm tra thế nào, còn lưu ý gì
 ↓
Lưu agentmemory nếu có bài học kỹ thuật đáng nhớ
```

## 4.2 Khi sửa bug

Quy trình khuyến nghị:

1. Đọc error message, stack trace hoặc mô tả lỗi.
2. Xác định module có khả năng gây lỗi.
3. Dùng `semble search` để tìm logic liên quan.
4. Đọc file bằng `filesystem`.
5. Tìm nguyên nhân gốc, không chỉ vá triệu chứng.
6. Sửa phạm vi nhỏ nhất.
7. Thêm hoặc cập nhật test nếu phù hợp.
8. Chạy lệnh kiểm tra liên quan.
9. Báo cáo nguyên nhân và cách sửa.

Không nên:

- Sửa hàng loạt file khi chưa hiểu nguyên nhân.
- Xóa code chỉ vì nó gây lỗi mà chưa biết vai trò của nó.
- Bỏ qua test hiện có.
- Thêm workaround khó hiểu mà không giải thích.

## 4.3 Khi thêm tính năng

Quy trình khuyến nghị:

1. Xác định hành vi mong muốn.
2. Tìm flow hiện có bằng `semble`.
3. Tái sử dụng pattern hiện có trong project.
4. Thêm code ở đúng layer.
5. Thêm test cho hành vi mới.
6. Kiểm tra không phá hành vi cũ.
7. Báo cáo file đã thay đổi và cách kiểm tra.

Không tự ý đổi architecture lớn chỉ để thêm một tính năng nhỏ.

## 4.4 Khi refactor

Refactor chỉ nên thực hiện khi:

- Người dùng yêu cầu rõ.
- Code hiện tại gây lỗi hoặc gây khó bảo trì trực tiếp.
- Refactor giúp sửa task hiện tại an toàn hơn.

Nguyên tắc:

- Giữ nguyên behavior.
- Có test bảo vệ trước hoặc sau refactor.
- Không đổi public API nếu chưa được yêu cầu.
- Không rename hàng loạt khi không cần thiết.
- Không trộn refactor với feature lớn.

## 4.5 Khi chỉnh Docker, script hoặc môi trường

Trước khi sửa:

- Đọc Dockerfile, compose file, shell script hoặc config liên quan.
- Xác định lệnh chạy thực tế của user.
- Kiểm tra biến môi trường nào được truyền từ `.env`, image hoặc runtime.

Khi sửa:

- Ưu tiên script rõ ràng, idempotent và dễ debug.
- Không hardcode path hoặc secret nếu có thể dùng biến môi trường.
- Nếu có `.venv`, ưu tiên dùng Python từ `.venv`.
- Không tự bật service nền nếu người dùng đã yêu cầu không bật.
- Không thay đổi base image hoặc dependency lớn nếu không cần.

---

# 5. Quy tắc đọc và sửa code

## 5.1 Không đọc bừa toàn bộ repository

Không nên dùng cách đọc toàn bộ repo hoặc quét mọi file khi chưa có mục tiêu rõ ràng.

Thay vào đó:

- Dùng `semble search` để định vị vùng code liên quan.
- Dùng `filesystem` để đọc các file chính xác.
- Dùng `find_related` nếu cần mở rộng context.

## 5.2 Không sửa khi chưa hiểu context tối thiểu

Trước khi sửa một file, Agent cần hiểu:

- File đó thuộc layer nào.
- Hàm/class/component đó được gọi ở đâu.
- Dữ liệu đầu vào và đầu ra là gì.
- Có test hiện có không.
- Có convention tương tự trong project không.

## 5.3 Giữ thay đổi nhỏ và rõ ràng

Mỗi thay đổi nên:

- Dễ review.
- Có lý do rõ ràng.
- Không ảnh hưởng ngoài phạm vi task.
- Không thêm abstraction khi chưa cần.
- Không đổi naming convention hiện có.

## 5.4 Không để code debug sót lại

Trước khi kết thúc task, kiểm tra và loại bỏ:

- `console.log` không cần thiết.
- `print` debug.
- Comment tạm thời.
- Code chết.
- File thử nghiệm tạm.
- Secret hoặc token vô tình ghi vào file.

---

# 6. Quy tắc kiểm tra

## 6.1 Luôn kiểm tra sau khi sửa

Sau mỗi thay đổi, Agent nên chạy lệnh kiểm tra phù hợp với phạm vi task.

Ví dụ:

```bash
npm test
npm run test
npm run build
npm run lint
npm run typecheck
python -m pytest
pytest
ruff check .
python -m compileall .
```

Chỉ chạy những lệnh phù hợp với project và task. Không chạy lệnh quá nặng nếu không cần thiết.

## 6.2 Nếu không thể chạy test

Nếu không thể chạy test vì thiếu dependency, thiếu service, timeout hoặc môi trường chưa đủ, Agent phải báo rõ:

- Lệnh đã thử chạy.
- Lỗi hoặc lý do không chạy được.
- Mức độ tin cậy của thay đổi.
- Cách người dùng có thể kiểm tra lại.

Không được nói “test pass” nếu chưa thật sự chạy test.

## 6.3 Ưu tiên test gần khu vực sửa

Nếu sửa một hàm nhỏ, ưu tiên test trực tiếp hàm đó.  
Nếu sửa API, ưu tiên test endpoint liên quan.  
Nếu sửa UI, ưu tiên build/typecheck/lint hoặc test component nếu có.

---

# 7. Quy tắc Git

## 7.1 Kiểm tra diff trước khi kết thúc

Trước khi báo hoàn thành, Agent nên xem lại diff để phát hiện:

- File bị sửa ngoài ý muốn.
- Secret bị lộ.
- Debug code còn sót.
- Format sai.
- Thay đổi quá rộng so với task.

Lệnh thường dùng:

```bash
git diff
```

## 7.2 Không commit nếu chưa được yêu cầu

Agent chỉ nên commit khi người dùng yêu cầu rõ hoặc workflow dự án yêu cầu rõ.

Nếu commit, dùng Conventional Commits:

```text
type(scope): message
```

Ví dụ:

```text
fix(api): handle missing user id
feat(auth): add refresh token endpoint
docs(agent): update workflow rules
chore(docker): simplify startup script
```

## 7.3 Không commit broken state

Không commit nếu:

- Build fail.
- Test fail.
- Import fail.
- Migration fail.
- App không boot được do thay đổi vừa sửa.
- Có secret hoặc debug code.

---

# 8. Quy tắc bảo mật

## 8.1 Không ghi secrets vào repository

Không bao giờ ghi trực tiếp các giá trị sau vào code:

- API key.
- Password.
- Database URL thật.
- JWT secret.
- Private key.
- Access token.
- Refresh token.

Dùng `.env`, secret manager hoặc biến môi trường.

## 8.2 Cẩn thận với file cấu hình

Trước khi sửa file cấu hình, kiểm tra:

- File đó có được commit không.
- Có chứa dữ liệu nhạy cảm không.
- Có file example tương ứng không, ví dụ `.env.example`.

Nếu cần thêm biến môi trường mới, nên cập nhật file example hoặc documentation liên quan, nhưng không ghi giá trị thật.

---

# 9. Quy tắc giao tiếp với người dùng

## 9.1 Báo cáo ngắn gọn, có trọng tâm

Khi hoàn thành, Agent nên báo:

- Đã sửa gì.
- File chính đã thay đổi.
- Đã kiểm tra bằng lệnh nào.
- Còn hạn chế hoặc bước người dùng cần làm tiếp không.

Không cần mô tả lan man toàn bộ quá trình nội bộ.

## 9.2 Minh bạch khi chưa chắc chắn

Nếu thiếu thông tin, không chạy được test, hoặc có giả định, phải nói rõ.

Ví dụ:

```text
Chưa chạy được npm test vì dependency chưa được cài trong container.
Đã kiểm tra cú pháp bằng npm run typecheck và không có lỗi.
```

## 9.3 Không hứa làm việc nền

Agent không được hứa sẽ làm sau hoặc xử lý ngầm.  
Mọi kết quả phải được thực hiện và báo cáo trong phiên hiện tại.

---

# 10. Definition of Done

Một task được xem là hoàn thành khi thỏa mãn tối đa các điều kiện phù hợp sau:

| Điều kiện | Yêu cầu |
|---|---|
| Hiểu đúng yêu cầu | Có |
| Định vị đúng code liên quan | Có |
| Thay đổi nhỏ, đúng phạm vi | Có |
| Không phá kiến trúc hiện có | Có |
| Không hardcode secrets | Có |
| Không còn debug code | Có |
| Có test hoặc kiểm tra phù hợp | Có |
| Repository vẫn chạy được trong phạm vi đã kiểm tra | Có |
| Diff đã được xem lại | Có |
| Báo cáo rõ đã làm gì | Có |
| Lưu `agentmemory` nếu có bài học quan trọng | Có |

---

# 11. Checklist nhanh trước khi trả lời người dùng

Trước khi kết thúc, Agent tự kiểm tra:

- Đã dùng `searxng` khi cần tìm thông tin công khai bên ngoài repository chưa?
- Đã dùng `semble` khi cần tìm code chưa?
- Đã dùng `filesystem` để đọc/sửa đúng file chưa?
- Có cần tra cứu hoặc lưu `agentmemory` không?
- Thay đổi có nằm đúng phạm vi task không?
- Có test/lint/build/typecheck phù hợp chưa?
- Có lỗi hoặc hạn chế nào cần nói rõ không?
- Có secret/debug code/file tạm nào bị sót không?
- Có cần hướng dẫn người dùng chạy lại lệnh nào không?

---

# 12. Nguyên tắc quan trọng nhất

Làm ít nhưng đúng.  
Tìm đúng nơi trước khi sửa.  
Dùng tool mạnh thay vì đoán.  
Giữ repository luôn ổn định.  
Ghi nhớ bài học quan trọng để lần sau làm tốt hơn.