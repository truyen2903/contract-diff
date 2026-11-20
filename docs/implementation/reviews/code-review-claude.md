# Code Review — Claude

Phạm vi review: các thay đổi chưa commit trên `main` (`git diff -- app tests`, cùng các file mới `app/core/config.py`, `app/schemas/health.py`, `tests/conftest.py`, `tests/test_text_mapping.py` và phần `# ── Phase A` trong `tests/test_comparisons_api.py`). Chuẩn đối chiếu là `round3-consensus.md` (D1–D22) và `coding-style-profile.md`.

Chạy lại test: `PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider` → `83 passed in 2.09s`.

Nhìn chung code bám đúng các quyết định D1–D22: route vẫn mỏng, extractor không import FastAPI, `is_identical` và `is_token_identical` tách đúng, separator theo vị trí, có fast path và có `strip()` validator. Các finding dưới đây chủ yếu là lệch nhỏ so với D10 và style profile, cùng với các chỗ tài liệu chưa nhất quán.

---

**ID:** CR-CL-001 · **Severity:** Medium · **File:line** `app/extractors/pdf_extractor.py:35-41`
**Vấn đề:** Nhánh `except PdfminerException` chỉ re-raise khi `args[0]` là `OSError`, còn lại thì đổi hết thành `InvalidPDFError`. Trong khi đó `pdfplumber.PDF.__init__` (`pdf.py:49-52`) và vòng lặp trang (`pdf.py:160-161`) bọc **mọi** `Exception` vào `PdfminerException`, kể cả `MemoryError`, `RecursionError` và lỗi lập trình (`KeyError`, `NotImplementedError`…). Kết quả là hết RAM bị trả về 400 `INVALID_OR_ENCRYPTED_PDF`. Điều này trái với D10 ("Không bắt `OSError`/`MemoryError`") và làm tập bắt lỗi rộng hơn hẳn tập hẹp mà consensus đã chốt.
**Bằng chứng:** [CONFIRMED] Script `scratchpad/mem.py` thay `pdfplumber.pdf.PDFDocument` bằng hàm `raise MemoryError()`, rồi gọi `extract_document("a.pdf", BytesIO(build_pdf(["x"])))`. Traceback cho thấy chuỗi `MemoryError` → `PdfminerException` → `InvalidPDFError` → `fastapi.exceptions.HTTPException: 400: {'error_code': 'INVALID_OR_ENCRYPTED_PDF', ...}`.
**Đề xuất sửa:** Đổi từ blacklist sang whitelist, dùng cùng tập lỗi với `count_pdf_pages`:
```python
except PdfminerException as error:
    if error.args and isinstance(error.args[0], PDF_PARSE_ERRORS):
        raise InvalidPDFError(...) from error
    raise
```
Như vậy `OSError`, `MemoryError` và lỗi lạ đều ra 500. Chú thích cũng nên đổi thành "chỉ tháo wrapper khi lỗi gốc là lỗi dữ liệu PDF".

---

**ID:** CR-CL-002 · **Severity:** Medium · **File:line** `tests/test_comparison_service.py:127-133` (`test_extract_pdf_does_not_hide_io_errors`)
**Vấn đề:** Tên test tuyên bố khóa hành vi "không giấu lỗi I/O", nhưng `FailingStream.read` đã ném `OSError` ngay trong `count_pdf_pages` (từ `PDFParser`). `OSError` không nằm trong `PDF_PARSE_ERRORS` nên lan ra luôn, và `read_page_texts` không bao giờ được gọi. Nhánh `isinstance(error.args[0], OSError)` ở `pdf_extractor.py:38` là nhánh duy nhất thực sự cần test, nhưng hoàn toàn không được phủ.
**Bằng chứng:** [CONFIRMED] `scratchpad/br.py`:
```
OSError OSError read_page_texts reached: False
PdfminerException PdfminerException(OSError('disk2'))
```
Dòng 1 là test hiện tại: `read_page_texts` không được gọi. Dòng 2 là stream chỉ lỗi sau khi đếm trang xong: lúc này nhánh đó mới chạy.
**Đề xuất sửa:** Thêm một ca mà stream chỉ lỗi ở lần đọc thứ hai (sau `count_pdf_pages`), assert `pytest.raises(PdfminerException)` (hoặc assert "không phải `InvalidPDFError`"). Nếu sửa theo CR-CL-001 thì thêm ca `MemoryError` tương tự.

---

**ID:** CR-CL-003 · **Severity:** Medium · **File:line** `app/main.py:5` + `requirements.txt`
**Vấn đề:** Implementation thêm phụ thuộc trực tiếp vào `starlette.middleware.body_limit.RequestBodyLimitMiddleware`, một module mới của Starlette (bản đang cài là `1.8.0`). Nhưng `requirements.txt` không pin `starlette`, và `fastapi==0.143.3` chỉ đòi `starlette>=0.46.0`. Nếu môi trường cài một bản Starlette cũ hơn mà vẫn thỏa ràng buộc này, `import app.main` sẽ `ModuleNotFoundError`. Khi đó cả 4 endpoint chết, không riêng giới hạn body. D6 chọn "middleware có sẵn" vì maintainability, nên ràng buộc phiên bản phải đi kèm.
**Bằng chứng:** [CONFIRMED] Lệnh `python -c "import starlette, importlib.metadata as m; ..."` in ra `1.8.0 ['starlette>=0.46.0']`. Việc module này vắng mặt ở các bản 0.4x là [HYPOTHETICAL]: tôi không kiểm được offline.
**Đề xuất sửa:** Thêm `starlette==1.8.0` (hoặc cận dưới tối thiểu có `body_limit`) vào nhóm Runtime của `requirements.txt`, ghi chú lý do. `requirements.txt` là file của tác giả, nhưng phụ thuộc mới là do implementation đưa vào.

---

**ID:** CR-CL-004 · **Severity:** Low · **File:line** `app/services/document_service.py:37`
**Vấn đề:** Implementation sửa một dòng không cần sửa: thêm 3 dấu cách thừa ở cuối dòng `"pages":pages`. Điều này vi phạm quy tắc §9.4 "Chỉ sửa dòng cần sửa; không reformat code cũ", làm diff nhiễu và tạo trailing whitespace mới.
**Bằng chứng:** [CONFIRMED] `git diff app/services/document_service.py | cat -A`:
```
-    "pages":pages$
+    "pages":pages   $
```
**Đề xuất sửa:** Hoàn nguyên dòng 37 về đúng nguyên bản.

---

**ID:** CR-CL-005 · **Severity:** Low · **File:line** `app/services/document_service.py:8-12`, `app/services/comparison_service.py:3,17-19`
**Vấn đề:** Helper hạ tầng `http_error` nằm trong `document_service` rồi được `comparison_service` import chéo. Như vậy một service phụ thuộc vào chi tiết tiện ích của service khác, không phải vào nghiệp vụ của nó. Package `app/core/` vừa được tạo ra đúng cho loại dùng chung này. Ngoài ra `check_text_length` là hàm module-level thứ hai mang tính "guard" nằm rải ở service khác, nên các kiểm tra đầu vào bị chia ra hai file.
**Bằng chứng:** [CONFIRMED] `comparison_service.py:3`: `from app.services.document_service import extract_document, http_error, validate_pdf_stream`.
**Đề xuất sửa:** Chuyển `http_error` sang `app/core/errors.py`, hoặc giữ nguyên nhưng ghi nhận là chủ đích. Đây là thay đổi tối thiểu nên không bắt buộc. Nếu giữ thì nên có ít nhất một dòng trong báo cáo cuối.

---

**ID:** CR-CL-006 · **Severity:** Low · **File:line** `app/extractors/pdf_extractor.py:7,44` + `app/services/document_service.py:5,28`
**Vấn đề:** Giới hạn số trang có hai nguồn sự thật. `extract_pdf(file_stream, max_pages=MAX_PDF_PAGES)` có default lấy từ config, khiến extractor phụ thuộc `app.core.config`, trong khi service vẫn truyền tường minh `MAX_PDF_PAGES`. Test monkeypatch `document_service.MAX_PDF_PAGES`, nên default ở extractor là code chết đối với đường API, chỉ phục vụ test gọi trực tiếp. Người đọc sẽ không biết chỉnh ở đâu mới có hiệu lực.
**Bằng chứng:** [CONFIRMED] `test_extract_document_maps_page_limit` và `test_page_limit` chỉ patch `document_service.MAX_PDF_PAGES`. Còn `test_extract_pdf_*` dựa vào default hoặc tham số `max_pages=3`.
**Đề xuất sửa:** Hoặc bỏ default (`max_pages` bắt buộc) và bỏ import config khỏi extractor, giữ extractor là lớp bọc thư viện thuần đúng profile §1. Hoặc bỏ đối số tường minh ở service. Chọn một trong hai.

---

**ID:** CR-CL-007 · **Severity:** Low · **File:line** `app/services/comparison_service.py:22-27`, `app/services/document_service.py:26`, `app/extractors/pdf_extractor.py:45`
**Vấn đề:** Với `/pdf`, mỗi stream bị `validate_pdf_stream` hai lần (ở `compare_document` và lại ở `extract_document`), và `seek(0)` bốn lần trước khi parse. D16 đúng là yêu cầu cả hai chỗ, nhưng code không thể hiện quan hệ này. Ai đọc `compare_document` sẽ nghĩ dòng 23-24 thừa và xóa đi, làm mất tính chất "kiểm cả hai tệp trước khi trích xuất". Test `test_compare_document_checks_both_files_before_extracting` có bảo vệ điều này, nhưng chú thích hiện tại ("Kiểm tra rẻ…") không nói lý do phải lặp.
**Bằng chứng:** [CONFIRMED] Đọc code: `compare_document` → `validate_pdf_stream` ×2 → `extract_document` → `validate_pdf_stream` (lần 2) → `extract_pdf` → `seek(0)`.
**Đề xuất sửa:** Không cần đổi cấu trúc. Chỉ cần sửa chú thích dòng 22 thành ví dụ: "Kiểm cả hai tệp trước khi parse tệp nào; extract_document kiểm lại vì /extract dùng riêng." Như vậy là đủ để không ai "dọn" nhầm.

---

**ID:** CR-CL-008 · **Severity:** Low · **File:line** `app/extractors/pdf_extractor.py:28,39,41`
**Vấn đề:** Chuỗi `"Tệp PDF hỏng hoặc cần mật khẩu"` bị lặp 3 lần, ba khối `raise InvalidPDFError(...) from error` gần như giống hệt nhau. Sửa thông báo sau này dễ sót chỗ.
**Bằng chứng:** [CONFIRMED] `grep -n "hỏng hoặc cần mật khẩu" app/extractors/pdf_extractor.py` → dòng 28, 39, 41.
**Đề xuất sửa:** Dùng một hằng `INVALID_PDF_MESSAGE` cạnh `PDF_PARSE_ERRORS`. Nếu áp CR-CL-001 thì hai nhánh `except` trong `read_page_texts` có thể gộp còn một.

---

**ID:** CR-CL-009 · **Severity:** Low · **File:line** `app/schemas/comparison.py:1-3`, `app/services/comparison_service.py:1-4`
**Vấn đề:** Import trong code mới không theo quy ước profile §4 ("ngoài → dòng trống → `app.*`"). Ở `comparison.py`, dòng `from app.core.config` mới thêm đứng sát `pydantic`, không có dòng trống. Ở `comparison_service.py`, `app.core` được chèn lên đầu, làm thứ tự thành core → engines → services → engines (dòng `text_mapping` là của tác giả).
**Bằng chứng:** [CONFIRMED] Diff dòng `+from app.core.config import MAX_TEXT_CHARS` ngay sau `from pydantic import ...`.
**Đề xuất sửa:** Thêm một dòng trống sau import `pydantic` ở `comparison.py`. Không reorder các dòng cũ của tác giả.

---

**ID:** CR-CL-010 · **Severity:** Low · **File:line** `README.md` (0 byte), `docs/ke-hoach-trien-khai-do-an-v2.md:204-209`
**Vấn đề:** Nhất quán tài liệu.
- (a) D6 yêu cầu "ghi tài liệu" rằng 413 ở tầng transport không có `error_code`. Profile §9 cũng yêu cầu "Ngoại lệ có chủ đích được ghi rõ trong báo cáo cuối". Hiện điều này chỉ xuất hiện trong các file review; README rỗng và không có báo cáo implementation.
- (b) Cùng ngưỡng `MAX_TEXT_CHARS`, nhưng `/text` trả 422 theo dạng Pydantic (`detail[0].type == "string_too_long"`, không có `error_code`), còn `/pdf` trả `{"error_code":"TEXT_TOO_LONG"}`. Trong khi đó v2 dòng 205 hứa "422 kèm mã lỗi tường minh". Chuỗi khoảng trắng ở `/text` cũng là 422 dạng Pydantic. Mục §3 "Sửa tài liệu v2" của consensus không liệt kê điểm này.
- (c) v2 ghi "15 MB", code dùng MiB (`15 * 1024 * 1024`).

**Bằng chứng:** [CONFIRMED] `wc -c README.md` → `0`. `test_text_comparison_length_limit` khóa `too_long.json()["detail"][0]["type"] == "string_too_long"`. `grep "Content Too Large" docs` chỉ trúng các file trong `reviews/` và `coding-style-profile.md`.
**Đề xuất sửa:** Thêm một mục ngắn "Hợp đồng lỗi API" vào README hoặc báo cáo Phase A, liệt kê 4 mã nghiệp vụ, 2 ngoại lệ có chủ đích (413 transport; 422 validation của `/text` theo dạng Pydantic) và 2 rủi ro mở (R-CPU, R-TIMEOUT). Bổ sung (b) và (c) vào danh sách sửa v2 §3.2.

---

**ID:** CR-CL-011 · **Severity:** Low · **File:line** `tests/test_comparisons_api.py:202,262,273,286`, `tests/test_comparison_service.py:101,118`
**Vấn đề:** Test mới import bên trong thân hàm (`from app.core.config import MAX_TEXT_CHARS`, `from app.services import document_service`, `import pdfplumber.page`), lệch với profile §8 (import và hằng ở đầu file). `test_comparison_service.py` thì lại import ở đầu, nên hai file không thống nhất với nhau. Ngoài ra có cặp test trùng ý giữa tầng service và tầng API (`test_compare_document_blank_pages_need_review` ↔ `test_blank_pdf_pages_need_review`, `test_extract_document_maps_page_limit` ↔ `test_page_limit`), làm tăng chi phí bảo trì mà không thêm bằng chứng mới.
**Bằng chứng:** [CONFIRMED] Đọc file. Các cặp test assert cùng `changes == []` / `needs_review is True` và cùng `PDF_TOO_MANY_PAGES`.
**Đề xuất sửa:** Đưa import lên đầu file. Ở tầng API chỉ giữ phần riêng của API (định dạng body phẳng, `warnings`); bỏ assert lặp lại logic service.

---

Ghi nhận (không phải lỗi): tôi đã kiểm chú thích `comparison.py:30` ("`strip()` dùng cùng định nghĩa khoảng trắng với tokenizer `\S+`") và nó **đúng**. Kiểm trên toàn bộ codepoint, `str.isspace()` và `re.fullmatch(r"\s", c)` không lệch nhau ở điểm nào (`diffs: []`).

Pre-existing (của tác giả, ngoài phạm vi): `tests/test_comparison_api.py` rỗng nhưng vẫn được git theo dõi, cạnh `tests/test_comparisons_api.py`. Hai tên gần trùng dễ gây nhầm; nên xóa hoặc gộp.

Kết luận: không còn Critical/High mới trong code Phase A. Nặng nhất là CR-CL-001 (lỗi `MemoryError` hoặc lỗi lạ bị trả nhầm thành 400, trái D10) và CR-CL-002 (test I/O không phủ nhánh nó tuyên bố), cả hai ở mức Medium. Hai rủi ro High đã biết từ consensus (R-CPU, R-TIMEOUT) vẫn đang mở và bị chặn, không thay đổi.
