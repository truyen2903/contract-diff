# Round 2 — Codex cross-examination

## Phạm vi và bằng chứng

Đã đọc brief Round 2, ba báo cáo Round 1, coding style profile, mã nguồn, test và các phần kế hoạch được brief viện dẫn. Tôi không sửa, tạo hoặc xóa tệp; trạng thái `git status --short` trước và sau không đổi.

**[CONFIRMED]** Lệnh pytest đã chạy:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTEST_ADDOPTS='--capture=sys'
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Kết quả: **5 passed in 1.44s**. Đây là năm test baseline, không phải nghiệm thu các phương án hardening chưa triển khai.

Các probe dùng lệnh:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.venv\Scripts\python.exe -c $probe
```

`$probe` là mã trong bộ nhớ. Các nhóm kiểm chứng được viện dẫn dưới đây:

| Mã | Nội dung đã chạy |
|---|---|
| E1 | FastAPI app thử handler có điều kiện; gọi API thật với PDF rác; kiểm tra filename, JSON encoding và mapping. |
| E2 | PDF dựng trong bộ nhớ: mã hóa mật khẩu rỗng, 0 trang, 1.000 trang và header có tiền tố. Đọc các định nghĩa builder từ `scratchpad/mkpdf.py`, `exp3.py` bằng AST; không thực thi phần benchmark dài của các tệp này. |
| E3 | Đo `diff_words` trên token lặp và token gần như duy nhất; mock đầu ra extractor dài 500.001 ký tự. |
| E4 | Fault injection cho `extract_text`/`pdfplumber.open`; kiểm tra warning NUL và định nghĩa whitespace. |
| E5 | Gọi ASGI trực tiếp với body chia chunk; kiểm tra 413 và đóng stream khi multipart bị ngắt. Stream tạm được thay bằng `BytesIO`. |
| E6 | Stream phát sinh `OSError`; kiểm tra phản ví dụ reconstruction. |

Các kết quả prototype chỉ chứng minh cơ chế tương ứng. Tôi không coi chúng là bằng chứng implementation mới đã tồn tại trong repository.

## Phản biện báo cáo Claude

### ADV-CL-001 — Handler có điều kiện không bắt buộc đổi 404/405

**Issue ID:** ADV-CL-001  
**Target:** Claude  
**Severity:** Medium  
**Claim:** `docs/implementation/reviews/round1-claude.md:120`: handler toàn cục “sẽ đổi luôn dạng 404/405 mặc định”, từ đó đề xuất sửa contract v2 sang lỗi lồng trong `detail`.

**Evidence:** **[CONFIRMED — E1]** Tôi đăng ký handler cho `starlette.exceptions.HTTPException`, chỉ trả JSON phẳng khi `exc.detail` có đúng hai khóa `error_code`, `detail`; các trường hợp khác gọi `http_exception_handler` mặc định. Lệnh `python.exe -c $probe` cho:

```text
GET  /missing → 404 {"detail":"Not Found"}
POST /policy  → 405 {"detail":"Method Not Allowed"}, Allow: GET
GET  /policy  → 400 {"error_code":"INVALID_OR_ENCRYPTED_PDF","detail":"Invalid PDF"}
```

**Counterexample:** Chính app thử nghiệm trên đạt body nghiệp vụ theo v2 mà vẫn giữ body và header của 404/405. Nhận định “sẽ đổi luôn” không đúng với handler có nhánh fallback.

**Recommendation:** Giữ contract top-level của brief; chỉ chuyển đổi lỗi nghiệp vụ có cấu trúc xác định. Giữ handler `RequestValidationError` và 422 thiếu field như hiện tại. Mô tả riêng các dạng 422 trong OpenAPI.

**Confidence:** High.

### ADV-CL-002 — Để reverse proxy xử lý là một điều kiện triển khai chưa được bảo đảm

**Issue ID:** ADV-CL-002  
**Target:** Claude  
**Severity:** High  
**Claim:** `round1-claude.md:129`, `:167`: chặn body sớm thuộc reverse proxy; middleware kiểm `Content-Length` có thể bị chunked request vượt qua.

**Evidence:** Phần phản biện middleware chỉ đúng với limiter **chỉ đọc header**. Mã nguồn đã cài tại `starlette/formparsers.py:185` chỉ áp `max_part_size` cho field không phải file; `parse()` đọc và ghi file trước endpoint.

**[CONFIRMED — E5]** Prototype ASGI bọc `receive()` để cộng byte thực cho kết quả:

```text
4 byte, limit 4                    → 200
5 byte, Content-Length: 5          → 413, không gọi receive
chunk [2, 3], không Content-Length → 413
multipart vượt trần giữa stream   → 413
UPLOAD_CLEANUP files 1 closed [True]
```

**Counterexample:** Chạy trực tiếp ứng dụng hiện tại mà không có proxy thực thi giới hạn. Kiểm tra 15 MiB ở service không ngăn Starlette spool trước đó. Ngược lại, request thiếu `Content-Length` vẫn bị prototype đếm byte chặn.

**Recommendation:** Giữ một limiter ASGI nhỏ đếm byte thực trước multipart; reverse proxy là lớp bổ sung khi triển khai. Limiter phải truyền lỗi qua luồng cleanup của parser. Không tuyên bố nó chặn sớm chính xác 15 MiB cho từng multipart file: giới hạn từng stream vẫn cần ở service.

**Confidence:** High.

### ADV-CL-003 — Ghi nhận CPU DoS nhưng không đặt admission guard để lại lỗ hổng chính

**Issue ID:** ADV-CL-003  
**Target:** Claude  
**Severity:** High  
**Claim:** `round1-claude.md:130-131`, `:216`: giữ giới hạn ký tự, ghi nhận rủi ro latency và hoãn xử lý thật sang giai đoạn sau.

**Evidence:** `app/engines/text_diff.py:20` gọi `SequenceMatcher(autojunk=False)` mà không có ngân sách tính toán.

**[CONFIRMED — E3]** Đã chạy:

```python
diff_words("a " * 6000, "a " * 5999 + "b")
```

Kết quả: **6.000 token mỗi phía**, khoảng **12.000 ký tự**, một change, **7,3105 giây** trong lần đo này. Đây là phép đo đơn lẻ, không phải SLA.

**Counterexample:** Đầu vào này nhỏ hơn nhiều cả 500.000 ký tự lẫn gợi ý 100.000 ký tự của Claude nhưng đã tiêu tốn nhiều giây. Hạ trần ký tự theo benchmark một loại văn bản không kiểm soát được phân bố token.

**Recommendation:** Hoãn hard timeout là hợp lý, nhưng thêm fast path exact/token equality và ngân sách token dùng chung cho `/text`, `/pdf`. Không đổi `autojunk`, không cắt nội dung rồi trả kết quả một phần. Ngưỡng phải được đo trên corpus đại diện và công bố như giới hạn chấp nhận đầu vào.

**Confidence:** High về rủi ro; Medium về ngưỡng vận hành phù hợp.

### ADV-CL-004 — `len(pdf.pages)` kiểm tra sau khi đã dựng toàn bộ trang

**Issue ID:** ADV-CL-004  
**Target:** Claude  
**Severity:** Medium  
**Claim:** `round1-claude.md:106`: dùng `len(pdf.pages) > max_pages` trước vòng trích xuất.

**Evidence:** `pdfplumber/pdf.py:144` dựng toàn bộ `_pages` trước khi trả danh sách.

**[CONFIRMED — E2]** Với PDF 1.000 trang trong bộ nhớ, đếm lời gọi constructor `pdfplumber.page.Page` bằng mock:

```text
LEN_PAGES     1000 PAGE_OBJECTS 1000
BOUNDED_COUNT 101  PAGE_OBJECTS 0
```

Nhánh thứ hai dùng:

```python
sum(1 for _ in islice(PDFPage.create_pages(pdf.doc), 101))
```

**Counterexample:** PDF vượt trần rất nhiều vẫn buộc phương án Claude dựng mọi `Page`, dù cuối cùng chỉ cần biết có trang thứ 101.

**Recommendation:** Đếm dừng ở 101 bằng iterator trước khi truy cập `pdf.pages`. Bắt lỗi tại cả bước duyệt trang này. Giới hạn đó không loại bỏ chi phí mở PDF, đọc xref hoặc phân tích cấu trúc trước khi iterator yield.

**Confidence:** High.

### ADV-CL-005 — “Encrypted chỉ nên nghĩa là cần mật khẩu” tự đổi chính sách của brief

**Issue ID:** ADV-CL-005  
**Target:** Claude  
**Severity:** Medium  
**Claim:** `round1-claude.md:114`: PDF mã hóa với user password rỗng “phải được chấp nhận”; “Encrypted” chỉ nên hiểu là cần mật khẩu.

**Evidence:** Brief gốc `phase-a-brief.md:31` yêu cầu xử lý PDF mã hóa; không nêu ngoại lệ owner-password-only.

**[CONFIRMED — E2]** PDF RC4 mở được bằng mật khẩu rỗng cho:

```text
ENCRYPTION True TEXT ABC
ENC_BASELINE [{'page_number': 1, 'text': 'ABC', 'warnings': []}]
```

**Counterexample:** File vẫn có encryption dictionary nhưng không phát sinh `PDFPasswordIncorrect`. Phương án dựa riêng vào việc mở thành công sẽ nhận nó.

**Recommendation:** Theo contract hiện tại, từ chối khi `pdf.doc.encryption is not None`. Nếu muốn hỗ trợ PDF mã hóa mở được bằng mật khẩu rỗng, phải ghi đây là thay đổi chính sách. Tôi không coi khả năng mở file này tự thân là một lỗ hổng bảo mật.

**Confidence:** High.

### ADV-CL-006 — `ValueError` không xác định được nguyên nhân “quá nhiều trang”

**Issue ID:** ADV-CL-006  
**Target:** Claude  
**Severity:** Medium  
**Claim:** `round1-claude.md:102-106`: bắt mọi `ValueError` từ `extract_pdf` rồi ánh xạ thành 422 `PDF_TOO_MANY_PAGES`.

**Evidence:** Claude đã nhận diện rủi ro ở `:212`, nhưng cách giảm thiểu “kiểm số trang trước vòng lặp” không thu hẹp phạm vi `except`.

**[CONFIRMED — E4]** Patch `Page.extract_text` phát sinh `ValueError("unrelated failure")`, rồi gọi extractor thật trên fixture hợp lệ. Áp dụng nhánh ánh xạ đề xuất cho:

```text
CLAUDE_MAP 422 PDF_TOO_MANY_PAGES actual_pages_not_over_limit
```

**Counterexample:** Số trang hợp lệ nhưng lỗi xảy ra khi trích xuất. Client nhận nguyên nhân sai và được hướng xử lý sai.

**Recommendation:** Dùng ngoại lệ nhỏ, riêng cho vượt số trang; chỉ bắt ngoại lệ đó khi trả mã page limit. Lỗi chưa phân loại không được tự động biến thành lỗi đầu vào. Đặt kiểm tra sớm vẫn nên làm, nhưng không thay thế phân loại exception.

**Confidence:** High.

## Phản biện báo cáo Antigravity

### ADV-AG-001 — Ngân sách token chỉ đặt ở `/text`, bỏ ngỏ `/pdf`

**Issue ID:** ADV-AG-001  
**Target:** Antigravity  
**Severity:** High  
**Claim:** `docs/implementation/reviews/round1-antigravity.md:48`, `:87`: thêm `MAX_TEXT_TOKENS = 50_000` trong `compare_text` để phòng thủ DoS.

**Evidence:** Phương án không đặt kiểm tra tương ứng trước `diff_words` của `compare_document`. Mã hiện tại gọi trực tiếp engine tại `app/services/comparison_service.py:25`. Phần extractor đề xuất ở `round1-antigravity.md:93-102` cũng không có trần văn bản trích xuất.

**[CONFIRMED — E3]** Cặp 6.000 token lặp vẫn nằm dưới trần 50.000 nhưng mất **7,3105 giây**. Ngoài ra, mock extractor trả một trang có 500.001 ký tự, rồi gọi `compare_document` thật:

```text
PDF_OUTPUT_MOCK chars 500001 changes 0 needs_review False
```

Đây là kiểm chứng tầng service bằng mock, không phải PDF thật chứa lượng chữ đó.

**Counterexample:** Cùng nội dung đắt khi diff được đưa qua `/pdf` sẽ không đi qua `compare_text`. Đồng thời, trần 50.000 token mỗi phía vẫn cho phép cặp có tích 2,5 tỷ.

**Recommendation:** Dùng helper admission chung trước hai lời gọi diff; bổ sung trần văn bản trích xuất được công bố rõ. Trần token độc lập mỗi phía không nên được mô tả như đã giải quyết CPU DoS. Chính báo cáo ở `:336-337` cũng thừa nhận hạn chế này.

**Confidence:** High.

### ADV-AG-002 — Trần JSON 4 MiB không chứa được mọi request hợp lệ theo schema

**Issue ID:** ADV-AG-002  
**Target:** Antigravity  
**Severity:** Medium  
**Claim:** `round1-antigravity.md:52`: 4 MiB đủ cho hai chuỗi 500.000 ký tự tiếng Việt cộng JSON overhead.

**Evidence:** **[CONFIRMED — E1]** Đã chạy:

```python
json.dumps(
    {"old_text": "\u1ec7" * 500000, "new_text": "\u1ec7" * 500000},
    ensure_ascii=escaped,
).encode()
```

Kết quả:

```text
ensure_ascii=False → 3.000.032 byte
ensure_ascii=True  → 6.000.032 byte
AG_LIMIT           → 4.194.304 byte
```

**Counterexample:** Hai request giải mã thành cùng một payload đạt `max_length`, nhưng bản dùng escape Unicode bị từ chối 413. Đây không phải nội dung vượt giới hạn ký tự.

**Recommendation:** Đặt trần body theo kích thước JSON trên đường truyền, xét cả escape hợp lệ và overhead; hoặc công bố giới hạn byte là điều kiện độc lập. Không khẳng định 4 MiB bao phủ mọi input schema cho phép.

**Confidence:** High.

### ADV-AG-003 — `Path(...).name` không phải bộ lọc injection

**Issue ID:** ADV-AG-003  
**Target:** Antigravity  
**Severity:** Medium  
**Claim:** `round1-antigravity.md:104`, `:239-241`: `Path(filename.strip()).name` loại cả ký tự điều khiển và “ngăn chặn triệt để” path traversal/log/HTML injection.

**Evidence:** `app/services/document_service.py:7` chỉ phản hồi filename; không dùng nó để mở đường dẫn.

**[CONFIRMED — E1]** Đã chạy `Path(name.strip()).name`:

```text
'a\r\nb.pdf' → 'a\r\nb.pdf'
'a\x00b.pdf' → 'a\x00b.pdf'
```

`PurePosixPath(r"C:\temp\a.pdf").name` cũng giữ nguyên chuỗi đường dẫn Windows.

**Counterexample:** CR/LF trong tên không bị loại bỏ. Một tên chứa markup cũng không được HTML-escape bằng `Path.name`. Hành vi tách đường dẫn còn phụ thuộc nền tảng.

**Recommendation:** Giữ filename như metadata trong Phase A. Escape hoặc xử lý ký tự điều khiển tại nơi xuất HTML/log; nếu sau này lưu file, dùng tên lưu do server sinh. Nếu cần tên hiển thị đã chuẩn hóa, đặc tả riêng thay vì gọi `Path.name` là biện pháp chống injection toàn diện.

**Confidence:** High.

### ADV-AG-004 — Bắt rộng lỗi kỹ thuật thành “PDF không hợp lệ” che lỗi server

**Issue ID:** ADV-AG-004  
**Target:** Antigravity  
**Severity:** Medium  
**Claim:** `round1-antigravity.md:95`, `:97`: bắt cả `ValueError`, `TypeError`, `OSError` quanh mở/trích xuất PDF rồi chuyển thành `InvalidPDFError`.

**Evidence:** **[CONFIRMED — E4]** Fault injection tại `pdfplumber.open`, áp dụng tập exception đề xuất, cho:

```text
AG_BROAD_MAP TypeError 400 INVALID_OR_ENCRYPTED_PDF
AG_BROAD_MAP OSError   400 INVALID_OR_ENCRYPTED_PDF
```

**[CONFIRMED — E6]** Với stream có `read()` phát sinh `OSError`, extractor thật cho:

```text
OPEN_IO PdfminerException WRAPPED OSError
```

**Counterexample:** Storage lỗi hoặc lỗi lập trình trở thành 400 trách nhiệm của client. Việc chỉ bắt mọi `PdfminerException` trong phương án Codex cũng mắc cùng vấn đề khi lỗi hạ tầng đã bị wrapper.

**Recommendation:** Ánh xạ các lỗi chính sách bằng ngoại lệ hẹp. Với lỗi thư viện, phân loại nguyên nhân đã được chứng minh là lỗi PDF; không bắt rộng mọi lỗi cùng kiểu chỉ để tránh 500. Cho lỗi hạ tầng/lập trình đi theo luồng lỗi server.

**Confidence:** High.

### ADV-AG-005 — Mapping khoảng trắng không vi phạm hợp đồng giao span

**Issue ID:** ADV-AG-005  
**Target:** Antigravity  
**Severity:** Medium  
**Claim:** `round1-antigravity.md:115`, `:201-204`: location trên trang chỉ có whitespace và kết quả `[]` cho separator-only là bug; đề nghị lọc/cắt whitespace.

**Evidence:** `app/engines/text_mapping.py:25` tính giao hai khoảng nửa mở, không hứa chỉ trả vị trí token.

**[CONFIRMED — E1]** Với ba trang `"hello foo"`, `"   "`, `"bar world"`, so với `"hello world"`:

```text
old_text = 'foo\n\n   \n\nbar'
locations = [
  {page_number: 1, start: 6, end: 9},
  {page_number: 2, start: 0, end: 3},
  {page_number: 3, start: 0, end: 3}
]
separator-only [9,11) → []
```

**Counterexample:** Ba dấu cách thực sự thuộc fragment thay đổi và thuộc text trang 2. Bỏ location đó làm thay đổi ý nghĩa mapping. Separator tổng hợp không thuộc trang nào nên `[]` là đúng. Span separator-only cũng không được sinh bởi engine hiện tại vì biên span lấy từ token `\S+`.

**Recommendation:** Giữ phép giao span hiện tại. Chỉ sửa separator theo vị trí phần tử trong `build_document_text`. Nếu UI muốn bỏ highlight whitespace, xử lý tại tầng hiển thị hoặc thiết kế riêng mapping theo token.

**Confidence:** High.

### ADV-AG-006 — Thiết kế chưa thực hiện chính sách từ chối mọi PDF mã hóa

**Issue ID:** ADV-AG-006  
**Target:** Antigravity  
**Severity:** Medium  
**Claim:** `round1-antigravity.md:68`, `:259`, `:309` dự kiến mọi PDF mã hóa trả 400; nhưng các bước extractor tại `:93-102` không kiểm tra encryption dictionary.

**Evidence:** **[CONFIRMED — E2]** PDF mã hóa mở được bằng mật khẩu rỗng trả text `ABC`, không warning; `pdf.doc.encryption is not None` là `True`.

**Counterexample:** Không exception nào phát sinh để các nhánh `except` chuyển thành `InvalidPDFError`. Chính sách được mô tả và luồng thực thi đề xuất không khớp nhau.

**Recommendation:** Thêm kiểm tra encryption sau khi mở và trước đếm/trích xuất trang. Ca mật khẩu rỗng phải có test độc lập với ca mật khẩu khác rỗng.

**Confidence:** High.

### ADV-AG-007 — Dung sai Acrobat không phải yêu cầu ISO

**Issue ID:** ADV-AG-007  
**Target:** Antigravity  
**Severity:** Low  
**Claim:** `round1-antigravity.md:146`, `:345-346`: ISO 32000-1 cho phép `%PDF-` xuất hiện trong 1.024 byte đầu; dùng parser mở được làm bằng chứng chuẩn.

**Evidence:** ISO 32000-1 §7.5.2 quy định header ở dòng đầu. Quy tắc 1.024 byte được Adobe ghi trong phần ghi chú hành vi Acrobat. Hai nguồn mô tả hai điều khác nhau. [ISO 32000-1, §7.5.2](https://opensource.adobe.com/dc-acrobat-sdk-docs/pdfstandards/PDF32000_2008.pdf), [Adobe PDF Reference 1.7, Appendix H, note 13](https://opensource.adobe.com/dc-acrobat-sdk-docs/pdfstandards/pdfreference1.7old.pdf).

**[CONFIRMED — E2]** `extract_pdf(BytesIO(b"JUNK" + pdf_bytes))` trích được `ABC`. Kết quả này xác nhận parser khoan dung; không xác nhận tệp tuân chuẩn.

**Counterexample:** File có tiền tố `JUNK` được parser nhận nhưng không bắt đầu bằng header theo quy định trên.

**Recommendation:** Giữ `%PDF-` ở byte 0 như chính sách upload nghiêm của Phase A; ghi rõ nó từ chối một số file parser đọc được. Không gọi đây là biện pháp chống polyglot hoàn chỉnh.

**Confidence:** High.

### ADV-AG-008 — Chưa có bằng chứng 500 hiện tại trả stack trace cho client

**Issue ID:** ADV-AG-008  
**Target:** Antigravity  
**Severity:** Low  
**Claim:** `round1-antigravity.md:243-244`: “Information Disclosure qua 500 Stack Trace [CONFIRMED]”.

**Evidence:** `app/main.py:6` tạo `FastAPI` không bật debug.

**[CONFIRMED — E1]** Gọi API thật bằng `TestClient(..., raise_server_exceptions=False)` với PDF rác:

```text
REAL_500 500 'Internal Server Error'
```

**Counterexample:** Response HTTP được kiểm chứng không chứa stack trace. Exception hiện trên terminal hoặc được TestClient ném lại không chứng minh client HTTP nhận trace.

**Recommendation:** Sửa phân loại thành rủi ro giả định nếu bật debug hoặc trả `str(exc)`. Vẫn dùng detail cố định cho lỗi nghiệp vụ và không đưa nội dung hợp đồng vào thông báo lỗi.

**Confidence:** High.

## Self-correction

1. **Rút đề xuất thêm hai cờ equality vào `/pdf` trong Phase A.** `round1-codex.md:133-138` đã định nghĩa equality trên văn bản trích xuất, nên không sai về phép so sánh chuỗi. Tuy nhiên, Claude và Antigravity đúng về nguy cơ người dùng hiểu thành equality của tài liệu. Với mục tiêu tối thiểu, giữ schema `/pdf` hiện tại hợp lý hơn; `changes=[]` phải luôn được đọc cùng giới hạn trích xuất và `needs_review`.

2. **Đổi lựa chọn exception ở extractor.** Tôi rút đề xuất dùng `HTTPException` trong extractor tại `round1-codex.md:207`. Vài ngoại lệ hẹp cho invalid PDF, page limit và extracted-text limit có lý do rõ ràng; service ánh xạ chúng sang HTTP. Đây không cần trở thành một framework exception.

3. **Sửa cách bắt mọi `PdfminerException`.** E6 chứng minh wrapper có thể chứa `OSError`. Nhận định “bắt đúng wrapper là đủ để trả 400” của tôi chưa đầy đủ. Cần phân loại nguyên nhân; lỗi I/O không phải PDF không hợp lệ.

4. **Không chốt `MAX_DIFF_TOKEN_PRODUCT = 4_000_000`.** **[CONFIRMED — E3]** Cặp 3.000 token gần như duy nhất có tích 9.000.000 nhưng chỉ mất **0,0072 giây**, vẫn bị ngưỡng tôi đề xuất từ chối. Tôi giữ lập trường cần admission guard, nhưng con số Round 1 chưa đủ bằng chứng để nghiệm thu và có tác động tương thích lớn.

5. **Hoãn `CID_FONT_ERROR` khỏi tập thay đổi tối thiểu.** Probe Round 1 về `(cid:0)` vẫn là bằng chứng hữu ích, nhưng regex cũng khớp văn bản literal hợp lệ. Tôi không giữ warning mới này như yêu cầu bắt buộc của Phase A. Chấp nhận sửa điều kiện `EMPTY_TEXT` cho trang chỉ có NUL theo Antigravity, giữ nguyên text gốc.

6. **Giữ các lập trường về handler, limiter, đếm trang và PDF mã hóa.** E1, E2, E5 bảo vệ các cơ chế này. Giới hạn body chỉ chặn tổng request; đếm trang dừng sớm không bảo đảm toàn bộ parser có chi phí hữu hạn nhỏ.

7. **Giữ validator `str.strip()`.** **[CONFIRMED — E4]** ZWSP/BOM/NUL đều còn lại sau `strip()` và đều là token theo `\S+`; NBSP thì bị bỏ. Chính sách này nhất quán với tokenizer và yêu cầu whitespace hiện tại. Danh sách ký tự vô hình của Antigravity là chính sách bổ sung, không phải hệ quả bắt buộc của validation khoảng trắng.

8. **Giữ phản biện reconstruction.** **[CONFIRMED — E6]** Hai lời gọi:

   ```python
   compare_text("a b", "  x a b")
   compare_text("a b", "a x b  ")
   ```

   trả response service giống hệt nhau dù thứ tự token đích khác nhau. Không thể khôi phục duy nhất token đích từ `old_text + response` hiện tại. Kiểm tra lại opcodes có thể kiểm tra engine, nhưng không chứng minh response đủ để reconstruction.

## Lập trường cho 13 điểm bất đồng

1. **Body lỗi:** Chọn top-level `{"error_code","detail"}` cho lỗi nghiệp vụ; handler có điều kiện giữ nguyên 404/405 và 422 validation mặc định.
2. **Giới hạn body:** Chọn ASGI limiter đếm byte thực trước multipart, kèm kiểm tra từng stream tại service; proxy là lớp bổ sung.
3. **Magic PDF:** Chọn `%PDF-` ở byte 0; công bố việc từ chối file có tiền tố và không coi magic là bảo đảm an toàn.
4. **Mã hóa mật khẩu rỗng:** Từ chối theo chính sách hiện tại bằng kiểm tra encryption dictionary, dù parser mở được.
5. **Đếm trang:** Chọn `PDFPage.create_pages` kết hợp `islice(..., 101)` trước `pdf.pages`; không tin riêng `/Count`.
6. **Ngân sách diff/text:** Giữ 500.000 ký tự, bổ sung trần văn bản trích xuất và admission guard chung cho `/text`/`/pdf`; không chốt 4.000.000 hay 50.000 như ngưỡng đã được nghiệm thu.
7. **Equality `/pdf`:** Hoãn thêm `is_identical` và `is_token_identical` trong Phase A; giữ hai trường này cho `/text`.
8. **Whitespace validator:** Dùng `str.strip()` để kiểm tra và trả nguyên input; chưa thêm blacklist ZWSP/BOM/NUL vào validation.
9. **Filename:** Giữ metadata và fallback hiện có; không dùng `Path.name` như biện pháp chống path/log/HTML injection.
10. **PDF 0 trang:** Trả 400 `INVALID_OR_ENCRYPTED_PDF`; E2 xác nhận baseline hiện trả thành công với `needs_review=False`.
11. **Exception extractor:** Chọn ngoại lệ hẹp tại extractor, ánh xạ HTTP tại service; tránh `except ValueError` chung và tránh đổi lỗi hạ tầng thành 400.
12. **Health/schema/prefix:** Giữ `HealthResponse(status: Literal["ok"])`; đặt prefix `/health` ở router tổng theo quy ước repo, route con dùng `""`; không cần service chuyển tiếp.
13. **Warnings:** Sửa `EMPTY_TEXT` khi text chỉ có NUL bằng kiểm tra bản sao bỏ NUL; giữ text và `NULL_CHARACTER`; hoãn warning mới `CID_FONT_ERROR`.