# Round 2 — Cross-Examination (tổng hợp)

Tệp này ghép **nguyên văn** ba báo cáo Round 2 độc lập. Mỗi agent tự đánh số Issue ID theo **đích bị phản biện**, nên ID có thể trùng giữa các phần; khi trích dẫn ở Round 3 dùng tiền tố tác giả:
`CX/…` = do Codex viết, `CL/…` = do Claude viết, `AG/…` = do Antigravity viết (ví dụ `AG/ADV-CX-002` = Antigravity phản biện Codex, mục 002).

Nguồn: `round2-codex.md` (codex-cli 0.169.0, `-s read-only`), `round2-claude.md` (Claude Code subagent, tiếp nối phiên Round 1), `round2-antigravity.md` (agy 1.5.11, Gemini 4 Neon, `--mode plan --sandbox`; `git status` trước/sau giống nhau).

---

# PHẦN CX — tác giả: Codex


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
---

# PHẦN CL — tác giả: Claude


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

---

# PHẦN AG — tác giả: Antigravity


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
