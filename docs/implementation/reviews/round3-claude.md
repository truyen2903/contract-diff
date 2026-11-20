# Round 3 — Claude rebuttal

Môi trường: `.venv/Scripts/python`, `PYTHONDONTWRITEBYTECODE=1`, mỗi lệnh dưới 60 s. Script tạm nằm trong scratchpad (`r3.py`, `r3b.py`, `mkpdf.py`). Không ghi file nào vào repository.

## Phản hồi phản biện

**Từ Codex (phần CX):**
- **CX/ADV-CL-001** — ACCEPT. Đã tự sửa ở Round 2: handler có điều kiện giữ nguyên 404/405 [CONFIRMED trong Round 2 của tôi].
- **CX/ADV-CL-002** — PARTIAL. Đồng ý cần giới hạn body ngay trong app, không phụ thuộc proxy. Không đồng ý viết limiter riêng; dùng `RequestBodyLimitMiddleware` có sẵn (xem O2).
- **CX/ADV-CL-003** — PARTIAL. Chấp nhận:
  - fast path khi chuỗi hoặc danh sách token bằng nhau;
  - áp `MAX_TEXT_CHARS` lên fulltext của `/pdf`.

  Trần token dạng số thì NEEDS EXPERIMENT (lý do và số đo ở O6).
- **CX/ADV-CL-004** — ACCEPT về hướng, nhưng phải kèm sửa lỗi O4. Đếm bằng `islice` bên trong `with pdfplumber.open` vẫn dựng toàn bộ trang lúc thoát `with`.
- **CX/ADV-CL-005** — REJECT (xem O1).
- **CX/ADV-CL-006** — ACCEPT. Đã chuyển sang exception riêng `PDFPageLimitError`. Phương án ở O5 có `[101-page] PDFPageLimitError` tách biệt với lỗi parse [CONFIRMED `r3b.py`].

**Từ Antigravity (phần AG):**
- **AG/ADV-CL-001** — ACCEPT cả PDF 0 trang → 400 và đếm trang dừng sớm. Xác nhận: `[0-page] InvalidPDFError(0 pages)` [CONFIRMED `r3b.py`].
- **AG/ADV-CL-002** — PARTIAL. Chấp nhận bắt thêm `MalformedPDFException`, `TypeError`, `IndexError`, vì cả ba đều phát sinh trong frame thư viện:

  | PDF lỗi | Ngoại lệ | Frame phát sinh |
  |---|---|---|
  | `/MediaBox [0 0 (x) 100]` | `MalformedPDFException` | `page.py:167 _normalize_box` |
  | `/Rotate /Invalid` | `TypeError` | `page.py:212 __init__` |
  | `/CropBox [0 0]` | `IndexError` | `page.py:170 _normalize_box` |

  [CONFIRMED `r3.py`]. Điều kiện: thân `try` chỉ chứa lời gọi thư viện; code của mình (dựng `warnings`) nằm ngoài. Không bắt `OSError` (xem O5).
- **AG/ADV-CL-003** — PARTIAL, như CX/ADV-CL-002.
- **AG/ADV-CL-004** — PARTIAL, như CX/ADV-CL-003.
- **AG/ADV-CL-005** — ACCEPT. Đã tự sửa ở Round 2.
- **AG/ADV-CL-006** — PARTIAL. Chấp nhận kiểm tra ở byte 0 vì đơn giản và khớp v2, nhưng lý do "chặn polyglot" không đứng được. PDF hợp lệ có nối `<html><script>alert(1)</script></html>` **sau** `%%EOF` vẫn cho `byte0 ok: True` và trích xuất được `'Hello'` [CONFIRMED, lệnh `python -c` với `make_pdf(['Hello']) + b'<html>...'`]. Kiểm tra byte 0 không ngăn được polyglot.
- **AG/ADV-CL-007** — ACCEPT (xem O7).

## Lập trường O1–O8

### O1 — PDF mã hóa mở được bằng mật khẩu rỗng: ACCEPT (chấp nhận file, trả 200), REJECT quy tắc `encryption is not None`

- V2 §3.2, nguồn mà brief dẫn cho mã lỗi, định nghĩa ca lỗi bằng `PDFPasswordIncorrect`. Theo v2, "mã hóa" nghĩa là cần mật khẩu mới mở được, nên không phải tôi tự đổi chính sách.
- PDF chỉ có owner password vẫn trích xuất đúng: `encryption is not None: True | text: Hello` [CONFIRMED Round 2].
- Từ chối các file này chuyển một ca đang trả 200 đúng sang 400 mà không có lợi ích an ninh.
- Antigravity cũng đứng về phía này (AG/ADV-CX-005).
- Đề xuất: ghi rõ chính sách trong tài liệu API và thêm test "owner-only encrypted → 200".
- Trong pre-check, PDF cần mật khẩu bị bắt thành `InvalidPDFError`, nguyên nhân `PDFPasswordIncorrect` [CONFIRMED `r3b.py`].

### O2 — Giới hạn body: chọn (a), một mã lỗi nghiệp vụ

- Trong `main.py` thêm `app.add_middleware(RequestBodyLimitMiddleware, max_body_size=MAX_REQUEST_BODY_BYTES)`, với `MAX_REQUEST_BODY_BYTES = 2 * MAX_UPLOAD_FILE_BYTES + 1 MiB`.
- Middleware này xử lý cả `Content-Length` lẫn chunked:
  - Content-Length vượt trần → `413 text/plain`;
  - chunked vượt trần → `413 {"detail":"Content Too Large"}`.

  [CONFIRMED Round 2.]
- Không dùng trần riêng cho từng path: trần 4 MiB của `/text` từ chối request hợp lệ (JSON `ensure_ascii` của 2 × 500k ký tự tiếng Việt là 6 000 032 byte) [CONFIRMED Round 2].
- Không tự viết limiter: lặp lại code thư viện, cộng thêm các test ASGI mà chính Codex đã liệt kê.
- Về mã lỗi 413:
  - Lỗi nghiệp vụ dùng **một** mã duy nhất `PAYLOAD_TOO_LARGE`, phát từ service khi một file vượt 15 MiB.
  - 413 ở tầng transport do middleware trả không có `error_code`. Ghi rõ trong tài liệu, không cố đồng nhất.

### O3 — Magic bytes: PARTIAL → kiểm ở byte 0

- Kiểm tra `file_stream.read(5) == b"%PDF-"`: khớp v2 ("magic bytes đầu tệp") và là phương án hai agent kia cùng chọn.
- Về an ninh, byte 0 và 1024 byte tương đương nhau (phản ví dụ polyglot ở AG/ADV-CL-006).
- Đánh đổi: PDF có rác trước header bị từ chối. Ghi điều này vào tài liệu.

### O4 — Đếm trang: ACCEPT tiền kiểm ngoài pdfplumber

- Mã nguồn `PDF.close()` gọi `self.flush_cache()` rồi `for page in self.pages: page.close()` [CONFIRMED qua `inspect.getsource`].
- Đo trên PDF 3000 trang, đếm số lần gọi `Page.__init__` [CONFIRMED `r3.py`]:

  | Cách đếm | Số trang đếm được | `Page` bị dựng | Thời gian |
  |---|---|---|---|
  | `islice` trong `with`, rồi `raise` | 101 | **3000** | 0,90 s |
  | `PDFDocument(PDFParser(stream), password="")` + `islice` | 101 | **0** | 0,09 s |

- Chốt cách đếm trong `extract_pdf`:
  1. Tiền kiểm bằng `PDFDocument` + `islice(PDFPage.create_pages(doc), max_pages + 1)`.
  2. Nếu đếm được 0 trang → `InvalidPDFError`; nếu vượt `max_pages` → `PDFPageLimitError`.
  3. `seek(0)` rồi mới `pdfplumber.open`.
- Kết quả trên prototype: `100-page OK`, `101-page PDFPageLimitError` [CONFIRMED `r3b.py`].
- Lưu ý: pre-check ném ngoại lệ thô của pdfminer, không qua lớp bọc của pdfplumber. Quan sát được: `PDFSyntaxError`, `PSEOF`, `PDFPasswordIncorrect` (đều là con của `PSException`) và `AttributeError` (catalog có `/Pages` dạng inline dict) [CONFIRMED `r3.py`, `r3b.py`].

### O5 — Phạm vi bắt lỗi: PARTIAL, bắt hẹp quanh lời gọi thư viện

Prototype đã chạy [CONFIRMED `r3b.py`, 12/12 ca được phân loại, không ca nào thoát ra thành 500]:

```python
try:   # chỉ lời gọi pdfminer
    document = PDFDocument(PDFParser(file_stream), password="")
    page_count = sum(1 for _ in islice(PDFPage.create_pages(document), max_pages + 1))
except (PSException, AttributeError, TypeError) as error:
    raise InvalidPDFError(...) from error
...
try:   # chỉ lời gọi pdfplumber
    with pdfplumber.open(file_stream) as pdf:
        texts = [page.extract_text() or "" for page in pdf.pages]
except (PdfminerException, MalformedPDFException, TypeError, IndexError) as error:
    raise InvalidPDFError(...) from error
# dựng warnings (code của mình) nằm ngoài try
```

Kết quả phân loại:

| Ca | Kết quả | Nguyên nhân gốc |
|---|---|---|
| 0 byte, rác | `InvalidPDFError` | `PDFSyntaxError` |
| PDF bị cắt | `InvalidPDFError` | `PSEOF` |
| Cần mật khẩu | `InvalidPDFError` | `PDFPasswordIncorrect` |
| `/MediaBox` có phần tử chuỗi | `InvalidPDFError` | `MalformedPDFException` |
| `/Rotate /Invalid` | `InvalidPDFError` | `TypeError` |
| `/CropBox [0 0]` | `InvalidPDFError` | `IndexError` |
| `/Pages` inline dict | `InvalidPDFError` | `AttributeError` |

- Vì thân `try` chỉ có lời gọi thư viện trên dữ liệu không tin cậy, `TypeError`/`IndexError` ở đây là lỗi do đầu vào. Lỗi lập trình trong code warnings vẫn ra 500.
- **Không** bắt `OSError` hay `MemoryError` (lỗi hạ tầng). Trong pre-check, `OSError` thô vẫn thoát ra thành 500.
- `ValueError` từ thư viện (AG dẫn `geometry.py:72`) có thể thêm vào tuple của khối thứ hai nếu tái hiện được. Hiện tôi chưa dựng được ca này [HYPOTHETICAL].

### O6 — Admission guard: PARTIAL / NEEDS EXPERIMENT

**Làm ngay ở Phase A:**
1. Fast path `old_text == new_text` hoặc danh sách token bằng nhau → `[]`, áp cho cả `/text` và `/pdf`.
2. `MAX_TEXT_CHARS` cho fulltext của `/pdf` → 422 `TEXT_TOO_LONG` trong `compare_document`. Không áp cho `/extract`.

**Chưa đặt trần token dạng số.** Lý do: không có ngưỡng nào vừa giữ worst-case dưới 30 s, vừa nhận được hợp đồng 100 trang.
- Đầu vào lặp một token: 8000 token → **15,27 s** [CONFIRMED, `python -c`]; 4000 token → 3,50 s [CONFIRMED Round 1]. Tăng theo bậc hai, nên muốn dưới 30 s cần trần khoảng 11 k token mỗi bên.
- Mật độ fixture khoảng 197 token/trang [CONFIRMED Round 2], nên 11 k token chỉ tương đương khoảng 55 trang, mâu thuẫn với `MAX_PDF_PAGES = 100`.
- Ngược lại, hợp đồng thật ít lặp chạy nhanh: AG đo bản ×32 có 12,7 k token mất 0,35 s.
- Kết luận: trần token cố định hoặc từ chối hợp đồng hợp lệ, hoặc không chặn được đầu vào đối kháng.

Đề xuất: đo trên 15 hợp đồng thật của đợt thu thập T1 (v2 §10 mục 6). Chỉ thêm `MAX_DIFF_TOKENS` khi có số liệu, và ghi rõ CPU vẫn là rủi ro còn lại cho đến khi có cô lập process.

### O7 — Health: ACCEPT

- `app/schemas/health.py` chứa `HealthResponse(status: Literal["ok"])`.
- `health.py` dùng `@router.get("", response_model=HealthResponse)`.
- `router.py` đăng ký `include_router(health.router, prefix="/health", tags=["Health"])`, nhất quán với hai module route kia.
- Đã kiểm: `GET /api/v1/health` → `200 {"status":"ok"}`; OpenAPI ghi `$ref HealthResponse`. Riêng `/api/v1/health/` → 307 (hành vi trailing slash mặc định) [CONFIRMED, `python -c`].

### O8 — Vị trí kiểm tra: giữ trong `document_service.extract_document`, PARTIAL cho `/pdf`

- Kiểm tra bằng `seek` (`seek(0, SEEK_END)` rồi `seek(0)`) chạy được với cả `SpooledTemporaryFile` lẫn `BytesIO` [CONFIRMED Round 1]. Không ai phản đối vị trí này.
- Tách phần kiểm tra rẻ (size + magic) thành `validate_pdf_stream(filename, file_stream)` trong `document_service`:
  - `extract_document` gọi hàm này (dùng cho `/extract`);
  - `compare_document` gọi nó cho **cả hai** file trước khi trích xuất file đầu: thêm hai dòng, tránh trích xuất xong một PDF 100 trang rồi mới phát hiện file kia là rác.
- Pre-check số trang vẫn nằm trong extractor, không nhân đôi. Chi phí kiểm tra rẻ lặp lại là không đáng kể (`seek` + đọc 5 byte).
