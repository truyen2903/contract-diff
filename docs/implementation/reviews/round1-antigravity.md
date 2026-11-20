# Round 1 — Antigravity (Adversarial Reviewer)

## 1. Problem understanding

Phase A có mục tiêu **hardening tối thiểu nhưng đúng** cho 4 endpoint hiện có (`GET /api/v1/health`, `POST /api/v1/comparisons/text`, `POST /api/v1/comparisons/pdf`, `POST /api/v1/documents/extract`) trước khi bước vào các pha cấu trúc ở Kế hoạch v2, tuân thủ quy ước phân tầng và phong cách trong [coding-style-profile.md](file:///C:/Users/Admin/contract-diff/docs/implementation/coding-style-profile.md).

Dưới góc nhìn hội đồng phản biện kỹ thuật, bài toán Phase A không chỉ là "bổ sung vài câu `if` validate" theo [ke-hoach-trien-khai-do-an-v2.md](file:///C:/Users/Admin/AppData/Local/Temp/claude/7a81e431fe1166c9/3ae8a7db-bd9c-402e-b3dc-61914ab153f4/scratchpad/plandocs/ke-hoach-trien-khai-do-an-v2.md) (§3.2, §3.3, §7.1, §9 Câu 8, §10), mà còn phải **vạch trần các giả định sai trong chính Kế hoạch v2 và codebase hiện tại**:

1. **Giả định sai về bắt ngoại lệ `pdfplumber` [CONFIRMED]:** Kế hoạch v2 §3.2 yêu cầu bắt `PDFSyntaxError`, `PDFPasswordIncorrect` của `pdfminer.six`, nhưng `pdfplumber==0.11.10` bọc toàn bộ ngoại lệ mở PDF vào `pdfplumber.utils.exceptions.PdfminerException` (kế thừa trực tiếp từ `Exception`, **không** kế thừa `PDFException`/`PDFSyntaxError`/`PDFPasswordIncorrect`). Làm đúng như chữ trong v2 sẽ vẫn làm API sập 500.
2. **Giả định sai về bất biến Reconstruction của v2 §7.1 và §9 Câu 8 [CONFIRMED]:** V2 sửa F03 bằng cách tuyên bố áp dụng `changes` lên `old_text` từ cuối lên đầu rồi chuẩn hóa khoảng trắng sẽ tái tạo `new_text`. Phản chứng: mọi thay đổi `type == "insert"` trong [text_diff.py](file:///C:/Users/Admin/contract-diff/app/engines/text_diff.py#L29-L35) đều có `old_span = None`, tức **không hề chứa vị trí chèn trong `old_text`**, nên phép tái tạo đó bất khả thi về mặt toán học khi có `insert`.
3. **Giả định sai về chống DoS bằng `MAX_UPLOAD_FILE_BYTES = 15 MB` ở tầng route/service và `MAX_TEXT_CHARS = 500_000` [CONFIRMED]:** Starlette `MultiPartParser` đã spool không giới hạn file ra đĩa tạm trước khi handler chạy; còn `SequenceMatcher(autojunk=False)` chỉ cần **11.999 ký tự** (2,4% của 500.000 ký tự) đầu vào đối kháng đã ngốn **4,575 giây** CPU.
4. **Mâu thuẫn nội bộ ngay trong Kế hoạch v2 [CONFIRMED]:** §3.3 và §10 mục 2 giữ `is_identical` + thêm `is_token_identical`, nhưng §9 Câu 8 lại đổi tên thành `is_exact_match` + `is_token_identical` (phá vỡ tương thích ngược); §3.2 yêu cầu payload lỗi phẳng `{"error_code": ..., "detail": ...}` mâu thuẫn với `HTTPException` mặc định của FastAPI (`{"detail": ...}`); §3.2 yêu cầu `COMPARISON_TIMEOUT_SECONDS = 30.0` dù trên Windows không có `SIGALRM` và thread đồng bộ không thể hủy trong Python.
5. **Tác động lên câu hỏi nghiên cứu (RQ1–RQ4):** Phase A khóa hành vi **Baseline 1** (`diff_words` phẳng). Nếu Phase A vô tình đổi `autojunk=False` thành `True`, chuẩn hóa Unicode NFC ngầm, hay lọc ký tự `"\x00"` trong `diff_words`, kết quả đối chứng Baseline 1 ở RQ2/RQ4 sẽ bị lệch khỏi hiện trạng đã mô tả ở v2 §1.1. Ngược lại, nếu để lọt các bug hiện có (PDF 0 trang cho `needs_review=False`, `text_mapping` nối sai separator, timeout giả gây treo worker), toàn bộ phép đo latency (H3b) và đánh giá fail-safe (RQ4) sẽ mất độ tin cậy.

---

## 2. Current implementation

Kiểm tra trực tiếp trên repository `C:\Users\Admin\contract-diff` (Python `3.14.3`, `fastapi==0.143.3`, `starlette==1.8.0`, `pydantic==2.14.1`, `pdfplumber==0.11.10`, `pdfminer==20260107`):

* **Lưu ý thực thi môi trường [CONFIRMED]:** Trong sandbox Windows hiện tại, `TestClient` và `asyncio.run` bị treo khi tạo socketpair nội bộ của AnyIO/ProactorEventLoop; mọi xác nhận dưới đây được kiểm chứng trực tiếp bằng `python -B -c` đồng bộ trên mã nguồn thật, không làm thay đổi file nào trong repo (`git status --short` giữ nguyên).

| Thành phần | Vị trí (`file:line`) | Hiện trạng thực tế & Lỗ hổng | Trạng thái |
|---|---|---|---|
| App & Router | [main.py](file:///C:/Users/Admin/contract-diff/app/main.py#L1-L8), [router.py](file:///C:/Users/Admin/contract-diff/app/api/router.py#L1-L16), [health.py](file:///C:/Users/Admin/contract-diff/app/api/routes/health.py) | `health.py` rỗng 0 byte, chưa include vào `api_router`. `app.openapi()['paths']` chỉ có 3 đường dẫn: `/api/v1/comparisons/pdf`, `/api/v1/comparisons/text`, `/api/v1/documents/extract`. Không có middleware giới hạn body. | **[CONFIRMED]** |
| Route so sánh | [comparisons.py](file:///C:/Users/Admin/contract-diff/app/api/routes/comparisons.py#L9-L21) | Tác giả **đã thêm sẵn** fallback `old_file.filename or "old_document.pdf"` và `new_file.filename or "new_document.pdf"` (khác mô tả lỗi cũ của v2 §1.1). Tuy nhiên cả hai endpoint đều là `def` đồng bộ, không kiểm tra size/magic bytes/lỗi PDF, không vệ sinh `filename` (chấp nhận `"   "` và `"../../etc/passwd"`). | **[CONFIRMED]** |
| Route trích xuất | [documents.py](file:///C:/Users/Admin/contract-diff/app/api/routes/documents.py#L7-L12) | Có fallback `file.filename or "document.pdf"`, không kiểm tra size/magic bytes/lỗi PDF/số trang, không vệ sinh `filename`. | **[CONFIRMED]** |
| Schema so sánh | [comparison.py](file:///C:/Users/Admin/contract-diff/app/schemas/comparison.py#L4-L37) | `TextComparisonRequest` chỉ có `Field(min_length=1)`: không có `max_length`, chấp nhận chuỗi chỉ khoảng trắng (`"   "`, `"\n\t"`). `TextComparisonResponse` chỉ có `is_identical` (không có `is_token_identical`). `PDFComparisonResponse` chỉ có `old_document`, `new_document`, `changes`, `needs_review`. `ChangeItem` mặc định `old_locations=[]`, `new_locations=[]` nên `/text` cũng trả 2 mảng rỗng này. | **[CONFIRMED]** |
| Schema tài liệu | [document.py](file:///C:/Users/Admin/contract-diff/app/schemas/document.py#L3-L11) | `DocumentPage` (`page_number`, `text`, `warnings`), `DocumentExtractionResponse` (`filename`, `page_count`, `pages`). Không có trường `needs_review` ở `/documents/extract`. | **[CONFIRMED]** |
| Service so sánh | [comparison_service.py](file:///C:/Users/Admin/contract-diff/app/services/comparison_service.py#L5-L36) | `compare_text` (`L9`) tính `"is_identical": old_text == new_text` mâu thuẫn với `changes = diff_words(...)` khi chỉ khác khoảng trắng. `compare_document` (`L22-L23`) tính `needs_review = any(page["warnings"] for page in ...)` → trả `False` khi PDF có 0 trang! Không có `try/except`. | **[CONFIRMED]** |
| Service tài liệu | [document_service.py](file:///C:/Users/Admin/contract-diff/app/services/document_service.py#L3-L10) | Gọi thẳng `extract_pdf(file_stream)`, không kiểm tra stream rỗng, dung lượng, magic bytes, số trang hay ngoại lệ. | **[CONFIRMED]** |
| PDF Extractor | [pdf_extractor.py](file:///C:/Users/Admin/contract-diff/app/extractors/pdf_extractor.py#L1-L17) | `pdfplumber.open(file_stream)` tung `PdfminerException` (chưa bắt) với tệp 0 byte, text giả `.pdf`, PDF hỏng, PDF mã hóa. `L8-L11`: nếu trang chỉ chứa `"\x00"` thì `"\x00".strip()` khác rỗng → chỉ gắn `NULL_CHARACTER`, **bỏ sót `EMPTY_TEXT`**. Dùng `enumerate(pdf.pages, start=1)` ép tải toàn bộ danh sách `Page` vào bộ nhớ. | **[CONFIRMED]** |
| Text Diff Engine | [text_diff.py](file:///C:/Users/Admin/contract-diff/app/engines/text_diff.py#L4-L54) | Tách token bằng `r"\S+"`, dùng `SequenceMatcher(autojunk=False)`. Không đối xứng với khối lặp/hoán vị; `insert` có `old_span=None`; dễ dính DoS $O(N^2)$ ở đầu vào lặp ngắn; nhạy cảm với NFC vs NFD tiếng Việt. | **[CONFIRMED]** |
| Text Mapping | [text_mapping.py](file:///C:/Users/Admin/contract-diff/app/engines/text_mapping.py#L1-L36) | `L6`: `separator = "" if page["page_number"] == 1 else "\n\n"` sai khi danh sách trang không bắt đầu từ 1 (chèn `"\n\n"` đầu chuỗi, lệch offset +2) hoặc trùng `page_number == 1` (dính từ thành `"helloworld"`). `L18-L36`: `span_to_page_locations` sinh `PageLocation` trỏ vào trang chỉ toàn khoảng trắng (`"   "`) khi thay đổi vắt qua 3 trang; trả `[]` nếu span nằm trọn trong separator `"\n\n"`. | **[CONFIRMED]** |
| Tests & Deps | [requirements.txt](file:///C:/Users/Admin/contract-diff/requirements.txt#L1-L10), [test_comparisons_api.py](file:///C:/Users/Admin/contract-diff/tests/test_comparisons_api.py#L1-L139), [test_text_diff.py](file:///C:/Users/Admin/contract-diff/tests/test_text_diff.py#L1-L12) | `requirements.txt` đã có 7 gói pin trên Python 3.14.3 (mâu thuẫn mục tiêu `Python 3.11.x` của v2 §7.3). `test_comparison_api.py` và `test_comparison_service.py` rỗng 0 byte (trùng tên gần giống với `test_comparisons_api.py` số nhiều); `test_text_diff.py` không có hàm `test_*`. | **[CONFIRMED]** |

---

## 3. Proposed solution

Thiết kế hardening tối thiểu, giữ nguyên kiến trúc 4 tầng mỏng theo [coding-style-profile.md](file:///C:/Users/Admin/contract-diff/docs/implementation/coding-style-profile.md), không thêm thư viện ngoài:

### 3.1. Cấu hình giới hạn tập trung — `app/core/config.py` (mới)
Dùng hằng số module-level (không tạo class `BaseSettings` hay thêm `pydantic-settings`):
* `MAX_UPLOAD_FILE_BYTES: int = 15 * 1024 * 1024` (15 MB/tệp)
* `MAX_PDF_PAGES: int = 100`
* `MAX_TEXT_CHARS: int = 500_000`
* `MAX_TEXT_TOKENS: int = 50_000` (bổ sung phòng thủ DoS cho `SequenceMatcher(autojunk=False)` — xem Mục 4 & 6)
* `MAX_MULTIPART_OVERHEAD_BYTES: int = 1 * 1024 * 1024` (1 MB cho header/boundary multipart)
* `MAX_PDF_COMPARE_BODY_BYTES: int = 2 * MAX_UPLOAD_FILE_BYTES + MAX_MULTIPART_OVERHEAD_BYTES` (31 MB)
* `MAX_PDF_EXTRACT_BODY_BYTES: int = MAX_UPLOAD_FILE_BYTES + MAX_MULTIPART_OVERHEAD_BYTES` (16 MB)
* `MAX_TEXT_COMPARE_BODY_BYTES: int = 4 * 1024 * 1024` (đủ cho 2 chuỗi 500k ký tự UTF-8 tiếng Việt ~3 MB + JSON overhead)
* `PDF_MAGIC_BYTES: bytes = b"%PDF-"`

### 3.2. Endpoint Health — `app/api/routes/health.py` & `app/api/router.py`
* `app/api/routes/health.py`:
  * Định nghĩa `router = APIRouter()`, hàm `health_check_endpoint()` cho `@router.get("", response_model=HealthResponse)` trả `{"status": "ok"}`.
* `app/schemas/health.py` (hoặc đặt `HealthResponse(BaseModel)` gồm `status: str` trong [document.py](file:///C:/Users/Admin/contract-diff/app/schemas/document.py) hoặc ngay trong `app/schemas/health.py` cho gọn miền — khuyến nghị `app/schemas/health.py` để không trộn miền).
* [router.py](file:///C:/Users/Admin/contract-diff/app/api/router.py): đăng ký `api_router.include_router(health.router, prefix="/health", tags=["Health"])` → lộ diện chính xác tại `GET /api/v1/health` (HTTP `200`, `{"status": "ok"}`).

### 3.3. Chính sách Định dạng Lỗi Thống nhất & ASGI Body-Size Guardrail — `app/main.py`
1. **Định dạng lỗi (`error_code` + `detail`):**
   * Dùng chính `HTTPException` của FastAPI ở tầng service (tuân thủ [coding-style-profile.md](file:///C:/Users/Admin/contract-diff/docs/implementation/coding-style-profile.md#L46-L47)), truyền `detail={"error_code": "...", "detail": "..."}`.
   * Đăng ký một handler gọn (~6 dòng) `@app.exception_handler(HTTPException)` trong [main.py](file:///C:/Users/Admin/contract-diff/app/main.py): nếu `isinstance(exc.detail, dict) and "error_code" in exc.detail`, trả thẳng `JSONResponse(status_code=exc.status_code, content=exc.detail, headers=exc.headers)` để tạo payload phẳng `{"error_code": "...", "detail": "..."}` đúng chuẩn v2 §3.2; ngược lại ủy quyền cho `fastapi.exception_handlers.http_exception_handler`.
   * **Không** ghi đè `RequestValidationError` (422 của Pydantic/FastAPI) để giữ nguyên 100% tương thích với test hiện có (`response.json()["detail"]` là danh sách lỗi có `"loc"` tại [test_comparisons_api.py](file:///C:/Users/Admin/contract-diff/tests/test_comparisons_api.py#L136-L139)).
   * Danh mục mã lỗi chuẩn hóa:
     * `413 Payload Too Large`: `PAYLOAD_TOO_LARGE` (quá dung lượng body hoặc tệp > 15 MB)
     * `400 Bad Request`: `INVALID_OR_ENCRYPTED_PDF` (tệp 0 byte, sai magic bytes `%PDF-`, PDF hỏng cấu trúc, PDF mã hóa, hoặc PDF 0 trang)
     * `422 Unprocessable Entity` (nghiệp vụ): `PDF_PAGE_LIMIT_EXCEEDED` (> 100 trang), `TEXT_TOKEN_LIMIT_EXCEEDED` (> `MAX_TEXT_TOKENS`)
     * `422 Unprocessable Entity` (Pydantic): chuỗi rỗng, chuỗi chỉ khoảng trắng/ký tự vô hình, chuỗi > `MAX_TEXT_CHARS`, thiếu field bắt buộc.
2. **Middleware ASGI thuần giới hạn kích thước request trước khi Starlette spool ra đĩa:**
   * Viết một pure-ASGI middleware nhỏ `MaxBodySizeMiddleware` (không dùng `BaseHTTPMiddleware` để tránh đọc đệm lại stream) gắn vào `app` trong [main.py](file:///C:/Users/Admin/contract-diff/app/main.py), ánh xạ giới hạn theo đường dẫn (`POST /api/v1/comparisons/pdf` → 31 MB, `POST /api/v1/documents/extract` → 16 MB, `POST /api/v1/comparisons/text` → 4 MB):
     * Kiểm tra nhanh header `Content-Length` (nếu có và hợp lệ > limit → trả ngay `413` `{"error_code": "PAYLOAD_TOO_LARGE", "detail": "..."}` mà không đọc body).
     * Bọc hàm `receive()` để cộng dồn `received_bytes += len(message.get("body", b""))` trên từng chunk (chặn `Transfer-Encoding: chunked` và `Content-Length` giả mạo): nếu vượt limit → dừng đọc và trả ngay `413`.

### 3.4. So sánh văn bản (`/api/v1/comparisons/text`) — Schema & Service
* [comparison.py](file:///C:/Users/Admin/contract-diff/app/schemas/comparison.py):
  * `TextComparisonRequest`:
    * `old_text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)`
    * `new_text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)`
    * Bổ sung `@field_validator("old_text", "new_text")` kiểm tra sau khi loại bỏ ký tự khoảng trắng Unicode, NUL `"\x00"`, BOM `"\ufeff"`, và zero-width (`\u200b`, `\u200c`, `\u200d`, `\u2060`) mà chuỗi rỗng thì `raise ValueError("Văn bản không được chỉ chứa khoảng trắng hoặc ký tự trống")` → FastAPI tự trả HTTP `422`.
  * `TextComparisonResponse`:
    * Giữ nguyên `is_identical: bool`, `old_length: int`, `new_length: int`, `changes: list[ChangeItem]`.
    * Bổ sung **`is_token_identical: bool`** (tương thích ngược theo v2 §3.3 & §10 mục 2; **bác bỏ** việc đổi tên `is_identical` thành `is_exact_match` ở v2 §9 Câu 8).
  * `PDFComparisonResponse`: **không** thêm `is_identical` hay `is_token_identical` ở Phase A (xem phản biện ở Mục 4 & 5 về bẫy PDF scan rỗng bị báo giống hệt nhau).
* [comparison_service.py](file:///C:/Users/Admin/contract-diff/app/services/comparison_service.py):
  * Trong `compare_text(old_text: str, new_text: str)`: kiểm tra số token (`len(tokenize_with_spans(...))` hoặc đếm nhanh trước khi gọi `SequenceMatcher`) vượt `MAX_TEXT_TOKENS` thì raise `HTTPException(422, detail={"error_code": "TEXT_TOKEN_LIMIT_EXCEEDED", ...})`.
  * Trả về thêm `"is_token_identical": len(changes) == 0` bên cạnh `"is_identical": old_text == new_text`.

### 3.5. Upload an toàn, Trích xuất PDF & Sửa lỗi Mapping
* `app/extractors/pdf_extractor.py`:
  * Giữ extractor **không phụ thuộc FastAPI**. Định nghĩa tối giản 2 ngoại lệ 1 dòng kế thừa `ValueError`: `InvalidPDFError(ValueError)` và `PDFPageLimitExceededError(ValueError)` (ngoại lệ có chủ đích theo [coding-style-profile.md](file:///C:/Users/Admin/contract-diff/docs/implementation/coding-style-profile.md#L71)).
  * Hàm `extract_pdf(file_stream, max_pages: int = MAX_PDF_PAGES) -> list[dict]`:
    1. Gọi `file_stream.seek(0)` trước khi mở.
    2. Mở `with pdfplumber.open(file_stream) as pdf:` trong `try/except (PdfminerException, PDFException, PSEOF, ValueError, TypeError, OSError)` → `raise InvalidPDFError(...)`.
    3. **Đếm trang dừng sớm (short-circuit)** trước khi đụng `pdf.pages`: duyệt `PDFPage.create_pages(pdf.doc)` tối đa `max_pages + 1` lần; nếu đếm được `0` trang → `raise InvalidPDFError("Tệp PDF không có trang nào")`; nếu vượt `max_pages` → `raise PDFPageLimitExceededError(...)`.
    4. Trích văn bản từng trang trong khối `try/except (PdfminerException, PDFException, ValueError, TypeError)` để bắt lỗi lazy parsing khi giải mã nội dung trang.
    5. Sửa điều kiện `EMPTY_TEXT` tại [pdf_extractor.py](file:///C:/Users/Admin/contract-diff/app/extractors/pdf_extractor.py#L10-L11):
       ```python
       if not text.replace("\x00", "").strip():
           warnings.append("EMPTY_TEXT")
       ```
* `app/services/document_service.py`:
  * Thêm helper nội bộ `_sanitize_filename(filename: str | None, default_name: str) -> str`: dùng `Path(filename.strip()).name` (loại bỏ `../`, `\`, ký tự điều khiển `\r\n\x00`), fallback `default_name` nếu rỗng hoặc là `.`/`..`.
  * Thêm helper nội bộ `_validate_pdf_stream(file_stream, max_bytes: int = MAX_UPLOAD_FILE_BYTES) -> None`:
    * Xác định chính xác số byte bằng `file_stream.seek(0, os.SEEK_END)`, `size = file_stream.tell()`, `file_stream.seek(0)`:
      * Nếu `size == 0` → `HTTPException(400, detail={"error_code": "INVALID_OR_ENCRYPTED_PDF", "detail": "Tệp PDF rỗng (0 byte)."})`.
      * Nếu `size > max_bytes` → `HTTPException(413, detail={"error_code": "PAYLOAD_TOO_LARGE", "detail": ...})`.
    * Đọc `header = file_stream.read(len(PDF_MAGIC_BYTES))` rồi `file_stream.seek(0)`:
      * Nếu `header != PDF_MAGIC_BYTES` → `HTTPException(400, detail={"error_code": "INVALID_OR_ENCRYPTED_PDF", "detail": "Tệp không có chữ ký đầu tệp PDF hợp lệ (%PDF-)."})`.
  * Trong `extract_document(filename, file_stream, default_filename: str = "document.pdf")`: gọi `_sanitize_filename`, `_validate_pdf_stream`, gọi `extract_pdf(file_stream, max_pages=MAX_PDF_PAGES)` và ánh xạ `InvalidPDFError` → HTTP `400` (`INVALID_OR_ENCRYPTED_PDF`), `PDFPageLimitExceededError` → HTTP `422` (`PDF_PAGE_LIMIT_EXCEEDED`).
* [comparisons.py](file:///C:/Users/Admin/contract-diff/app/api/routes/comparisons.py#L14-L21) & [documents.py](file:///C:/Users/Admin/contract-diff/app/api/routes/documents.py#L7-L12): giữ route siêu mỏng, truyền `old_file.filename` / `new_file.filename` / `file.filename` vào service (để service làm chuẩn hóa tên tệp tập trung).
* [text_mapping.py](file:///C:/Users/Admin/contract-diff/app/engines/text_mapping.py):
  * `L5-L6`: đổi `for page in pages:` + `page["page_number"] == 1` thành `for index, page in enumerate(pages): separator = "" if index == 0 else "\n\n"`.
  * `L18-L36`: giữ `span_to_page_locations` đơn giản nhưng lưu ý lọc/cắt khoảng trắng biên hoặc bỏ qua trang chỉ có khoảng trắng khi sinh location (chi tiết phân tích ở Mục 4 & 5).
* **Timeout 30s (`COMPARISON_TIMEOUT_SECONDS`):** **Hoãn khỏi Phase A**, không cài `asyncio.wait_for` giả hiệu.

---

## 4. Technical rationale

Mỗi quyết định thiết kế dưới đây đều đi kèm đối chiếu phản biện và phân tích điểm yếu cố hữu (không có quyết định nào "hoàn hảo"):

### 4.1. `is_identical` vs `is_token_identical` (và tại sao không thêm cho `/pdf`)
* **Quyết định:** Giữ `is_identical = (old_text == new_text)` và thêm `is_token_identical = (len(changes) == 0)` trên `TextComparisonResponse`; giữ nguyên `PDFComparisonResponse`.
* **Lập luận:**
  * **[CONFIRMED]** `compare_text("a b", "a  b")` trả `{'is_identical': False, 'old_length': 3, 'new_length': 4, 'changes': []}`. Thêm `is_token_identical` làm minh bạch ngữ nghĩa cho người dùng và giải quyết F03 mà không phá client cũ.
  * **[CONFIRMED]** Đổi tên `is_identical` thành `is_exact_match` (như v2 §9 Câu 8) là breaking change không cần thiết và mâu thuẫn với chính v2 §3.3 & §10 mục 2.
  * **Tại sao KHÔNG thêm `is_identical` / `is_token_identical` vào `/comparisons/pdf` ở Phase A [CONFIRMED]:** Khi hai hợp đồng scan khác nhau hoàn toàn đều không có text layer, `extract_pdf` trả `text=""` cho mọi trang của cả hai tệp, dẫn tới `old_fulltext == new_fulltext == ""` và `changes == []`. Nếu `/pdf` trả `is_identical: True` hoặc `is_token_identical: True`, hệ thống đang đưa ra khẳng định sai lệch nghiêm trọng ("hai hợp đồng giống hệt nhau") dù có `needs_review: True`.
* **Điểm yếu của quyết định này:** Client gọi cả `/text` và `/pdf` sẽ thấy schema bất đối xứng (`/text` có `is_identical` + `is_token_identical`, `/pdf` không có), buộc client phải tự kiểm tra `len(changes) == 0 and not needs_review` ở `/pdf`. Ngoài ra, `is_token_identical` vẫn trả `False` khi hai chuỗi tiếng Việt giống hệt nhau về mặt thị giác nhưng khác dạng chuẩn hóa Unicode NFC vs NFD (**[CONFIRMED]**: `diff_words('Điều 1', 'Đie\u0302\u0300u 1')` trả `replace`).

### 4.2. Kiểm tra kích thước upload 2 lớp (ASGI Middleware + Service Stream Check)
* **Quyết định:** Kết hợp `MaxBodySizeMiddleware` (ASGI thuần) và kiểm tra kích thước từng tệp qua `seek(0, SEEK_END)` trong `document_service.py`.
* **Lập luận:**
  * **[CONFIRMED]** Kiểm tra mã nguồn `starlette.formparsers.MultiPartParser` (Starlette 1.8.0): `MultiPartParser.spool_max_size = 1048576` (1 MB) và `on_part_data` chỉ áp `max_part_size` khi `self._current_part.file is None` (tức chỉ áp cho form field văn bản, **không giới hạn file upload**). Do đó mọi tệp tải lên > 1 MB đều bị Starlette ghi không giới hạn vào `SpooledTemporaryFile` trên đĩa tạm **trước khi route handler chạy**.
  * Chỉ kiểm tra `UploadFile.size` trong handler là **quá trễ** để chặn cạn đĩa/băng thông; chỉ kiểm tra `Content-Length` lại bị vượt mặt bởi `Transfer-Encoding: chunked`; chỉ kiểm tra tổng body 31 MB ở middleware lại lọt trường hợp `old_file = 20 MB`, `new_file = 1 MB` (tổng 21 MB ≤ 31 MB nhưng vi phạm giới hạn 15 MB/tệp). Do đó bắt buộc phải có cả 2 lớp.
* **Điểm yếu của quyết định này:** Middleware ASGI không giải mã ranh giới multipart nên ở `/comparisons/pdf`, một request có `old_file = 25 MB` + `new_file = 1 MB` vẫn bị spool 26 MB ra đĩa tạm rồi mới bị lớp 2 từ chối `413` (giảm rủi ro từ vô hạn xuống chặn trên 31 MB, không triệt tiêu hoàn toàn spooling). Đồng thời, middleware gắn cứng theo `path` sẽ dễ lệch nếu sau này đổi prefix `/api/v1`.

### 4.3. Kiểm tra Magic Bytes `%PDF-` và Bắt Ngoại lệ `PdfminerException`
* **Quyết định:** Kiểm tra chặt `header == b"%PDF-"` ở offset 0, đồng thời bắt `(PdfminerException, PDFException, PSEOF, ValueError, TypeError, OSError)` trong `pdf_extractor.py`, và từ chối PDF 0 trang bằng HTTP `400`.
* **Lập luận:**
  * **[CONFIRMED]** Chạy thực nghiệm với `pdfplumber==0.11.10`: `PdfminerException.__mro__` là `['PdfminerException', 'Exception', 'BaseException', 'object']`, `issubclass(PdfminerException, PDFSyntaxError)` và `issubclass(PdfminerException, PDFPasswordIncorrect)` đều là `False`. Tệp 0 byte, text thường, `%PDF-1.4\ngarbage`, và PDF mã hóa đều ném `PdfminerException`. Nếu chỉ bắt các class của `pdfminer.six` như v2 §3.2 viết, 100% các ca lỗi trên vẫn văng `500`.
  * **[CONFIRMED]** PDF hợp lệ có `/Count 0` đi qua `extract_pdf` trả `[]`, khiến `compare_document` trả `200 OK`, `changes=[]`, `needs_review=False` — một lỗ hổng im lặng nghiêm trọng.
  * **[CONFIRMED]** `pdfplumber.PDF.pages` khởi tạo toàn bộ `Page` object cho mọi trang trước khi trả list, nên kiểm tra `len(pdf.pages) > 100` vẫn tốn tài nguyên dựng 10.000 đối tượng `Page` cho PDF 10.000 trang. Đếm dừng sớm bằng `PDFPage.create_pages(pdf.doc)` chặn đứng vấn đề này.
* **Điểm yếu của quyết định này:**
  * Theo chuẩn ISO 32000-1 §7.5.2, `%PDF-` được phép xuất hiện trong 1024 byte đầu (**[CONFIRMED]**: `b'JUNK' + zero_page_pdf` vẫn mở được bởi `pdfplumber`). Kiểm tra chặt ở byte 0 sẽ từ chối các PDF hiếm có UTF-8 BOM/preamble rác đứng trước `%PDF-` (đánh đổi một phần độ khoan dung lấy khả năng chặn tệp đa hình/polyglot).
  * Việc gom chung PDF hỏng và PDF mã hóa vào một mã lỗi `INVALID_OR_ENCRYPTED_PDF` (theo v2 §3.2) làm người dùng không phân biệt được tệp bị lỗi tải lên với tệp cần gỡ mật khẩu.
  * **[CONFIRMED]** Với PDF có luồng `FlateDecode` hỏng (`bad-flate-stream-pdf`), `pdfminer` nuốt lỗi âm thầm và trả trang rỗng `warnings=['EMPTY_TEXT']` chứ không ném ngoại lệ, nên không trả `400`.

### 4.4. Tại sao KHÔNG làm Timeout 30s ở Phase A
* **Quyết định:** Không cài `COMPARISON_TIMEOUT_SECONDS = 30.0` bằng `asyncio.wait_for` hay `signal` trong Phase A; dùng giới hạn đầu vào làm chặn trên tài nguyên và hoãn timeout thật sang tầng triển khai/kiến trúc sau.
* **Lập luận:**
  * **[CONFIRMED]** Trên Windows, `hasattr(signal, "SIGALRM")` là `False`.
  * **[CONFIRMED]** Các route hiện tại là hàm `def` đồng bộ chạy trên threadpool của AnyIO. Trong Python, không có cơ chế an toàn nào để giết một thread đang mắc kẹt trong vòng lặp C/Python của `pdfplumber` hay `SequenceMatcher`. Nếu bọc `asyncio.wait_for(..., timeout=30.0)` quanh `run_in_threadpool`, client nhận `504` sau 30 giây nhưng **thread nền vẫn sống và tiếp tục đốt 100% CPU/RAM**, khiến 40 request chậm làm treo toàn bộ server.
  * Muốn timeout thật và giết được tác vụ trên Windows phải dùng `ProcessPoolExecutor` / `multiprocessing.Process` (chế độ `spawn`), đòi hỏi tuần tự hóa stream qua IPC và trả chi phí khởi tạo tiến trình mới, vi phạm trực tiếp ràng buộc Phase A ("không đổi kiến trúc", "hardening tối thiểu").
* **Điểm yếu của quyết định này:** Chưa thực hiện đúng một mục của v2 §3.2 (`COMPARISON_TIMEOUT_SECONDS = 30.0`); một tệp PDF hợp lệ 100 trang chứa đồ họa vector dày đặc vẫn có thể xử lý quá 30 giây và chiếm giữ 1 worker thread.

### 4.5. Vị trí đặt logic & Tác động lên RQ1–RQ4
* **Quyết định:** Giữ `app/engines/` và `app/extractors/` sạch khỏi FastAPI; đặt validation nghiệp vụ và ánh xạ `HTTPException` ở `app/services/`; không đổi `autojunk=False` và không chuẩn hóa NFC trong `diff_words`.
* **Lập luận:** Tuân thủ đúng [coding-style-profile.md](file:///C:/Users/Admin/contract-diff/docs/implementation/coding-style-profile.md#L7-L14) và bảo toàn tính toàn vẹn của **Baseline 1** cho RQ2/RQ4 (so sánh công bằng với hệ thống đề xuất trong Chương 4).
* **Điểm yếu của quyết định này:** Giới hạn `MAX_TEXT_TOKENS = 50_000` dù thấp hơn 500.000 ký tự vẫn chưa loại bỏ hoàn toàn kịch bản xấu nhất $O(N^2)$ của `SequenceMatcher(autojunk=False)` (xem Mục 6 & 9); đặt `HTTPException` trong `document_service.py` và `comparison_service.py` làm tầng service gắn nhẹ với FastAPI (tuy chấp nhận được theo coding style profile §6, nhưng khi các script thực nghiệm `experiments/run_evaluation.py` ở pha sau gọi trực tiếp service sẽ phải bắt `HTTPException` thay vì ngoại lệ Python thuần).

---

## 5. Edge cases

Dưới đây là các ca biên và phản ví dụ thuật toán đã kiểm chứng trên codebase hiện tại:

1. **Phản ví dụ phá vỡ Bất biến Reconstruction của Kế hoạch v2 §7.1 & §9 Câu 8 [CONFIRMED]:**
   * Lệnh: `diff_words('a c', 'a b c')`
   * Kết quả: `[{'type': 'insert', 'old_text': '', 'new_text': 'b', 'old_span': None, 'new_span': {'start': 2, 'end': 3}}]`
   * Hệ quả: Vì `old_span` là `None`, không tồn tại vị trí chèn trong `old_text` để áp dụng `changes` từ cuối về đầu nhằm tái tạo `new_text` (kể cả sau chuẩn hóa khoảng trắng). Bất biến Reconstruction trong v2 §7.1 **sai về mặt đặc tả** đối với `diff_words`.

2. **Phản ví dụ phá vỡ tính đối xứng `diff_words(A, B)` vs `diff_words(B, A)` [CONFIRMED]:**
   * Lệnh: `diff_words('A B C D', 'C D A B')` và chiều ngược lại.
   * Kết quả:
     * `A -> B`: `[('insert', '', 'C D'), ('delete', 'C D', '')]`
     * `B -> A`: `[('insert', '', 'A B'), ('delete', 'A B', '')]`
   * Hệ quả: Nghịch đảo của `A -> B` phải là xóa/chèn `'C D'`, nhưng `B -> A` lại xóa/chèn `'A B'`. Test `test_new_to_old_reverses_changes` trong [test_comparisons_api.py](file:///C:/Users/Admin/contract-diff/tests/test_comparisons_api.py#L111-L122) chỉ pass trên cặp fixture hiện tại vì các thay đổi nằm cô lập, **không phải** tính chất tổng quát của `diff_words`.

3. **Mâu thuẫn `is_identical` với khoảng trắng [CONFIRMED]:**
   * `compare_text('a b', 'a  b')` → `{'is_identical': False, 'old_length': 3, 'new_length': 4, 'changes': []}`.
   * `TextComparisonRequest(old_text='   ', new_text='\n\t')` → hiện qua validation và trả `is_identical: False, changes: []`.

4. **Ký tự vô hình vượt mặt `.strip()` thông thường [CONFIRMED]:**
   * Lệnh: `repr('\u200b'.strip()), repr('\ufeff'.strip()), repr('\x00'.strip()), repr('\u00a0'.strip())`
   * Kết quả: `'\u200b'`, `'\ufeff'`, `'\x00'`, `''`.
   * Hệ quả: Nếu validator ở `/comparisons/text` chỉ viết `if not value.strip():`, chuỗi chứa duy nhất Zero-Width Space (`"\u200b"`), BOM (`"\ufeff"`) hoặc NUL (`"\x00"`) vẫn lọt qua với HTTP `200` và tạo token rác.

5. **Unicode tiếng Việt NFC vs NFD gây diff giả [CONFIRMED]:**
   * Lệnh: `diff_words('Điều 1', 'Đie\u0302\u0300u 1')`
   * Kết quả: `[{'type': 'replace', 'old_text': 'Điều', 'new_text': 'Điều', 'old_span': {'start': 0, 'end': 4}, 'new_span': {'start': 0, 'end': 6}}]`
   * Tác động: Hai bản hợp đồng xuất từ macOS (NFD) và Windows (NFC) sẽ báo toàn bộ từ có dấu tiếng Việt bị `replace`. Không nên tự ý chuẩn hóa NFC trong `diff_words` ở Phase A vì thay đổi offset gốc và làm lệch Baseline 1, nhưng cần test để ghi nhận rõ hành vi.

6. **Bug `text_mapping.build_document_text` phụ thuộc `page_number == 1` [CONFIRMED]:**
   * Lệnh 1: `build_document_text([{'page_number': 2, 'text': 'hello'}, {'page_number': 3, 'text': 'world'}])`
   * Kết quả 1: `{'fulltext': '\n\nhello\n\nworld', 'page_ranges': [{'page_number': 2, 'start': 2, 'end': 7}, {'page_number': 3, 'start': 9, 'end': 14}]}` (dư `"\n\n"` ở đầu).
   * Lệnh 2: `build_document_text([{'page_number': 1, 'text': 'hello'}, {'page_number': 1, 'text': 'world'}])`
   * Kết quả 2: `{'fulltext': 'helloworld', ...}` (mất separator, ghép dính 2 từ thành 1 token sai).

7. **Bug `span_to_page_locations` với trang chỉ có khoảng trắng và span trong separator [CONFIRMED]:**
   * Lệnh: trang 1 `'hello foo'`, trang 2 `'   '` (trang trống chỉ có khoảng trắng), trang 3 `'bar world'`, so với `'hello world'`.
   * Kết quả: `old_text = 'foo\n\n   \n\nbar'` (chứa cả separator tổng hợp `"\n\n"`), và `old_locations = [{'page_number': 1, 'start': 6, 'end': 9}, {'page_number': 2, 'start': 0, 'end': 3}, {'page_number': 3, 'start': 0, 'end': 3}]` — trả về vị trí thay đổi trên trang 2 dù trang 2 không có chữ nào và đã bị gắn `EMPTY_TEXT`!
   * Lệnh: `span_to_page_locations({'start': 9, 'end': 11}, page_ranges)` (span nằm gọn trong `"\n\n"`) → trả `[]` im lặng.

8. **Bug `NULL_CHARACTER` che khuất `EMPTY_TEXT` trong `pdf_extractor.py` [CONFIRMED]:**
   * Logic hiện tại tại [pdf_extractor.py](file:///C:/Users/Admin/contract-diff/app/extractors/pdf_extractor.py#L8-L11): với `text = '\x00'` hoặc `' \x00 '`, kết quả `warnings = ['NULL_CHARACTER']` (thiếu `'EMPTY_TEXT'`), dù `text.replace('\x00', '').strip() == ''`.

9. **PDF 0 trang cho `needs_review = False` [CONFIRMED]:**
   * Lệnh: `compare_document('a.pdf', BytesIO(zero_page_pdf), 'b.pdf', BytesIO(zero_page_pdf))`
   * Kết quả: `{'old_document': {'filename': 'a.pdf', 'page_count': 0, 'pages': []}, 'new_document': {'filename': 'b.pdf', 'page_count': 0, 'pages': []}, 'changes': [], 'needs_review': False}`.

10. **PDF có `FlateDecode` hỏng hoặc mã hóa mật khẩu rỗng (owner password only):**
    * **[CONFIRMED]** Luồng `FlateDecode` hỏng (`NOTZLIBDATA`) không ném ngoại lệ mà trả `[{'page_number': 1, 'text': '', 'warnings': ['EMPTY_TEXT']}]`.
    * **[HYPOTHETICAL]** PDF đặt owner password (chỉ khóa in/sửa, user password rỗng `""`) — rất phổ biến ở mẫu hợp đồng ngân hàng/cơ quan nhà nước — sẽ được `pdfplumber` mở với `password=""` thành công (với RC4/AES-128) hoặc văng lỗi giải mã tùy bản `cryptography` (với AES-256 R6); cần bổ sung fixture kiểm chứng khi có công cụ sinh PDF mã hóa.

11. **Lỗi font bảng mã cũ (TCVN3/VNI) vượt qua `needs_review` [HYPOTHETICAL]:**
    * Văn bản trích ra dạng `"§iÒu 1"` không chứa `"\x00"` và không rỗng nên `warnings == []`, `needs_review == False`. Đây là giới hạn có chủ đích ở Phase A (thuộc phạm vi Tầng 1 của pha sau theo v2 §4.1).

---

## 6. Security considerations

1. **Unbounded Disk-Fill DoS qua Starlette `MultiPartParser` [CONFIRMED]:**
   * `MultiPartParser.spool_max_size` = 1 MB và `on_part_data` bỏ qua `max_part_size` với mọi phần file upload. Không có `MaxBodySizeMiddleware` ở tầng ASGI, kẻ tấn công chỉ cần đẩy 1 request 5 GB là có thể làm đầy ổ đĩa `%TEMP%` trên máy chủ trước khi FastAPI gọi endpoint.
   * **Lưu ý đồng thời [HYPOTHETICAL]:** Ngay cả khi đã có giới hạn 15 MB/tệp (31 MB/request `/pdf`), với threadpool mặc định 40 luồng của AnyIO, 40 request song song vẫn có thể chiếm tới ~1,2 GB đĩa tạm cùng lúc; cần bảo đảm Starlette đóng `UploadFile` ở `finally` và giới hạn concurrency/body ở reverse proxy khi triển khai thực tế.

2. **Algorithmic Complexity CPU DoS trên `SequenceMatcher(autojunk=False)` [CONFIRMED]:**
   * Đo thực nghiệm trên `diff_words`:
     * `n = 1.000` token xen kẽ (`1.999` ký tự): `0,102s`
     * `n = 3.000` token xen kẽ (`5.999` ký tự): `0,931s`
     * `n = 6.000` token xen kẽ (`11.999` ký tự — chỉ **2,4%** của `MAX_TEXT_CHARS = 500_000`!): **`4,575s`**
   * Ngoại suy bậc hai ($T \propto N^2$): tại `n = 250.000` token (`500.000` ký tự hợp lệ theo v2 §3.2), một request đơn lẻ có thể chiếm 100% một nhân CPU trong **hơn 2 giờ**! `MAX_TEXT_CHARS = 500_000` hoàn toàn **không** bảo vệ được `/comparisons/text` trước DoS CPU. Giảm xuống `MAX_TEXT_TOKENS = 50_000` giúp hạ trần lý thuyết nhưng vẫn còn rủi ro với chuỗi lặp đối kháng (xem Mục 10).

3. **PDF Decompression Bomb & Vector/Object Bomb [HYPOTHETICAL]:**
   * Một tệp PDF chỉ nặng 50 KB (< 15 MB) và chỉ có 1 trang (< 100 trang) có thể chứa luồng `FlateDecode` nén tỷ lệ 1000:1 bung ra hàng trăm MB trong RAM, hoặc chứa 200.000 ký tự/đường kẻ chồng lấn làm `page.extract_text()` của `pdfplumber` treo hàng phút hoặc gây OOM.
   * Vì `pdfminer.six` không có công tắc giới hạn tổng byte giải nén hay tổng số đối tượng ký tự/trang, đây là rủi ro **chưa giải quyết triệt để được trong Phase A** nếu không chạy trong subprocess có memory/time limit (OS-level isolation).

4. **Path Traversal & Log/HTML Injection qua `filename` [CONFIRMED]:**
   * Chạy `extract_document('../../etc/passwd', ...)` trả nguyên `{"filename": "../../etc/passwd", ...}`; `extract_document('   ', ...)` trả `{"filename": "   ", ...}`.
   * Tuy Phase A chưa ghi file ra đĩa theo tên người dùng, việc phản hồi và lưu nguyên `filename` bẩn tạo bẫy nghiêm trọng cho các pha sau (ví dụ xuất báo cáo HTML tĩnh ở Tầng 6 hoặc ghi log có ký tự `\r\n` gây log forging). Vệ sinh bằng `Path(filename.strip()).name` ngay từ Phase A ngăn chặn triệt để rủi ro này.

5. **Information Disclosure qua 500 Stack Trace [CONFIRMED]:**
   * Hiện tại mọi tệp PDF lỗi đều làm ném `PdfminerException` chưa xử lý (HTTP `500`). Khi bắt lỗi và trả thông điệp tĩnh kèm `error_code`, tuyệt đối **không** nhúng `str(exc)` của `pdfminer` hay đường dẫn hệ thống vào trường `detail` trả cho client.

6. **Threadpool Exhaustion nếu dùng `asyncio.wait_for` giả hiệu [HYPOTHETICAL]:**
   * Như đã phân tích ở Mục 4.4, gắn timeout mềm mà không hủy được thread nền tạo lỗ hổng DoS dễ khai thác hơn cả khi không có timeout (kẻ tấn công nhận 504 sau 30s rồi gửi tiếp trong khi thread cũ vẫn sống).

---

## 7. Compatibility impact

| Thay đổi đề xuất | Tương thích ngược với API hiện có & 5 baseline tests | Lưu ý chuyển đổi |
|---|---|---|
| Thêm `GET /api/v1/health` | **Hoàn toàn tương thích** (endpoint mới). | Không ảnh hưởng client cũ. |
| Thêm `is_token_identical: bool` vào `TextComparisonResponse`, giữ `is_identical: bool` | **Tương thích cộng thêm (additive).** | Client cũ bỏ qua field mới vẫn chạy bình thường. **Cảnh báo:** Nếu ai đó theo v2 §9 Câu 8 đổi tên `is_identical` → `is_exact_match` sẽ **phá vỡ tương thích ngược**. |
| Giữ nguyên `PDFComparisonResponse` (chưa thêm `is_identical`) | **Hoàn toàn tương thích.** | Toàn bộ 5 test trong [test_comparisons_api.py](file:///C:/Users/Admin/contract-diff/tests/test_comparisons_api.py#L94-L139) không đổi contract. |
| Từ chối chuỗi chỉ khoảng trắng / ký tự vô hình và chuỗi > 500k ký tự ở `/text` bằng `422` | **Thay đổi hành vi trên đầu vào rác (intentional tightening).** | Trước đây trả `200` vô nghĩa; nay trả `422` chuẩn Pydantic. |
| Từ chối PDF 0 byte / sai `%PDF-` / hỏng / mã hóa / 0 trang bằng `400`, > 15 MB bằng `413`, > 100 trang bằng `422` | **Cải thiện từ `500` sang `4xx`.** | Riêng PDF 0 trang và PDF có byte rác trước `%PDF-` trước đây trả `200` nay trả `400` (breaking có chủ đích cho đầu vào bất hợp lệ). |
| Định dạng lỗi phẳng `{"error_code", "detail"}` cho `400`/`413`/`422`-nghiệp vụ, giữ `{"detail": [...]}` cho `422`-Pydantic | **Tương thích 100%** với `test_missing_required_file_returns_422` ([test_comparisons_api.py](file:///C:/Users/Admin/contract-diff/tests/test_comparisons_api.py#L135-L139)). | Client cần chấp nhận `detail` có kiểu `str` (lỗi nghiệp vụ, kèm `error_code`) hoặc `list[dict]` (lỗi schema 422) — đây cũng là hành vi chuẩn sẵn có của FastAPI giữa `HTTPException` và `RequestValidationError`. |
| Vệ sinh `filename` bằng `Path(name.strip()).name` | **Không ảnh hưởng** tên tệp bình thường (`contract_old.pdf`). | Chỉ cắt tiền tố thư mục độc hại (`../../`) hoặc thay tên toàn khoảng trắng bằng tên mặc định. |
| Sửa `build_document_text` dùng `enumerate` thay cho `page_number == 1` | **Không đổi output** với mọi PDF từ `extract_pdf` (vì trang luôn đánh số `1..N`). | Chỉ sửa hành vi sai khi gọi hàm trực tiếp với tập trang con hoặc đánh số lại. |
| Sửa `EMPTY_TEXT` khi trang chỉ có `"\x00"` | **Tăng độ chính xác cảnh báo**; không ảnh hưởng PDF sạch. | Trang chỉ có NUL giờ có `["NULL_CHARACTER", "EMPTY_TEXT"]` thay vì chỉ `["NULL_CHARACTER"]`; `needs_review` vẫn là `True`. |
| Môi trường Python `3.14.3` trong `.venv` vs `Python 3.11.x` trong v2 §7.3 **[CONFIRMED]** | Không ảnh hưởng Phase A (các gói hiện có đã cài chạy tốt trên 3.14.3). | **Cảnh báo cho pha sau:** Cần thống nhất phiên bản Python sớm trước khi cài `scipy`/`scikit-learn`/`numpy`/embedding ở Phase B–C để tránh lệch wheel hoặc phá reproducibility protocol của v2 §7.3. |

---

## 8. Testing strategy

### 8.1. Tổ chức file test (dọn trùng lặp)
* **[CONFIRMED]** Hiện đang có đồng thời [test_comparisons_api.py](file:///C:/Users/Admin/contract-diff/tests/test_comparisons_api.py) (4.719 byte, 5 test pass) và 2 file rỗng [test_comparison_api.py](file:///C:/Users/Admin/contract-diff/tests/test_comparison_api.py), [test_comparison_service.py](file:///C:/Users/Admin/contract-diff/tests/test_comparison_service.py) (cùng [test_text_diff.py](file:///C:/Users/Admin/contract-diff/tests/test_text_diff.py) chỉ chứa bản sao `tokenize_with_spans`).
* **Đề xuất:** Không viết trùng hai file `test_comparison_api.py` và `test_comparisons_api.py` gây nhầm lẫn; giữ thống nhất theo [coding-style-profile.md](file:///C:/Users/Admin/contract-diff/docs/implementation/coding-style-profile.md#L55-L62):
  1. `tests/test_text_diff.py` — Unit test cho `tokenize_with_spans`, `diff_words`, `build_document_text`, `span_to_page_locations` (xóa hàm trùng `tokenize_with_spans` trong file test, import trực tiếp từ `app.engines.text_diff`).
  2. `tests/test_comparison_service.py` — Unit test tầng service (`compare_text`, `compare_document`, `extract_document`, `_sanitize_filename`, `_validate_pdf_stream`, `extract_pdf` với stream in-memory `io.BytesIO`).
  3. `tests/test_comparisons_api.py` — Integration test qua `TestClient` cho cả 4 endpoint (`/health`, `/comparisons/text`, `/comparisons/pdf`, `/documents/extract`).
  4. Lưu ý: sinh fixture PDF biên (0 byte, text giả `.pdf`, 0 trang, 101 trang, PDF mã hóa, PDF trang trắng, PDF nhiều trang) **bằng helper Python sinh byte PDF tối giản trong bộ nhớ** (không cần thêm thư viện nặng như `reportlab`/`pypdf` vào `requirements.txt` ở Phase A!).

### 8.2. Ma trận ca kiểm thử bắt buộc

1. **Unit tests thuật toán (`test_text_diff.py`):**
   * **Cơ bản:** Giống hệt nhau (`changes == []`), chèn đầu/giữa/cuối, xóa đầu/giữa/cuối, thay thế đơn từ và đa từ.
   * **Khoảng trắng:** `"a b"` vs `"a  b"`, `"a b"` vs `"a\n\tb"` → `changes == []`.
   * **Unicode tiếng Việt:** Dấu thanh đầy đủ (`"Điều 1. Giá trị hợp đồng: 100.000.000 đồng"`), dấu câu dính token (`"100.000.000đ."` vs `"100.000.000đ"`), và test khóa hành vi NFC vs NFD (`"Điều"` vs `"Đie\u0302\u0300u"`).
   * **Cụm lặp & Đảo điều khoản:** Cụm lặp `"Bên A và Bên A"`, đảo khối `"A B C D"` vs `"C D A B"` (xác nhận rõ hành vi thực tế của `SequenceMatcher` — **không** viết assert giả định đối xứng tuyệt đối!).
   * **Biên `text_mapping`:** Trang rỗng ở giữa (`page 2: text=""`), trang chỉ có khoảng trắng ở giữa (`page 2: text="   "`), thay đổi vắt qua ranh giới 2 trang và 3 trang, danh sách trang không bắt đầu từ `page_number == 1` (`[page 2, page 3]`), span nằm trọn trong separator `"\n\n"`, `span=None`.
   * **Bất biến kiểm thử (sửa sai của v2 §7.1):**
     * *Span validity:* mọi `old_span`/`new_span` khác `None` thỏa `0 <= start < end <= len(text)`, tăng nghiêm ngặt, không giao nhau, `old_text[start:end] == change["old_text"]`.
     * *Token-level reconstruction (khả thi toán học):* thay vì áp `changes` lên `old_text` (bất khả thi vì `insert` có `old_span=None`), kiểm chứng bằng cách đối chiếu ngược qua `SequenceMatcher.get_opcodes()` hoặc kiểm chứng tập token không đổi + token thay đổi khớp chính xác trên hai chuỗi token hóa `old_tokens` và `new_tokens`.

2. **Unit tests service & extractor (`test_comparison_service.py`):**
   * `compare_text`: `is_identical=True & is_token_identical=True` (giống nguyên văn); `is_identical=False & is_token_identical=True` (chỉ khác khoảng trắng); `is_identical=False & is_token_identical=False` (khác token); vượt `MAX_TEXT_TOKENS` → `HTTPException(422)`.
   * `extract_pdf`: trang có chữ, trang rỗng (`EMPTY_TEXT`), trang chứa `"\x00"` kèm chữ (`NULL_CHARACTER`), trang chỉ chứa `"\x00"` (`["NULL_CHARACTER", "EMPTY_TEXT"]`), PDF 0 trang → `InvalidPDFError`, PDF 101 trang → `PDFPageLimitExceededError` (kiểm chứng ngắn mạch không đọc trang 102), PDF hỏng/mã hóa → `InvalidPDFError`, stream con trỏ không ở vị trí 0 vẫn đọc đúng sau `seek(0)`.
   * `document_service`: `_sanitize_filename` với `None`, `""`, `"   "`, `"../../etc/passwd"`, `"C:\\temp\\a.pdf"`, `"a\r\nb.pdf"`; `_validate_pdf_stream` với 0 byte (400), sai magic bytes (400), đúng biên `15 MB` (pass), vượt biên `15 MB + 1 byte` (413).

3. **Integration API tests (`test_comparisons_api.py`):**
   * `GET /api/v1/health`: `200`, `{"status": "ok"}`.
   * `POST /api/v1/comparisons/text`:
     * Happy path tiếng Việt (có thay đổi, giống hệt, chỉ khác khoảng trắng kiểm tra cả `is_identical` và `is_token_identical`).
     * Input rỗng `""`, chỉ khoảng trắng `"   \n\t"`, chỉ ký tự vô hình `"\u200b"`, `"\ufeff"`, `"\x00"` → `422`.
     * Thiếu `old_text` hoặc `new_text`, sai kiểu dữ liệu → `422`.
     * Biên độ dài: đúng `MAX_TEXT_CHARS` (chấp nhận nếu trong hạn token) vs `MAX_TEXT_CHARS + 1` → `422`; vượt `MAX_TEXT_TOKENS` → `422` (`TEXT_TOKEN_LIMIT_EXCEEDED`).
     * Tương thích response: đủ khóa `is_identical`, `is_token_identical`, `old_length`, `new_length`, `changes` (kèm `old_locations`, `new_locations`).
   * `POST /api/v1/documents/extract` và `POST /api/v1/comparisons/pdf`:
     * Happy path với fixture thật `contract_old.pdf` / `contract_new.pdf` (giữ nguyên toàn bộ 5 test baseline).
     * Thiếu field `file` / `old_file` / `new_file` → `422` có `loc`.
     * Tệp 0 byte → `400` (`INVALID_OR_ENCRYPTED_PDF`).
     * Tệp văn bản đổi đuôi `.pdf` (`b"hello"`) và tệp sai đuôi `.txt` nhưng nội dung PDF hợp lệ (xác nhận kiểm tra theo nội dung thực `%PDF-`, không chặn mù theo đuôi file!).
     * Tệp giả magic bytes `%PDF-1.4\ngarbage` → `400` (`INVALID_OR_ENCRYPTED_PDF`).
     * Tệp PDF mã hóa → `400` (`INVALID_OR_ENCRYPTED_PDF`).
     * Tệp PDF 0 trang → `400` (`INVALID_OR_ENCRYPTED_PDF`).
     * Tệp PDF 101 trang → `422` (`PDF_PAGE_LIMIT_EXCEEDED`), và biên 100 trang → `200`.
     * Tệp > 15 MB (test cả qua `Content-Length` lẫn stream/per-file trong cặp 2 tệp) → `413` (`PAYLOAD_TOO_LARGE`).
     * PDF chứa trang trắng → `200`, `warnings == ["EMPTY_TEXT"]`, và ở `/comparisons/pdf` có `needs_review == True`.
     * `filename` là `"   "` hoặc `"../../secret.pdf"` → được làm sạch an toàn trong response.
     * Lưu ý chạy kiểm thử trên Windows: dùng `pytest -p no:cacheprovider -q` trong môi trường không chặn loopback socket để chạy toàn bộ `TestClient`.

---

## 9. Complexity assessment

| Thành phần | Độ phức tạp thời gian | Độ phức tạp bộ nhớ | Đánh giá định lượng & Rủi ro |
|---|---|---|---|
| `MaxBodySizeMiddleware` | $O(B)$ theo số byte nhận được | $O(1)$ (đếm biến cộng dồn) | Không nhân đôi buffer trong RAM; cắt ngay khi vượt 31 MB/16 MB/4 MB. |
| `_validate_pdf_stream` | $O(1)$ (`seek` + đọc 5 byte) | $O(1)$ | Phụ thuộc stream hỗ trợ `seek()` (luôn đúng với `SpooledTemporaryFile` và `BytesIO`). |
| `extract_pdf` (đếm trang dừng sớm + trích xuất) | $O(P \cdot C_p)$ với $P \le 100$ | $O(S_{\text{pdf}} + L_{\text{text}})$ | Đếm trang dừng sớm tại trang 101 giúp tránh dựng hàng nghìn `Page` object. Tuy nhiên $C_p$ (số ký tự/đối tượng đồ họa trên 1 trang) **không có chặn trên** trong `pdfplumber`. |
| `build_document_text` & `span_to_page_locations` | $O(P + K \cdot P)$ ($K$ = số thay đổi, $P \le 100$) | $O(L_{\text{text}})$ | Với $P \le 100$, vòng lặp tuyến tính trong `span_to_page_locations` rất nhỏ (< 1 ms), chưa cần tìm kiếm nhị phân. (Lưu ý `fulltext += ...` trong vòng lặp Python trên CPython tối ưu nội bộ nhưng dùng `list` + `"".join` sạch hơn; tuy nhiên với $P \le 100$ chênh lệch không đáng kể.) |
| `diff_words` (`SequenceMatcher(autojunk=False)`) | Trung bình $O(N \log N)$ trên văn bản tự nhiên; **xấu nhất $O(N_1 \cdot N_2)$** **[CONFIRMED]** | $O(N_1 + N_2)$ | **Điểm nghẽn lớn nhất:** đã đo thực nghiệm `n=6.000` token lặp tốn `4,575s`. Với trần `MAX_TEXT_TOKENS = 50_000`, văn bản hợp đồng bình thường (~10.000–20.000 từ) chạy < 100 ms, nhưng đầu vào đối kháng vẫn có thể chạy hàng phút. |
| Công sức triển khai Phase A | ~4–6 giờ code + test | Thay đổi ~7 file, thêm 1 file `app/core/config.py` (tổng ~250–350 dòng code + ~300 dòng test) | Hoàn toàn khả thi trong khung tuần T1 của v2 §10 (mục 2 & 3 ước lượng 7 giờ), không làm vỡ lịch trình 16 tuần. |

---

## 10. Potential weaknesses

Phản biện thẳng vào **chính phương án đề xuất ở Mục 3** — mỗi quyết định quan trọng đều còn tồn tại điểm yếu cụ thể cần ghi nhận minh bạch:

1. **Chưa loại bỏ triệt để CPU DoS bậc hai trên `diff_words` [CONFIRMED]:**
   * Đề xuất giữ nguyên `SequenceMatcher(autojunk=False)` để bảo toàn Baseline 1 cho RQ2/RQ4 và chỉ chặn `MAX_TEXT_TOKENS = 50_000`. Nhưng vì `n = 6.000` token lặp đã mất `4,575s`, một chuỗi đối kháng `n = 45.000` token (hợp lệ qua mọi bộ lọc!) vẫn có thể làm kẹt 1 worker thread trong ~4–5 phút. Hạ `MAX_TEXT_TOKENS` xuống thấp hơn (ví dụ 10.000) lại có nguy cơ từ chối hợp đồng hợp lệ dài 40–60 trang (~25.000–40.000 từ tiếng Việt).

2. **Chưa chặn được PDF Decompression Bomb / Vector Bomb và không có Timeout thật [HYPOTHETICAL / CONFIRMED]:**
   * Quyết định hoãn timeout 30s ở Phase A đồng nghĩa hệ thống vẫn chưa đạt đủ yêu cầu `COMPARISON_TIMEOUT_SECONDS = 30.0` của v2 §3.2. Một tệp PDF 100 KB, 5 trang nhưng có bảng/đồ họa vector cực dày hoặc luồng nén `FlateDecode` bung hàng trăm MB vẫn đi qua toàn bộ giới hạn 15 MB và 100 trang, gây OOM hoặc chiếm dụng thread vô thời hạn.

3. **Lệch kiểm tra `15 MB/tệp` tại tầng ASGI đối với `/comparisons/pdf` [CONFIRMED]:**
   * Do `MaxBodySizeMiddleware` chỉ chặn tổng kích thước body (31 MB) mà không parse multipart theo luồng, một yêu cầu chứa 1 tệp 28 MB + 1 tệp 1 KB vẫn bị Starlette spool 28 MB ra đĩa tạm rồi mới bị `document_service.py` từ chối `413`. Đây là thỏa hiệp tránh viết lại `MultiPartParser`, không phải bảo vệ tuyệt đối theo từng tệp ở tầng mạng.

4. **Kiểm tra chặt `header == b"%PDF-"` ở byte 0 có thể từ chối PDF hợp lệ theo ISO 32000-1 [CONFIRMED]:**
   * Đã xác nhận `pdfplumber` chấp nhận byte rác trước `%PDF-` (ví dụ UTF-8 BOM hoặc preamble ngắn từ một số máy in ảo cũ). Việc ép `startswith(b"%PDF-")` tăng an toàn trước tệp polyglot nhưng có rủi ro false-reject trên một số PDF đời cũ ngoài thực tế.

5. **Gộp `INVALID_OR_ENCRYPTED_PDF` làm mất khả năng chẩn đoán và không bắt lỗi `FlateDecode` bị `pdfminer` nuốt [CONFIRMED]:**
   * Gom tệp hỏng, 0 byte, 0 trang và tệp có mật khẩu vào chung một `error_code` (theo v2 §3.2) khiến giao diện/người dùng không biết phải gỡ mật khẩu hay xuất lại PDF. Đồng thời, tệp PDF có stream hỏng bên trong bị `pdfminer` bỏ qua âm thầm sẽ trả `200` kèm `EMPTY_TEXT` thay vì `400`.

6. **Rò rỉ ngữ nghĩa `HTTPException` vào tầng Service và hai dạng `detail` trên `422` [CONFIRMED]:**
   * Đặt `HTTPException` trong `document_service.py` và `comparison_service.py` giúp code gọn đúng [coding-style-profile.md](file:///C:/Users/Admin/contract-diff/docs/implementation/coding-style-profile.md#L46-L47), nhưng làm tầng service phụ thuộc trực tiếp vào FastAPI — khi bước sang pha đánh giá batch (`experiments/run_evaluation.py` không chạy HTTP server), script đánh giá sẽ phải xử lý `fastapi.HTTPException`.
   * Ngoài ra, giữ `422` Pydantic trả `{"detail": [...]}` trong khi `422` nghiệp vụ (`PDF_PAGE_LIMIT_EXCEEDED`, `TEXT_TOKEN_LIMIT_EXCEEDED`) trả `{"error_code": "...", "detail": "..."}` tạo ra hai cấu trúc JSON khác nhau trên cùng mã trạng thái `422`.

7. **Bất đối xứng giữa `/text` và `/pdf` và vấn đề NFC/NFD bị trì hoãn [CONFIRMED]:**
   * `/comparisons/text` có `is_identical` + `is_token_identical`, `/comparisons/pdf` chỉ có `needs_review` (không

> **[Ghi chú của Orchestrator]** Antigravity (`agy` 1.5.11, Gemini 4 Neon, `--mode plan --sandbox`) bị `--print-timeout 900s` cắt ở mục 10.7; nội dung trên là nguyên văn đầu ra, chỉ gỡ 3 dòng thông báo lỗi CLI chen giữa. Lần chạy đầu tiên thất bại do headless mode tự từ chối quyền `command`. `git status --porcelain` trước/sau lần chạy giống hệt nhau.
