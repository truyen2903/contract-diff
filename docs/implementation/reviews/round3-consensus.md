# Round 3 — Rebuttal & Consensus (Phase A)

Nguồn: `round3-codex.md`, `round3-claude.md`, `round3-antigravity.md` (nguyên văn), trên nền `round2-cross-examination.md`.
Orchestrator (Claude Code phiên chính) đưa ra quyết định cuối theo thứ tự ưu tiên: Correctness → Security → API compatibility → Research scope → Maintainability → Coding style → Performance → Effort. Không biểu quyết 2/3 máy móc.

Kiểm chứng độc lập của Orchestrator (`scratchpad/orch/o4o5.py`, PDF dựng trong bộ nhớ):
```text
O4 islice-inside-with: counted 101 Page objects built 2000 0.516s
O4 pre-check PDFDocument: counted 101 Page objects built 0 0.062s
O5 MalformedPDFException subclass of PdfminerException: False
O5 MediaBox-bad  pdfplumber.utils.exceptions.MalformedPDFException
O5 Rotate-bad    builtins.TypeError
O5 CropBox-short builtins.IndexError
```

## 1. Bảng quyết định

| # | Vấn đề | Codex | Claude | Antigravity | Quyết định cuối |
|---|---|---|---|---|---|
| D1 | `is_identical` vs token equality (`/text`) | Giữ + thêm `is_token_identical` | Như Codex | Như Codex | **Giữ `is_identical` (nguyên văn), thêm `is_token_identical = len(changes) == 0`**. Không đổi tên `is_exact_match` (v2 §9 Câu 8 cần sửa chữ). |
| D2 | Cờ equality cho `/pdf` | R1 thêm → R2 rút | Không | Không | **Không thêm** (hai PDF scan khác nhau sẽ báo "giống"). |
| D3 | Validator text | `strip()` | `strip()` | R1 blacklist → R2 `strip()` | **`field_validator` + `str.strip()`** (tương đương "≥1 token `\S+`"), `max_length=MAX_TEXT_CHARS`, trả nguyên giá trị. |
| D4 | Body lỗi | Handler có điều kiện | R1 lồng → R2 handler | Handler có điều kiện | **Handler có điều kiện trong `main.py`**: `detail` là dict có `error_code` → body phẳng `{"error_code","detail"}`; còn lại → handler mặc định. Không đụng `RequestValidationError`. |
| D5 (O1) | PDF mã hóa mở được bằng mật khẩu rỗng | R1 từ chối → R3 ACCEPT | Chấp nhận | Chấp nhận | **Chấp nhận (200)**. Chỉ 400 khi không mở được (`PDFPasswordIncorrect`, v2 §3.2). Test khóa cả hai ca. |
| D6 (O2) | Giới hạn body | R3 middleware có sẵn | Middleware có sẵn | Tự viết (dự phòng: có sẵn) | **`starlette.middleware.body_limit.RequestBodyLimitMiddleware`, trần toàn cục `MAX_REQUEST_BODY_BYTES = 2*15 MiB + 1 MiB`**. Ngoại lệ có chủ đích: 413 tầng transport không có `error_code` (text/plain hoặc `{"detail":"Content Too Large"}`) — ghi tài liệu. Lý do: không tự viết lại code thư viện + bộ test ASGI riêng (maintainability), lỗi định dạng không ảnh hưởng correctness. |
| D7 | Mã 413 nghiệp vụ | R3 một mã | Một mã | Một mã | **`PAYLOAD_TOO_LARGE`** (file > 15 MiB, kiểm tại service). |
| D8 (O3) | Magic bytes | Byte 0 | R3 byte 0 | Byte 0 | **`read(5) == b"%PDF-"` ở byte 0**. Không gọi là chống polyglot (Claude R3: polyglot nối sau `%%EOF` vẫn qua). |
| D9 (O4) | Đếm trang | R3 tiền kiểm | R3 tiền kiểm | Tiền kiểm | **`PDFDocument(PDFParser(stream), password="")` + `islice(PDFPage.create_pages(doc), MAX_PDF_PAGES + 1)` trước `pdfplumber.open`**, rồi `seek(0)`. 0 trang → 400; > 100 → 422 `PDF_TOO_MANY_PAGES`. |
| D10 (O5) | Phạm vi bắt lỗi parser | Tập rộng quanh lời gọi thư viện + tháo wrapper | Tập hẹp quanh lời gọi thư viện | Như Codex + giữ `OSError` → 500 | **`try` chỉ bọc lời gọi thư viện** (khối tiền kiểm; khối `pdfplumber.open`/`pages`/`extract_text`). Bắt `(PSException, MalformedPDFException, TypeError, IndexError, ValueError, AttributeError)` → `InvalidPDFError`. `PdfminerException`: nếu `args[0]` là `OSError` → re-raise (500), ngược lại → `InvalidPDFError`. Không bắt `OSError`/`MemoryError`. Code tạo `warnings` nằm ngoài `try`. |
| D11 | Exception extractor | R2 exception hẹp | R2 exception hẹp | Exception hẹp | **`InvalidPDFError(ValueError)`, `PDFPageLimitError(ValueError)` trong `pdf_extractor.py`**; service ánh xạ sang `HTTPException`. Extractor không import FastAPI. |
| D12 | PDF 0 trang | 400 | R2 400 | 400 | **400 `INVALID_OR_ENCRYPTED_PDF`**. |
| D13 (O6) | Admission guard `diff_words` | R3 hoãn | Hoãn | R3 hoãn | **Không có trần token ở Phase A** (AG R3: cùng 25k token, cùng tích, thời gian chênh 18× → không ngưỡng tĩnh nào hợp lệ). **Fast path** chuỗi/token bằng nhau trong `diff_words`. **`MAX_TEXT_CHARS` cho từng fulltext `/pdf`** tại `compare_document` → 422 `TEXT_TOO_LONG`; không áp cho `/extract`. CPU DoS ghi là rủi ro còn mở. |
| D14 | Timeout 30 s | Hoãn | Hoãn | Hoãn | **Không triển khai** (thread không hủy được; cần cô lập process). Rủi ro mở. |
| D15 (O7) | Health | Schema + prefix | R3 ACCEPT | Schema + prefix | **`app/schemas/health.py: HealthResponse(status: Literal["ok"])`**, `prefix="/health"`, route `""`. |
| D16 (O8) | Vị trí kiểm size/magic | Service, cả hai file trước | Service, cả hai file trước | Service, cả hai file trước | **`validate_pdf_stream(filename, file_stream)` trong `document_service`**; `extract_document` gọi; `compare_document` gọi cho cả hai stream trước khi trích xuất. Đo size bằng `seek/tell`, không đọc toàn tệp. |
| D17 | `build_document_text` separator | Theo vị trí | Theo vị trí | Theo vị trí | **Separator theo vị trí trong danh sách**, không theo `page_number`. |
| D18 | `span_to_page_locations` trang toàn khoảng trắng | Đúng | Đúng | R3 rút | **Không sửa** (hành vi đúng). |
| D19 | `EMPTY_TEXT` khi trang chỉ có NUL | R2 chấp nhận | Chấp nhận | Đề xuất | **`if not text.replace("\x00", "").strip()`**. |
| D20 | `CID_FONT_ERROR` | R2 rút | Không | Không | **Không làm** (thuộc tầng 1 v2 §4.1). |
| D21 | Vệ sinh filename | Metadata | Metadata | R2 rút | **Giữ metadata**, fallback hiện có của tác giả. |
| D22 | Bất biến reconstruction v2 §7.1 | Sai | Sai | Sai | **Không dùng làm tiêu chí nghiệm thu**; test bất biến span (biên, tăng, không chồng, fragment khớp) và `diff_words == [] ⇔ token bằng nhau`. Cần sửa v2 §7.1/§9 Câu 8. |

## 2. Vấn đề Critical/High còn mở (blocked / ghi nhận)

| ID | Mức | Mô tả | Trạng thái |
|---|---|---|---|
| R-CPU | High | `SequenceMatcher(autojunk=False)` có worst-case siêu tuyến tính; 25k token/100 sửa đổi ≈ 31,7 s; đầu vào lặp 8k token ≈ 15 s. Không có ngưỡng tĩnh hợp lệ. | **Blocked** — cần benchmark trên corpus T1 và/hoặc cô lập process. Không tuyên bố Phase A đã kiểm soát latency. |
| R-TIMEOUT | High | Không có hard timeout 30 s (v2 §3.2). | **Blocked** cùng R-CPU. |
| R-BOMB | Medium | PDF nhỏ có stream nén lớn / vector dày có thể tốn CPU/RAM trong `extract_text`. | Ghi nhận, chưa có test. |

## 3. Sửa tài liệu v2 được đề xuất (không tự sửa — thuộc quyền tác giả)
- §3.2: bắt `PdfminerException`/`MalformedPDFException`… thay vì `PDFSyntaxError`/`PDFPasswordIncorrect`; 413 transport không có `error_code`.
- §7.1, §9 Câu 8: dùng `is_identical` (không phải `is_exact_match`); bỏ bất biến reconstruction (phản ví dụ `compare_text("a b","  x a b") == compare_text("a b","a x b  ")`).
- §7.3/§10: môi trường thực tế Python 3.14.3, không phải 3.11.

## 4. Điều chỉnh sau adversarial code review (2026-11-20)

| ID | Thay đổi | Bằng chứng |
|---|---|---|
| D10 (sửa) | Tập exception hẹp **thất bại trên dữ liệu thật**: còn lọt `KeyError` (`/Encrypt` thiếu `/O`/`/U`/`/P`), `ZeroDivisionError`, `struct.error`, `AssertionError` → 500 (CR-CX-002, CR-AG-002); và `MemoryError` bọc trong `PdfminerException` bị dán nhãn 400 (CR-CL-001, CR-CX-003, CR-AG-004). Quy tắc mới: **chỉ quanh lời gọi thư viện**, mọi `Exception` → `InvalidPDFError`, trừ `OSError`/`MemoryError` (xét cả lỗi gốc trong `PdfminerException`) → giữ 500. Khớp cách pdfplumber tự bọc lỗi. | `code-review-*.md`; test `test_extract_pdf_rejects_broken_encryption_dictionary`, `..._wrapped_by_pdfplumber`, `..._memory_error_while_extracting` (đã chứng minh fail trên logic cũ). |
| D4 (sửa) | Thêm handler `RequestValidationError` bỏ trường `input`: surrogate lẻ `"\ud800"` làm handler mặc định sập 500; 422 trả lại nguyên ~0,5–1 MB input. | CR-CX-004, CR-AG-003; test `test_lone_surrogate_returns_422_not_500`, `test_validation_error_does_not_echo_input`. |
| D15 (sửa) | `health_endpoint` là `async def` để không phụ thuộc threadpool. | CR-AG-001. |
| R-LOOP (mới, Critical, pre-existing) | PDF ~290 byte có object tự tham chiếu trong cây `/Pages` làm pdfminer `resolve1` lặp vô hạn. Đã xác minh **code gốc tại HEAD cũng treo** (`pdfplumber/pdf.py:163` → `pdfminer/pdftypes.py:114`). Không sửa được trong thư viện mà không cô lập process. | **Blocked** cùng R-TIMEOUT. |
