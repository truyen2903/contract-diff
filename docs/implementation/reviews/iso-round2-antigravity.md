# Isolation Round 2 — Antigravity

> Phản biện chéo hai báo cáo Round 1 ([iso-round1-codex.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/iso-round1-codex.md), [iso-round1-claude.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/iso-round1-claude.md)) và tự phản biện ([iso-round1-antigravity.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/iso-round1-antigravity.md)). Chỉ đọc trong repo; 2 thực nghiệm bổ sung chạy ngoài repo với watchdog `faulthandler` 15 s trên Windows 11 / Python 3.14.3, `ACTIVE_CHILDREN: 0`.

---

## 1. Phản biện theo mức độ nghiêm trọng

### **Issue ID:** ISO-CL-001
- **Target:** Claude ([iso-round1-claude.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/iso-round1-claude.md#L82-L106))
- **Severity:** High
- **Claim:** `worker_session()` gọi `connection.send((function, args))` ngay sau `process.start()` mà không có `"ready"` handshake hay deadline bảo vệ; `finally` gọi `process.join()` không có timeout.
- **Evidence:** `[CONFIRMED]` Chạy kịch bản mô phỏng đúng mẫu Claude (`verify_r2.py`, watchdog 15 s, worker trễ 2,5 s trước `recv()`, parent `timeout=1.0s`, gửi 2 MiB qua `Pipe`):
  ```text
  .venv\Scripts\python.exe -B <scratch>\verify_r2.py
  TEST1_STALLED_SEND: timeout=1.0s send_elapsed=2.77s polled=False
  ACTIVE_CHILDREN: 0
  ```
  Trên Windows Named Pipe, `send()` payload lớn hơn buffer ống chặn đồng bộ cho tới khi con đọc, xuyên thủng hoàn toàn mốc `deadline` (2,77 s > 1,0 s). Chính Claude ghi nhận lỗ hở này ở §5.1 & §9.5.
- **Counterexample:** Dưới tải cao/Windows Defender quét khi spawn hoặc worker treo ở pha khởi động, một PDF 15 MiB làm `connection.send()` chặn luồng AnyIO vượt quá 30 s (thậm chí treo vô hạn) và không bao giờ tới được `poll(deadline)`. Tương tự, `process.join()` không timeout trong `finally` có thể khóa slot vô hạn nếu OS trì hoãn giải phóng handle.
- **Recommendation:** Bắt buộc chờ `"ready"` bằng `poll(startup_timeout)` hoặc bọc toàn bộ `send()+poll()+recv()` bằng `threading.Timer(remaining, process.kill)`; truyền đường dẫn tệp tạm (~80 B) thay vì 15 MiB bytes cho PDF; luôn dùng `process.join(timeout=3.0)`.
- **Confidence:** High.

### **Issue ID:** ISO-CX-001
- **Target:** Codex ([iso-round1-codex.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/iso-round1-codex.md#L117-L124), §5 dòng 308)
- **Severity:** High
- **Claim:** Đặt ASGI admission gate chiếm 1 trong **2 slot duy nhất** (`MAX_PROCESSING_WORKERS = 2, MAX_PENDING_REQUESTS = 0`) *trước* khi FastAPI đọc/parse request body.
- **Evidence:** `[CONFIRMED]` Từ luồng gọi Codex §3.1/§3.4 (`Admission gate → FastAPI validation → ... → spawn worker`) và chính thừa nhận của Codex ở §5 dòng 308 (*"Hai client upload rất chậm: Có thể chiếm cả hai slot"*). Đồng thời `deadline = monotonic() + 30` chỉ bắt đầu ở `Process.start()` (§3.3), tức **chưa chạy** trong suốt pha nhận body.
- **Counterexample:** Tấn công Slowloris cực rẻ: chỉ cần **2 kết nối TCP** gửi header `POST /api/v1/comparisons/pdf` với `Transfer-Encoding: chunked` rồi nhỏ giọt 1 byte mỗi 10 s. Cả 2/2 slot bị chiếm vô thời hạn mà chưa spawn worker nào và không bao giờ dính timeout 30 s; toàn bộ `/text`, `/extract`, `/pdf` hợp lệ bị từ chối với `503`. Ngoài ra request 422 lỗi JSON/thiếu file cũng chiếm slot trong lúc đọc body.
- **Recommendation:** Chỉ chiếm processing slot tại biên giới thực thi worker (sau khi FastAPI đã nhận xong body và qua validation rẻ); việc chống body lớn giữ nguyên ở `RequestBodyLimitMiddleware` ([main.py](file:///C:/Users/Admin/contract-diff/app/main.py#L15)).
- **Confidence:** High.

### **Issue ID:** ISO-CX-002
- **Target:** Codex ([iso-round1-codex.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/iso-round1-codex.md#L48-L69), §4 dòng 269–275)
- **Severity:** High
- **Claim:** Cô lập toàn bộ service (`compare_text`, `extract_document`, `compare_document`) trong worker `spawn` mới cho mỗi request.
- **Evidence:** `[CONFIRMED]` Số đo của chính Codex (§4 dòng 269–275): spawn + import `comparison_service` mất **1.161–1.261 ms (~1,2 s)** và 52 MiB WorkingSet cho **mỗi request**, do [document_service.py](file:///C:/Users/Admin/contract-diff/app/services/document_service.py#L3) có `from fastapi import HTTPException` kéo theo toàn bộ FastAPI/Starlette/Pydantic (+0,584 s `[CONFIRMED]` bởi Claude §3.1). Đối chiếu [ke-hoach-trien-khai-do-an-v2.md](file:///C:/Users/Admin/contract-diff/docs/ke-hoach-trien-khai-do-an-v2.md#L75): giả thuyết **H3b** đặt mục tiêu E2E **< 3,0 s (warm-run)** cho cặp PDF 20 trang; trong khi worker ấm của AG chạy `diff_words` chỉ **0,33 ms** và `extract_pdf` **88,3 ms** (`[CONFIRMED]` AG §4).
- **Counterexample:** (1) `POST /api/v1/comparisons/text` hai chuỗi ngắn chậm từ < 5 ms lên ~1.250 ms (**250×**); (2) Cặp PDF 20 trang mất ~42% ngân sách 3,0 s của H3b ngay trước khi mở PDF (chưa tính các tầng TF-IDF/Hungarian của Phase B–E sau này); (3) 92 test hiện có + acceptance test phình lên ~30–40 s.
- **Recommendation:** Đặt ranh giới worker quanh `extract_pdf` và `diff_words` (không import FastAPI trong worker), ưu tiên worker ấm để bảo toàn ngưỡng H3b.
- **Confidence:** High.

### **Issue ID:** ISO-CL-002
- **Target:** Claude ([iso-round1-claude.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/iso-round1-claude.md#L139-L145))
- **Severity:** High
- **Claim:** Trả **HTTP 422 `PROCESSING_TIMEOUT`** khi hết 30 s (coi là lỗi input, "retry vô ích"), và trả **500 mặc định** (`text/plain Internal Server Error`, không `error_code`) khi `WorkerCrashedError`.
- **Evidence:** `[CONFIRMED]` Theo RFC 9110 §15.5.21, 422 là lỗi client (ngữ nghĩa đầu vào sai), còn [phase-a-report.md](file:///C:/Users/Admin/contract-diff/docs/implementation/phase-a-report.md#L14-L28) chuẩn hóa body JSON phẳng `{"error_code", "detail"}` cho mọi lỗi nghiệp vụ/hệ thống có mã. Chính Claude thừa nhận ở §5.8 & §9.2 rằng khi máy quá tải, tài liệu hợp lệ vẫn bị dính 422; và thời gian spawn Windows (biến động theo tải CPU/AV) nằm trong ngân sách 30 s.
- **Counterexample:** 4 người dùng gửi đồng thời 4 hợp đồng 20 trang hoàn toàn hợp lệ khiến CPU tranh chấp → 1 request chạm 30 s và nhận **422** (đổ lỗi sai cho file hợp lệ, đồng thời che giấu sự cố quá tải/DoS R-LOOP khỏi hệ thống giám sát 5xx). Khi worker chết do OOM, client nhận `text/plain` 500 làm hỏng parser JSON phía gọi API.
- **Recommendation:** Dùng **504 `PROCESSING_TIMEOUT`** (5xx đúng bản chất vượt ngân sách thực thi server) và **500 `PROCESSING_FAILED`** (JSON phẳng D4) cho `WorkerCrashedError`.
- **Confidence:** High.

### **Issue ID:** ISO-CL-003
- **Target:** Claude ([iso-round1-claude.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/iso-round1-claude.md#L124-L126))
- **Severity:** High
- **Claim:** Đọc toàn bộ PDF vào RAM (`file_stream.read()`) và gửi `bytes` qua `Pipe`, ước lượng đỉnh RAM thêm `2 × 15 MiB` ở parent và `15 MiB` ở child (`[HYPOTHETICAL]`).
- **Evidence:** `[CONFIRMED]` Đo thực tế trên Windows 11 / Python 3.14.3 bằng `GetProcessMemoryInfo` (`verify_mem_r2.py`, stream 15 MiB trên đĩa mô phỏng `SpooledTemporaryFile`):
  ```text
  .venv\Scripts\python.exe -B <scratch>\verify_mem_r2.py
  TEMPFILE_15MiB:   parent_ws=18.4->20.6 peak=21.2 MiB | child_ws=20.2 peak=21.9 MiB
  PIPE_BYTES_15MiB: parent_ws=20.6->35.3 peak=65.3 MiB | child_ws=35.1 peak=50.1 MiB
  ACTIVE_CHILDREN: 0
  ```
  `PIPE_BYTES_15MiB` làm parent tăng đỉnh **+44,7 MiB (3× kích thước tệp)** và child tăng **+30 MiB (2× kích thước tệp)** — tổng **~75 MiB** riêng cho IPC của **1 tệp**, gấp **25×** so với `TEMPFILE_15MiB` (~+3 MiB).
- **Counterexample:** 4 request `/pdf` đồng thời với tệp 15 MiB đẩy riêng tiến trình API parent vọt thêm **~180 MiB** và tổng 5 tiến trình vọt **~300 MiB** ngay ở lớp IPC trước khi `pdfminer` dựng đối tượng trang.
- **Recommendation:** Với PDF, copy luồng 64 KiB ra tệp tạm (`+4,8 ms` so với Pipe theo AG §4) và gửi đường dẫn qua Pipe; chỉ gửi trực tiếp qua Pipe đối với chuỗi text/metadata nhỏ.
- **Confidence:** High.

### **Issue ID:** ISO-CX-003
- **Target:** Codex ([iso-round1-codex.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/iso-round1-codex.md#L97-L113))
- **Severity:** Medium
- **Claim:** Khi hết hạn gọi `terminate()` → `join(1)` → `kill()` → `join(1)`; nếu chưa xác nhận thoát thì **đánh dấu slot không dùng được** (với chỉ 2 slot tổng).
- **Evidence:** `[CONFIRMED]` Trên Windows `terminate()` và `kill()` đều gọi `TerminateProcess` (Codex xác nhận dòng 102), nên chu kỳ `terminate()+join(1)+kill()+join(1)` là dư thừa. Khi AV/kernel Windows trì hoãn thu hồi handle tiến trình > 1–2 s (vd. sau PDF bomb tốn RAM), `is_alive()` còn `True` khiến slot bị vô hiệu hóa vĩnh viễn cho tới khi restart server.
- **Counterexample:** Chỉ cần 2 lần trì hoãn `TerminateProcess` > 2 s trong thời gian vận hành, toàn bộ 2/2 slot bị khóa chết và server trả `503` vĩnh viễn dù không còn tải nào.
- **Recommendation:** Gọi thẳng `kill()` rồi `join(3.0)` trên Windows; nếu vẫn chưa reap xong thì đưa handle vào danh sách reap nền để tự thu hồi slot khi tiến trình kết thúc, không khóa chết vĩnh viễn; dùng `MAX_WORKERS = 4`.
- **Confidence:** High.

### **Issue ID:** ISO-AG-001
- **Target:** Antigravity — tự phản biện ([iso-round1-antigravity.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/iso-round1-antigravity.md#L66-L74), §9.4)
- **Severity:** Medium
- **Claim:** Mượn slot theo **từng bước** (`extract(old)`, `extract(new)`, `diff_words`) trong `compare_document` và dùng hàng đợi `MAX_PENDING_REQUESTS = 8`.
- **Evidence:** `[CONFIRMED]` Theo luồng [comparison_service.py](file:///C:/Users/Admin/contract-diff/app/services/comparison_service.py#L27-L38) + AG §3.2: một request `/pdf` đi qua `BoundedSemaphore` và hàng đợi `slots.get()` 3 lần độc lập.
- **Counterexample:** Dưới tải bão hòa, request A đã extract xong 2 PDF (tốn 10 s), nhả slot, rồi bị từ chối `503` hoặc xếp cuối hàng đợi 8 request và dính `504` ngay trước bước `diff_words` (chỉ cần 0,3 ms). Đồng thời hàng đợi 8 giữ tới 8 thread AnyIO + 8×31 MiB body đang chờ.
- **Recommendation:** Đổi sang `with pool.session(deadline) as run:` mượn **1 worker ấm cố định cho cả request `/pdf`** (tiếp thu ý tưởng session của Claude) và hạ hàng đợi chờ về **0** (hoặc rất nhỏ).
- **Confidence:** High.

### **Issue ID:** ISO-CX-004
- **Target:** Codex ([iso-round1-codex.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/iso-round1-codex.md#L54-L66), §6 dòng 321–323)
- **Severity:** Medium
- **Claim:** Tạo 3 wrapper riêng (`*_isolated`) ở route, để service gốc không cô lập và truyền mọi giới hạn override (`max_pages`, `max_upload_bytes`, ...) từ parent vào worker.
- **Evidence:** `[CONFIRMED]` [test_comparisons_api.py](file:///C:/Users/Admin/contract-diff/tests/test_comparisons_api.py#L273-L291) monkeypatch `document_service.MAX_UPLOAD_FILE_BYTES` và `MAX_PDF_PAGES`; [test_comparison_service.py](file:///C:/Users/Admin/contract-diff/tests/test_comparison_service.py#L221-L246) monkeypatch `comparison_service.extract_document` và `MAX_TEXT_CHARS`. Tách 2 bộ hàm service tạo nguy cơ phân kỳ API nội bộ và làm phình chữ ký hàm service bởi các tham số override chỉ phục vụ test.
- **Counterexample:** Bất kỳ lời gọi trực tiếp nào tới `compare_document()` (trong test/script/route mới) đều không được cô lập; bất kỳ test API nào monkeypatch `MAX_TEXT_CHARS` sẽ fail nếu quên thêm override vào payload worker.
- **Recommendation:** Giữ ranh giới cô lập quanh `extract_pdf` và `diff_words` bên trong service hiện có; `validate_pdf_stream` và `check_text_length` chạy tại parent nên tự động thấy mọi monkeypatch, chỉ cần truyền duy nhất `max_pages`.
- **Confidence:** High.

### **Issue ID:** ISO-CX-005
- **Target:** Codex & Claude ([iso-round1-codex.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/iso-round1-codex.md#L106), [iso-round1-claude.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/iso-round1-claude.md#L134), §4.2)
- **Severity:** Medium
- **Claim:** Chỉ dùng `faulthandler.dump_traceback_later(timeout + 5, exit=True)` trong worker để chống orphan khi API chết đột ngột, bỏ qua Windows Job Object.
- **Evidence:** `[CONFIRMED]` Trong `exp2.py` của Claude (§4.2): sau khi parent chết (`os._exit(0)`), worker R-LOOP vẫn chạy 100% CPU ở `t~3s` và chỉ chết sau `~9s` (tương ứng **35 giây** ở production với `timeout=30s`). Trong khi đó `proto_windows_edge.py` của AG (§4) chứng minh Job Object (`KILL_ON_JOB_CLOSE`) chấm dứt worker **tức thì** (`still_alive=False`) ngay khi parent chết.
- **Counterexample:** Server bị crash/restart khi 4 worker đang chạy R-LOOP → 4 worker mồ côi tiếp tục đốt 4 lõi CPU suốt 35 s chồng lên tiến trình server vừa khởi động lại. Ngoài ra, nếu worker treo trong pha `spawn` *trước* khi vào hàm kích hoạt `faulthandler`, watchdog không chạy.
- **Recommendation:** Kết hợp **cả hai**: Windows Job Object (~25 dòng `ctypes`, khai báo đủ `argtypes`/`restype`, fallback log cảnh báo nếu OS từ chối) để diệt orphan tức thì trên Windows + `faulthandler` watchdog làm lưới an toàn đa nền tảng.
- **Confidence:** High.

### **Issue ID:** ISO-CX-006
- **Target:** Codex ([iso-round1-codex.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/iso-round1-codex.md#L79-L89), §9.4)
- **Severity:** Medium
- **Claim:** Ghi cả request `/text` lẫn `result.part` → `os.replace()` → `result.json` trên đĩa để tránh Pipe deadlock; parent đọc/parse `result.json` sau khi worker đã thoát.
- **Evidence:** `[CONFIRMED]` AG §4 (`proto_pipe_large.py`) và Claude §4.1 chứng minh Pipe **không deadlock** nếu đọc trước `join` (2M ký tự trong 0,49 s; 5.000 changes OK). Ngược lại, ghi/rename/xóa tệp cho mọi request `/text` tăng rủi ro `WinError 5/32` với Windows Defender, và bước `json.load(result.json)` ở parent nằm ngoài hard timeout 30 s (Codex thừa nhận §9.4).
- **Counterexample:** `/extract` trên PDF 100 trang nhiều chữ (không có trần `MAX_TEXT_CHARS` theo D13) tạo `result.json` lớn; worker thoát lúc `t=29,5s`, parent vẫn mất thêm thời gian và nhân đôi RAM để `json.loads()` ngoài biên deadline.
- **Recommendation:** Chỉ dùng tệp tạm cho **input PDF**; trả kết quả qua Pipe (đọc trước `join`) kèm `threading.Timer(remaining, proc.kill)` bọc quanh `send+poll+recv` để đóng nốt khoảng hở `recv()` trên payload lớn.
- **Confidence:** High.

### **Issue ID:** ISO-CL-004
- **Target:** Claude ([iso-round1-claude.md](file:///C:/Users/Admin/contract-diff/docs/implementation/reviews/iso-round1-claude.md#L54), §4.4 dòng 209–214)
- **Severity:** Low
- **Claim:** Sửa `compare_document` gọi `read_document` khiến phải sửa 1 test cũ (`test_compare_document_checks_both_files_before_extracting`), và không có fast-path cho `compare_text(s, s)` trước khi mở session.
- **Evidence:** `[CONFIRMED]` Claude §4.4 báo `AttributeError` nếu giữ nguyên [test_comparison_service.py](file:///C:/Users/Admin/contract-diff/tests/test_comparison_service.py#L221-L234), và chính Claude thừa nhận ở §6 dòng 265 có thể tránh bằng `extract_document(..., run=None)`. Ngoài ra `compare_text("a", "a")` vẫn tốn ~0,5 s spawn chỉ để trả `[]`.
- **Counterexample:** Thay đổi không cần thiết trên test hồi quy và phạt ~500 ms cho mọi cặp text giống hệt nhau.
- **Recommendation:** Giữ `extract_document(filename, file_stream, *, _run=None)` (**0 test cũ phải sửa**) và đặt fast-path `if old_text == new_text` ở parent trước khi mượn worker.
- **Confidence:** High.

---

## 2. Self-correction (Tự sửa phương án Antigravity Round 1)

1. **Bỏ mượn slot 3 lần cho `/pdf` (`ISO-AG-001`):** Tiếp thu mô hình session của Claude — dùng `with worker_pool.session(deadline) as run:` giữ **1 worker ấm cho cả request `/pdf`**, truyền `_run=run` vào `extract_document` (mặc định `_run=None` tự mở session riêng) để giữ **0 test cũ phải sửa** và xóa sạch rủi ro `503`/`504` giữa chừng.
2. **Hạ `MAX_PENDING_REQUESTS` từ `8` về `0`:** Đồng thuận với Codex/Claude về hàng đợi = 0 để không giữ thread/body khi chờ và không làm nhiễu mốc 30 s bởi thời gian xếp hàng; giữ `MAX_WORKERS = 4`.
3. **Bịt 2 khoảng hở hard-timeout & phòng thủ orphan đa nền tảng:** (a) Thêm `threading.Timer(remaining, slot.force_kill)` bọc quanh `send()+poll()+recv()` để đóng hẳn khoảng hở `send()` chặn và `recv()` treo trên message lớn; (b) Bổ sung `faulthandler.dump_traceback_later(task_timeout + 5, exit=True)` (hủy ngay sau mỗi task bằng `cancel_dump_traceback_later()`) **song song** với Windows Job Object (`ctypes` có đủ `argtypes`/`restype` và fallback); (c) Đọc `COMPARISON_TIMEOUT_SECONDS` tại parent lúc mở session và truyền tường minh sang worker (giải quyết bài toán hạ timeout trong test khi `spawn` không thấy monkeypatch).
4. **Lộ trình tối giản nếu ưu tiên giảm LOC:** Giao diện `worker_session(deadline)` tách hẳn khỏi service — nếu tác giả muốn bản v1 tối giản (~85 LOC) có thể cài spawn-per-request (đã vá TempFile + handshake/Timer + 504/500 + Job Object) rồi đổi ruột sang pool ấm mà không sửa một dòng service nào; tuy nhiên về kỹ thuật tôi vẫn khuyến nghị **pool ấm 4 slot + session** để đạt mục tiêu H3b (< 3 s warm-run).

---

## 3. Lập trường 9 điểm

1. **Mô hình:** Chọn **pool thường trực có giám sát (lazy-start, recycle 50 task) + session theo request** — loại bỏ phạt spawn 0,5–1,2 s/request để bảo toàn H3b (< 3,0 s warm-run cho PDF 20 trang, đặc biệt khi Phase B–E nạp thêm TF-IDF/scipy); độ phức tạp ~160 LOC stdlib hoàn toàn xứng đáng và được đóng gói gọn sau một context manager.
2. **Ranh giới worker:** Chỉ cô lập **`extract_pdf` và `diff_words`** (không đưa `HTTPException`/FastAPI vào worker); `validate_pdf_stream` và `check_text_length` ở parent, truyền `max_pages` tường minh và giữ `extract_document(..., _run=None)` → **0 test cũ phải sửa**.
3. **Slot theo request vs theo bước:** **1 slot/request** (rút cơ chế 3 bước của AG Round 1) qua `worker_session(deadline)` — không bao giờ 503/504 giữa chừng sau khi đã extract xong PDF.
4. **IPC:** **Tệp tạm (stream 64 KiB, `kill→join→unlink`) cho input PDF** (~3 MiB RAM vs ~75 MiB của Pipe bytes) và **Pipe cho text + kết quả** (đọc trước `join` nên không deadlock, tránh overhead và khóa đĩa của `result.json`).
5. **Mã lỗi:** **`504 PROCESSING_TIMEOUT`** cho timeout (5xx chuẩn, không đổ lỗi input 422 khi server tải cao), **`503 SERVER_BUSY`** (+`Retry-After`) khi đầy slot, và **`500 PROCESSING_FAILED`** (JSON phẳng D4) cho worker crash.
6. **Admission:** **`MAX_WORKERS = 4`, hàng đợi `= 0`**, kiểm slot tại biên giới `worker_session` (sau nhận body + validation rẻ) để tránh lỗ hổng Slowloris khóa chết 2 slot của ASGI gate trước đọc body.
7. **Chống orphan:** **Cả hai** — Windows Job Object `KILL_ON_JOB_CLOSE` (~25 dòng `ctypes` có fallback) diệt orphan tức thì khi API chết, cộng `faulthandler.dump_traceback_later(timeout + 5, exit=True)` làm lưới an toàn đa nền tảng.
8. **Hard-timeout coverage:** Bắt buộc `"ready"` handshake có timeout lúc khởi động và bọc toàn bộ pha `send() + poll() + recv()` bằng `threading.Timer(remaining, force_kill)` + `join(3.0)` hữu hạn để không còn khoảng hở không có deadline.
9. **Kế hoạch test:** Đọc `COMPARISON_TIMEOUT_SECONDS` tại parent lúc mở session và truyền tường minh xuống worker để `monkeypatch` hạ timeout (1–2 s) hoạt động qua `spawn`; mọi test treo có `faulthandler_timeout` dự phòng; kiểm `active_children() == []` và thư mục tạm rỗng sau mỗi test; thời gian suite ~13–20 s là chấp nhận được (và thấp hơn nếu dùng pool ấm ở fixture session cho acceptance test).
