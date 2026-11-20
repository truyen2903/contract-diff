# Round 1 — Codex (Software Engineering Critic)

## 1. Problem understanding

**[CONFIRMED]** Phạm vi Phase A là hardening bốn endpoint hiện có, giữ thuật toán baseline và kiến trúc route → service → extractor/engine. Căn cứ: đọc `docs/implementation/reviews/phase-a-brief.md`, coding style profile và các phần liên quan của kế hoạch v1, v2 cùng hai báo cáo phản biện.

**[HYPOTHETICAL — đề xuất]** Phương án nên chốt:

- Giữ `is_identical` với nghĩa so sánh chuỗi nguyên văn; bổ sung `is_token_identical`.
- Validation văn bản trả 422 nhưng không sửa nội dung đầu vào.
- Giới hạn body trước multipart, giới hạn byte từng tệp trước parser, giới hạn trang trước trích xuất.
- PDF không hợp lệ hoặc mã hóa trả 400 với `error_code` ở cấp ngoài cùng.
- Giữ cảnh báo trích xuất và cơ chế tổng hợp `needs_review`.
- Không tuyên bố đã có timeout cưỡng chế 30 giây.
- Không đưa bất biến tái tạo văn bản/token chưa đúng vào tiêu chí nghiệm thu.

**[CONFIRMED]** Tôi không sửa file hoặc chạy lệnh Git ghi. Các lệnh Python dùng `PYTHONDONTWRITEBYTECODE=1`. Kết quả review dựa trên working tree thực tế, không coi mô tả hiện trạng trong tài liệu cũ là bằng chứng cho code hiện tại.

## 2. Current implementation

### 2.1. Bằng chứng kiểm chứng

**[CONFIRMED]** Các nhóm lệnh đã chạy:

| Mã | Lệnh/phương pháp | Kết quả |
|---|---|---|
| E0 | `Get-Content -Encoding UTF8`, `rg`, `git --no-optional-locks status --short` | Đọc source, tài liệu, test và trạng thái working tree. |
| E1 | `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider` | Capture mặc định thất bại vì không tạo được file tạm. Đặt `PYTEST_ADDOPTS=--capture=sys`, chạy lại đúng lệnh trên: **5 passed in 1.45s**. |
| E2 | Python + `TestClient(app, raise_server_exceptions=False)` | Kiểm chứng health, validation text, PDF rỗng/hỏng, tên tệp và response. |
| E3 | `.venv\Scripts\python.exe -c $probe`; PDF dựng trong bộ nhớ với objects/xref hợp lệ | Kiểm chứng PDF trắng, 0/101 trang, PDF mã hóa và tệp lớn qua service. Không tạo fixture trên đĩa. |
| E4 | Python gọi trực tiếp `diff_words`, `compare_text`, các hàm mapping | Kiểm chứng khoảng trắng, vị trí chèn, Unicode, separator, trang rỗng, đảo chiều và thời gian chạy. |
| E5 | `inspect.getsource`, `inspect.getsourcelines`, `importlib.metadata.version` | Kiểm tra cơ chế multipart, exception của pdfplumber, HTTPException và threadpool trong thư viện đã cài. |
| E6 | FastAPI app nhỏ, độc lập, chỉ tồn tại trong bộ nhớ | Kiểm chứng dạng lỗi 413 của limiter có sẵn và một limiter dạng hàm. |

**[CONFIRMED — E5]** Môi trường thực thi: Python 3.14.3, FastAPI 0.143.3, Starlette 1.8.0, Pydantic 2.14.1, pdfplumber 0.11.10, pdfminer.six 20260107, python-multipart 0.0.32, AnyIO 4.15.1.

### 2.2. Đối chiếu mã nguồn

| Vị trí | Nhận định |
|---|---|
| [main.py:8](C:/Users/Admin/contract-diff/app/main.py:8), [router.py:3](C:/Users/Admin/contract-diff/app/api/router.py:3) | **[CONFIRMED — E0, E2]** Chỉ đăng ký comparisons/documents; `health.py` rỗng. `GET /api/v1/health` trả **404**. |
| [comparison.py:4](C:/Users/Admin/contract-diff/app/schemas/comparison.py:4) | **[CONFIRMED — E0, E2]** Chỉ có `min_length=1`; chuỗi trắng và chuỗi 500.001 ký tự vẫn trả **200**. |
| [comparison_service.py:5](C:/Users/Admin/contract-diff/app/services/comparison_service.py:5) | **[CONFIRMED — E4]** `is_identical` dùng chuỗi nguyên văn, trong khi `changes` dùng token. |
| [comparisons.py:15](C:/Users/Admin/contract-diff/app/api/routes/comparisons.py:15), [documents.py:8](C:/Users/Admin/contract-diff/app/api/routes/documents.py:8) | **[CONFIRMED — E0, E2]** Cả hai route đã có fallback filename. Đây **không còn là lỗi cần sửa** trong working tree hiện tại. |
| [document_service.py:3](C:/Users/Admin/contract-diff/app/services/document_service.py:3), [pdf_extractor.py:4](C:/Users/Admin/contract-diff/app/extractors/pdf_extractor.py:4) | **[CONFIRMED — E2, E3]** Không kiểm tra byte, magic, số trang hay xử lý lỗi parser. |
| [comparison_service.py:22](C:/Users/Admin/contract-diff/app/services/comparison_service.py:22) | **[CONFIRMED — E3]** `needs_review` đã tổng hợp cảnh báo của cả hai PDF. |
| [text_diff.py:20](C:/Users/Admin/contract-diff/app/engines/text_diff.py:20) | **[CONFIRMED — E0, E4]** Dùng `SequenceMatcher(autojunk=False)`; không có giới hạn khối lượng tính toán. |
| [text_mapping.py:6](C:/Users/Admin/contract-diff/app/engines/text_mapping.py:6) | **[CONFIRMED — E4]** Quyết định separator theo `page_number`, không theo vị trí trong danh sách. |
| [test_comparisons_api.py:94](C:/Users/Admin/contract-diff/tests/test_comparisons_api.py:94) | **[CONFIRMED — E0, E1]** Năm test chỉ bao phủ `/pdf`: ba ca thành công và hai ca thiếu field. Hai file test khác rỗng; `test_text_diff.py` chưa có hàm `test_*`. |

### 2.3. Phát hiện cần ưu tiên

**[CONFIRMED — P1, E2/E3] PDF không hợp lệ trả lỗi server.**

Trên cả `/documents/extract` và `/comparisons/pdf`:

| Input | Kết quả hiện tại |
|---|---|
| `b""` | 500, `Internal Server Error` |
| `b"hello"` giả tên `.pdf` | 500 |
| `b"%PDF-1.7\nnot-a-document"` | 500 |
| PDF mã hóa, mật khẩu khác rỗng | 500 |

**[CONFIRMED — P1, E3] Giới hạn tài nguyên chưa tồn tại.**

- PDF hợp lệ **101 trang** được cả hai endpoint chấp nhận với 200.
- `extract_document(..., BytesIO(pdf))` chấp nhận PDF **15.729.223 byte**, lớn hơn `15 * 1024 * 1024`.
- `/text` chấp nhận chuỗi **500.001 ký tự**.

**[HYPOTHETICAL]** Chưa xác nhận upload HTTP lớn hơn 15 MiB trong môi trường này: multipart vượt ngưỡng spool cần file tạm, trong khi filesystem chỉ đọc. Kết quả tệp lớn ở trên là kiểm chứng trực tiếp service; không được trình bày như kiểm chứng HTTP đầy đủ.

**[CONFIRMED — P1, E3] Chính sách PDF mã hóa cần kiểm tra cả trường hợp mở được.**

PDF mã hóa với mật khẩu người dùng rỗng trả 200, trích xuất `"ABC"`, `needs_review=False`. Đối chứng bằng `pdfplumber.open(..., password=...)` xác nhận cả hai mẫu mã hóa đều hợp lệ và `pdf.doc.encryption` có giá trị. Chỉ bắt `PDFPasswordIncorrect` sẽ không từ chối mọi PDF mã hóa.

**[CONFIRMED — P2, E3] PDF 0 trang bị coi như một phép so sánh không cần rà soát.**

- `/extract`: 200, `page_count=0`, `pages=[]`.
- `/pdf` so với chính nó: 200, `changes=[]`, `needs_review=False`.

Nguyên nhân là `any([])` trả `False`, không phải vì trích xuất đã được xác nhận đáng tin cậy.

**[CONFIRMED — P2, E4] Kế hoạch v2 vẫn có bất biến tái tạo token sai với response hiện tại.**

Lệnh đã chạy:

```powershell
.venv\Scripts\python.exe -c "from app.services.comparison_service import compare_text; a=compare_text('a b','  x a b'); b=compare_text('a b','a x b  '); print(a == b); print(a)"
```

Kết quả:

```text
True
{
  'is_identical': False,
  'old_length': 3,
  'new_length': 7,
  'changes': [{
    'type': 'insert',
    'old_text': '',
    'new_text': 'x',
    'old_span': None,
    'new_span': {'start': 2, 'end': 3}
  }]
}
```

Hai đích có token lần lượt là `["x", "a", "b"]` và `["a", "x", "b"]`, nhưng toàn bộ response service giống nhau. Vì thiếu vị trí chèn trong bản cũ, từ `old_text + response` không thể khôi phục duy nhất ngay cả chuỗi token. Chuẩn hóa khoảng trắng không giải quyết được thiếu thông tin này.

## 3. Proposed solution

**[HYPOTHETICAL — toàn bộ mục này là thiết kế chưa cài vào repository]**

### 3.1. Health

**[HYPOTHETICAL]** Thêm:

- `HealthResponse` với `status: Literal["ok"]`.
- `health_endpoint()` trong `app/api/routes/health.py`, trả `{"status": "ok"}`.
- Đăng ký router với prefix `/health`, tags `["Health"]`.

**[HYPOTHETICAL]** Đây là liveness đơn giản, không chạy trích xuất PDF hay diff. Cho route trả dict trực tiếp là ngoại lệ nhỏ, có chủ đích với quy ước “gọi một service”; tạo service chuyển tiếp cho một hằng số không mang lại lợi ích.

### 3.2. Ngữ nghĩa equality

**[HYPOTHETICAL]** Giữ và bổ sung schema như sau:

| Endpoint | Trường | Nghĩa |
|---|---|---|
| `/text` | `is_identical` giữ nguyên | `old_text == new_text` |
| `/text` | `is_token_identical: bool` mới | `len(changes) == 0` |
| `/pdf` | `is_identical: bool` mới | Hai `fulltext` sau trích xuất và nối trang bằng nhau |
| `/pdf` | `is_token_identical: bool` mới | `len(changes) == 0` |

**[HYPOTHETICAL]** Không đổi tên `is_identical` thành `is_exact_match`, không thêm alias thứ ba, không tạo change `FORMATTING_ONLY`. Chọn cách diễn đạt tương thích trong v2 §3.3/§10; ghi rõ §9 Câu 8 dùng tên khác.

**[HYPOTHETICAL]** Với `/pdf`, mô tả schema phải nói rõ equality trên **văn bản trích xuất**, không chứng minh hai file PDF giống byte, bố cục hoặc hình ảnh. `is_token_identical=True` cũng không làm mất `needs_review=True`.

### 3.3. Validation text

**[HYPOTHETICAL]** Trong `TextComparisonRequest`:

```python
old_text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
new_text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
```

**[HYPOTHETICAL]** Thêm `field_validator("old_text", "new_text")`, ví dụ `validate_non_blank_text`, kiểm tra `if not value.strip(): raise ValueError(...)`, rồi **trả nguyên `value`**.

**[HYPOTHETICAL]** Chốt hành vi:

- Thiếu field, sai kiểu, `""`, chỉ có khoảng trắng, dài hơn 500.000 ký tự: **422**.
- Đúng 500.000 ký tự: qua kiểm tra độ dài.
- Không `.strip()` hoặc NFC hóa giá trị được trả xuống service; `old_length`, `new_length` và span tiếp tục tính trên chuỗi gốc.

### 3.4. Cấu hình

**[HYPOTHETICAL]** Thêm `app/core/config.py` với hằng số module-level:

```python
MAX_UPLOAD_FILE_BYTES = 15 * 1024 * 1024
MAX_PDF_PAGES = 100
MAX_TEXT_CHARS = 500_000
MAX_REQUEST_BODY_BYTES = 2 * MAX_UPLOAD_FILE_BYTES + 1024 * 1024
```

**[HYPOTHETICAL]** Dùng đúng đơn vị byte của v2: 15 MiB/tệp. Body tối đa 31 MiB cho phép hai tệp cùng đạt trần cộng phần multipart; đây là giới hạn bổ sung cho toàn request, không thay thế giới hạn từng tệp.

### 3.5. Kiểm tra PDF

**[HYPOTHETICAL]** Thêm `_validate_pdf_stream(file_stream)` trong `document_service.py`, dùng chung qua `extract_document`:

1. Đo kích thước bằng `seek/tell`, không `read()` toàn tệp.
2. Nếu vượt 15 MiB: **413**, `UPLOAD_TOO_LARGE`.
3. Nếu 0 byte hoặc năm byte đầu khác `%PDF-`: **400**, `INVALID_OR_ENCRYPTED_PDF`.
4. Đặt con trỏ về 0 trước khi parser chạy.

**[HYPOTHETICAL]** Trong `extract_pdf`:

1. Mở PDF.
2. Nếu `pdf.doc.encryption is not None`: **400**, `INVALID_OR_ENCRYPTED_PDF`.
3. Kiểm tra số trang trước `page.extract_text()`.
4. Không có trang: **400**, `INVALID_OR_ENCRYPTED_PDF`.
5. Trên 100 trang: **422**, `PDF_PAGE_LIMIT_EXCEEDED`.
6. Trích xuất và giữ nguyên cảnh báo từng trang.

**[HYPOTHETICAL]** Để chặn sớm việc duyệt tài liệu rất nhiều trang, ưu tiên đếm tối đa 101 phần tử từ `PDFPage.create_pages(pdf.doc)` bằng `islice`. Sau khi xác nhận số trang hợp lệ mới dùng luồng trích xuất hiện tại. Không tin riêng `/Count` trong PDF.

**[CONFIRMED — E5]** `pdfplumber.PDF.pages` hiện tạo danh sách trang đầy đủ. Vì vậy, cách đơn giản `len(pdf.pages) > 100` chỉ chặn trích xuất nội dung; nó chưa chặn chi phí dựng toàn bộ danh sách trang.

**[HYPOTHETICAL]** Bổ sung giới hạn tổng văn bản trích xuất, tính cả separator, không vượt `MAX_TEXT_CHARS`; vượt trả **422**, `EXTRACTED_TEXT_TOO_LONG`. Áp dụng tại extractor giúp `/extract` và `/pdf` dùng cùng chính sách. Đây là bổ sung bảo vệ đầu ra ngoài giới hạn “văn bản thuần” được nêu rõ trong v2.

### 3.6. Exception và response lỗi

**[CONFIRMED — E3/E5]** Phiên bản đã cài ném:

```text
PdfminerException(PDFSyntaxError(...))
PdfminerException(PDFPasswordIncorrect(...))
```

Do đó, chỉ bắt trực tiếp `PDFSyntaxError` hoặc `PDFPasswordIncorrect` như mô tả v2 sẽ bỏ sót các ca đã kiểm chứng.

**[HYPOTHETICAL]** `extract_document` bắt `pdfplumber.utils.exceptions.PdfminerException` quanh lời gọi extractor và chuyển thành HTTP 400. Không dùng `except Exception: return 400`, vì sẽ che lỗi lập trình hoặc hạ tầng.

**[HYPOTHETICAL]** Dùng `HTTPException` cho lỗi chính sách. Cho phép extractor phát sinh HTTPException ở các nhánh mã hóa/trang/độ dài là một đánh đổi có chủ đích để giữ thay đổi nhỏ; engine vẫn hoàn toàn độc lập FastAPI. Không tạo hệ thống exception class mới.

**[CONFIRMED — E5]** Lệnh gọi `http_exception_handler` với:

```python
HTTPException(
    400,
    detail={"error_code": "INVALID_OR_ENCRYPTED_PDF", "detail": "Invalid PDF"},
)
```

trả:

```json
{"detail":{"error_code":"INVALID_OR_ENCRYPTED_PDF","detail":"Invalid PDF"}}
```

Dạng này không đúng body v2 yêu cầu. [Tài liệu FastAPI](https://fastapi.tiangolo.com/tutorial/handling-errors/) cũng mô tả việc đưa giá trị vào trường `detail` và hỗ trợ custom exception handler.

**[HYPOTHETICAL]** Đăng ký một handler cho `starlette.exceptions.HTTPException` trong `main.py`:

- Nếu `exc.detail` là dict đúng dạng lỗi nghiệp vụ, trả trực tiếp `JSONResponse(exc.detail, status_code=..., headers=...)`.
- Với lỗi khác, gọi lại handler mặc định.
- Không thay handler `RequestValidationError`.

**[HYPOTHETICAL]** Thêm `APIErrorResponse(error_code: str, detail: str)` để mô tả lỗi nghiệp vụ. OpenAPI phải thể hiện 422 có thể là lỗi validation mặc định hoặc lỗi chính sách; không ghi đè toàn bộ 422 bằng schema chỉ cho phép `detail: str`.

### 3.7. Giới hạn trước multipart

**[CONFIRMED — E5]** FastAPI gọi `await request.form()` trước `solve_dependencies` và trước endpoint. Vì vậy, kiểm tra trong route, service hay dependency thông thường đều quá muộn để ngăn spool upload. `max_part_size` của Starlette đang áp dụng cho field không phải file. Điều này phù hợp với [tài liệu Starlette](https://starlette.dev/requests/#request-files).

**[HYPOTHETICAL]** Thêm một middleware ASGI nhỏ dạng hàm, chẳng hạn `limit_request_body(app, max_body_bytes)` trong `app/core/request_limits.py`:

- Từ chối sớm `Content-Length` vượt trần.
- Luôn đếm byte thực qua `receive`, kể cả không có `Content-Length`.
- Không gom body bằng `request.body()`.
- Trả **413**, `REQUEST_TOO_LARGE`, dạng JSON đã chốt.
- Khi multipart đang chạy, để exception đi qua luồng đóng tài nguyên của parser.

**[CONFIRMED — E6]** Prototype dạng hàm trong bộ nhớ với trần 4 byte cho kết quả:

```text
4 byte                  → 200
5 byte, Content-Length  → 413 JSON
5 byte, chia chunk      → 413 JSON
```

**[CONFIRMED — E5/E6]** Starlette đã cài có `RequestBodyLimitMiddleware`, nhưng FastAPI/APIRouter chưa có tham số `max_body_size` tương ứng. Prototype dùng middleware có sẵn cộng custom error handler cho kết quả:

```text
Content-Length vượt trần → 413 text/plain
Body chia chunk vượt trần → 413 application/json
```

**[HYPOTHETICAL]** Vì vậy, không dùng middleware có sẵn rồi giả định handler toàn cục sẽ thống nhất được mọi body lỗi. Middleware dạng hàm nhỏ là ngoại lệ hạ tầng có lý do, không phải thay đổi kiến trúc.

### 3.8. Giới hạn tính toán và timeout

**[HYPOTHETICAL]** Chưa triển khai timeout cưỡng chế 30 giây ở Phase A. Ghi rõ đây là mục chưa hoàn thành của v2; không khai báo một hằng số rồi coi yêu cầu đã được bảo đảm.

**[HYPOTHETICAL]** Bổ sung helper dùng chung trong `comparison_service.py`, ví dụ `_compare_text_changes(old_text, new_text)`:

1. Nếu chuỗi bằng nhau: trả `[]`.
2. Nếu hai danh sách token bằng nhau: trả `[]`.
3. Kiểm tra ngân sách số token trước khi gọi `diff_words`.
4. Quá ngân sách: **422**, `DIFF_TOO_COMPLEX`.

**[HYPOTHETICAL]** Có thể bắt đầu với `MAX_DIFF_TOKEN_PRODUCT = 4_000_000`, tính `len(old_tokens) * len(new_tokens)`. Đây là ngưỡng vận hành ban đầu cần hiệu chỉnh, không phải SLA. Nó là giới hạn bổ sung được công bố, không thay thế hoặc âm thầm đổi `MAX_TEXT_CHARS`.

## 4. Technical rationale

**[CONFIRMED — E4]** Hai ngữ nghĩa equality thực sự khác nhau:

```python
compare_text("a b", "a  b")
# is_identical=False, changes=[]
```

**[HYPOTHETICAL]** Bổ sung trường mới giải thích được kết quả này mà giữ hành vi cũ. Đổi `is_identical` thành token equality sẽ thay nghĩa của trường đang có.

**[CONFIRMED — E5]** Route hiện tại là hàm `def`; FastAPI đưa nó vào threadpool. AnyIO mô tả rằng hủy tác vụ chờ không cưỡng chế dừng mã Python đang chạy trong thread. [Tài liệu AnyIO](https://anyio.readthedocs.io/en/stable/threads.html#reacting-to-cancellation-in-worker-threads) xác nhận giới hạn này.

**[HYPOTHETICAL]** Bọc `wait_for` hoặc `fail_after` quanh thread có thể giới hạn thời gian chờ nhưng không bảo đảm parser/diff ngừng tiêu thụ CPU. Một hard timeout đúng cần cơ chế thực thi có thể kết thúc, chẳng hạn process được quản lý; thay đổi đó vượt mức tối thiểu của Phase A.

**[CONFIRMED — E4]** Đo trực tiếp với:

```python
diff_words("a " * n, "a " * (n - 1) + "b")
```

cho kết quả:

| Số token mỗi phía | Thời gian quan sát |
|---:|---:|
| 1.000 | 0,2104 giây |
| 2.000 | 0,8285 giây |
| 4.000 | 3,6575 giây |

**[CONFIRMED — E4]** Đây là một lần đo nhỏ trong môi trường hiện tại, không phải benchmark chuẩn. Tuy nhiên, chỉ khoảng 8.000 ký tự đã tốn vài giây; giới hạn 500.000 ký tự riêng lẻ không chứng minh thời gian xử lý an toàn. Tài liệu [Python 3.14 về difflib](https://docs.python.org/3.14/library/difflib.html) mô tả trường hợp xấu có độ phức tạp bậc hai.

**[HYPOTHETICAL]** Ngân sách token là biện pháp bù tối thiểu khi hoãn hard timeout. Nếu không nhận bổ sung này, phải ghi nhận CPU vẫn là rủi ro chưa được xử lý, thay vì tuyên bố hardening tài nguyên đã hoàn tất.

## 5. Edge cases

### 5.1. Mapping và separator

**[CONFIRMED — E4]** `build_document_text` hiện cho:

```text
pages=[{3:"A"},{4:"B"}] → "\n\nA\n\nB"
pages=[{1:"A"},{1:"B"}] → "AB"
```

**[HYPOTHETICAL]** Sửa quyết định separator theo chỉ số vòng lặp: phần tử đầu không separator, các phần tử sau có `"\n\n"`. Có thể dùng `parts` rồi `"".join(parts)`; vẫn giữ `page_number` nguồn.

**[CONFIRMED — E0]** Extractor hiện đánh số liên tiếp từ 1. Vì vậy, đây là lỗi hợp đồng của helper đã chứng minh, nhưng chưa phải lỗi HTTP được tái hiện với luồng extractor hiện tại.

**[CONFIRMED — E4]** Với `"A\n\nB"`:

```text
span [1,3) → []
span [0,4) → trang 1 [0,1), trang 2 [0,1)
```

**[HYPOTHETICAL]** Giữ hành vi này: separator tổng hợp không thuộc trang nào. Không gán nó tùy tiện cho trang trước hoặc sau.

**[CONFIRMED — E4]** `diff_words` tạo span bắt đầu/kết thúc ở token không trắng; do đó, span dương nằm hoàn toàn trong separator không được tạo bởi engine hiện tại. Không nên gọi kết quả `[]` của helper trong trường hợp này là bug endpoint.

**[CONFIRMED — E4]** Trang rỗng ở giữa vẫn có range `[start,start)`. Ví dụ `"A\n\n\n\nB"` ánh xạ thay đổi xuyên trang về trang 1 và 3, bỏ qua trang 2 rỗng.

**[HYPOTHETICAL]** Giữ range rỗng và quy ước span nửa mở `[start,end)`. Không xóa trang rỗng vì sẽ làm thay đổi số trang nguồn.

### 5.2. Cảnh báo và `needs_review`

**[CONFIRMED — E3/E4]** Hành vi hiện tại:

| Tình huống | Kết quả |
|---|---|
| PDF một trang trắng, so với chính nó | `EMPTY_TEXT`, `changes=[]`, `needs_review=True` |
| `extract_text()` trả whitespace — mock unit | `EMPTY_TEXT` |
| `extract_text()` trả `"\x00"` — mock unit | `NULL_CHARACTER` |
| PDF sinh glyph mã 0 bằng Helvetica | Text `"(cid:0)"`, không warning, `needs_review=False` |

**[HYPOTHETICAL]** Giữ hai điều kiện warning độc lập, giữ nguyên text và tổng hợp `needs_review` từ mọi trang của cả hai bên. Không suy ra “PDF quét” một cách chắc chắn từ `EMPTY_TEXT`; một trang trắng thật cũng tạo cùng tín hiệu.

**[HYPOTHETICAL]** Bổ sung warning `CID_FONT_ERROR` cho placeholder dạng `\(cid:\d+\)` để xử lý ca đã tái hiện. Đây là heuristic cần test và công bố khả năng báo nhầm khi tài liệu thật chứa literal tương tự; không tự sửa hoặc xóa placeholder.

**[HYPOTHETICAL]** `/extract` tiếp tục trả warnings cấp trang; chưa cần thêm `needs_review` vào schema này. PDF có trang nhưng không lấy được text vẫn trả 200 kèm warning; PDF không có trang trả 400.

### 5.3. Filename, Unicode và đảo chiều

**[CONFIRMED — E2]** PDF hợp lệ tên `.txt` với MIME `text/plain` được chấp nhận. PDF hợp lệ tên `.PDF` với `application/octet-stream` cũng được chấp nhận.

**[HYPOTHETICAL]** Giữ chính sách nhận dạng bằng nội dung: suffix/MIME là metadata, không phải chứng cứ định dạng. PDF thật sai đuôi được nhận; văn bản giả đuôi `.pdf` bị từ chối.

**[CONFIRMED — E2]** Raw multipart `filename=""` kích hoạt fallback `"document.pdf"` và trả 200. Nếu bỏ hẳn tham số `filename`, Starlette phân loại part thành field thường; FastAPI trả 422 “Expected UploadFile”.

**[HYPOTHETICAL]** Giữ 422 khi không có file part đúng kiểu. Không mở rộng schema sang `str | UploadFile` chỉ để cố kích hoạt fallback.

**[CONFIRMED — E4]** `"Tiền"` ở NFC và NFD tạo change `replace`, độ dài lần lượt 4 và 6. Unicode tiếng Việt thông thường cho span đúng trong ca thay `"30"` bằng `"15"`.

**[HYPOTHETICAL]** Giữ hành vi này trong baseline; không chuẩn hóa Unicode khi chưa có ánh xạ offset.

**[CONFIRMED — E4]** `diff_words("a b", "b a")` chọn chèn/xóa `"b"`; chiều ngược lại có thể chọn chèn/xóa `"a"`. Vì vậy, không áp dụng assertion “mọi change đều đảo chiều thành đúng change nghịch đảo” cho mọi input.

## 6. Security considerations

**[CONFIRMED — E0/E5]** Biên tin cậy gồm JSON, multipart metadata, byte PDF và kết quả parser. Luồng hiện tại không có giới hạn nghiệp vụ trước các bước xử lý này.

**[HYPOTHETICAL]** Các kiểm soát bắt buộc của Phase A:

| Rủi ro | Kiểm soát |
|---|---|
| Body lớn, nhiều part hoặc part thừa | Giới hạn byte toàn request trước multipart. |
| Một tệp quá lớn nhưng tổng request chưa vượt trần | Giới hạn riêng từng stream trước parser. |
| PDF giả/hỏng/mã hóa | Magic + parser + kiểm tra encryption. |
| Nhiều trang | Dừng kiểm tra ở trang thứ 101, không trích xuất toàn bộ rồi mới kiểm tra. |
| Văn bản trích xuất lớn | Giới hạn tổng ký tự đầu ra. |
| Token lặp gây diff chậm | Fast path equality và ngân sách token. |
| Lộ nội dung hợp đồng | Detail lỗi cố định; không trả `str(exception)` hoặc log toàn body. |

**[CONFIRMED — E0]** Filename hiện chỉ được đưa vào response, không dùng để mở đường dẫn ghi. Chưa có bằng chứng về path traversal trong bốn endpoint này.

**[HYPOTHETICAL]** Giữ filename như metadata; không thêm thao tác lưu bằng tên do client cung cấp.

**[HYPOTHETICAL]** Magic `%PDF-`, trần byte và trần trang không bảo đảm an toàn tuyệt đối trước PDF có stream nén hoặc cấu trúc phức tạp. Giới hạn text chỉ có thể kiểm tra sau khi parser giải mã đủ nội dung trang; đây là phần rủi ro còn lại khi chưa có cô lập process/hard timeout.

## 7. Compatibility impact

| Thay đổi | Đánh giá |
|---|---|
| Giữ `is_identical` | **[HYPOTHETICAL]** Giữ nghĩa và kiểu hiện tại của `/text`. |
| Thêm equality fields | **[HYPOTHETICAL]** Mở rộng response; client chỉ đọc field cũ tiếp tục hoạt động. Client cấm unknown fields hoặc so sánh nguyên JSON có thể cần cập nhật. |
| Giữ `changes`, spans và locations | **[HYPOTHETICAL]** Không thêm loại change, không đổi quy ước `None` ở phía không có token. |
| Validation chặt hơn | **[HYPOTHETICAL]** Có chủ đích đổi whitespace, input quá lớn và PDF quá nhiều trang từ thành công sang 422/413. |
| PDF hỏng/mã hóa | **[HYPOTHETICAL]** Đổi 500 hoặc trường hợp được nhận trước đây sang 400 có mã lỗi. |
| Validation mặc định | **[HYPOTHETICAL]** Giữ `{"detail":[...]}` và vị trí field cho missing/type/length errors. |
| Warning mới | **[HYPOTHETICAL]** `CID_FONT_ERROR` có thể làm `needs_review` chuyển từ false sang true; cần ghi trong hợp đồng response. |
| PDF trắng | **[HYPOTHETICAL]** Giữ thành công có cảnh báo; không đổi thành lỗi chỉ vì không trích xuất được text. |
| Health | **[HYPOTHETICAL]** Thêm endpoint trả 200. |

**[HYPOTHETICAL]** Không bổ sung `is_exact_match`; không thay tên field để chạy theo cách gọi không nhất quán của tài liệu. Không cam kết response là edit script có thể tái dựng tài liệu.

## 8. Testing strategy

### 8.1. Unit tests

**[HYPOTHETICAL]** Bổ sung các nhóm test hành vi sau:

| Thành phần | Ca kiểm thử và kỳ vọng |
|---|---|
| `TextComparisonRequest` | Thiếu, `None`, sai kiểu, rỗng, whitespace → 422 qua API; 500.000/500.001 ký tự kiểm tra biên. |
| Validator text | Chuỗi có khoảng trắng đầu/cuối được giữ nguyên; Unicode không bị chuẩn hóa. |
| `compare_text` | Exact match; chỉ khác whitespace; nội dung khác; cờ equality đúng. |
| `_validate_pdf_stream` | 0 byte, 4 byte, sai magic, đúng magic nhưng hỏng; giới hạn byte −1/đúng/+1; con trỏ về 0. |
| `extract_pdf` | 0/1/100/101 trang; mã hóa mật khẩu rỗng/khác rỗng; lỗi khi mở, duyệt trang và trích xuất. |
| Warnings | `None`, `""`, whitespace, literal NUL, CID placeholder, tiếng Việt bình thường. |
| `build_document_text` | Danh sách rỗng; một trang; trang đầu/giữa/cuối rỗng; số trang không bắt đầu từ 1. |
| `span_to_page_locations` | `None`, đúng biên trang, separator-only, xuyên trang và xuyên trang rỗng. |
| Ngân sách diff | Đúng/ngay trên ngưỡng; fast path exact/token equality không bị từ chối vô ích. |

### 8.2. Integration tests

**[HYPOTHETICAL]** Giữ nguyên năm test hiện có; bổ sung:

| Endpoint/nhóm | Kỳ vọng |
|---|---|
| `/health` | 200, JSON `{"status":"ok"}`, có trong OpenAPI. |
| `/text` | Happy path, tiếng Việt, thiếu từng field, rỗng, whitespace, biên độ dài. |
| `/text` whitespace-only difference | `is_identical=False`, `is_token_identical=True`, `changes=[]`. |
| `/extract` và `/pdf` | PDF rỗng/hỏng/giả/mã hóa → 400 với hai key cấp ngoài cùng. |
| Upload quá trần | 413 cho từng field của `/pdf` và field `/extract`. |
| Trang quá trần | 100 được nhận; 101 → 422 trước trích xuất nội dung. |
| Filename | `.PDF`, `.txt`, MIME khác; filename rỗng; thiếu tham số filename; thiếu file field. |
| PDF trắng | Warnings giữ nguyên; `/pdf` có `needs_review=True` dù không có changes. |
| Response compatibility | Các field cũ giữ kiểu, giá trị, spans và locations; chỉ thêm field dự kiến. |
| Cleanup | Stream tạm được đóng khi lỗi parse, vượt body limit hoặc validation thất bại. |

**[HYPOTHETICAL]** Với middleware, cần test ASGI có `receive` chia chunk thật, không chỉ generator của TestClient: thiếu `Content-Length`, header khai thấp, vượt trần giữa multipart, body đúng trần và phần overhead. Một test HTTP happy path không chứng minh chặn sớm hoặc cleanup.

### 8.3. Thuật toán và bất biến

**[HYPOTHETICAL]** Kiểm thử `diff_words` trên: giống nhau; chèn/xóa đầu, giữa, cuối; thay một/nhiều token; whitespace; cụm lặp; đảo điều khoản; tiếng Việt; thay đổi xuyên trang rỗng.

**[HYPOTHETICAL]** Chốt các bất biến phù hợp với output hiện tại:

- Span khác `None` nằm trong biên và trỏ đúng fragment nguồn.
- Span trên từng phía tăng theo thứ tự và không chồng lấn.
- Phía insert/delete không có token giữ span `None`.
- `diff_words(a, b) == []` khi và chỉ khi hai dãy token bằng nhau.
- Mapping chỉ trả phần giao với text thật của trang.

**[CONFIRMED — E4]** Không được dùng bất biến tái tạo từ response hiện tại: phản ví dụ ở §2.3 bác bỏ cả phiên bản token. Thêm `is_token_identical` không bổ sung vị trí chèn.

**[HYPOTHETICAL]** Phase A giữ output baseline và sửa tiêu chí kiểm thử. Nếu sau này cần edit script tái dựng được, phải thiết kế thêm insertion anchor hoặc token opcodes; đó là thay đổi hợp đồng riêng.

### 8.4. Giới hạn của kết quả hiện có

**[CONFIRMED — E1]** Năm test baseline đã chạy đạt; các test đề xuất ở trên chưa được viết hoặc chạy.

**[CONFIRMED — E3]** Các mẫu PDF kiểm chứng mới được dựng trong bộ nhớ; mẫu mã hóa có kiểm tra đối chứng giải mã thành `"ABC"`.

**[HYPOTHETICAL]** Boundary upload HTTP lớn, tải đồng thời, cleanup khi ngắt kết nối và corpus PDF hỏng đa dạng vẫn cần được kiểm chứng trong môi trường có thư mục tạm ghi được.

## 9. Complexity assessment

**[HYPOTHETICAL]** Khối lượng thay đổi dự kiến:

| Nhóm | Mức độ |
|---|---|
| Health/router/schema | Nhỏ |
| Validator, equality và config | Nhỏ |
| Validation PDF và chuyển lỗi | Trung bình |
| Middleware body và error handler | Trung bình; cần test thứ tự thực thi/cleanup |
| Mapping | Nhỏ |
| Test biên và PDF lỗi | Phần công việc lớn nhất |

**[HYPOTHETICAL]** Không cần dependency mới, class service, repository layer, parser cấu trúc hoặc framework exception riêng. Chỉ thêm schema Pydantic và một middleware dạng hàm.

**[CONFIRMED — E0]** Mapping hiện duyệt các page range cho mỗi change. Với trần 100 trang đề xuất, chưa có bằng chứng cần interval tree hoặc tối ưu cấu trúc dữ liệu.

**[HYPOTHETICAL]** Kiểm tra body có bộ nhớ phụ hằng số; kiểm tra size/magic không sao chép toàn tệp; token preflight tuyến tính theo input. Phần diff vẫn giữ thuật toán baseline, nên ngân sách token chỉ giới hạn đầu vào tính toán, không tạo bảo đảm thời gian tuyệt đối.

## 10. Potential weaknesses

1. **[HYPOTHETICAL] Chưa hoàn thành hard timeout 30 giây.**  
   Phương án chủ động để hạng mục này chưa đạt. Giới hạn token và kích thước giảm rủi ro nhưng không thay thế việc kết thúc process.

2. **[HYPOTHETICAL] Ngưỡng token có thể từ chối hợp đồng hợp lệ.**  
   `4_000_000` là đề xuất ban đầu từ phép đo nhỏ. Cần đo trên hợp đồng đại diện và công bố giới hạn bổ sung; không mô tả 500.000 ký tự như điều kiện đủ để được xử lý.

3. **[HYPOTHETICAL] PDF nhỏ vẫn có thể đắt khi giải mã.**  
   Giới hạn trang và text không ngăn mọi chi phí bên trong một trang. Chưa đủ cơ sở gọi phương án này là chống DoS hoàn chỉnh.

4. **[HYPOTHETICAL] Extractor có phụ thuộc HTTPException.**  
   Đây là đánh đổi để tránh hệ thống exception mới. Nếu extractor sắp được dùng độc lập ngoài API, cần cân nhắc lại biên này.

5. **[HYPOTHETICAL] CID warning là heuristic.**  
   Nó bắt được ca đã tái hiện nhưng có false positive/false negative. Không chứng minh toàn bộ chất lượng font hoặc nội dung trích xuất.

6. **[HYPOTHETICAL] Chặn magic ở byte đầu là chính sách nghiêm.**  
   Có thể từ chối tài liệu mà parser vẫn đọc được khi có dữ liệu đứng trước header. Cần ghi rõ đây là định dạng upload được hỗ trợ.

7. **[HYPOTHETICAL] Equality của PDF chỉ phản ánh text đã trích xuất.**  
   Hình ảnh, chữ ký, vị trí và lỗi trích xuất có thể khác dù cờ equality là true. Vì vậy, warnings và `needs_review` phải được giữ độc lập.

8. **[CONFIRMED — E5] Hành vi phụ thuộc phiên bản thư viện.**  
   Wrapper exception, giới hạn multipart và dạng lỗi middleware đã được kiểm tra trên các phiên bản đang cài. Không nên suy rộng kết quả này sang phiên bản khác mà không chạy lại test.

9. **[CONFIRMED — E1/E3] Chưa có bằng chứng nghiệm thu implementation mới.**  
   Review đã xác nhận các lỗi và thử một số cơ chế trong bộ nhớ; repository chưa được sửa và bộ test hardening chưa tồn tại.