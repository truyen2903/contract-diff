root agent idle; waiting up to 30m0s for 1 background task(s)
Đang chờ hoàn tất phép đo benchmark `diff_words` cho O6.
# Round 3 — Antigravity rebuttal

## Phản hồi phản biện

- `CX/ADV-AG-001` — **ACCEPT** — Self-correction R2 mới xử lý phần bỏ ngỏ `/pdf`; kiểm chứng mới ở O6 (`[CONFIRMED]`) xác nhận `"a "*5000` (5.000 token) đã mất `5,6584s` và hợp đồng 100 trang 25.000 token có 100 chỗ sửa mất `31,7148s`, nên rút đề xuất `MAX_TEXT_TOKENS = 50_000` ở Phase A.
- `CX/ADV-AG-002` — **ACCEPT** — `json.dumps` mặc định (`ensure_ascii=True`) cho 2×500.000 ký tự `'ệ'` dài `6.000.032` byte (> `4 MiB`), mâu thuẫn với `MAX_TEXT_CHARS = 500_000`; rút trần body riêng 4 MiB cho `/text` (xem O2).
- `CX/ADV-AG-003` — **ACCEPT** — R2 mới thừa nhận thiếu Path Traversal và lệch OS; chấp nhận thêm phản chứng `Path.name` giữ nguyên `\r\n`, `\x00`, markup HTML nên không phải bộ lọc injection, giữ `filename` là metadata ở Phase A.
- `CX/ADV-AG-004` — **PARTIAL** — Chấp nhận bỏ `OSError` khỏi nhóm 400 và bóc `OSError` bị `PdfminerException` bọc để trả 500, đồng thời không bao `try/except` quanh code tạo `warnings`; bác bỏ việc chỉ bắt `PdfminerException` vì `[CONFIRMED]` 4 PDF lỗi cấu trúc vẫn gây 500 (`MalformedPDFException`, `TypeError`, `IndexError`, `AttributeError`, xem O5).
- `CX/ADV-AG-005` — **ACCEPT** — Trong `"foo\n\n   \n\nbar"`, 3 khoảng trắng thực sự thuộc trang 2 nên giao span trả `[0, 3)` đúng hợp đồng và giữ bất biến `page_text[start:end]` tại [test_comparisons_api.py](file:///C:/Users/Admin/contract-diff/tests/test_comparisons_api.py#L88-L91); separator-only trả `[]` là đúng; rút đề xuất cắt location khoảng trắng.
- `CX/ADV-AG-006` — **ACCEPT** — Thừa nhận R1 mâu thuẫn giữa mô tả chính sách ("từ chối mọi PDF mã hóa") và luồng code không kiểm `encryption`; đã chốt theo hướng chấp nhận PDF chỉ đặt owner password (mở được bằng mật khẩu rỗng, xem O1).
- `CX/ADV-AG-007` — **ACCEPT** — ISO 32000-1 §7.5.2 quy định `%PDF-` ở dòng đầu; dung sai 1.024 byte là ghi chú hành vi Adobe Acrobat (Appendix H note 13), không phải chuẩn ISO; giữ quy tắc kiểm byte 0 và đính chính trích dẫn.
- `CX/ADV-AG-008` — **ACCEPT** — [main.py](file:///C:/Users/Admin/contract-diff/app/main.py#L6) khởi tạo `FastAPI(title="ContractDiff")` mặc định `debug=False`, nên HTTP 500 trả `'Internal Server Error'` thuần văn bản, không lộ stack trace cho client; hạ từ `[CONFIRMED]` xuống rủi ro giả định nếu bật `debug=True` hoặc đưa `str(exc)` ra response.
- `CL/ADV-CL-002` — **ACCEPT** — Rút hoàn toàn nhận định không có số đo "`< 100 ms` cho 10k–20k từ" và rút `MAX_TEXT_TOKENS = 50_000` sau benchmark O6 (`1,50s`–`31,71s` cho hợp đồng 100 trang).
- `CL/ADV-CL-004` — **ACCEPT** — Cùng bằng chứng `6.000.032` byte như `CX/ADV-AG-002`; bỏ ngưỡng 4 MiB cho `/text` và chuyển sang trần toàn cục 31 MiB (xem O2).
- `CL/ADV-CL-005` — **PARTIAL** — Chấp nhận bỏ ánh xạ trần theo path (tránh lệch prefix và sai ngưỡng `/text`); nhưng `[CONFIRMED]` kiểm chứng `RequestBodyLimitMiddleware` cho thấy `send_with_limit` ghi đè 413 thành `text/plain` khi có `Content-Length` còn chunked trả `application/json`, gây bất nhất định dạng 413 và không gắn được `error_code` thống nhất (xem O2).
- `CL/ADV-CL-006` — **ACCEPT** — Chấp nhận toàn phần phản biện về lệch OS, không loại `\r\n\x00` và đổi response không tăng bảo mật; giữ `filename` là metadata ở Phase A.
- `CL/ADV-CL-009` — **PARTIAL** — Chấp nhận bỏ `OSError` và đặt `try/except` hẹp quanh đúng lời gọi thư viện để không che lỗi hạ tầng/lập trình; bác bỏ chỉ bắt `PdfminerException` vì `[CONFIRMED]` bỏ lọt `MalformedPDFException`, `TypeError`, `IndexError`, `AttributeError` trên PDF hỏng (xem O5).
- `CL/ADV-CL-011` — **ACCEPT** — Giống `CX/ADV-AG-005`; giữ nguyên phép giao span hiện tại để bảo toàn bất biến kiểm thử ở [test_comparisons_api.py](file:///C:/Users/Admin/contract-diff/tests/test_comparisons_api.py#L88-L91).
- `CL/ADV-CL-012` — **ACCEPT** — Rút gọn `app/core/config.py` về đúng 3 hằng số v2 (`MAX_UPLOAD_FILE_BYTES`, `MAX_PDF_PAGES`, `MAX_TEXT_CHARS`) cộng 1 hằng số dẫn xuất `MAX_REQUEST_BODY_BYTES = 2 * MAX_UPLOAD_FILE_BYTES + 1 MiB` (31 MiB).
- `CL/ADV-CL-014` — **ACCEPT** — `[CONFIRMED]` Lệnh `asyncio.ProactorEventLoop()` bị chặn tạo self-pipe trong sandbox Windows nên `TestClient` treo ở R1; hạ các khẳng định cấp HTTP chưa chạy qua `TestClient` ở R1 xuống `[HYPOTHETICAL]` (bổ sung chạy thử ASGI thuần bằng coroutine driver ở O2 bên dưới).

*(Lưu ý: `CL/ADV-CL-010` về validator `str.strip()` đã được chấp nhận trong self-correction R2 #5.)*

---

## Lập trường O1–O8

### O1 — PDF mã hóa mở được bằng mật khẩu rỗng (owner-only)
- **Lập trường:** **ACCEPT** chấp nhận (HTTP `200`, theo Claude/Antigravity); **REJECT** chặn theo `pdf.doc.encryption is not None` (Codex).
- **Lý do & bằng chứng:** Brief [phase-a-brief.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/phase-a-brief.md#L31) dẫn chiếu v2 §3.2 vốn nêu rõ `PDFPasswordIncorrect`, không yêu cầu từ chối PDF chỉ đặt owner password. Cả 3 agent đều xác nhận `pdfminer`/`pdfplumber` trích đúng toàn bộ văn bản từ PDF chỉ khóa quyền in/sửa (rất phổ biến ở hợp đồng ngân hàng/công chứng). Chặn `pdf.doc.encryption is not None` là breaking change `200 → 400` không có lợi ích bảo mật (chính Codex thừa nhận ở `CX/ADV-CL-005`).
- **Đề xuất cụ thể:** Chỉ trả `400 INVALID_OR_ENCRYPTED_PDF` khi `PDFDocument(..., password="")` / `pdfplumber.open` thất bại (`PDFPasswordIncorrect` hoặc lỗi cấu trúc). Thêm 2 test khóa hành vi: user password khác rỗng → `400`, owner-only (user password rỗng) → `200`.

### O2 — Giới hạn body & số lượng mã lỗi 413
- **Lập trường:** **PARTIAL** — **REJECT** (c) trần theo path `31/16/4 MiB` (tự rút); **ACCEPT** (b) pure-ASGI limiter trần toàn cục **31 MiB** + **1 mã lỗi 413 duy nhất** `PAYLOAD_TOO_LARGE`; xem (a) `RequestBodyLimitMiddleware` là phương án dự phòng tối giản nếu chấp nhận đánh đổi định dạng 413.
- **Bằng chứng `[CONFIRMED]`:** Chạy `.venv\Scripts\python.exe` gọi trực tiếp `starlette.middleware.body_limit.RequestBodyLimitMiddleware(max_body_size=1000)` (Starlette 1.8.0) bằng pure-coroutine ASGI driver, kể cả khi đăng ký handler chuyển `_RequestBodyTooLarge` sang JSON `PAYLOAD_TOO_LARGE`:
  ```text
  === map_413= False ===
  JSON CL:      (413, b'text/plain; charset=utf-8', b'Content Too Large')
  JSON chunked: (413, b'application/json', b'{"detail":"Content Too Large"}')
  === map_413= True ===
  JSON CL:      (413, b'text/plain; charset=utf-8', b'Content Too Large')
  JSON chunked: (413, b'application/json', b'{"error_code":"PAYLOAD_TOO_LARGE","detail":"Request body exceeds limit"}')
  ```
  Nguyên nhân nằm trong mã nguồn `starlette/middleware/body_limit.py`: `RequestBodyLimitResponder.send_with_limit` kiểm tra `if self.content_length is not None and self.content_length > self.max_body_size` và ghi đè mọi response (kể cả JSONResponse của `ExceptionMiddleware`) thành `PlainTextResponse("Content Too Large", status_code=413)`, khiến cùng một lỗi 413 trả `text/plain` khi có `Content-Length` nhưng lại trả `application/json` khi chunked.
- **Đề xuất cụ thể:**
  - Dùng 1 trần toàn cục `MAX_REQUEST_BODY_BYTES = 2 * MAX_UPLOAD_FILE_BYTES + 1024 * 1024` (31 MiB) — vừa tránh mâu thuẫn `6.000.032` byte ở `/text`, vừa không phụ thuộc prefix URL.
  - Dùng pure-ASGI middleware ngắn (~25–30 dòng) trong `app/core/` kiểm nhanh `Content-Length` + cộng dồn chunk trên `receive()`, trả thống nhất `413 application/json {"error_code": "PAYLOAD_TOO_LARGE", "detail": "..."}` (truyền exception qua luồng cleanup của `MultiPartParser`).
  - Dùng **duy nhất 1 mã lỗi `PAYLOAD_TOO_LARGE`** cho cả middleware (tổng request > 31 MiB) lẫn `document_service` (từng tệp > 15 MiB), tránh tách 2 mã `REQUEST_TOO_LARGE`/`UPLOAD_TOO_LARGE`.
  - *(Dự phòng nếu tác giả ưu tiên 1 dòng code hơn tính đồng nhất 413: dùng `RequestBodyLimitMiddleware` có sẵn và ghi rõ trong tài liệu API rằng 413 tầng transport có thể là `text/plain` không kèm `error_code`.)*

### O3 — Magic bytes `%PDF-`
- **Lập trường:** **ACCEPT** kiểm chặt tại **byte 0** (`header[:5] == b"%PDF-"`, Codex & Antigravity); **REJECT** quét 1.024 byte đầu (Claude).
- **Lý do & bằng chứng:** ISO 32000-1 §7.5.2 yêu cầu `%PDF-` ở đầu tệp; `[CONFIRMED]` tại `AG/ADV-CL-006`, tệp polyglot `b"<html><script>alert(1)</script></html>\n" + real_pdf` vượt qua điều kiện `b"%PDF-" in header[:1024]` và trả `200 OK`. Kiểm ở byte 0 đơn giản, chặn lớp tệp đa hình có preamble rác; tài liệu API cần ghi rõ chính sách này (và không tuyên bố thay thế hoàn toàn kiểm định an toàn tệp).

### O4 — Đếm trang PDF
- **Lập trường:** **ACCEPT** tiền kiểm `PDFDocument(PDFParser(file_stream), password="")` + `islice(PDFPage.create_pages(doc), max_pages + 1)` **trước** `pdfplumber.open()`, rồi `file_stream.seek(0)`; **REJECT** đặt `islice` bên trong `with pdfplumber.open(...)`.
- **Bằng chứng `[CONFIRMED]`:** Kiểm tra `inspect.getsource(pdfplumber.pdf.PDF.close)` cho thấy `PDF.close()` luôn chạy `for page in self.pages: page.close()` bất kể `self._pages` chưa được dựng. Chạy `.venv\Scripts\python.exe` đo trên PDF 2.000 trang và 100 trang trong bộ nhớ:
  ```text
  O4 inside with (2000p): cnt=101, _pages_before_exit=False, _pages_after_exit=2000, time=0.3152s
  O4 pre-check (2000p):   cnt=101, time=0.0527s
  O4 valid 100p:          precheck+open=0.0247s (cnt=100, n=100), direct_open=0.0150s
  ```
  - Đặt `islice` bên trong `with pdfplumber.open(...)` vẫn dựng toàn bộ 2.000 `Page` lúc thoát `with` (`0,3152s`).
  - Tiền kiểm trước `pdfplumber.open()` nhanh gấp **6×** trên PDF 2.000 trang (`0,0527s`, 0 `Page`), chặn luôn cả 0 trang (`cnt == 0` → `InvalidPDFError` → `400`) lẫn vượt trần (`cnt > max_pages` → `PDFPageLimitExceededError` → `422`), trong khi chi phí parse xref lần hai trên PDF 100 trang hợp lệ chỉ thêm **`9,7 ms`**.

### O5 — Phạm vi bắt lỗi parser
- **Lập trường:** **PARTIAL** — Bắt tập ngoại lệ parser có chọn lọc **sát quanh đúng lời gọi thư viện**, tuyệt đối không bắt `OSError` và chủ động bóc `OSError` bị `PdfminerException` bọc để giữ HTTP 500 cho lỗi hạ tầng/lập trình.
- **Bằng chứng `[CONFIRMED]`:** Chạy `.venv\Scripts\python.exe` kiểm chứng luồng `PDFDocument` tiền kiểm + `pdfplumber.open` + `extract_text()` trên 5 PDF hỏng cấu trúc và 1 `FailingStream` ném `OSError`:
  ```text
  zlib.error is OSError: False
  struct.error is OSError: False
  O5 PDFDocument on FailingStream:    type=OSError
  O5 pdfplumber.open on FailingStream: type=PdfminerException, args0_type=OSError, ctx=OSError
  O5 pdfplumber.open on junk:          type=PdfminerException, args0_type=PDFSyntaxError, ctx=PDFSyntaxError
  inline_pages   : step=precheck         exc=builtins.AttributeError: 'dict' object has no attribute 'objid'
  bad_mediabox   : step=open_and_extract exc=pdfplumber.utils.exceptions.MalformedPDFException
  bad_rotate     : step=open_and_extract exc=builtins.TypeError
  bad_cropbox    : step=open_and_extract exc=builtins.IndexError
  truncated      : step=precheck         exc=pdfminer.psexceptions.PSEOF
  ```
- **Đề xuất cụ thể (trong [pdf_extractor.py](file:///C:/Users/Admin/contract-diff/app/extractors/pdf_extractor.py)):**
  - Đặt 2 khối `try/except` **hẹp, chỉ bọc đúng lời gọi thư viện** (khối 1: `PDFDocument` + `islice(PDFPage.create_pages(doc), ...)`; khối 2: `pdfplumber.open`, truy cập `pdf.pages` và `page.extract_text()`); phần xây `warnings` và `pages.append(...)` nằm **ngoài** `try/except` để bug của ứng dụng không bị nuốt thành 400.
  - Trong cả 2 khối `except`:
    1. `except OSError: raise` (giữ 500 cho lỗi I/O).
    2. `except PdfminerException as exc:` nếu `(exc.args and isinstance(exc.args[0], OSError)) or isinstance(exc.__context__, OSError)` thì `raise` lại `OSError` gốc (500); ngược lại `raise InvalidPDFError(...) from exc` (400).
    3. `except (MalformedPDFException, PDFException, PSEOF, TypeError, IndexError, ValueError, AttributeError, zlib.error, struct.error) as exc: raise InvalidPDFError(...) from exc` (400).
  - `document_service.py` chỉ ánh xạ `InvalidPDFError` → `400 INVALID_OR_ENCRYPTED_PDF` và `PDFPageLimitExceededError` → `422 PDF_TOO_MANY_PAGES`.

### O6 — Admission guard cho `diff_words` và `MAX_TEXT_CHARS` trên `/pdf`
- **Lập trường:** **ACCEPT** đề xuất của Claude cho Phase A — **không thêm** ngưỡng token/`DIFF_TOO_COMPLEX` ở Phase A; **có** thêm fast-path equality; **có** áp `MAX_TEXT_CHARS` (500.000 ký tự) lên fulltext của `/pdf` trước `diff_words` (không áp cho `/extract`).
- **Bằng chứng `[CONFIRMED]`:** Chạy `.venv\Scripts\python.exe` benchmark [diff_words](file:///C:/Users/Admin/contract-diff/app/engines/text_diff.py#L14-L54) trên fixture `tests/fixtures/contract_old.pdf` mở rộng 100 trang và input đối kháng, đo đồng thời tích `prod = len(a)*len(b)` lẫn tích vô hướng tần suất `dot = sum(ca[w]*cb[w])`:
  ```text
  Fixture: 2 pages, 1777 chars, 395 tokens, unique=210
  100p realistic (5 edits)         | chars= 92921 | toks=20450 | prod=  417998000 | dot=   2861150 | changes= 25 | t=1.5021s
  100p varied 25k tok (5 edits)    | chars=180530 | toks=25000 | prod=  625000000 | dot=   3597380 | changes=  5 | t=1.7663s
  100p varied 25k tok (100 edits)  | chars=180530 | toks=25000 | prod=  625000000 | dot=   3597000 | changes=100 | t=31.7148s
  Adversarial a*3000               | chars=  6000 | toks= 3000 | prod=    9000000 | dot=   8997000 | changes=  1 | t=2.0378s
  Adversarial a*5000               | chars= 10000 | toks= 5000 | prod=   25000000 | dot=  24995000 | changes=  1 | t=5.6584s
  Adversarial ab*2500              | chars= 10000 | toks= 5000 | prod=   25000000 | dot=  12497500 | changes=  1 | t=2.9131s
  100p realistic IDENTICAL         | chars= 92921 | toks=20450 | prod=  418202500 | dot=   2866650 | changes=  0 | t=0.7422s
  ```
  - Hai ca `100p varied 25k tok` (5 sửa đổi vs 100 sửa đổi) có **cùng** số token (`25.000`), **cùng** `prod` (`625M`) và **cùng** `dot` (`3,60M`), nhưng thời gian chạy chênh **18×** (`1,77s` vs `31,71s`) do số nhánh đệ quy của `SequenceMatcher.get_matching_blocks()`.
  - Như vậy không có ngưỡng tĩnh tiền-diff nào vừa bảo đảm không từ chối nhầm hợp đồng thực tế ≤ 100 trang vừa chặn được CPU chậm.
- **Đề xuất cụ thể:**
  1. Trong [text_diff.py](file:///C:/Users/Admin/contract-diff/app/engines/text_diff.py#L14-L24), thêm fast-path `if old_text == new_text: return []` và `if old == new: return []` (cắt `0,74s` của hợp đồng 100 trang giống nhau về ~0 ms).
  2. Trong [comparison_service.py](file:///C:/Users/Admin/contract-diff/app/services/comparison_service.py#L15-L25) (`compare_document`), kiểm `len(old_data["fulltext"]) > MAX_TEXT_CHARS or len(new_data["fulltext"]) > MAX_TEXT_CHARS` trước `diff_words` → trả `422 TEXT_TOO_LONG` (đồng nhất giới hạn đầu vào `diff_words` với `/text`, không chặn `/extract`).
  3. Không thêm `DIFF_TOO_COMPLEX` ở Phase A; ghi rõ hạn chế CPU của `SequenceMatcher(autojunk=False)` và để Phase B+ xử lý căn cơ bằng căn chỉnh theo điều khoản/đoạn kết hợp process isolation.

### O7 — Health endpoint & schema
- **Lập trường:** **ACCEPT** dùng `HealthResponse(status: Literal["ok"])` + `prefix="/health"` tại [router.py](file:///C:/Users/Admin/contract-diff/app/api/router.py#L7-L16) + `@router.get("", response_model=HealthResponse)` (Codex, Antigravity); **REJECT** bỏ schema (Claude).
- **Lý do:** Toàn bộ router hiện tại (`comparisons`, `documents`) đều gắn `prefix` trong `router.py` và mọi endpoint đều khai báo `response_model`. Thêm `HealthResponse` chỉ tốn 2 dòng nhưng sinh OpenAPI schema rõ ràng (`{"status": "ok"}`) thay vì `{}` rỗng; dùng route `""` tránh redirect trailing slash cho `GET /api/v1/health`.

### O8 — Vị trí kiểm tra kích thước/magic & thứ tự kiểm tra ở `/pdf`
- **Lập trường:** **ACCEPT** kiểm tra kích thước (`0 < size <= MAX_UPLOAD_FILE_BYTES`) và magic bytes (`%PDF-` tại byte 0) bằng `seek/tell` trong [document_service.py](file:///C:/Users/Admin/contract-diff/app/services/document_service.py), **và** tách helper `validate_pdf_stream(file_stream)` để `/pdf` tiền kiểm rẻ **cả 2 tệp** trước khi trích xuất tệp đầu tiên.
- **Bằng chứng `[CONFIRMED]`:** Chạy `.venv\Scripts\python.exe` kiểm chứng trên `tempfile.SpooledTemporaryFile`: `seek(0, os.SEEK_END)` → `tell()` → `seek(0)` → `read(5)` → `seek(0)` cho `size=14, hdr=b'%PDF-', pos_after=0` với chi phí $O(1)$, không nạp tệp vào RAM.
- **Đề xuất cụ thể:**
  - `validate_pdf_stream(file_stream)` trong `document_service.py`: `0` byte → `400 INVALID_OR_ENCRYPTED_PDF`; `> 15 MiB` → `413 PAYLOAD_TOO_LARGE`; `header != b"%PDF-"` → `400 INVALID_OR_ENCRYPTED_PDF`; cuối hàm luôn `file_stream.seek(0)`.
  - `extract_document` gọi `validate_pdf_stream(file_stream)` trước `extract_pdf`.
  - `compare_document` trong [comparison_service.py](file:///C:/Users/Admin/contract-diff/app/services/comparison_service.py#L15-L18) gọi `validate_pdf_stream(old_file_stream)` và `validate_pdf_stream(new_file_stream)` **trước** khi gọi `extract_document(...)`, tránh tốn CPU parse 100 trang của `old_file` khi `new_file` rỗng, sai định dạng hoặc vượt 15 MiB.
