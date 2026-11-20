# Round 2 — Antigravity cross-examination

> Môi trường kiểm chứng (chỉ đọc, `PYTHONDONTWRITEBYTECODE=1`, không sửa/tạo/xóa file trong repo): Python 3.14.3, FastAPI 0.143.3, Starlette 1.8.0, Pydantic 2.14.1, pdfplumber 0.11.10, pdfminer.six 20260107. Mọi lệnh dưới đây đều chạy bằng `.venv\Scripts\python.exe` dưới 10 giây.

---

## Phần 1 — Phản biện các báo cáo Round 1 (ưu tiên theo mức độ nghiêm trọng)

### **Issue ID:** ADV-CX-001
**Target:** Codex
**Severity:** Critical
**Claim:** Đề xuất ngưỡng `MAX_DIFF_TOKEN_PRODUCT = 4_000_000` tính theo `len(old_tokens) * len(new_tokens)` trước khi gọi `diff_words`, quá ngưỡng trả HTTP `422 DIFF_TOO_COMPLEX` ([round1-codex.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-codex.md#L271-L274)).
**Evidence:** **[CONFIRMED]** Chạy benchmark trên chính fixture thật `tests/fixtures/contract_old.pdf` (`395` token / 2 trang) mở rộng thành hợp đồng nhiều điều khoản với 1 đoạn sửa đổi:
- Lệnh: `.venv\Scripts\python.exe` đo `diff_words` với `contract_old`/`contract_new` lặp ×8, ×16, ×32 điều khoản có số thứ tự `Điều {i}.` vs chuỗi lặp đối kháng `"a " * 2000`.
- Kết quả:
  - `Realistic x8`: `14.294` ký tự (**2,8%** của `MAX_TEXT_CHARS`), `3.176 × 3.174` token (`product = 10.080.624`), thời gian chạy **`0,0269s`**, Codex từ chối (`True`).
  - `Realistic x32`: `57.205` ký tự (11,4% của `MAX_TEXT_CHARS`), `12.704 × 12.702` token (`product = 161.366.208`), thời gian chạy **`0,3469s`**, Codex từ chối (`True`).
  - Đối kháng `"a " * 2000` vs `"a " * 1999 + "b"`: `product = 4.000.000` (qua cửa Codex!), thời gian chạy **`0,7436s`** — chậm gấp **28 lần** hợp đồng 14 KB bị Codex chặn.
**Counterexample:** Một hợp đồng tiếng Việt bình thường chỉ khoảng 5–7 trang (~2.500–3.200 từ, ~14 KB) có 1 từ sửa đổi (không đi qua fast-path bằng nhau) bị từ chối với HTTP `422 DIFF_TOO_COMPLEX`, dù `diff_words` chỉ tốn 27 ms.
**Recommendation:** Bác bỏ ngưỡng `4_000_000` ($\sqrt{4\text{M}} = 2.000$ token/bên là phi thực tế). Nếu dùng ngân sách token cho Phase A, phải đặt trần đủ cho hợp đồng 50–100 trang (ví dụ `MAX_TEXT_TOKENS = 40_000`–`50_000`/bên hoặc kiểm tra thêm tỷ lệ lặp token thay vì chặn mù theo tích $N_1 \cdot N_2$), đồng thời giữ fast-path `old_text == new_text` và `old_tokens == new_tokens`.
**Confidence:** High.

---

### **Issue ID:** ADV-CX-002
**Target:** Codex
**Severity:** Critical
**Claim:** Trong `extract_pdf`, sau khi mở `pdfplumber.open`, đếm tối đa 101 phần tử từ `PDFPage.create_pages(pdf.doc)` bằng `islice` để "chặn sớm việc duyệt tài liệu rất nhiều trang", tránh chi phí dựng danh sách `pdf.pages` ([round1-codex.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-codex.md#L179-L190)).
**Evidence:** **[CONFIRMED]** Đọc `inspect.getsource(pdfplumber.pdf.PDF.close)` và đo trên PDF 2.000 trang trong bộ nhớ:
- Mã nguồn `PDF.close()` (`pdfplumber/pdf.py`): gọi vô điều kiện `for page in self.pages: page.close()` kể cả khi `self._pages` chưa từng được khởi tạo.
- Kết quả đo trên PDF 2.000 trang:
  - `with pdfplumber.open(...) as pdf:` + `islice(PDFPage.create_pages(pdf.doc), 101)` rồi `raise`: **`0,2793s`**, `len(pdf._pages) == 2000` (vẫn dựng toàn bộ 2.000 đối tượng `Page` khi thoát `with`!).
  - `len(pdf.pages)`: `0,3034s`, `n = 2000`.
  - `PDFDocument(PDFParser(stream), password="")` + `islice(PDFPage.create_pages(doc), 101)` **trước** `pdfplumber.open`: **`0,0402s`**, `cnt = 101` (nhanh gấp **7 lần**).
**Counterexample:** Tải lên PDF 2.000–10.000 trang vào phương án của Codex: nhánh `raise HTTPException(422)` thoát khối `with pdfplumber.open(...)`, kích hoạt `pdf.__exit__() -> pdf.close() -> self.pages`, vẫn dựng toàn bộ hàng nghìn `Page` và triệt tiêu mục tiêu chặn sớm.
**Recommendation:** Đếm trang dừng sớm bằng `PDFDocument(PDFParser(file_stream), password="")` + `islice(PDFPage.create_pages(doc), max_pages + 1)` **trước** khi gọi `pdfplumber.open()`, rồi `file_stream.seek(0)` nếu số trang nằm trong `1..max_pages`.
**Confidence:** High.

---

### **Issue ID:** ADV-CL-001
**Target:** Claude
**Severity:** Critical
**Claim:** `extract_pdf(file_stream, max_pages=None)` chỉ kiểm tra `if len(pdf.pages) > max_pages: raise ValueError(...)` sau `pdfplumber.open`, không kiểm tra trường hợp 0 trang ([round1-claude.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-claude.md#L106)).
**Evidence:** **[CONFIRMED]**
1. Kiểm chứng trên codebase hiện tại ([comparison_service.py](file:///C:/Users/Admin/contract-diff/app/services/comparison_service.py#L22-L23)): `needs_review = any(page["warnings"] for page in old_document["pages"] + new_document["pages"])`. Với PDF hợp lệ `/Pages << /Kids [] /Count 0 >>`, `extract_pdf` trả `[]` → `compare_document` trả `200 OK`, `changes=[]`, `needs_review=False`.
2. Kiểm chứng hiệu năng `len(pdf.pages)` trên PDF 2.000 trang: mất **`0,3034s`** (dựng đủ 2.000 đối tượng `pdfplumber.page.Page`), so với **`0,0402s`** khi đếm dừng sớm bằng `PDFDocument` + `islice(..., 101)`.
**Counterexample:** (a) Gửi 2 tệp PDF 0 trang vào `/api/v1/comparisons/pdf`: API trả `200 OK` với `changes=[]` và `needs_review=False` (khẳng định im lặng không cần rà soát trên tài liệu không có trang); (b) Gửi PDF 5.000 trang: `len(pdf.pages)` vẫn cấp phát toàn bộ 5.000 `Page` trước khi từ chối `422`.
**Recommendation:** Từ chối PDF 0 trang với HTTP `400` (`INVALID_OR_ENCRYPTED_PDF`), và thay `len(pdf.pages)` bằng bước tiền kiểm `PDFDocument` + `islice(PDFPage.create_pages(doc), max_pages + 1)` trước `pdfplumber.open()`.
**Confidence:** High.

---

### **Issue ID:** ADV-CL-002
**Target:** Claude
**Severity:** High
**Claim:** Trong `extract_document`, chỉ cần bắt `except PdfminerException` → `400` ("Bắt đúng một loại: mọi lỗi lúc mở là `PdfminerException`") và `except ValueError` → `422 PDF_TOO_MANY_PAGES`; rủi ro `except ValueError` quá rộng được giảm thiểu bằng "kiểm số trang ngay sau `open`, trước vòng lặp" ([round1-claude.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-claude.md#L98-L103), [L128](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-claude.md#L128), [L212](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-claude.md#L212)).
**Evidence:** **[CONFIRMED]**
1. Kiểm tra `pdfplumber.utils.exceptions`: tồn tại lớp anh em `MalformedPDFException(Exception)` với `issubclass(MalformedPDFException, PdfminerException) == False`.
2. Chạy `pdfplumber.open` + `extract_text()` trên 3 PDF lỗi cấu trúc trang hợp lệ header:
   - `/MediaBox [0 0 (x) 100]` → `pdfplumber.utils.exceptions.MalformedPDFException`
   - `/Rotate /Invalid` → `builtins.TypeError: unsupported operand type(s) for %: 'PSLiteral' and 'int'`
   - `/CropBox [0 0]` → `builtins.IndexError: list index out of range`
3. Về logic: trong [round1-claude.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-claude.md#L98-L103), `try/except ValueError` ở `extract_document` bao trùm toàn bộ lời gọi `extract_pdf(file_stream, MAX_PDF_PAGES)`, nên đặt lệnh kiểm trang trước vòng `for` bên trong `extract_pdf` **không hề thu hẹp phạm vi bắt `ValueError`** nếu `extract_text()` ném `ValueError` (chẳng hạn `pdfplumber/utils/geometry.py:72`).
**Counterexample:** Tải lên PDF 1 trang chứa `/MediaBox [0 0 (x) 100]` hoặc `/Rotate /Invalid`: đi qua `pdfplumber.open()` bình thường rồi làm server sập **HTTP 500**. Tải lên PDF 1 trang phát sinh `ValueError` trong `pdfplumber`: bị báo sai thành **HTTP 422 `PDF_TOO_MANY_PAGES`**.
**Recommendation:** Định nghĩa 2 ngoại lệ 1 dòng trong `pdf_extractor.py` (`InvalidPDFError(ValueError)`, `PDFPageLimitExceededError(ValueError)`) và bắt tường minh `(PdfminerException, MalformedPDFException, PDFException, PSEOF, ValueError, TypeError, IndexError, AttributeError)` quanh các bước parse/extract của `pdfplumber`/`pdfminer` để ánh xạ sang `InvalidPDFError` → HTTP `400`.
**Confidence:** High.

---

### **Issue ID:** ADV-CX-003
**Target:** Codex
**Severity:** High
**Claim:** `extract_document` chỉ bắt `pdfplumber.utils.exceptions.PdfminerException` quanh lời gọi extractor và chuyển thành HTTP 400 ([round1-codex.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-codex.md#L205)).
**Evidence:** **[CONFIRMED]** Cùng kết quả kiểm chứng như `ADV-CL-002`:
- `issubclass(MalformedPDFException, PdfminerException)` là `False`.
- PDF 1 trang `/MediaBox [0 0 (x) 100]` ném `MalformedPDFException`; `/Rotate /Invalid` ném `TypeError`; `/CropBox [0 0]` ném `IndexError`.
- Đặc biệt với phương án Codex gọi trực tiếp `PDFPage.create_pages(pdf.doc)` ([round1-codex.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-codex.md#L188)), lời gọi này **đi vòng qua** lớp bọc `except Exception as e: raise PdfminerException(e)` bên trong `PDF.pages` (`pdfplumber/pdf.py:157-161`): với PDF có `/Catalog` chứa `/Pages` là inline dict, `PDFPage.create_pages(pdf.doc)` ném trực tiếp `AttributeError("'dict' object has no attribute 'objid'")`.
**Counterexample:** Bất kỳ tệp PDF nào có `/MediaBox` chứa phần tử không phải số, `/CropBox` thiếu phần tử, hoặc `/Rotate` sai kiểu đều đi qua `extract_document` của Codex và trả **HTTP 500**.
**Recommendation:** Chuyển toàn bộ lỗi phân tích của `pdfminer`/`pdfplumber` (`PdfminerException`, `MalformedPDFException`, `PDFException`, `PSEOF`, `TypeError`, `IndexError`, `AttributeError`, `ValueError` từ thư viện) sang `InvalidPDFError` ngay trong `extract_pdf` và ánh xạ sang HTTP `400` ở `document_service.py`.
**Confidence:** High.

---

### **Issue ID:** ADV-CX-004
**Target:** Codex
**Severity:** High
**Claim:** Bổ sung `is_identical: bool` (so hai `fulltext`) và `is_token_identical: bool` (`len(changes) == 0`) vào response của `POST /api/v1/comparisons/pdf` ([round1-codex.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-codex.md#L129-L138)).
**Evidence:** **[CONFIRMED]** Chạy `compare_document` + `build_document_text` trên hai PDF scan rỗng text (2 trang vs 2 trang, và 2 trang vs 3 trang):
- Kết quả `Scan 2 vs 2` (`lease_scan.pdf` vs `loan_scan.pdf`): `is_identical=True`, `is_token_identical=True`, `needs_review=True`.
- Kết quả `Scan 2 vs 3`: `is_identical=False` (`"\n\n"` vs `"\n\n\n\n"`), **`is_token_identical=True`**, `needs_review=True`.
**Counterexample:** Người dùng so sánh hai bản hợp đồng scan hoàn toàn khác nhau (cùng 2 trang, không có lớp text): API trả `"is_identical": true, "is_token_identical": true`. Trong bài toán so sánh hợp đồng pháp lý, cờ boolean khẳng định "giống hệt nhau" khi thực tế không trích xuất được chữ nào là thiết kế fail-unsafe nghiêm trọng, bất chấp mô tả trong schema và cờ `needs_review=True`.
**Recommendation:** Không thêm `is_identical` hay `is_token_identical` vào `PDFComparisonResponse` ở Phase A; chỉ thêm `is_token_identical` vào `TextComparisonResponse` như yêu cầu tương thích ngược của v2 §3.3.
**Confidence:** High.

---

### **Issue ID:** ADV-CL-003
**Target:** Claude
**Severity:** High
**Claim:** Không thêm ASGI middleware giới hạn kích thước request trong ứng dụng; đẩy hoàn toàn việc chặn body sang reverse proxy ngoài repo (`nginx`), với lập luận "middleware kiểm `Content-Length` bị chunked request vượt qua" ([round1-claude.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-claude.md#L129), [L167](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-claude.md#L167)).
**Evidence:** **[CONFIRMED]**
1. Kiểm tra `starlette.formparsers.MultiPartParser`: file upload > 1 MB luôn bị ghi không giới hạn vào `SpooledTemporaryFile` trước khi route/service chạy (`max_part_size` chỉ áp cho non-file field); JSON body ở `/text` cũng được đọc hết vào RAM trước khi Pydantic chạy `max_length`.
2. Lập luận của Claude chỉ đánh vào loại middleware ngây thơ chỉ đọc header `Content-Length`. Một pure-ASGI middleware (~25 dòng) bọc `receive()` cộng dồn byte theo từng chunk chặn được **cả** `Transfer-Encoding: chunked` lẫn `Content-Length` khai gian (đã được Codex kiểm chứng thực nghiệm tại [round1-codex.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-codex.md#L246-L252)), và kiểm tra `MultiPartParser.parse` (`except BaseException: for file in self._files_to_close_on_error: file.close()`) xác nhận Starlette tự dọn file tạm khi stream bị ngắt.
**Counterexample:** Trong môi trường chạy trực tiếp `uvicorn` (môi trường phát triển/demo đồ án không có nginx), gửi 1 request multipart hoặc JSON 2 GB bằng `Transfer-Encoding: chunked` vào phương án của Claude vẫn làm tràn `%TEMP%` hoặc OOM trước khi `extract_document` hay Pydantic kịp từ chối.
**Recommendation:** Bổ sung pure-ASGI middleware nhẹ đếm byte trên `receive()` kèm kiểm tra nhanh `Content-Length` trong `app/core/`, kết hợp kiểm tra kích thước từng tệp (15 MiB) tại `document_service.py`.
**Confidence:** High.

---

### **Issue ID:** ADV-CL-004
**Target:** Claude
**Severity:** High
**Claim:** Giữ `MAX_TEXT_CHARS = 500_000` (hoặc gợi ý tác giả tự hạ xuống ~100.000 ký tự) và không thêm bất kỳ kiểm soát khối lượng tính toán nào trước `diff_words`, dù chính số đo của Claude chứng minh 8.000 ký tự lặp tốn `3,50s` và 142.000 ký tự hợp đồng tốn `47,77s` ([round1-claude.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-claude.md#L130-L131), [L216](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-claude.md#L216)).
**Evidence:** **[CONFIRMED]** Số liệu thực nghiệm của cả 3 agent đều thống nhất: `diff_words` dùng `SequenceMatcher(autojunk=False)` tăng bậc hai theo số token lặp (`n = 6.000` token = `11.999` ký tự tốn `4,575s`; ngoại suy `50.000` token = `100.000` ký tự lặp tốn hàng phút/request). Ngoài ra Claude còn bỏ qua fast-path $O(N)$ khi `old_text == new_text` hoặc `old_tokens == new_tokens`, nên ngay cả 2 văn bản dài giống hệt nhau vẫn phải đi qua `SequenceMatcher`.
**Counterexample:** Gửi cặp chuỗi `old_text = "a " * 40000`, `new_text = "a " * 39999 + "b"` (80.000 ký tự — nhỏ hơn cả ngưỡng gợi ý 100.000 ký tự của Claude) vào `/comparisons/text`: chặn kín 1 worker thread trong nhiều phút.
**Recommendation:** Tối thiểu phải thêm fast-path bằng nhau (chuỗi và token) trước `diff_words`, áp cùng một giới hạn độ dài văn bản (`MAX_TEXT_CHARS`) và trần số token/độ phức tạp hợp lý cho cả `/text` và `/pdf`, đồng thời ghi rõ phần rủi ro còn lại khi chưa có process isolation.
**Confidence:** High.

---

### **Issue ID:** ADV-CX-005
**Target:** Codex
**Severity:** High
**Claim:** Trong `extract_pdf`, từ chối mọi PDF có `pdf.doc.encryption is not None` bằng HTTP `400 INVALID_OR_ENCRYPTED_PDF`, bao gồm cả PDF mở được với mật khẩu người dùng rỗng `""` ([round1-codex.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-codex.md#L72-L74), [L182](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-codex.md#L182)).
**Evidence:** **[CONFIRMED]** Chính Codex ([round1-codex.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-codex.md#L74)) và Claude ([round1-claude.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-claude.md#L114)) đã chứng minh `pdfplumber` mở và trích xuất toàn bộ văn bản chính xác từ PDF có `/Encrypt` với mật khẩu người dùng rỗng (`"ABC"`, `"Hello secret"`). Trong thực tế hợp đồng Việt Nam (ngân hàng, bất động sản, biểu mẫu công chứng), rất nhiều PDF được đặt owner password chỉ để khóa sửa/in mà vẫn cho đọc không cần mật khẩu.
**Counterexample:** Người dùng tải lên bản hợp đồng PDF thật xuất từ ngân hàng có khóa chỉnh sửa (owner password, user password `""`): phiên bản hiện tại trích xuất đúng và trả `200 OK`, nhưng phương án của Codex từ chối với `400 INVALID_OR_ENCRYPTED_PDF` dù không có lý do bảo mật nào.
**Recommendation:** Chấp nhận PDF mã hóa mở được bằng mật khẩu rỗng (theo đề xuất của Claude); chỉ trả `400 INVALID_OR_ENCRYPTED_PDF` khi `pdfplumber`/`pdfminer` không thể mở hoặc giải mã (`PDFPasswordIncorrect` bọc trong `PdfminerException`).
**Confidence:** High.

---

### **Issue ID:** ADV-CL-005
**Target:** Claude
**Severity:** Medium
**Claim:** Từ chối dạng body lỗi phẳng `{"error_code", "detail"}` của Kế hoạch v2 §3.2 và chọn `{"detail": {"error_code", "message"}}`, với khẳng định "muốn vậy phải thêm exception handler toàn cục và handler đó sẽ đổi luôn dạng 404/405 mặc định" ([round1-claude.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-claude.md#L120)).
**Evidence:** **[CONFIRMED]** Chạy kiểm chứng trực tiếp với FastAPI 0.143.3 + Starlette 1.8.0:
- Đăng ký conditional handler trên `StarletteHTTPException` kiểm tra `isinstance(exc.detail, dict) and "error_code" in exc.detail` (nếu không khớp thì ủy quyền cho `fastapi.exception_handlers.http_exception_handler`):
  - Lỗi nghiệp vụ: `400 {"error_code":"INVALID_OR_ENCRYPTED_PDF","detail":"PDF loi"}`
  - 404 mặc định: `404 {"detail":"Not Found"}` (**không đổi**)
  - 405 mặc định: `405 {"detail":"Method Not Allowed"}` (**không đổi**)
- Thậm chí kiểm tra `app.exception_handlers.keys()` cho thấy đăng ký `@app.exception_handler(fastapi.HTTPException)` không hề ghi đè handler `starlette.exceptions.HTTPException` của 404/405.
**Counterexample:** Client hoặc bộ test bám theo đặc tả v2 §3.2 đọc `response.json()["error_code"]` sẽ ném `KeyError` với cấu trúc lồng `{"detail": {"error_code": ...}}` của Claude, trong khi lý do kỹ thuật Claude đưa ra để bác bỏ v2 là sai.
**Recommendation:** Dùng conditional exception handler ~5 dòng trong `app/main.py` để vừa đạt đúng contract phẳng `{"error_code", "detail"}` của v2 §3.2, vừa giữ nguyên 100% dạng mặc định của 404/405 và 422 Pydantic.
**Confidence:** High.

---

### **Issue ID:** ADV-CX-006
**Target:** Codex
**Severity:** Medium
**Claim:** Cho phép `app/extractors/pdf_extractor.py` ném trực tiếp `fastapi.HTTPException` ([round1-codex.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-codex.md#L207)) và áp giới hạn `EXTRACTED_TEXT_TOO_LONG` (tính cả separator `"\n\n"`) ngay trong `extract_pdf` cho cả `/extract` và `/pdf` ([round1-codex.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-codex.md#L192)).
**Evidence:** **[CONFIRMED]** Đối chiếu [coding-style-profile.md](file:///C:/Users/Admin/contract-diff/docs/implementation/coding-style-profile.md#L11-L13) và mã nguồn [pdf_extractor.py](file:///C:/Users/Admin/contract-diff/app/extractors/pdf_extractor.py#L1-L17), [text_mapping.py](file:///C:/Users/Admin/contract-diff/app/engines/text_mapping.py#L6):
1. `pdf_extractor.py` hiện hoàn toàn thuần `pdfplumber`, không phụ thuộc FastAPI; ngược lại Codex tách đôi việc dịch lỗi HTTP giữa `document_service.py` (413, 400 magic/parser) và `pdf_extractor.py` (400 encryption/0-page, 422 page/text limit).
2. Tính độ dài "gồm cả separator" trong `extract_pdf` làm extractor phải biết quy ước nối trang `"\n\n"` của `text_mapping.py`.
3. `/documents/extract` chỉ trích văn bản tuyến tính $O(L)$ và không chạy `diff_words`, nên chặn `EXTRACTED_TEXT_TOO_LONG` trên `/extract` vừa thiếu căn cứ vừa tạo mã lỗi ngoài v2.
**Counterexample:** Một hợp đồng PDF hợp lệ 90 trang dày chữ (~550.000 ký tự, < 15 MB, < 100 trang) gửi tới `/api/v1/documents/extract` chỉ để trích văn bản bị Codex từ chối `422 EXTRACTED_TEXT_TOO_LONG`; và các script thực nghiệm Phase B–D gọi `extract_pdf()` trực tiếp buộc phải import/bắt `fastapi.HTTPException`.
**Recommendation:** Giữ `pdf_extractor.py` độc lập FastAPI (ném `InvalidPDFError`/`PDFPageLimitExceededError`), chuyển toàn bộ ánh xạ `HTTPException` về `document_service.py`, và chỉ kiểm `MAX_TEXT_CHARS` trước `diff_words` ở `comparison_service.compare_document` (`/pdf`), không chặn `/extract`.
**Confidence:** High.

---

### **Issue ID:** ADV-CX-007
**Target:** Codex
**Severity:** Medium
**Claim:** Dùng duy nhất một ngưỡng `MAX_REQUEST_BODY_BYTES = 31 MiB` cho toàn bộ ứng dụng ([round1-codex.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-codex.md#L165), [L238](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-codex.md#L238)), đồng thời trả `error_code: "REQUEST_TOO_LARGE"` ở middleware ([L243](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-codex.md#L243)) nhưng trả `error_code: "UPLOAD_TOO_LARGE"` ở `document_service` ([L175](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-codex.md#L175)).
**Evidence:** **[CONFIRMED]** Đối chiếu [round1-codex.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-codex.md#L162-L168), [L175](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-codex.md#L175), [L243](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-codex.md#L243): một trần 31 MiB dùng chung khiến `/comparisons/text` (chỉ cần tối đa ~4 MiB cho 2 chuỗi 500k ký tự UTF-8) vẫn nhận body JSON 31 MiB vào RAM; `/documents/extract` (trần 15 MiB) vẫn cho spool 31 MiB ra đĩa. Đồng thời hai mã lỗi khác nhau trên cùng HTTP `413` làm contract API thiếu nhất quán.
**Counterexample:** Client gửi 1 tệp 16 MiB tới `/extract` nhận `413 {"error_code": "UPLOAD_TOO_LARGE", ...}`, gửi tệp 32 MiB tới đúng endpoint đó lại nhận `413 {"error_code": "REQUEST_TOO_LARGE", ...}`. Gửi JSON 30 MiB rác tới `/text` vẫn vượt qua middleware và tiêu tốn RAM phân tích JSON.
**Recommendation:** Ánh xạ trần body theo từng endpoint (`31 MiB` `/pdf`, `16 MiB` `/extract`, `4 MiB` `/text`) và thống nhất duy nhất một mã lỗi `PAYLOAD_TOO_LARGE` cho mọi HTTP `413`.
**Confidence:** High.

---

### **Issue ID:** ADV-CL-006
**Target:** Claude
**Severity:** Medium
**Claim:** Kiểm tra magic bytes bằng `b"%PDF-" not in header` trong 1024 byte đầu (`file_stream.read(1024)`) để chấp nhận PDF có byte rác đứng trước ([round1-claude.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-claude.md#L94-L96), [L109](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-claude.md#L109)).
**Evidence:** **[CONFIRMED]** Chạy kiểm chứng với `contract_old.pdf`:
- `polyglot = b"<html><script>alert(1)</script></html>\n" + real_pdf`
- Kết quả: `b"%PDF-" in polyglot[:1024]` là `True`; `pdfplumber.open(BytesIO(polyglot))` mở thành công `pages=2`, trích ra `'CONTRACTDIFF / DỮ LIỆU GIẢ LẬP'`.
**Counterexample:** Tệp đa hình HTML/JS hoặc script chứa `<script>` ghép trước nội dung PDF (< 1024 byte) vượt qua bộ lọc magic của Claude với HTTP `200 OK`. Nếu các pha sau lưu trữ tệp upload hoặc tích hợp trình xem tài liệu, chấp nhận tệp polyglot ở cổng vào tạo bề mặt tấn công không cần thiết.
**Recommendation:** Yêu cầu chặt `header[:5] == b"%PDF-"` ở byte 0 và ghi rõ chính sách định dạng hỗ trợ trong tài liệu API (đánh đổi hợp lý: chặn polyglot, tránh hành vi mập mờ của preamble rác).
**Confidence:** High.

---

### **Issue ID:** ADV-CX-008
**Target:** Codex
**Severity:** Medium
**Claim:** Bổ sung cảnh báo mới `CID_FONT_ERROR` dùng regex `\(cid:\d+\)` trong `extract_pdf` ngay tại Phase A ([round1-codex.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-codex.md#L352), [L404](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-codex.md#L404)).
**Evidence:** **[CONFIRMED]** [phase-a-brief.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/phase-a-brief.md#L34-L38) chỉ yêu cầu đánh giá hành vi hiện tại của `EMPTY_TEXT`/`NULL_CHARACTER` và khẳng định hardening tối thiểu, giữ nguyên baseline (phát hiện lỗi font/encoding thuộc Tầng 1 của pha sau). Chính Codex thừa nhận ở [round1-codex.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-codex.md#L404) rằng cảnh báo mới này có thể đổi `needs_review` từ `False` sang `True` và có false-positive ([L504](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-codex.md#L504)).
**Counterexample:** Một hợp đồng kỹ thuật phần mềm hoặc tài liệu chứa chuỗi nguyên văn `(cid:101)` (ví dụ tham chiếu Content-ID trong đặc tả email/MIME) bị gắn nhầm `CID_FONT_ERROR` và đẩy `needs_review=True`, làm lệch kết quả đối chứng Baseline 1 ở RQ4.
**Recommendation:** Hoãn `CID_FONT_ERROR` sang Tầng 1 (kiểm định chất lượng trích xuất ở pha sau) cùng với nhận diện TCVN3/VNI và tỷ lệ ký tự rác, không nhồi heuristic mới vào Phase A.
**Confidence:** High.

---

### **Issue ID:** ADV-CL-007
**Target:** Claude
**Severity:** Low
**Claim:** Đặt `@router.get("/health")` trực tiếp trong `health.py`, đăng ký `api_router.include_router(health.router, tags=["Health"])` không có `prefix`, và không tạo `HealthResponse` ([round1-claude.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-claude.md#L64)).
**Evidence:** **[CONFIRMED]** Đối chiếu [app/api/router.py](file:///C:/Users/Admin/contract-diff/app/api/router.py#L7-L16) và [coding-style-profile.md](file:///C:/Users/Admin/contract-diff/docs/implementation/coding-style-profile.md#L10), [L69](file:///C:/Users/Admin/contract-diff/docs/implementation/coding-style-profile.md#L69): mọi module route khác đều gắn `prefix` tại `router.py` (`prefix="/comparisons"`, `prefix="/documents"`) và mọi endpoint đều gắn `response_model`. Thiếu `response_model=HealthResponse` khiến OpenAPI sinh schema response rỗng `{}` thay vì đối tượng `{"status": "ok"}`.
**Counterexample:** Client hoặc công cụ sinh SDK từ `/openapi.json` không nhận được kiểu trả về cho `GET /api/v1/health`, và cấu trúc `router.py` trở nên bất nhất giữa 3 module route.
**Recommendation:** Thêm `HealthResponse(BaseModel)` (2 dòng với `status: Literal["ok"]`) và đăng ký `api_router.include_router(health.router, prefix="/health", tags=["Health"])` cùng `@router.get("", response_model=HealthResponse)`.
**Confidence:** High.

---

## Phần 2 — Self-correction (Tự kiểm điểm Round 1 — Antigravity)

### Các điểm thừa nhận sai / cần sửa trong [round1-antigravity.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-antigravity.md)

1. **[CONFIRMED — Thừa nhận sai nghiêm trọng] Bug `PDF.close()` làm vô hiệu đếm trang dừng sớm ([round1-antigravity.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-antigravity.md#L95-L96)):** Đề xuất Round 1 của tôi đặt `PDFPage.create_pages(pdf.doc)` bên trong `with pdfplumber.open(file_stream) as pdf:`. Kiểm chứng thực tế ở `ADV-CX-002` chứng minh khi thoát `with`, `PDF.close()` vẫn duyệt `self.pages` và dựng toàn bộ 2.000 `Page` (`0,2793s`). **Sửa lại:** Tiền kiểm số trang bằng `PDFDocument(PDFParser(file_stream), password="")` + `islice(PDFPage.create_pages(doc), max_pages + 1)` **trước** khi gọi `pdfplumber.open()`, rồi `seek(0)` (`0,0402s`).
2. **[CONFIRMED — Thừa nhận sai mức High] Bỏ sót `MalformedPDFException` và `IndexError` trong `extract_pdf` ([round1-antigravity.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-antigravity.md#L95-L97)):** Khối `except (PdfminerException, PDFException, PSEOF, ValueError, TypeError, OSError)` ở Round 1 bỏ lọt `pdfplumber.utils.exceptions.MalformedPDFException` (không kế thừa `PdfminerException`) và `IndexError` (`/CropBox [0 0]`), gây HTTP 500 trên các PDF lỗi bbox. **Sửa lại:** Bổ sung `MalformedPDFException`, `IndexError`, `AttributeError` vào bộ bắt lỗi thư viện trong `extract_pdf`.
3. **[CONFIRMED — Thừa nhận sai mức High] Bỏ sót giới hạn độ dài văn bản/token cho `/comparisons/pdf` ([round1-antigravity.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-antigravity.md#L87)):** Round 1 chỉ kiểm `MAX_TEXT_TOKENS` trong `compare_text`, quên áp `MAX_TEXT_CHARS` và giới hạn token trước `diff_words` trong `compare_document` (`/pdf`), đồng thời chưa có fast-path bằng nhau (chuỗi/token) như Codex §3.8. **Sửa lại:** Bổ sung helper kiểm tra chung trước `diff_words` cho cả `/text` và `/pdf` (không áp cho `/extract`).
4. **[CONFIRMED — Thừa nhận sai mức Medium] Đánh giá quá mức rủi ro Path Traversal của `filename` ở Phase A và lỗi cross-platform của `Path(...).name` ([round1-antigravity.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-antigravity.md#L104), [L239-L241](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-antigravity.md#L239-L241)):** Codex ([L388](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-codex.md#L388)) và Claude ([L168-L169](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-claude.md#L168-L169)) đúng khi chỉ ra Phase A không dùng `filename` để mở/ghi đường dẫn nên chưa có Path Traversal. Hơn nữa `PurePosixPath("C:\\temp\\a.pdf").name` trả nguyên `'C:\\temp\\a.pdf'` trên Linux. **Sửa lại:** Hạ vệ sinh `filename` xuống mức không bắt buộc ở Phase A (giữ metadata hoặc chỉ chuẩn hóa tối thiểu khi lưu trữ/xuất HTML ở pha sau).
5. **[CONFIRMED — Thừa nhận điều chỉnh mức Medium] Validator khoảng trắng lọc thêm ZWSP/BOM/NUL ([round1-antigravity.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-antigravity.md#L81)):** Lập luận của Claude ([round1-claude.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-claude.md#L79), [L140](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-claude.md#L140)) thuyết phục: `str.strip()` khớp 1-1 với tokenizer `r"\S+"` (đã chặn cả `\x1c`, `\u00a0`, `\u3000`). **Sửa lại:** Chấp nhận dùng `str.strip()` để giữ tính nhất quán tuyệt đối "hợp lệ ⇔ ≥1 token".
6. **[CONFIRMED — Thừa nhận thiếu sót mức Low] Bị cắt cụt mục 10.7 do giới hạn timeout CLI ([round1-antigravity.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/round1-antigravity.md#L355-L358))**, và đồng tình bổ sung lập trường của Claude về việc **chấp nhận PDF chỉ có owner password (mật khẩu người dùng rỗng `""`)** (vốn mới dừng ở mức `[HYPOTHETICAL]` trong Round 1 của tôi).

### Các điểm giữ nguyên (bảo vệ bằng bằng chứng)
- **Conditional `HTTPException` handler cho payload phẳng `{"error_code", "detail"}`:** Đã kiểm chứng giữ nguyên 404/405 mặc định và 422 Pydantic, khớp đúng v2 §3.2.
- **Pure-ASGI body-size middleware theo từng endpoint + 1 mã `PAYLOAD_TOO_LARGE`:** Khắc phục triệt để việc Starlette spool file không giới hạn và tránh 2 mã lỗi 413 khác nhau của Codex.
- **Hai ngoại lệ 1 dòng trong `pdf_extractor.py` (`InvalidPDFError`, `PDFPageLimitExceededError`):** Giữ extractor sạch khỏi FastAPI (hơn Codex) và không dán nhãn nhầm `ValueError` (hơn Claude).
- **Từ chối PDF 0 trang bằng `400`, giữ `HealthResponse` + `prefix="/health"`, không thêm `is_identical` cho `/pdf`, và sửa `EMPTY_TEXT` khi trang chỉ có `"\x00"` (`text.replace("\x00", "").strip()`):** Đều có phản ví dụ đã xác nhận, tác động nhỏ, không vượt phạm vi Phase A.

---

## Phần 3 — Lập trường cho 13 điểm bất đồng

1. **Dạng body lỗi:** Chọn top-level `{"error_code", "detail"}` qua conditional `HTTPException` handler (Codex, Antigravity) — khớp v2 §3.2 và đã xác nhận không làm thay đổi 404/405 hay 422 Pydantic.
2. **Middleware ASGI giới hạn body:** Chọn pure-ASGI middleware bọc `receive()` đếm chunk với giới hạn riêng theo endpoint (`31 MiB` `/pdf`, `16 MiB` `/extract`, `4 MiB` `/text`) + kiểm per-file ở service (Antigravity, tránh phụ thuộc reverse proxy ngoài repo như Claude).
3. **Magic `%PDF-`:** Chọn kiểm chặt ở byte 0 (`header[:5] == b"%PDF-"`) (Codex, Antigravity) để chặn tệp polyglot HTML/JS+PDF đã chứng minh vượt qua cửa 1024 byte của Claude.
4. **PDF mã hóa mở được với mật khẩu rỗng:** Chọn **chấp nhận** (Claude) vì nhiều hợp đồng thực tế đặt owner password khóa in/sửa nhưng mở đọc bình thường; bác bỏ quy tắc `pdf.doc.encryption is not None` của Codex.
5. **Đếm trang:** Chọn đếm dừng sớm `islice(PDFPage.create_pages(doc), max_pages + 1)` trên `PDFDocument(PDFParser(...))` **trước** `pdfplumber.open()` (sửa lỗi `PDF.close()` của cả Codex & Antigravity R1 và lỗi dựng toàn bộ `Page` của `len(pdf.pages)` bên Claude).
6. **Ngân sách token/diff + giới hạn text cho `/pdf`:** Áp `MAX_TEXT_CHARS` + fast-path bằng nhau (Codex) + trần token thực tế trước `diff_words` cho cả `/text` và `/pdf` (không chặn `/extract` như Codex; bác bỏ `MAX_DIFF_TOKEN_PRODUCT = 4_000_000` quá thấp của Codex và việc bỏ trống bảo vệ của Claude).
7. **`/pdf` thêm `is_identical` + `is_token_identical`:** Chọn **không thêm** ở Phase A (Claude, Antigravity) để tránh bẫy trả `is_identical=True` cho hai hợp đồng scan không có text khác nhau.
8. **Validator khoảng trắng:** Chọn **`str.strip()`** (Codex, Claude; Antigravity tự điều chỉnh) để giữ tương đương 1-1 với tokenizer `r"\S+"` của Baseline 1.
9. **Vệ sinh filename `Path(...).name`:** Chọn **giữ metadata nguyên trạng** ở Phase A (Codex, Claude; Antigravity tự điều chỉnh hạ mức ưu tiên vì Phase A chưa ghi file ra đĩa).
10. **PDF 0 trang:** Chọn trả **HTTP `400` (`INVALID_OR_ENCRYPTED_PDF`)** (Codex, Antigravity) để loại bỏ lỗ hổng `200 OK` với `needs_review=False` mà Claude bỏ sót.
11. **Exception ở extractor:** Chọn 2 lớp ngoại lệ 1 dòng kế thừa `ValueError` (`InvalidPDFError`, `PDFPageLimitExceededError`) trong `pdf_extractor.py` và ánh xạ sang `HTTPException` ở `document_service.py` (Antigravity), tránh phụ thuộc FastAPI trong extractor (Codex) và tránh bắt nhầm `ValueError` (Claude).
12. **`HealthResponse` schema & prefix router:** Chọn **có `HealthResponse` + `prefix="/health"` trong `router.py`** (Codex, Antigravity) để nhất quán với `coding-style-profile.md` và OpenAPI.
13. **Warning `CID_FONT_ERROR` và sửa `EMPTY_TEXT` khi chỉ có NUL:** **Bác bỏ `CID_FONT_ERROR`** ở Phase A (vượt phạm vi, dễ báo nhầm, làm lệch Baseline 1) và **chọn sửa `EMPTY_TEXT` bằng `text.replace("\x00", "").strip()`** (Antigravity) để vá lỗi bỏ sót cảnh báo trên trang chỉ chứa NUL.
