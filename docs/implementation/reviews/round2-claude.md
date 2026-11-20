# Round 2 — Claude cross-examination

Mọi thí nghiệm dưới đây chạy bằng `.venv/Scripts/python` với `PYTHONDONTWRITEBYTECODE=1`. Mỗi lệnh dưới 60 giây. Script tạm nằm trong scratchpad (`r2.py`, `mkpdf.py`, `exp3.py`). Không ghi file nào vào repository.

---

**Issue ID:** ADV-CL-001
**Target:** Codex
**Severity:** High
**Claim:** Đề xuất `MAX_DIFF_TOKEN_PRODUCT = 4_000_000` (tính `len(old_tokens) * len(new_tokens)`), vượt ngưỡng thì trả 422 `DIFF_TOO_COMPLEX` (round1-codex.md:267-274).
**Evidence:**
- [CONFIRMED] `r2.py`: fixture `contract_old.pdf` có 2 trang, 395 token, tức khoảng 197,5 token/trang. Ngân sách 4e6 tương đương tối đa 2000 token mỗi bên, tức khoảng **10 trang**.
- [CONFIRMED, Round 1 của tôi] Fixture nhân 10 lần (17 760 ký tự, khoảng 3950 token mỗi bên, tích khoảng 15,6 triệu) chạy `diff_words` mất **0,12 s**.
**Counterexample:** Một hợp đồng 20 trang có mật độ như fixture sẽ bị từ chối 422, dù chỉ cần khoảng 0,1 s để diff. Trong khi đó v2 cho phép tới 100 trang. Ngưỡng này làm hỏng chính use-case chính của hệ thống.
**Recommendation:** Không đưa ngân sách token vào Phase A khi chưa có benchmark trên hợp đồng đại diện. Chỉ giữ hai việc:
- Fast path rẻ của Codex: chuỗi bằng nhau hoặc danh sách token bằng nhau thì trả `[]`.
- Ghi rõ "CPU chưa bị chặn" trong tài liệu.
**Confidence:** High

---

**Issue ID:** ADV-CL-002
**Target:** Antigravity
**Severity:** High
**Claim:** `MAX_TEXT_TOKENS = 50_000`. Báo cáo cho rằng "văn bản hợp đồng bình thường (~10.000–20.000 từ) chạy < 100 ms" (round1-antigravity.md, bảng §9).
**Evidence:** [CONFIRMED, Round 1] dùng fixture hợp đồng tiếng Việt thật nhân lên:

| Phiên bản | Kích thước | Thời gian |
|---|---|---|
| ×40 | 71 k ký tự, khoảng 15,8 k token | 6,51 s |
| ×80 | 142 k ký tự, khoảng 31,6 k token | **47,77 s** |

**Counterexample:** Bản ×80 có khoảng 31,6 k token, nằm dưới trần 50 k, nhưng vượt mốc 30 s. Như vậy giới hạn này vừa không bảo vệ được server, vừa đi kèm một nhận định latency sai và không có số đo.
**Recommendation:** Bỏ nhận định "< 100 ms". Nếu giữ trần thì phải hiệu chỉnh từ benchmark và ghi là "giảm rủi ro", không phải "bảo vệ". Đề xuất hợp lý vẫn là hoãn, như ở ADV-CL-001.
**Confidence:** High (đầu vào lặp lại nhiều; văn bản thật ít lặp hơn có thể nhanh hơn)

---

**Issue ID:** ADV-CL-003
**Target:** Codex
**Severity:** High
**Claim:** "Nếu `pdf.doc.encryption is not None`: **400** `INVALID_OR_ENCRYPTED_PDF`" (round1-codex.md:182). Quy tắc này từ chối mọi PDF mã hóa, kể cả PDF mở được.
**Evidence:** [CONFIRMED] `r2.py` trên PDF RC4 R2 chỉ đặt owner password (user password rỗng) cho kết quả `encryption is not None: True | text: Hello`.
**Counterexample:** Mẫu hợp đồng của cơ quan nhà nước hoặc ngân hàng thường chỉ khóa quyền in/sửa. pdfplumber vẫn trích xuất đúng các tệp này, nhưng phương án của Codex biến chúng từ 200 thành 400. Đây là breaking change không có lợi ích an ninh: nội dung đã được trích xuất mà không cần mật khẩu.
**Recommendation:** Chỉ từ chối khi mở thất bại (`PdfminerException`, bọc `PDFPasswordIncorrect`). V2 §3.2 cũng chỉ nêu `PDFPasswordIncorrect`. Có thể thêm test khóa hành vi "owner-only encrypted → 200".
**Confidence:** High

---

**Issue ID:** ADV-CL-004
**Target:** Antigravity
**Severity:** Medium
**Claim:** `MAX_TEXT_COMPARE_BODY_BYTES = 4 MB`, với lý do "đủ cho 2 chuỗi 500k ký tự UTF-8 tiếng Việt ~3 MB" (round1-antigravity.md §3.1).
**Evidence:** [CONFIRMED] `r2.py` với hai chuỗi 500 000 ký tự "ệ":

| Cách client mã hóa JSON | Kích thước body |
|---|---|
| `json.dumps` mặc định (`ensure_ascii=True`, là mặc định của Python và nhiều client) | **6 000 032 byte** |
| `ensure_ascii=False` | 3 000 032 byte |

**Counterexample:** Request hợp lệ (đúng `MAX_TEXT_CHARS`) từ client Python mặc định bị trả 413, trước khi Pydantic kịp áp giới hạn ký tự. Hai giới hạn mâu thuẫn nhau.
**Recommendation:** Không đặt trần body riêng cho `/text`. Nếu cần một trần, dùng một trần toàn cục ≥ 6 × 2 × `MAX_TEXT_CHARS` + overhead, hoặc dùng chung trần 31 MiB của `/pdf`.
**Confidence:** High

---

**Issue ID:** ADV-CL-005
**Target:** Codex, Antigravity
**Severity:** Medium
**Claim:** Viết middleware ASGI tự chế (Codex: `limit_request_body` trong `app/core/request_limits.py`; Antigravity: `MaxBodySizeMiddleware` ánh xạ theo path).
**Evidence:**
- [CONFIRMED] `starlette/middleware/body_limit.py` đã có sẵn `RequestBodyLimitMiddleware(app, max_body_size)`, xử lý cả `Content-Length` và chunked.
- [CONFIRMED] Chạy thử `app.add_middleware(RequestBodyLimitMiddleware, max_body_size=1000)` trong bộ nhớ:
  - `/extract` có Content-Length 5 KB → `413 text/plain "Content Too Large"`.
  - Body chunked 3 KB → `413 application/json {"detail":"Content Too Large"}`.
- Codex cũng thấy middleware này (round1-codex.md:254-261) nhưng loại nó chỉ vì body 413 không đồng nhất.
**Counterexample:**
- Middleware tự viết phải tự xử lý cleanup và trường hợp response đã bắt đầu. Codex tự liệt kê 5 kịch bản test ASGI cần thêm (round1-codex.md:445). Đây là gánh nặng bảo trì cho một đồ án.
- Ánh xạ theo path của Antigravity tự thừa nhận "dễ lệch nếu đổi prefix".
**Recommendation:** Một dòng trong `main.py`: `app.add_middleware(RequestBodyLimitMiddleware, max_body_size=MAX_REQUEST_BODY_BYTES)`, dùng một trần toàn cục (31 MiB như Codex). Chấp nhận body 413 ở tầng transport không có `error_code`, ghi rõ trong tài liệu. Kiểm tra 15 MiB/tệp vẫn nằm ở service.
**Confidence:** High

---

**Issue ID:** ADV-CL-006
**Target:** Antigravity
**Severity:** Medium
**Claim:** `_sanitize_filename` dùng `Path(filename.strip()).name`, được mô tả là "loại bỏ `../`, `\`, ký tự điều khiển `\r\n\x00`" (round1-antigravity.md §3.5).
**Evidence:** [CONFIRMED] `r2.py`:

| Đầu vào | `PurePosixPath(...).name` | `PureWindowsPath(...).name` |
|---|---|---|
| `'C:\\temp\\a.pdf'` | `'C:\\temp\\a.pdf'` | `'a.pdf'` |
| `'a\r\nb.pdf'` | giữ nguyên | giữ nguyên |
| `'a\x00b.pdf'` | giữ nguyên | giữ nguyên |

**Counterexample:**
- Kết quả **phụ thuộc hệ điều hành** của server: dev trên Windows, deploy trên Linux sẽ cho response khác nhau.
- Hàm không xóa ký tự điều khiển, trái với mô tả.
- Hàm đổi giá trị trường `filename` trong response (thay đổi tương thích) mà không mang lại an ninh: Phase A không ghi file theo tên người dùng.
**Recommendation:** Giữ filename là metadata, như Codex và tôi đề xuất. Vệ sinh tại nơi dùng: escape HTML ở báo cáo, `repr` khi ghi log.
**Confidence:** High

---

**Issue ID:** ADV-CL-007
**Target:** Codex
**Severity:** Medium
**Claim:** `/pdf` thêm `is_identical` (hai fulltext trích xuất bằng nhau) và `is_token_identical` (round1-codex.md:133-134).
**Evidence:** [CONFIRMED, Round 1] Hai PDF một trang trắng trả `changes=[]`, `needs_review=True`, và fulltext đều là `""`. Antigravity đã nêu cùng phản ví dụ (round1-antigravity.md §4.1).
**Counterexample:** Hai hợp đồng scan khác nhau hoàn toàn (đều không có lớp text) sẽ cho `is_identical: true`. Client chỉ đọc cờ này sẽ kết luận sai. Codex tự thừa nhận cờ này "không chứng minh giống byte hay hình ảnh", nghĩa là tên trường gây hiểu nhầm. Ngoài ra fulltext còn chứa separator tổng hợp `"\n\n"` không có trong tài liệu gốc.
**Recommendation:** Không thêm vào `/pdf` ở Phase A. `changes == []` kết hợp `needs_review` là đủ.
**Confidence:** High

---

**Issue ID:** ADV-CL-008
**Target:** Codex
**Severity:** Medium
**Claim:** Cho extractor ném `HTTPException` ở các nhánh mã hóa, số trang và độ dài (round1-codex.md:207, 501-502).
**Evidence:**
- Coding style profile §1 mô tả extractor là lớp "Bọc thư viện ngoài, trả `list[dict]`".
- V2 §7.2 có kế hoạch `experiments/` gọi trực tiếp pipeline ngoài HTTP.
- Service là điểm nghẽn chung của hai endpoint PDF (`comparison_service.py:16-17` gọi `extract_document`).
**Counterexample:** Script đánh giá batch gọi `extract_pdf` trên 100 PDF thì phải bắt `fastapi.HTTPException` để biết PDF quá trang. Tầng thấp nhất bị khóa vào framework.
**Recommendation:** Extractor ném exception thuần (xem Self-correction 5). Service đổi sang `HTTPException`.
**Confidence:** Medium

---

**Issue ID:** ADV-CL-009
**Target:** Antigravity
**Severity:** Medium
**Claim:** Bọc `pdfplumber.open` và cả vòng `extract_text` bằng `except (PdfminerException, PDFException, PSEOF, ValueError, TypeError, OSError)` → `InvalidPDFError` → 400 (round1-antigravity.md §3.5, bước 2 và 4).
**Evidence:** [CONFIRMED, Round 1] Mọi lỗi lúc mở đều đã được pdfplumber bọc thành `PdfminerException` (`pdfplumber/pdf.py:49-52`). Vì vậy các loại còn lại trong tuple không bổ sung gì cho bước mở.
**Counterexample:** Một bug lập trình trong vòng trích xuất (ví dụ `TypeError` do sửa sai code warning, hoặc `OSError` của đĩa tạm đầy) bị trả về là "PDF hỏng" 400. Lỗi hạ tầng bị che, và người dùng được khuyên xuất lại một PDF thật ra hợp lệ.
**Recommendation:** Chỉ bắt `PdfminerException`. Lỗi khác để thành 500 (Codex cùng quan điểm, round1-codex.md:205).
**Confidence:** Medium (chưa dựng được ca pdfminer ném `TypeError` thật)

---

**Issue ID:** ADV-CL-010
**Target:** Antigravity
**Severity:** Low
**Claim:** Validator loại thêm `\x00`, `\ufeff`, `\u200b-\u200d`, `\u2060` trước khi `strip()` (round1-antigravity.md §3.4).
**Evidence:** [CONFIRMED, Round 1] `diff_words` coi `"\u200b"` là một token hợp lệ: request đó trả 200 với 1 change.
**Counterexample:**
- Danh sách ký tự này tùy ý: bỏ sót `\u2061-\u2064`, `\u180e`.
- Nó tạo bất nhất giữa endpoint: `/text` từ chối text chỉ có NUL, nhưng `/pdf` coi trang chỉ có NUL là cảnh báo, không phải lỗi.
- Validator không còn tương đương "có ít nhất 1 token theo tokenizer".
**Recommendation:** Dùng `str.strip()`. Nó khớp với định nghĩa `\s` của Python `re` mà tokenizer dùng, kể cả `\x1c` mà regex Rust bỏ sót (Round 1 [CONFIRMED]).
**Confidence:** Medium

---

**Issue ID:** ADV-CL-011
**Target:** Antigravity
**Severity:** Low
**Claim:** "`span_to_page_locations` sinh `PageLocation` trỏ vào trang chỉ toàn khoảng trắng" được xem là bug, kèm đề xuất "lọc/cắt khoảng trắng biên" (round1-antigravity.md §2, §3.5).
**Evidence:** Trong phản ví dụ của chính Antigravity, `old_text = 'foo\n\n   \n\nbar'` thật sự chứa 3 khoảng trắng của trang 2. Location `[0,3)` trên trang 2 khớp đúng phần giao giữa span và text trang.
**Counterexample:** Nếu cắt location này, bất biến "`page_text[start:end]` ghép lại bằng fragment" (`tests/test_comparisons_api.py:88-91`) không còn kiểm được.
**Recommendation:** Không sửa. Ghi đây là hành vi đúng.
**Confidence:** Medium

---

**Issue ID:** ADV-CL-012
**Target:** Antigravity
**Severity:** Low
**Claim:** `config.py` có 9 hằng số, gồm `PDF_MAGIC_BYTES`, 3 trần body theo endpoint và `MAX_MULTIPART_OVERHEAD_BYTES`.
**Evidence:** V2 §3.2 chỉ yêu cầu 3 giới hạn. Ba trần body theo path đi kèm middleware tự viết (ADV-CL-005) và một giá trị sai (ADV-CL-004).
**Counterexample:** Đổi `MAX_UPLOAD_FILE_BYTES` thì phải nhớ cập nhật dây chuyền hằng số phụ thuộc, nếu không giới hạn ở middleware và service lệch nhau.
**Recommendation:** Dùng 3 hằng số của v2, cộng tối đa `MAX_REQUEST_BODY_BYTES` dẫn xuất từ chúng (như Codex).
**Confidence:** Medium

---

**Issue ID:** ADV-CL-013
**Target:** Codex
**Severity:** Low
**Claim:** Thêm warning `CID_FONT_ERROR` cho `\(cid:\d+\)` (round1-codex.md:352).
**Evidence:** Brief chỉ hỏi hành vi hiện tại của `EMPTY_TEXT`/`NULL_CHARACTER` có đúng không. Warning mới làm `needs_review` đổi từ false sang true (Codex tự ghi ở dòng 404). V2 đưa phát hiện lỗi font vào `layout_cleaner` (§4.1).
**Counterexample:** Hợp đồng kỹ thuật có chuỗi literal `"(cid:1)"` sẽ bị gắn cờ rà soát nhầm.
**Recommendation:** Hoãn sang tầng 1 của v2. Phase A chỉ thêm một test khóa hành vi hiện tại (`"(cid:0)"` không có warning).
**Confidence:** Medium

---

**Issue ID:** ADV-CL-014
**Target:** Antigravity
**Severity:** Low
**Claim:** Các nhận định tương thích ở cấp HTTP được gắn "Tương thích 100%" (§7). Tuy nhiên báo cáo tự ghi "`TestClient` ... bị treo" và chỉ kiểm chứng bằng gọi đồng bộ (§2).
**Evidence:** round1-antigravity.md §2 (ghi chú môi trường) so với bảng §7.
**Counterexample:** Hành vi multipart với `filename=""` chỉ thấy được qua HTTP (Round 1 [CONFIRMED]: 200 + fallback). Một số kết luận HTTP của Antigravity vì vậy chỉ nên coi là HYPOTHETICAL.
**Recommendation:** Hạ nhãn các khẳng định cấp HTTP xuống [HYPOTHETICAL], hoặc chạy lại qua `TestClient`.
**Confidence:** Medium

---

## Self-correction

1. **Sai: "handler toàn cục sẽ đổi dạng 404/405".** [CONFIRMED] Handler có điều kiện (`isinstance(exc.detail, dict) and "error_code" in exc.detail`, nếu không thì gọi `http_exception_handler`) vẫn giữ `404 {"detail":"Not Found"}` và trả phẳng `{"error_code":"X","detail":"y"}`. Tôi rút lại lập luận và **chấp nhận handler có điều kiện** khoảng 6 dòng trong `main.py`, theo đúng v2 §3.2. Không đụng `RequestValidationError`.
2. **Sai một phần: `len(pdf.pages)`.** [CONFIRMED] Với PDF 5000 trang: `open` mất 0,03 s, `islice(PDFPage.create_pages(pdf.doc), 101)` mất 0,12 s, còn `len(pdf.pages)` mất 1,38 s. Ở 1000 trang là 0,32 s. Trần 15 MiB vẫn chứa được hàng chục nghìn trang, nên chi phí không nhỏ. **Chấp nhận đếm dừng sớm bằng `islice`** (Codex, Antigravity).
3. **Thiếu: PDF 0 trang.** [CONFIRMED] `compare_document` trên PDF 0 trang trả `page_count 0, changes [], needs_review False`. **Chấp nhận trả 400 `INVALID_OR_ENCRYPTED_PDF`.**
4. **Điều chỉnh: "chỉ để reverse proxy".** Vì Starlette đã có `RequestBodyLimitMiddleware` (một dòng, đã chạy thử), tôi đổi sang dùng middleware có sẵn với trần toàn cục. Vẫn **phản đối middleware tự viết** (ADV-CL-005).
5. **Điều chỉnh: `ValueError` trần mà service tự ánh xạ.** Rủi ro dán nhãn sai đã được thừa nhận ở Round 1. Lập luận của Antigravity đúng ở chỗ service import `PdfminerException` làm lộ thư viện ra ngoài extractor. Chấp nhận hai exception một dòng trong extractor:
   - `InvalidPDFError(ValueError)`: bọc `PdfminerException`, PDF 0 trang.
   - `PDFPageLimitError(ValueError)`.

   Chỉ bắt `PdfminerException` (ADV-CL-009). Service ánh xạ sang `HTTPException`.
6. **Giữ nguyên:**
   - Không có ngân sách token (ADV-CL-001/002 cho thấy các ngưỡng đã đề xuất hoặc làm hỏng use-case, hoặc không bảo vệ được). Chấp nhận fast path equality của Codex.
   - Không timeout.
   - Không thêm trường cho `/pdf`.
   - Validator dùng `strip()`.
   - Magic trong 1024 byte đầu.
   - Không dùng `HealthResponse`.
7. **Khóa lỗi:** đổi từ `message` sang `detail` để khớp v2 (hệ quả của điểm 1).

## Lập trường cho 13 điểm bất đồng

1. **Dạng lỗi:** chuyển sang top-level `{"error_code","detail"}` bằng handler có điều kiện, không đụng 404 hay `RequestValidationError` (đã tự sửa).
2. **Middleware giới hạn body:** dùng `starlette.middleware.body_limit.RequestBodyLimitMiddleware` có sẵn, trần toàn cục 31 MiB. Không viết middleware riêng, không ánh xạ theo path.
3. **Magic bytes:** quét `%PDF-` trong 1024 byte đầu (theo dung sai ISO 32000-1 §7.5.2, cả hai bên đã xác nhận pdfplumber mở được PDF có byte rác ở đầu). Mức độ thấp, chấp nhận byte 0 nếu tác giả ưu tiên đơn giản.
4. **PDF mã hóa mở được bằng mật khẩu rỗng:** chấp nhận (200). Chỉ từ chối khi mở thất bại (ADV-CL-003).
5. **Đếm trang:** `islice(PDFPage.create_pages(pdf.doc), MAX_PDF_PAGES + 1)` (đã tự sửa).
6. **Ngân sách token:** không thêm ở Phase A. Thêm fast path equality. Giữ `TEXT_TOO_LONG` cho fulltext của `/pdf` theo `MAX_TEXT_CHARS`, đặt ở service. Ghi rõ CPU chưa bị chặn.
7. **`/pdf` thêm `is_identical`/`is_token_identical`:** không thêm (ADV-CL-007).
8. **Validator khoảng trắng:** `str.strip()` (ADV-CL-010).
9. **Filename:** giữ nguyên làm metadata, escape tại nơi dùng (ADV-CL-006).
10. **PDF 0 trang:** 400 `INVALID_OR_ENCRYPTED_PDF` (đã tự sửa).
11. **Exception:** hai class một dòng `InvalidPDFError` và `PDFPageLimitError` trong extractor, service ánh xạ sang `HTTPException`. Không đặt `HTTPException` trong extractor (ADV-CL-008, đã tự sửa).
12. **Health:** không có `HealthResponse`. Đăng ký `include_router(health.router, tags=["Health"])` với route `"/health"`, hoặc prefix `"/health"` với route `""`. Cả hai cho `GET /api/v1/health`; tránh route `"/"` vì sinh trailing slash.
13. **Warning mới:** hoãn `CID_FONT_ERROR` (ADV-CL-013). Chấp nhận sửa `EMPTY_TEXT` khi trang chỉ có NUL (`text.replace("\x00", "").strip()`): rẻ, đúng và không đổi `needs_review`.
