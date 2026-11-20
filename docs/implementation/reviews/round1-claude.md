# Round 1 — Claude (Architect & Implementation Reviewer)

> Phạm vi: chỉ đọc. Mọi thí nghiệm chạy bằng `.venv/Scripts/python` với `PYTHONDONTWRITEBYTECODE=1`; script/PDF tạm nằm trong scratchpad (`C:\Users\Admin\AppData\Local\Temp\claude\7a81e431fe1166c9\3ae8a7db-bd9c-402e-b3dc-61914ab153f4\scratchpad\{mkpdf,exp1,exp2,exp3,exp4,proto}.py`), PDF dựng trong bộ nhớ. `git status` không đổi.
> Môi trường thực tế: Python 3.14.3, fastapi 0.143.3, starlette 1.8.0, pydantic 2.14.1, pdfplumber 0.11.10, pdfminer.six 20260107. Baseline `pytest -q` → `5 passed in 1.54s` **[CONFIRMED]**.

---

## 1. Problem understanding

Phase A phải làm cứng 4 endpoint hiện có mà không đổi kiến trúc 4 tầng (route → service → extractor/engine). Ba nhóm vấn đề thực chất:
1. **Ngữ nghĩa kết quả** của `/text`: `is_identical` (so chuỗi nguyên văn) và `changes` (so token `\S+`) dùng hai khái niệm "giống nhau" khác nhau.
2. **Kiểm soát đầu vào**: text toàn khoảng trắng được nhận (200), PDF hỏng/rỗng/mã hóa làm server trả 500, chưa có giới hạn byte/trang/độ dài, chưa có `/health`.
3. **Tính đúng của engine ánh xạ trang** (`text_mapping`) và độ phủ test (hiện chỉ có happy path của `/pdf`).

Mục tiêu: sửa tối thiểu nhưng đúng, giữ phong cách tác giả (route mỏng, service trả dict, engine thuần, `HTTPException` thay vì hệ thống exception riêng).

## 2. Current implementation (file:line)

| Thành phần | Vị trí | Hiện trạng |
|---|---|---|
| Đăng ký router | `app/api/router.py:3-16` | Chỉ `comparisons`, `documents`; không import `health` |
| `/health` | `app/api/routes/health.py` (0 byte) | `GET /api/v1/health` → **404** `{"detail":"Not Found"}` **[CONFIRMED exp1]** |
| `/text` route | `app/api/routes/comparisons.py:9-12` | Mỏng, gọi `compare_text` |
| `/pdf` route | `comparisons.py:14-21` | Fallback filename đã có (thay đổi chưa commit) |
| `/extract` route | `app/api/routes/documents.py:7-12` | Mỏng, fallback `"document.pdf"` |
| Request schema | `app/schemas/comparison.py:4-6` | Chỉ `Field(min_length=1)` |
| Response `/text` | `comparison.py:27-31` | `is_identical`, `old_length`, `new_length`, `changes` |
| `compare_text` | `app/services/comparison_service.py:5-13` | `is_identical = old_text == new_text` (dòng 9) |
| `compare_document` | `comparison_service.py:15-36` | Gọi `extract_document` cho từng file (dòng 16-17) — **điểm nghẽn chung của `/pdf` và `/extract`** |
| `extract_document` | `app/services/document_service.py:3-10` | Không kiểm tra gì |
| `extract_pdf` | `app/extractors/pdf_extractor.py:2-17` | `pdfplumber.open` không try; warning `NULL_CHARACTER`/`EMPTY_TEXT` |
| `build_document_text` | `app/engines/text_mapping.py:1-16` | Separator quyết định bằng `page["page_number"] == 1` (dòng 6) |
| `span_to_page_locations` | `text_mapping.py:18-36` | Bỏ qua overlap rỗng (dòng 28) |
| Test | `tests/test_comparisons_api.py` (5 ca); `tests/test_comparison_api.py`, `tests/test_comparison_service.py` **0 byte**; `tests/test_text_diff.py` chỉ chép lại `tokenize_with_spans`, không có `test_*` |

Hành vi hiện tại đã kiểm chứng (`exp1.py`, `exp2.py`) **[CONFIRMED]**:

| Đầu vào | Kết quả |
|---|---|
| `/text` `"   "` / `"\n\t"` | **200** `{"is_identical":false,...,"changes":[]}` |
| `/text` `"a b"` / `"a  b"` | 200 `is_identical:false, changes:[]` — mâu thuẫn F03 có thật |
| `/text` NFC `"Điều khoản"` / NFD cùng chữ | `is_identical:false`, 1 change `replace`, độ dài 10 vs 13 |
| `/extract` 0 byte / `b"hello"` / PDF bị cắt 200 byte / PDF `/Encrypt` cần mật khẩu | **500 Internal Server Error** |
| `/pdf` với một file rác | 500 |
| `/extract` file `.txt` nhưng nội dung PDF hợp lệ | 200 |
| multipart `filename=""` (raw) | 200, `"filename":"document.pdf"` — **fallback cần thiết, không phải code chết** |
| part không có `filename` | 422 `Expected UploadFile, received: <class 'str'>` |

Loại ngoại lệ thực tế từ `extract_pdf` (`exp2.py`) **[CONFIRMED]**: mọi ca đều là `pdfplumber.utils.exceptions.PdfminerException`, với nguyên nhân bọc bên trong là `PDFSyntaxError('No /Root object! ...')` (0 byte, không phải PDF), `PSEOF('Unexpected EOF')` (bị cắt), `PDFPasswordIncorrect()` (cần user password). pdfplumber bọc mọi lỗi lúc mở ở `pdfplumber/pdf.py:49-52` (`except Exception as e: raise PdfminerException(e)`).

## 3. Proposed solution

Nguyên tắc: **mọi kiểm tra PDF đặt trong `document_service.extract_document`** — đây là điểm duy nhất mà cả `/extract` lẫn `/pdf` đi qua (`comparison_service.py:16-17`), nên route không đổi.

### 3.1 `app/core/config.py` (mới, chỉ hằng số — không class, không pydantic-settings)
```python
MAX_UPLOAD_FILE_BYTES = 15 * 1024 * 1024
MAX_PDF_PAGES = 100
MAX_TEXT_CHARS = 500_000
```
Repo dùng namespace package (`find app tests -name __init__.py` → rỗng **[CONFIRMED]**), không cần `__init__.py`. **Không** thêm `COMPARISON_TIMEOUT_SECONDS` ở Phase A (xem §4.5).

### 3.2 `/health`
`health.py`: `router = APIRouter()` + `@router.get("/health") def health_endpoint(): return {"status": "ok"}`. `router.py`: `api_router.include_router(health.router, tags=["Health"])` (không prefix). Không tạo `HealthResponse` — ngoại lệ có chủ đích với quy tắc "route gắn `response_model`"; schema một trường là overengineering.

### 3.3 `/text`
`TextComparisonRequest` (`comparison.py`):
```python
old_text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
new_text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)

@field_validator("old_text", "new_text")
@classmethod
def reject_blank_text(cls, value: str) -> str:
    if not value.strip():
        raise ValueError("Văn bản không được chỉ chứa khoảng trắng")
    return value
```
Dùng `field_validator` + `str.strip()` chứ **không** dùng `Field(pattern=r"\S")`: regex Rust của pydantic-core hiểu `\s` khác Python `re` — `\x1c`, `\x1f`, `\ufeff` lọt qua `pattern` trong khi Python `\S+` không sinh token nào cho `\x1c`/`\x1f` **[CONFIRMED, lệnh `python -c` ở §5]**. `strip()` dùng cùng định nghĩa khoảng trắng với tokenizer `r"\S+"`, nên "không rỗng sau validate" ⇔ "có ≥1 token". Lỗi → **422** dạng Pydantic mặc định (prototype: `'   '` và `'\x1c'` → `value_error` "Văn bản không được chỉ chứa khoảng trắng"; 500 001 ký tự → `string_too_long`).

`TextComparisonResponse`: thêm `is_token_identical: bool`; **giữ `is_identical`** với nghĩa nguyên văn. `compare_text` thêm một dòng `"is_token_identical": len(changes) == 0`. Prototype: `"a b"` vs `"a  b"` → `is_identical False, is_token_identical True` **[CONFIRMED]**.

**Không** đổi tên thành `is_exact_match` (v2 §9 Câu 8): `is_identical` đã mang đúng nghĩa đó, đổi tên phá client. Sửa câu chữ v2 §9 Câu 8 / §7.1 thành "`is_identical` (nguyên văn) vs `is_token_identical`".

**`/pdf` không thêm trường**: "giống nguyên văn" của hai PDF không xác định rõ (byte khác nhưng text trích xuất có thể trùng); `changes == []` đã chính là token-identical. Nếu muốn đồng nhất sau này, chỉ thêm `is_token_identical`, không bao giờ `is_identical`.

### 3.4 Upload PDF — `document_service.extract_document`
```python
def extract_document(filename, file_stream):
    size = file_stream.seek(0, os.SEEK_END)
    file_stream.seek(0)
    if size > MAX_UPLOAD_FILE_BYTES:
        raise HTTPException(status_code=413, detail={"error_code": "FILE_TOO_LARGE", "message": ...})
    header = file_stream.read(1024)
    file_stream.seek(0)
    if b"%PDF-" not in header:
        raise HTTPException(status_code=400, detail={"error_code": "INVALID_OR_ENCRYPTED_PDF", "message": ...})
    try:
        pages = extract_pdf(file_stream, MAX_PDF_PAGES)
    except PdfminerException:
        raise HTTPException(status_code=400, detail={"error_code": "INVALID_OR_ENCRYPTED_PDF", "message": ...})
    except ValueError as error:
        raise HTTPException(status_code=422, detail={"error_code": "PDF_TOO_MANY_PAGES", "message": ...})
    ...
```
- Extractor: `extract_pdf(file_stream, max_pages=None)` — ngay sau `pdfplumber.open`, nếu `len(pdf.pages) > max_pages` thì `raise ValueError(...)` **trước** vòng `extract_text`. Phần còn lại giữ nguyên.
- `message` có `filename` để `/pdf` báo đúng file lỗi.
- Đo kích thước bằng `seek` trên stream (không qua `UploadFile.size`) để service chỉ biết stream, test được bằng `BytesIO`. `seek(0, 2)` trả đúng `2000005` trên `SpooledTemporaryFile` **[CONFIRMED exp4]**.
- Magic bytes kiểm tra trong 1024 byte đầu (dung sai như Acrobat), không bắt buộc ở byte 0: pdfminer đọc được PDF có 10 byte rác đứng trước **[CONFIRMED exp2: `garbage-before-header OK`]** — `startswith` sẽ từ chối nhầm.
- **Route không đổi.**

Prototype monkeypatch (`proto.py`) **[CONFIRMED]**: 0 byte → 400; `b"hello"` → 400; PDF cần mật khẩu → 400 "PDF hỏng hoặc cần mật khẩu"; PDF có rác ở đầu → 200; 4 trang với giới hạn 3 → 422 `PDF_TOO_MANY_PAGES`; 15 MB + 6 byte → 413; `/pdf` với `new_file` rác → 400 `"new.pdf: không phải tệp PDF"`.

PDF mã hóa chỉ owner password (user password rỗng) **phải được chấp nhận**, và thiết kế trên chấp nhận vì pdfplumber mở được: đã dựng PDF RC4 R2 user password rỗng → `[{'page_number': 1, 'text': 'Hello secret', ...}]` **[CONFIRMED exp3]**. "Encrypted" ở đây chỉ nên có nghĩa "cần mật khẩu".

### 3.5 Giới hạn văn bản cho `/pdf`
Trong `compare_document`, sau `build_document_text`, trước `diff_words`: nếu `len(fulltext) > MAX_TEXT_CHARS` → `HTTPException(422, {"error_code": "TEXT_TOO_LONG", ...})`. Lý do: `/pdf` chung engine với `/text` nên phải chịu chung giới hạn; `/extract` không chạy diff nên không cần.

### 3.6 Định dạng lỗi
`HTTPException(detail={"error_code": ..., "message": ...})` → body thực tế `{"detail": {"error_code": "...", "message": "..."}}` **[CONFIRMED exp4]**. Dạng top-level `{"error_code", "detail"}` của v2 §3.2 **không đạt được bằng `HTTPException`**; muốn vậy phải thêm exception handler toàn cục và handler đó sẽ đổi luôn dạng 404/405 mặc định. Đề xuất sửa v2, không sửa code; dùng khóa con `message` để tránh `detail.detail`.

### 3.7 `text_mapping.build_document_text`
Dòng 6: `separator = "\n\n" if page_ranges else ""` — separator theo **vị trí** trong danh sách, không theo số trang. Sửa một dòng, không đổi kết quả với API hiện tại.

## 4. Technical rationale

1. **Điểm nghẽn thay vì sửa route**: kiểm tra ở `extract_document` bảo vệ cả hai endpoint PDF, `comparisons.py`/`documents.py` giữ nguyên — khớp quy tắc 1 của profile. Ngoại lệ có chủ đích: service import `fastapi.HTTPException` (profile §6 cho phép "ưu tiên `HTTPException`, đặt ở chỗ đơn giản nhất"); engine vẫn thuần.
2. **Bắt đúng một loại**: mọi lỗi lúc mở là `PdfminerException` [CONFIRMED]. Không `except Exception` (che lỗi lập trình thành 400).
3. **Kích thước — kiểm ở đâu mới có nghĩa**: Starlette đã spool **toàn bộ** phần file trước khi handler chạy; `max_part_size` chỉ áp cho field không phải file (`starlette/formparsers.py:186-190`), file ghi vào `SpooledTemporaryFile(max_size=1MB)` rồi tràn ra đĩa (`formparsers.py:234`) **[CONFIRMED đọc mã nguồn]**. Vậy kiểm tra 15 MB trong service **không bảo vệ băng thông/đĩa**, chỉ chặn chi phí CPU của pdfminer. Chặn sớm thực sự thuộc reverse proxy (nginx `client_max_body_size`) **[HYPOTHETICAL, ngoài repo]**; middleware kiểm `Content-Length` bị chunked request vượt qua **[HYPOTHETICAL]**.
4. **Giới hạn kích thước không chặn được thời gian**: file header `%PDF-` + thân rác — 1.0 MB → 2.40 s, 4.2 MB → 10.79 s, 14 MB → 51.35 s (đo khi có tiến trình song song) trước khi `PdfminerException`. `diff_words` siêu tuyến tính **[CONFIRMED, đo không tải]**: 4000 token `a` lặp (8 k ký tự) → 3.50 s; Zipf 300 từ 18.5 k ký tự → 2.60 s, 37 k → 18.98 s; văn bản fixture hợp đồng ×40 (71 k ký tự) → 6.51 s, ×80 (142 k ký tự) → **47.77 s**. Kết luận: `MAX_TEXT_CHARS = 500_000` **không giới hạn được latency**; 142 k ký tự (trong mọi giới hạn) đã vượt 30 s, ngoại suy 500 k lặp lại → hàng giờ CPU **[HYPOTHETICAL, ngoại suy bậc 2]**. Nguyên nhân là `SequenceMatcher(autojunk=False)` (`text_diff.py:20-24`); đổi nó là đổi baseline, ngoài phạm vi.
5. **Timeout 30 s — không làm ở Phase A**: endpoint là `def` đồng bộ trong threadpool; `asyncio.wait_for` quanh `run_in_threadpool` chỉ trả 504 cho client, thread vẫn đốt CPU vì Python không hủy được thread **[HYPOTHETICAL — ngữ nghĩa Python đã biết, chưa chạy]**. Đó là an toàn giả. Timeout thật cần cô lập tiến trình (process pool/subprocess) = đổi kiến trúc, trái brief. Phase A nên (a) ghi nhận giới hạn, (b) để tác giả chọn `MAX_TEXT_CHARS` bằng benchmark thay vì 500 k (số liệu trên gợi ý ~100 k ký tự/bên trên máy này — quyết định thuộc tác giả).
6. **`is_token_identical = len(changes) == 0`**: vì `equal` là opcode duy nhất bị bỏ qua, `changes == []` ⇔ hai dãy token bằng nhau; không cần tính thêm. Bất biến: `is_identical ⇒ is_token_identical`.

## 5. Edge cases

| Ca | Hiện tại | Sau đề xuất | Trạng thái |
|---|---|---|---|
| Text toàn khoảng trắng `"   "`, `"\n\t"`, `"\u00a0"`, `"\u3000"` | 200, `changes=[]` | 422 | [CONFIRMED] |
| `"\x1c"` (Python whitespace, Rust regex không) | 200 | 422 nhờ `strip()`; `pattern` sẽ để lọt | [CONFIRMED] `python -c` với `Field(pattern=r'\S')` |
| `"\u200b"`, `"\ufeff"` | 1 token | Vẫn hợp lệ (nhất quán tokenizer) | [CONFIRMED] |
| Chỉ khác khoảng trắng | `is_identical False`, `changes []` | + `is_token_identical True` | [CONFIRMED] |
| NFC vs NFD | 1 `replace` giả | Không đổi; ghi nhận ngoài phạm vi (pdfplumber có `unicode_norm`) | [CONFIRMED] |
| NUL trong `/text` `"a\x00b"` | 200, 1 token | Không đổi | [CONFIRMED] |
| PDF 0 byte | 500 | 400 | [CONFIRMED proto] |
| PDF có rác ở đầu | 200 | 200 (quét 1024 byte) | [CONFIRMED] |
| PDF chỉ owner password | 200 | 200 | [CONFIRMED] |
| PDF cần user password | 500 | 400 | [CONFIRMED] |
| Đuôi `.txt` nội dung PDF | 200 | 200 — **không kiểm tra đuôi**; nội dung là căn cứ (F04 nói kiểm đuôi không giải quyết lỗi parser) | [CONFIRMED] |
| Thiếu `filename` | 422 (FastAPI coi là str) | Không đổi | [CONFIRMED] |
| `filename=""` | 200 fallback | Không đổi | [CONFIRMED] |
| Trang rỗng ở giữa | Ánh xạ đúng trang 3, `needs_review True` | Không đổi | [CONFIRMED] |
| Hai PDF scan giống nhau | `changes []`, `needs_review True` | Đúng — danh sách rỗng không đáng tin khi có `EMPTY_TEXT` | [CONFIRMED] |
| Ngắt trang dịch chuyển (`"one two three|four five"` → `"one two|three four five"`) | `changes []` | Đúng | [CONFIRMED] |
| Thay đổi vắt 2 trang | `old_text "three\n\nfour"`, 2 location p1[8:13], p2[0:4] | Đúng (`old_text` chứa separator) | [CONFIRMED] |
| Danh sách trang bắt đầu từ 2 | `fulltext "\n\nabc\n\ndef"` (separator thừa đầu) | Sửa bằng §3.7 | [CONFIRMED] gọi engine trực tiếp |
| Hai trang cùng `page_number=1` | `"abcdef"` (dính token) | Sửa bằng §3.7 | [CONFIRMED] |
| Span trọn trong `"\n\n"` | `[]` | Không xảy ra qua `diff_words` (span luôn bắt đầu/kết thúc ở ký tự `\S`) | [CONFIRMED] engine trả `[]`; không xảy ra: suy luận từ `text_diff.py:31-40` |
| Change `insert` | `old_locations []` — không có điểm neo trong bản cũ | Hạn chế UX, ngoài Phase A | [CONFIRMED] |
| `/text` luôn có `old_locations: []` | Nhiễu do chung `ChangeItem` | Giữ để tương thích | [CONFIRMED] |
| Trang trắng có chủ đích ("trang này để trống") | `EMPTY_TEXT` → `needs_review True` | Chấp nhận (hướng bảo thủ) | [HYPOTHETICAL] |
| `(cid:NN)` lỗi font | Không cảnh báo | Ngoài phạm vi | [HYPOTHETICAL] |

## 6. Security considerations

- **DoS CPU** là rủi ro lớn nhất và giới hạn kích thước không khử được (số liệu §4.4) [CONFIRMED]. Endpoint đồng bộ dùng threadpool mặc định anyio (40 luồng) → vài request chậm có thể chiếm hết luồng [HYPOTHETICAL].
- **Flate bomb**: 15 MB nén có thể bung ra hàng GB trong pdfminer [HYPOTHETICAL, chưa dựng].
- **JSON body `/text`** không có giới hạn byte; Pydantic chỉ từ chối sau khi parse toàn body [HYPOTHETICAL, suy từ cách FastAPI đọc body]. Giới hạn ở proxy.
- **Filename** do người dùng gửi được đưa vào `message` và `filename` — JSON đã escape, an toàn ở tầng API; báo cáo HTML sau này phải escape [HYPOTHETICAL].
- Không lưu file → không có path traversal. Không trả stack trace (400/413/422 thay 500).

## 7. Compatibility impact

- `/text`: thêm `is_token_identical` (additive); `is_identical` giữ nghĩa. Request trước 200 với text toàn khoảng trắng hoặc > 500 k nay 422 (thay đổi hành vi có chủ đích).
- `/pdf`, `/extract`: 500 → 400/413/422; body thành công không đổi.
- **Xung đột dạng 422**: lỗi Pydantic có `detail` là **list** `[{loc,msg,type}]`; `PDF_TOO_MANY_PAGES`/`TEXT_TOO_LONG` có `detail` là **object**. Client lặp `response.json()["detail"]` như test hiện tại (`tests/test_comparisons_api.py:136-139`) sẽ hỏng nếu gặp 422 nghiệp vụ. Đề xuất ghi rõ quy ước "`detail` là list ⇔ lỗi validation; object ⇔ có `error_code`". Phương án khác: dùng 413 cho quá số trang — nhưng lệch v2.
- v2 cần sửa: dạng lỗi (§3.2), tên `is_exact_match` (§7.1, §9 Câu 8), nhận định "timeout 30 s".
- Ghi chú: v2 §10 ghi Python 3.11, môi trường thật 3.14.3 [CONFIRMED].

## 8. Testing strategy

Tổ chức: giữ `tests/test_comparisons_api.py` (tên số nhiều của tác giả, khớp module route) cho API; `tests/test_text_diff.py` (xóa bản sao `tokenize_with_spans`, viết unit engine); `tests/test_text_mapping.py` (mới); `tests/test_comparison_service.py` (service). `tests/test_comparison_api.py` 0 byte trùng tên gần giống → đề nghị tác giả xóa.

Dựng PDF: helper `make_pdf(pages_text, encrypt=False)` ~35 dòng trong file test (như `scratchpad/mkpdf.py`), tạo PDF nhiều trang, trang rỗng, và PDF `/Encrypt` với U sai (sinh `PDFPasswordIncorrect`). Không thêm thư viện, không thêm fixture nhị phân.

**Unit (engine)**
- `diff_words`: giống nhau → `[]`; insert/delete/replace; `"a b"` vs `"a\nb"` → `[]`; cụm lặp (`"a a a"` → `"a a"`); đảo hai mệnh đề (ghi lại hành vi delete+insert hiện tại); tiếng Việt có dấu; bất biến span `0 ≤ start < end ≤ len`, tăng chặt, `text[span] == old_text`.
- `build_document_text`: separator chỉ giữa trang; trang rỗng; một trang; danh sách bắt đầu `page_number=2` (phải pass sau §3.7).
- `span_to_page_locations`: `None`; span vắt 2 trang; span trong separator → `[]`; span rỗng → `[]`.

**Service**
- `compare_text`: `is_identical ⇒ is_token_identical`; ca khoảng trắng.
- `extract_document` với `BytesIO`: 0 byte, không phải PDF, bị cắt, mã hóa, quá số trang (monkeypatch `app.services.document_service.MAX_PDF_PAGES` hoặc dựng 101 trang), quá dung lượng → assert `HTTPException.status_code` và `detail["error_code"]`.

**API** (giữ helper `post_pdf_pair`, `successful_json`)
- `/health` → 200 `{"status":"ok"}`.
- `/text`: toàn khoảng trắng (parametrize `"   "`, `"\n\t"`, `"\x1c"`), rỗng, thiếu field, `null`, quá dài (`MAX_TEXT_CHARS + 1`), tiếng Việt, khóa schema response (tập key gồm `is_token_identical`).
- `/pdf` & `/extract` (parametrize cả hai endpoint): 0 byte, rác, mã hóa, 15 MB + 1 → 413; file `.txt` chứa PDF → 200; một bên lỗi → `message` chứa đúng tên file; fixture happy path giữ nguyên.

**Không làm ở Phase A**: `hypothesis`, marker pytest.

## 9. Complexity assessment

| Hạng mục | Ước lượng |
|---|---|
| Code app: `config.py`, `health.py`, `router.py`, schema validator, 1 dòng service text, kiểm tra trong `extract_document`, tham số `max_pages` extractor, sửa `text_mapping`, 422 `TEXT_TOO_LONG` | ~+55–65 dòng, 0 thư viện mới, 0 class mới (ngoài schema có sẵn) |
| Test | ~+200–250 dòng |
| Thời gian | 3–4 giờ, khớp ngân sách v2 §10 mục 2–3 |
| Route bị sửa | Không route nào (chỉ thêm `health.py`) |

## 10. Potential weaknesses (của chính phương án này)

1. **`except ValueError` quá rộng**: nếu pdfminer ném `ValueError` không bọc trong lúc `extract_text`, nó bị dán nhãn sai `PDF_TOO_MANY_PAGES` [HYPOTHETICAL]. Giảm thiểu: kiểm số trang ngay sau `open`, trước vòng lặp (đã đề xuất), hoặc một subclass một dòng `class PDFPageLimitError(ValueError)` trong extractor — đánh đổi với quy tắc "không tạo exception class".
2. **Service phụ thuộc FastAPI** (`HTTPException`): script thí nghiệm gọi `extract_document` ngoài web sẽ nhận `HTTPException` — dùng được nhưng không đẹp.
3. Lỗi trong `extract_text` không thuộc `PdfminerException` vẫn trả 500 (chủ ý: không che bug).
4. Trong `/pdf`, `old_file` được trích xuất xong mới kiểm tra `new_file` → tốn công nếu `new_file` lỗi. Có thể kiểm tra rẻ cả hai trước, nhưng phải tách thêm hàm.
5. **Latency vẫn không bị chặn**: byte/trang/ký tự không chặn CPU (§4.4). Phương án chấp nhận rủi ro đó và chuyển timeout thật sang giai đoạn có thay đổi kiến trúc.
6. Dạng 422 không đồng nhất (list vs object) — xem §7.
7. Quét `%PDF-` trong 1024 byte vẫn để lọt rác có header giả; kiểm tra này chỉ giúp báo lỗi sớm và rõ, không phải biện pháp an ninh.

---

## Phụ lục: kiểm chứng `coding-style-profile.md`

Đối chiếu với code (`cat -n`, `grep`, `find`, `file`, `git log`):

| Mục trong profile | Đánh giá | Bằng chứng |
|---|---|---|
| Header "commit `a5e9c60`" | **Sai nhẹ**: HEAD là `3304f00` (chỉ thêm docs; code giống `a5e9c60`) | `git log --oneline` [CONFIRMED] |
| §1 các tham chiếu dòng (`comparisons.py:9-21`, `documents.py:7-12`, `comparison_service.py:5-36`, `document_service.py:3-10`, `pdf_extractor.py:2-17`, `router.py:7-16`, `comparison.py:2`, `comparison.py:24-25`) | Đúng | [CONFIRMED] |
| §3 "engine có hint" | **Sai một phần** | `tokenize_with_spans(text)` không hint (`text_diff.py:4`); `compare_text` có hint tham số, không hint trả về (`comparison_service.py:5`) [CONFIRMED] |
| §3 "vòng `for` + `append` thay vì comprehension" | **Không chính xác** | Có list comprehension ở `text_diff.py:17-18` và generator trong `any()` ở `comparison_service.py:22-23` — nên viết "không comprehension phức tạp" [CONFIRMED] |
| §4 "Import thư viện ngoài, **dòng trống**, rồi `app.*`" | **Sai về tính nhất quán** | Không có dòng trống ở `documents.py:1-3`, `schemas/comparison.py:1-2`, `pdf_extractor.py:1-2`; thứ tự lộn ở `comparison_service.py:1-3` (engine, service, engine); `text_diff.py:1-2` đặt `from difflib` trước `import re` [CONFIRMED] |
| §7 "Comment và docstring bằng tiếng Việt" | **Chỉ đúng cho tests** | `grep -rn '#\|"""' app` → không có: `app/` không có comment/docstring nào [CONFIRMED] |
| §7 "Không có formatter config" | Đúng | Không có `pyproject.toml`, `setup.cfg`, `ruff.toml` [CONFIRMED] |
| §6 "không `try/except`, không `HTTPException`" | Đúng | `grep -rn "try:\|except\|HTTPException\|raise" app` → không có [CONFIRMED] |
| §9 quy tắc 5 "tên `*_service`" | **Mơ hồ** | Hậu tố `_service` chỉ ở tên **module**; hàm service là `compare_text`… không hậu tố [CONFIRMED] |
| §5, §8 (schema, test) | Đúng | [CONFIRMED] |

Thiếu trong profile:
- Không có `__init__.py` (namespace package) [CONFIRMED].
- `__pycache__/*.pyc` bị commit vào git; `.gitignore` chỉ có `.venv` [CONFIRMED `git ls-files`] → mọi diff đều nhiễu.
- Line ending lẫn lộn: `comparison_service.py` CRLF; `comparisons.py`, `text_mapping.py` LF [CONFIRMED `file`].
- Môi trường chạy Python 3.14 [CONFIRMED].

Ghi chú về brief: brief nói kế hoạch v2 "không có trên working tree `main`", nhưng thực tế có ở `docs/` (commit `3304f00`); `diff` báo khác toàn bộ dòng, nhiều khả năng chỉ do line ending [HYPOTHETICAL].
