# Code Review — Antigravity

> Kiểm chứng hồi quy: `PYTHONDONTWRITEBYTECODE=1 .venv\Scripts\python.exe -m pytest -q -p no:cacheprovider` → `83 passed in 2.51s`. Mọi bằng chứng `[CONFIRMED]` bên dưới được chạy lại trực tiếp trên code hiện tại.

---

### CR-AG-001
- **ID:** CR-AG-001 · **Severity:** Critical
- **File:line:** [app/extractors/pdf_extractor.py:24-31](file:///C:/Users/Admin/contract-diff/app/extractors/pdf_extractor.py#L24-L31), [app/api/routes/health.py:7-9](file:///C:/Users/Admin/contract-diff/app/api/routes/health.py#L7-L9)
- **Vấn đề:** Một tệp PDF hỏng chỉ ~290 byte có đối tượng tự tham chiếu (`3 0 obj 3 0 R endobj`) trong cây `/Pages` khiến `count_pdf_pages` rơi vào **vòng lặp vô hạn (100% CPU, không bao giờ kết thúc và không ném `RecursionError`)** bên trong `pdfminer.pdftypes.resolve1()` (`while isinstance(x, PDFObjRef): x = x.resolve()` không kiểm tra chu trình). Khác với rủi ro `R-CPU` (`SequenceMatcher`) và `R-BOMB` (stream nén/vector) trong `round3-consensus.md` §2, lỗi này xảy ra trước cả khi `pdfplumber` mở tệp và không hề cần nén hay dữ liệu lớn. Nghiêm trọng hơn, cả 4 endpoint — **kể cả `health_endpoint` (`def health_endpoint()`, không phải `async def`)** — đều chạy trên cùng threadpool AnyIO mặc định (40 thread) và không có timeout/cô lập tiến trình (D14): chỉ cần 40 request × 290 byte (~12 KB) là **treo vĩnh viễn toàn bộ server, làm chết cả `/api/v1/health` và `/api/v1/comparisons/text`**.
- **Bằng chứng:** `[CONFIRMED]`
  - Lệnh:
    ```powershell
    $env:PYTHONDONTWRITEBYTECODE='1'; .venv\Scripts\python.exe -c "import faulthandler; faulthandler.dump_traceback_later(2, exit=True); from io import BytesIO; from app.extractors.pdf_extractor import extract_pdf; pdf = b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n3 0 R\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n136\n%%EOF\n'; print(len(pdf)); extract_pdf(BytesIO(pdf))"
    ```
  - Output:
    ```text
    Timeout (0:00:02)!
    Thread ... (most recent call first):
      File "...\pdfminer\pdfdocument.py", line 843 in getobj
      File "...\pdfminer\pdftypes.py", line 102 in resolve
      File "...\pdfminer\pdftypes.py", line 114 in resolve1
      File "...\pdfminer\pdftypes.py", line 203 in dict_value
      File "...\pdfminer\pdfpage.py", line 104 in depth_first_search
      ...
      File "...\app\extractors\pdf_extractor.py", line 29 in count_pdf_pages
    ```
- **Đề xuất sửa:**
  1. Đổi `health_endpoint` sang `async def health_endpoint():` để liveness probe không bị khóa khi worker threadpool bị treo.
  2. Chặn chu trình tham chiếu gián tiếp (ví dụ kiểm tra/bọc bước resolve hoặc chạy trích xuất PDF trong subprocess có hard timeout — gắn trực tiếp với R-TIMEOUT) trước khi đưa vào vận hành; trước mắt tối thiểu chuyển `extract_pdf` sang tiến trình con có timeout hoặc thêm guard chống `PDFObjRef` lặp chu trình.

---

### CR-AG-002
- **ID:** CR-AG-002 · **Severity:** High
- **File:line:** [app/extractors/pdf_extractor.py:13](file:///C:/Users/Admin/contract-diff/app/extractors/pdf_extractor.py#L13), [app/extractors/pdf_extractor.py:24-31](file:///C:/Users/Admin/contract-diff/app/extractors/pdf_extractor.py#L24-L31)
- **Vấn đề:** Tương tác giữa quyết định **D9** và **D10** sai khi gặp code thật: ít nhất **4 lớp ngoại lệ** do PDF hỏng (`KeyError`, `ZeroDivisionError`, `struct.error`, `AssertionError`) lọt khỏi `count_pdf_pages` và gây **HTTP 500 Internal Server Error** trên cả `/api/v1/documents/extract` lẫn `/api/v1/comparisons/pdf`. Nguyên nhân gốc: `pdfplumber.pdf.PDF.__init__` và `iter_pages` thực chất bọc mọi `Exception` của `PDFDocument`/`PDFPage.create_pages` vào `PdfminerException` (`pdfplumber/pdf.py:51,160`). Khi D9 gọi trực tiếp `PDFDocument(PDFParser(...))` và `PDFPage.create_pages(...)` trước `pdfplumber.open`, nhưng D10 chỉ bắt `PDF_PARSE_ERRORS = (PSException, MalformedPDFException, TypeError, IndexError, ValueError, AttributeError)`, các lỗi parse từ `/Encrypt` thiếu khóa (`/P`, `/StrF`, `/StmF`), `/Length 0`, `/P` tràn 32-bit, hoặc `/PageLabels` có `/St -1` với `/S /R` không còn được bọc nữa và thoát thẳng thành 500.
- **Bằng chứng:** `[CONFIRMED]`
  - Lệnh (trên `extract_pdf` và qua `TestClient` tới cả 2 endpoint PDF):
    ```powershell
    $env:PYTHONDONTWRITEBYTECODE='1'; .venv\Scripts\python.exe C:\Users\Admin\.gemini\antigravity-cli\brain\021da3a2-2510-43c3-bf8f-c6d9710c93df\scratch\probe1.py
    $env:PYTHONDONTWRITEBYTECODE='1'; .venv\Scripts\python.exe C:\Users\Admin\.gemini\antigravity-cli\brain\021da3a2-2510-43c3-bf8f-c6d9710c93df\scratch\probe_errors.py
    $env:PYTHONDONTWRITEBYTECODE='1'; .venv\Scripts\python.exe C:\Users\Admin\.gemini\antigravity-cli\brain\021da3a2-2510-43c3-bf8f-c6d9710c93df\scratch\probe_http.py
    ```
  - Output:
    ```text
    encrypt_missing_keys: *** UNHANDLED 500 *** builtins.KeyError: 'P'
    encrypt_v4_bad_cfm:   *** UNHANDLED 500 *** builtins.KeyError: 'StrF'
    encrypt_v5_missing_oe:*** UNHANDLED 500 *** builtins.KeyError: 'StmF'
    encrypt_v2_bad_len:   *** UNHANDLED 500 *** builtins.ZeroDivisionError: division by zero
    encrypt_huge_p:       *** UNHANDLED 500 *** struct.error: 'L' format requires 0 <= number <= 4294967295
    pagelabels_roman_neg: *** UNHANDLED 500 *** builtins.AssertionError

    extract encrypt_missing_keys: status=500 body='Internal Server Error'
    compare encrypt_missing_keys: status=500 body='Internal Server Error'
    extract encrypt_v2_bad_len:   status=500 body='Internal Server Error'
    compare encrypt_v2_bad_len:   status=500 body='Internal Server Error'
    extract encrypt_huge_p:       status=500 body='Internal Server Error'
    compare encrypt_huge_p:       status=500 body='Internal Server Error'
    ```
- **Đề xuất sửa:** Mở rộng `PDF_PARSE_ERRORS` thêm `(KeyError, ZeroDivisionError, struct.error, AssertionError, OverflowError, NotImplementedError, RecursionError)` (hoặc trong phạm vi hẹp bọc đúng 2 lời gọi thư viện `count_pdf_pages` / `read_page_texts`, re-raise tường minh `(OSError, MemoryError)` rồi chuyển các `Exception` còn lại thành `InvalidPDFError`), đồng thời bổ sung test khóa cho từng loại lỗi trên.

---

### CR-AG-003
- **ID:** CR-AG-003 · **Severity:** High
- **File:line:** [app/main.py:15-20](file:///C:/Users/Admin/contract-diff/app/main.py#L15-L20), [app/schemas/comparison.py:5-15](file:///C:/Users/Admin/contract-diff/app/schemas/comparison.py#L5-L15)
- **Vấn đề:** Quyết định **D4** ("Không đụng `RequestValidationError`") gặp lỗi thực tế: gửi JSON chỉ 35 byte chứa UTF-16 lone surrogate (`{"old_text": "\uD800", "new_text": "a"}` hoặc byte UTF-8 lỗi `\xed\xa0\x80`) tới `POST /api/v1/comparisons/text` gây **HTTP 500 Internal Server Error (`UnicodeEncodeError`)** thay vì 422. Chuỗi lỗi: `json.loads` tạo chuỗi Python `'\ud800'` → Pydantic ném `RequestValidationError` kèm `'input': '\ud800'` → handler mặc định của FastAPI tạo `JSONResponse` gọi `json.dumps(..., ensure_ascii=False).encode("utf-8")` → sập vì UTF-8 không mã hóa được surrogate đơn lẻ. Kèm theo đó, handler mặc định sao chép nguyên văn trường `"input"` vào response 422, gây **khuếch đại phản hồi** (~500 KB khi `old_text` vượt `MAX_TEXT_CHARS`, hoặc tới ~1–31 MB khi multipart gửi field `file` không có thuộc tính `filename=`).
- **Bằng chứng:** `[CONFIRMED]`
  - Lệnh:
    ```powershell
    $env:PYTHONDONTWRITEBYTECODE='1'; .venv\Scripts\python.exe C:\Users\Admin\.gemini\antigravity-cli\brain\021da3a2-2510-43c3-bf8f-c6d9710c93df\scratch\probe_surrogate.py
    ```
  - Output:
    ```text
    fastapi.exceptions.RequestValidationError: 1 validation error:
      {'type': 'string_unicode', 'loc': ('body', 'old_text'), 'msg': 'Input should be a valid string, unable to parse raw data as a unicode string', 'input': '\ud800'}
    ...
    UnicodeEncodeError: 'utf-8' codec can't encode character '\ud800' in position 156: surrogates not allowed
    lone_surrogate_diff: status=500 ct=text/plain; charset=utf-8 body='Internal Server Error'
    lone_surrogate_same: status=500 ct=text/plain; charset=utf-8 body='Internal Server Error'
    ```
  - Đo khuếch đại response 422:
    ```text
    text_too_long 422 response bytes: 500158
    missing_filename_attr 422 response bytes: 1000153
    ```
- **Đề xuất sửa:** Đăng ký `@app.exception_handler(RequestValidationError)` trong `app/main.py`: loại bỏ hoặc cắt ngắn/escape trường `"input"` khỏi mỗi phần tử lỗi (vẫn giữ nguyên cấu trúc 422 `{"detail": [{"type", "loc", "msg", ...}]}` tương thích FastAPI, hoặc serialize an toàn không để surrogate sống trong UTF-8).

---

### CR-AG-004
- **ID:** CR-AG-004 · **Severity:** High
- **File:line:** [app/extractors/pdf_extractor.py:38-42](file:///C:/Users/Admin/contract-diff/app/extractors/pdf_extractor.py#L38-L42), [tests/test_comparison_service.py:128-134](file:///C:/Users/Admin/contract-diff/tests/test_comparison_service.py#L128-L134)
- **Vấn đề:** `read_page_texts` **vi phạm trực tiếp quyết định D10 ("Không bắt `OSError`/`MemoryError`")**: `pdfplumber/pdf.py:51` và `160` dùng `except Exception as e: raise PdfminerException(e)`, mà `MemoryError` là lớp con của `Exception`. Khi `MemoryError` xảy ra trong `pdfplumber.open` hoặc `pdf.pages`, nhánh `except PdfminerException` tại `pdf_extractor.py:40` chỉ kiểm tra `isinstance(error.args[0], OSError)` nên **dán nhãn sai lỗi hết bộ nhớ hệ thống thành `InvalidPDFError` → HTTP 400 `INVALID_OR_ENCRYPTED_PDF`**. Ngoài ra, test `test_extract_pdf_does_not_hide_io_errors` ([tests/test_comparison_service.py:128-134](file:///C:/Users/Admin/contract-diff/tests/test_comparison_service.py#L128-L134)) ném `OSError` ngay ở lần `read()` đầu tiên trong `count_pdf_pages`, **chưa bao giờ đi tới `read_page_texts` dòng 40–41**, nên không thực sự kiểm chứng nhánh tháo vỏ `PdfminerException`.
- **Bằng chứng:** `[CONFIRMED]`
  - Lệnh (giả lập `MemoryError` trong `pdfplumber.open` và truy vết `FailingStream`):
    ```powershell
    $env:PYTHONDONTWRITEBYTECODE='1'; .venv\Scripts\python.exe C:\Users\Admin\.gemini\antigravity-cli\brain\021da3a2-2510-43c3-bf8f-c6d9710c93df\scratch\probe_http.py
    ```
  - Output:
    ```text
    === A. MemoryError inside pdfplumber.open (read_page_texts) ===
    CONFIRMED: MemoryError inside pdfplumber.open mislabeled as InvalidPDFError (400)! cause=PdfminerException((MemoryError('simulated OOM inside pdfplumber.open'),))

    === 1. FailingStream traceback ===
      File "...\app\extractors\pdf_extractor.py", line 49, in extract_pdf
        page_count = count_pdf_pages(file_stream, max_pages)
      File "...\app\extractors\pdf_extractor.py", line 28, in count_pdf_pages
        document = PDFDocument(PDFParser(file_stream), password="")
    OSError: disk error
    ```
- **Đề xuất sửa:** Sửa `app/extractors/pdf_extractor.py:40` thành `if error.args and isinstance(error.args[0], (OSError, MemoryError)): raise error.args[0] from error` (re-raise lỗi gốc hoặc `raise`), và bổ sung test cho cả `OSError` lẫn `MemoryError` xảy ra ở lượt đọc thứ hai bên trong `read_page_texts`.

---

### CR-AG-005
- **ID:** CR-AG-005 · **Severity:** Medium
- **File:line:** [app/main.py:13](file:///C:/Users/Admin/contract-diff/app/main.py#L13), [app/api/routes/documents.py:8-12](file:///C:/Users/Admin/contract-diff/app/api/routes/documents.py#L8-L12), [app/schemas/comparison.py:5-7](file:///C:/Users/Admin/contract-diff/app/schemas/comparison.py#L5-L7)
- **Vấn đề:** Trần body toàn cục duy nhất `MAX_REQUEST_BODY_BYTES = 31 MiB` (D6) cho phép gửi dữ liệu rác vượt giới hạn nghiệp vụ lên các endpoint nhỏ hơn mà vẫn nhận **200 OK**:
  1. Trên `POST /api/v1/documents/extract` (giới hạn 15 MiB/tệp): gửi part trùng tên `file` (part đầu 16 MiB rác + part sau PDF hợp lệ) hoặc part thừa `junk` 20 MiB khiến `python-multipart` ghi 16–30 MiB ra đĩa tạm (`SpooledTemporaryFile`), trong khi FastAPI chỉ lấy part `file` cuối cùng và trả **200 OK**, bỏ qua hoàn toàn `MAX_UPLOAD_FILE_BYTES` trên các part bị bỏ qua.
  2. Trên `POST /api/v1/comparisons/text` (tối đa 500k ký tự × 2): Pydantic mặc định `extra="ignore"`, nên request JSON 20–30 MiB có khóa thừa vẫn được `json.loads` nạp toàn bộ vào RAM rồi trả **200 OK**.
  3. (Ghi nhận thêm về D6) `RequestBodyLimitMiddleware` trả hai định dạng khác nhau cho cùng lỗi 413: `text/plain` (`"Content Too Large"`) khi có header `Content-Length`, nhưng `application/json` (`{"detail":"Content Too Large"}`) khi gửi `Transfer-Encoding: chunked` vì `ExceptionMiddleware` nằm bên trong middleware này và bắt `_RequestBodyTooLarge(HTTPException)`. Test `test_request_body_limit_rejects_before_parsing` ([tests/test_comparisons_api.py:298-308](file:///C:/Users/Admin/contract-diff/tests/test_comparisons_api.py#L298-L308)) chỉ kiểm tra nhánh `Content-Length`.
- **Bằng chứng:** `[CONFIRMED]`
  - Output từ `probe_http.py`:
    ```text
    duplicate file (16MiB bad + ok): status=200 body='{"filename":"good.pdf","page_count":1,"pages":[{"page_number":1,"text":"Hello","warnings":[]}]}'
    extra ignored 20MiB part on /extract: status=200 body='{"filename":"good.pdf","page_count":1,"pages":[{"page_number":1,"text":"Hello","warnings":[]}]}'
    20MiB JSON with extra key on /text: status=200 body='{"is_identical":false,"is_token_identical":false,"old_length":1,"new_length":1,...'
    413 with Content-Length: status=413 ct=text/plain; charset=utf-8 body='Content Too Large'
    413 chunked (no Content-Length): status=413 ct=application/json body='{"detail":"Content Too Large"}'
    ```
- **Đề xuất sửa:** Đặt `model_config = ConfigDict(extra="forbid")` cho `TextComparisonRequest` và cân nhắc áp giới hạn body theo từng route (hoặc tối thiểu bổ sung test cho nhánh chunked 413 và ghi rõ giới hạn 31 MiB áp chung trong tài liệu API).

---

### CR-AG-006
- **ID:** CR-AG-006 · **Severity:** Medium
- **File:line:** [app/services/comparison_service.py:21-33](file:///C:/Users/Admin/contract-diff/app/services/comparison_service.py#L21-L33), [app/services/document_service.py:25-28](file:///C:/Users/Admin/contract-diff/app/services/document_service.py#L25-L28)
- **Vấn đề:** `compare_document` chỉ fail-fast ở mức `validate_pdf_stream` (kích thước + 5 byte `%PDF-`), nhưng sau đó thực thi **trích xuất đầy đủ toàn bộ `old_file`** (có thể 100 trang nặng) trước khi kiểm tra cấu trúc/số trang (`count_pdf_pages`) của `new_file` — và tương tự, trích xuất xong toàn bộ `new_file` mới kiểm tra `check_text_length(old_filename, ...)` của `old_file`. Nếu `new_file` là PDF 101 trang, 0 trang, hoặc mã hóa mật khẩu (vẫn có đầu `%PDF-`), server tốn trọn chi phí giải mã `old_file` rồi mới trả 400/422. Ngoài ra, `extract_document` chạy lại `validate_pdf_stream` lần thứ hai cho mỗi tệp.
- **Bằng chứng:** `[CONFIRMED]` — đọc trực tiếp luồng gọi tại [app/services/comparison_service.py:23-32](file:///C:/Users/Admin/contract-diff/app/services/comparison_service.py#L23-L32):
  `validate_pdf_stream(old)` → `validate_pdf_stream(new)` → `extract_document(old)` (gồm `validate_pdf_stream` + `count_pdf_pages` + `read_page_texts`) → `extract_document(new)` → `check_text_length(old)` → `check_text_length(new)`.
- **Đề xuất sửa:** Trong `compare_document`, chạy tiền kiểm nhẹ (`validate_pdf_stream` + đếm trang/kiểm tra mở được) cho cả hai tệp trước khi trích xuất nội dung trang, và kiểm tra `check_text_length(old_filename, old_data["fulltext"])` ngay sau khi trích xuất `old_document` trước khi trích xuất `new_document`.

---

### CR-AG-007
- **ID:** CR-AG-007 · **Severity:** Medium
- **File:line:** [app/extractors/pdf_extractor.py:34-37](file:///C:/Users/Admin/contract-diff/app/extractors/pdf_extractor.py#L34-L37)
- **Vấn đề:** Khuếch đại CPU/RAM không cần nén (`FlateDecode`): một PDF thuần văn bản chỉ **808 byte** khai báo bảng độ rộng CIDFont `/W [0 2000000 500]` khiến `pdfminer` tạo dictionary 2.000.000 phần tử trong `page.extract_text()` (~0,7 giây và ~150 MB RAM). Tăng hằng số thành `200000000` trong cùng 810 byte dễ dàng gây cạn RAM (`MemoryError`), và kết hợp với CR-AG-004 sẽ bị che giấu thành HTTP 400 nếu xảy ra ở bước khởi tạo `pdfplumber`.
- **Bằng chứng:** `[CONFIRMED]`
  - Lệnh: đoạn 3 trong script kiểm chứng `CIDFont /W [0 2000000 500]` (chạy trên `extract_pdf`).
  - Output:
    ```text
    === 3. CIDFont /W [0 2000000 500] === size=808B time=0.701s
    ```
- **Đề xuất sửa:** Ghi nhận bổ sung vào nhóm rủi ro tài nguyên cùng `R-BOMB` và xử lý triệt để bằng cô lập tiến trình con có giới hạn thời gian + bộ nhớ (`RLIMIT_AS` / job object trên Windows) ở giai đoạn sau; không nên dựa vào kích thước tệp (15 MiB) hay số trang (100) để kết luận an toàn RAM/CPU.

---

### CR-AG-008
- **ID:** CR-AG-008 · **Severity:** Low
- **File:line:** [app/extractors/pdf_extractor.py:13](file:///C:/Users/Admin/contract-diff/app/extractors/pdf_extractor.py#L13), [app/extractors/pdf_extractor.py:30-31](file:///C:/Users/Admin/contract-diff/app/extractors/pdf_extractor.py#L30-L31), [app/extractors/pdf_extractor.py:38-42](file:///C:/Users/Admin/contract-diff/app/extractors/pdf_extractor.py#L38-L42)
- **Vấn đề:** `pdfminer.pdfexceptions.PDFIOError` kế thừa đồng thời cả `PSException` lẫn `IOError` (`OSError`). Do đó cùng một loại ngoại lệ này bị xử lý mâu thuẫn giữa hai hàm trong cùng module: `count_pdf_pages` bắt qua `PSException` thành `InvalidPDFError` (400), còn `read_page_texts` thấy `isinstance(error.args[0], OSError)` là `True` nên ném lại thành 500.
- **Bằng chứng:** `[CONFIRMED]` — kiểm tra định nghĩa tại `.venv/Lib/site-packages/pdfminer/pdfexceptions.py:32`:
  ```python
  class PDFIOError(PDFException, IOError):  # PDFException kế thừa PSException; IOError là OSError
      pass
  ```
- **Đề xuất sửa:** Trong `count_pdf_pages` đặt `except OSError: raise` trước `except PDF_PARSE_ERRORS` (hoặc loại trừ tường minh `PDFIOError` khỏi nhánh `OSError` nếu coi `PDFIOError` là lỗi định dạng PDF) để hai hàm nhất quán.

---

### CR-AG-009
- **ID:** CR-AG-009 · **Severity:** Low
- **File:line:** [app/services/document_service.py:20-23](file:///C:/Users/Admin/contract-diff/app/services/document_service.py#L20-L23), [app/services/comparison_service.py:17-19](file:///C:/Users/Admin/contract-diff/app/services/comparison_service.py#L17-L19), [app/services/comparison_service.py:29-32](file:///C:/Users/Admin/contract-diff/app/services/comparison_service.py#L29-L32)
- **Vấn đề:** Đánh giá tác động tới tính hợp lệ nghiên cứu (Baseline 1): lõi thuật toán `diff_words` (fast path `old == new` tương đương toán học với `SequenceMatcher`), `compare_text` (giữ `is_identical`, chỉ thêm `is_token_identical`), và sự đồng nhất giữa `str.strip()` với `\S+` (khớp 100% trên toàn bộ 1.114.112 code point Unicode, 0 sai khác) **không làm thay đổi kết quả Baseline 1**. Tuy nhiên có hai thay đổi biên cần lưu ý khi chạy trên corpus hợp đồng thật:
  1. D8 kiểm tra `%PDF-` cố định tại byte 0 từ chối các PDF hợp lệ có UTF-8 BOM (`\xef\xbb\xbf%PDF-`) hoặc byte đệm trong 1024 byte đầu (được ISO 32000-1 và `pdfplumber`/Baseline 1 chấp nhận).
  2. `check_text_length` đo độ dài `fulltext` **đã cộng thêm `(page_count - 1) * 2` ký tự phân cách `"\n\n"`** từ `build_document_text` (tối đa 198 ký tự với 100 trang), nên tài liệu có đúng `MAX_TEXT_CHARS` ký tự trích xuất vẫn bị từ chối với 422 `TEXT_TOO_LONG`.
- **Bằng chứng:** `[CONFIRMED]`
  - Output kiểm chứng:
    ```text
    strip() vs \S+ diffs: 0 []
    === 4. BOM-prefixed PDF ===
      extract_pdf directly (Baseline 1): [{'page_number': 1, 'text': 'Hello BOM', 'warnings': []}]
    2 pages x 5 chars with MAX_TEXT_CHARS=10 (fulltext=12): status=422 body='{"error_code":"TEXT_TOO_LONG","detail":"a.pdf: văn bản trích xuất vượt quá 10 ký tự"}'
    ```
- **Đề xuất sửa:** Ghi nhận rõ giới hạn byte-0 của D8 khi tiền xử lý corpus T1 (hoặc tìm `b"%PDF-"` trong 1024 byte đầu nếu corpus thực có file BOM), và nếu muốn đo đúng số ký tự trích xuất thực thì kiểm tra `sum(len(p["text"]) for p in pages) > MAX_TEXT_CHARS` (hoặc ghi rõ trong tài liệu rằng `MAX_TEXT_CHARS` áp cho `fulltext` sau khi ghép trang).

---

### CR-AG-010
- **ID:** CR-AG-010 · **Severity:** Low
- **File:line:** [app/schemas/comparison.py:9-15](file:///C:/Users/Admin/contract-diff/app/schemas/comparison.py#L9-L15), [app/extractors/pdf_extractor.py:59-62](file:///C:/Users/Admin/contract-diff/app/extractors/pdf_extractor.py#L59-L62)
- **Vấn đề:** Không nhất quán định nghĩa "văn bản rỗng / vô nghĩa" giữa hai luồng: ở `extract_pdf` (D19), trang chỉ chứa NUL (`"\x00"`) được gắn `EMPTY_TEXT` (cùng `NULL_CHARACTER`); ngược lại ở `TextComparisonRequest.reject_blank_text`, chuỗi chỉ gồm `"\x00"` hoặc ký tự độ rộng bằng 0 (`\u200b`, `\ufeff`) vẫn qua `str.strip()` và trả **200 OK** trên `/api/v1/comparisons/text` (và tạo token diff chứa `"\x00"` hoặc `"\u200b"`).
- **Bằng chứng:** `[CONFIRMED]`
  - Output từ `probe_http.py`:
    ```text
    nul_char_text: status=200 ct=application/json body='{"is_identical":false,"is_token_identical":false,"old_length":1,"new_length":1,"changes":[{"type":"replace","old_text":"\\u0000","new_text":"a",...'
    zwsp_text:     status=200 ct=application/json body='{"is_identical":false,"is_token_identical":false,"old_length":1,"new_length":1,"changes":[{"type":"replace","old_text":"\u200b","new_text":"a",...'
    bom_text:      status=200 ct=application/json body='{"is_identical":false,"is_token_identical":false,"old_length":1,"new_length":1,"changes":[{"type":"replace","old_text":"\ufeff","new_text":"a",...'
    ```
- **Đề xuất sửa:** Tối thiểu dùng `value.replace("\x00", "").strip()` trong `reject_blank_text` để nhất quán với D19 (không làm đổi giá trị gốc trả về khi hợp lệ nên không ảnh hưởng Baseline 1); ghi nhận `\u200b`/`\ufeff` thuộc phạm vi chuẩn hóa văn bản giai đoạn sau.

---

**Kết luận: còn Critical/High** (1 Critical: CR-AG-001; 3 High: CR-AG-002, CR-AG-003, CR-AG-004). Cần xử lý trước khi chốt Phase A.
