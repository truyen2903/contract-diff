# Code Review — Codex

Đã review độc lập theo brief, đối chiếu D1–D22 và coding style profile; không sửa file.

Kiểm thử:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTEST_ADDOPTS='--capture=sys'
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Kết quả: **83 passed in 2.20s**. Capture mặc định không chạy được do môi trường không cho tạo file tạm.

Các đoạn Python tái hiện dưới đây chạy bằng here-string PowerShell qua `.venv\Scripts\python.exe -`, với `PYTHONDONTWRITEBYTECODE=1`.

---

**ID:** CR-CX-001 · **Severity:** High  
**File:line:** [app/engines/text_diff.py:22](/C:/Users/Admin/contract-diff/app/engines/text_diff.py:22), [app/core/config.py:3](/C:/Users/Admin/contract-diff/app/core/config.py:3)

**Vấn đề:** Đầu vào hợp lệ vẫn giữ request chạy quá 30 giây. `MAX_TEXT_CHARS` không giới hạn được chi phí của `SequenceMatcher(autojunk=False)` khi token lặp; fast path chỉ giúp khi hai danh sách token bằng nhau.

Đây là **rủi ro pre-existing đã được D13/D14 chấp nhận hoãn**, tương ứng R-CPU/R-TIMEOUT, không phải regression mới. Tuy nhiên, kiểm chứng thực tế xác nhận rủi ro High vẫn tồn tại.

**Bằng chứng — [CONFIRMED]:**

```python
from time import perf_counter
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import MAX_TEXT_CHARS

old = "a b " * 8500
new = "a c " + old[4:]
with TestClient(app) as client:
    start = perf_counter()
    r = client.post("/api/v1/comparisons/text",
                    json={"old_text": old, "new_text": new})
    elapsed = perf_counter() - start
    print(f"HTTP={r.status_code} chars_per_text={len(old)} "
          f"max_chars={MAX_TEXT_CHARS} elapsed={elapsed:.3f}s "
          f"changes={len(r.json()['changes'])}")
```

Output:

```text
HTTP=200 chars_per_text=34000 max_chars=500000 elapsed=34.046s changes=2
```

Test giới hạn độ dài tại `tests/test_comparisons_api.py:204` sử dụng một token dài, nên không kiểm tra dạng chi phí này.

**Đề xuất sửa:** Giữ R-CPU/R-TIMEOUT ở trạng thái chưa giải quyết. Nếu cần bảo đảm thời gian xử lý, chạy phép so sánh trong process có thể kết thúc khi quá hạn, kèm giới hạn tác vụ đồng thời. Không coi timeout chờ thread là hard timeout và không thay đổi `autojunk` âm thầm vì sẽ ảnh hưởng Baseline 1.

---

**ID:** CR-CX-002 · **Severity:** Medium  
**File:line:** [app/extractors/pdf_extractor.py:13](/C:/Users/Admin/contract-diff/app/extractors/pdf_extractor.py:13), [app/extractors/pdf_extractor.py:28](/C:/Users/Admin/contract-diff/app/extractors/pdf_extractor.py:28)

**Vấn đề:** PDF mã hóa thiếu khóa bắt buộc làm bước tiền kiểm ném `KeyError` chưa được ánh xạ. Cả `/documents/extract` và `/comparisons/pdf` trả 500 cho dữ liệu PDF hỏng, thay vì 400 `INVALID_OR_ENCRYPTED_PDF`.

Implementation theo đúng danh sách ngoại lệ D10, nhưng **danh sách đã chốt còn thiếu**. Bước `PDFDocument(...)` mới chạy trực tiếp bằng pdfminer, trước lớp bọc `PdfminerException` của pdfplumber.

**Bằng chứng — [CONFIRMED]:**

```python
from io import BytesIO
from fastapi.testclient import TestClient
from app.main import app
from app.extractors.pdf_extractor import extract_pdf
from tests.conftest import build_pdf

good = build_pdf(["x"])
bad = build_pdf(["x"], encryption="owner_only").replace(b"/O <", b"/Q <")
try:
    extract_pdf(BytesIO(bad))
except Exception as e:
    print(type(e).__name__, str(e))

with TestClient(app, raise_server_exceptions=False) as c:
    print("extract", c.post("/api/v1/documents/extract",
          files={"file": ("bad.pdf", bad)}).status_code)
    for field in ("old_file", "new_file"):
        files = {"old_file": ("old.pdf", good),
                 "new_file": ("new.pdf", good)}
        files[field] = ("bad.pdf", bad)
        print(field, c.post("/api/v1/comparisons/pdf",
                           files=files).status_code)
```

Output:

```text
KeyError 'O'
extract 500
old_file 500
new_file 500
```

Thay khóa `/U` hoặc `/P` cũng tái hiện `KeyError` và HTTP 500.

**Đề xuất sửa:** Bổ sung `KeyError` trong phạm vi bắt lỗi quanh lời gọi parser; cập nhật D10. Thêm regression test cho encryption dictionary thiếu `/O`, `/U`, `/P`, kiểm tra cả hai endpoint và body lỗi phẳng.

---

**ID:** CR-CX-003 · **Severity:** Medium  
**File:line:** [app/extractors/pdf_extractor.py:38](/C:/Users/Admin/contract-diff/app/extractors/pdf_extractor.py:38), [tests/test_comparison_service.py:128](/C:/Users/Admin/contract-diff/tests/test_comparison_service.py:128)

**Vấn đề:** `MemoryError` do pdfplumber bọc trong `PdfminerException` bị chuyển thành lỗi PDF hỏng. Việc chỉ loại trừ `OSError` không thực hiện đầy đủ yêu cầu D10 “không bắt `MemoryError`”.

Hệ quả là lỗi cạn tài nguyên phía server được trả thành 400 và gán trách nhiệm sai cho tài liệu của người dùng.

**Bằng chứng — [CONFIRMED, fault injection]:**

```python
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from tests.conftest import build_pdf

with TestClient(app, raise_server_exceptions=False) as c:
    for error in (MemoryError("ram"), OSError("disk")):
        with patch("pdfplumber.page.PDFPageInterpreter.process_page",
                   side_effect=error):
            r = c.post("/api/v1/documents/extract",
                       files={"file": ("good.pdf", build_pdf(["x"]))})
            print(type(error).__name__, r.status_code,
                  r.json().get("error_code") if r.status_code == 400
                  else r.text)
```

Output:

```text
MemoryError 400 INVALID_OR_ENCRYPTED_PDF
OSError 500 Internal Server Error
```

Test `test_extract_pdf_does_not_hide_io_errors` hiện gây lỗi ngay khi đọc stream ở bước tiền kiểm; nó chưa kiểm tra nhánh ngoại lệ được pdfplumber bọc trong quá trình trích xuất.

**Đề xuất sửa:** Kiểm tra ngoại lệ gốc trong `PdfminerException` và cho `MemoryError` truyền tiếp tương tự `OSError`. Thêm test gây lỗi tại `process_page`/`extract_text`, khóa riêng hành vi lỗi tài nguyên và lỗi PDF.

---

**ID:** CR-CX-004 · **Severity:** Medium  
**File:line:** [app/main.py:15](/C:/Users/Admin/contract-diff/app/main.py:15), [tests/test_comparisons_api.py:191](/C:/Users/Admin/contract-diff/tests/test_comparisons_api.py:191)

**Vấn đề:** JSON chứa lone surrogate như `"\ud800"` được Pydantic nhận diện là lỗi `string_unicode`, nhưng handler validation mặc định đưa giá trị lỗi vào response. Khi mã hóa response UTF-8, `UnicodeEncodeError` phát sinh và biến kết quả dự kiến 422 thành 500.

Đây là **pre-existing trong schema/handler mặc định**, không do handler `HTTPException` mới gây ra. Tuy nhiên, quyết định D4 giữ nguyên `RequestValidationError` để lại trường hợp lỗi cụ thể này.

**Bằng chứng — [CONFIRMED]:**

```python
import json
from fastapi.testclient import TestClient
from app.main import app

with TestClient(app, raise_server_exceptions=False) as c:
    r = c.post(
        "/api/v1/comparisons/text",
        content=json.dumps({"old_text": "a", "new_text": "\ud800"}).encode(),
        headers={"content-type": "application/json"},
    )
    print(r.status_code, r.text)
```

Output:

```text
500 Internal Server Error
```

Khi bật `raise_server_exceptions=True`, chuỗi lỗi quan sát được là:

```text
RequestValidationError: ... 'type': 'string_unicode' ...
UnicodeEncodeError: 'utf-8' codec can't encode character '\ud800' ...
```

Đã tái hiện cùng lỗi với schema trước Phase A và handler mặc định.

**Đề xuất sửa:** Điều chỉnh D4 để cho phép xử lý trường hợp validation chứa Unicode không hợp lệ: giữ status 422 và cấu trúc lỗi hiện hành, nhưng escape hoặc loại giá trị `input` không thể mã hóa. Thêm test gửi raw JSON có `\ud800`/`\udfff`; validator field thông thường không đủ vì Pydantic từ chối trước khi gọi validator.

---

**Kết luận: có còn Critical/High — còn 1 High đã được consensus ghi nhận; không phát hiện Critical.**