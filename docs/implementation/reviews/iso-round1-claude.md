# Isolation Round 1 — Claude

Vai trò: Agent B, Kiến trúc sư và Reviewer triển khai. Tôi không ghi gì vào repository. Mọi prototype nằm trong `C:\Users\Admin\AppData\Local\Temp\claude\7a81e431fe1166c9\3ae8a7db-bd9c-402e-b3dc-61914ab153f4\scratchpad\iso-claude\`. Thư mục `repo\` trong đó là bản sao `app/` và `tests/` đã áp dụng thiết kế đề xuất. Sau mỗi thí nghiệm tôi chạy `tasklist`, không còn tiến trình `python.exe` nào.

## 1. Hiểu bài toán

- **R-LOOP**: `resolve1` của pdfminer lặp vô hạn bằng Python thuần trong main thread của bất kỳ process nào chạy nó. Thread không hủy được, nên chỉ có một cách chấm dứt thật sự là giết process (TerminateProcess trên Windows).
- **R-CPU**: `SequenceMatcher` chạy CPU-bound và không có ngưỡng tĩnh hợp lệ (D13). Tình huống giống R-LOOP: phải giết process.
- **R-TIMEOUT**: v2 §3.2 quy định `COMPARISON_TIMEOUT_SECONDS = 30.0` cho "một yêu cầu so sánh". Nghĩa là **hạn chót tính theo request**, không theo từng bước. `/pdf` gồm 2 lần extract và 1 lần diff, tổng phải ≤ 30 s, không được thành 90 s.
- Các bất biến cần giữ:
  - Mỗi request nặng có tối đa **một** process con.
  - Số process con không vượt một trần.
  - Mọi process con đều bị kill khi request kết thúc, dù thành công, lỗi hay timeout.
  - Process con tự chết nếu server chết trước khi kịp kill nó.
  - `/health` không phụ thuộc worker.
  - Hợp đồng 400/413/422 hiện có không đổi. `MemoryError`/`OSError` vẫn trả 500.
- Ngoài phạm vi: sandbox ở mức OS. Process con vẫn có toàn quyền như server, không bị giới hạn RAM hay filesystem.

## 2. Ma trận so sánh

| Tiêu chí | P1. Process theo từng lời gọi | P2. Pool bền (`ProcessPoolExecutor`/`Pool`) | P3. Worker sống lâu + Pipe, tự khởi động lại | **P4 (đề xuất). Một process cho mỗi request ("worker session")** |
|---|---|---|---|---|
| Correctness | Đúng | Đúng khi không timeout | Đúng, nhưng có nguy cơ rò trạng thái giữa các request (cache pdfminer, heap phân mảnh) | Đúng. Process mới cho mỗi request nên không rò trạng thái |
| Hard timeout | `poll(timeout)` rồi `kill()` | **Không có**. `Future.result(timeout)` không giết worker, `cancel()` trên future đang chạy trả `False` [CONFIRMED §4.5] | `poll` rồi kill worker đó | `poll(deadline − now)` rồi `kill()` |
| Kết thúc worker | Đơn giản | Phải dùng `pool._processes` (API riêng tư). Kill một worker làm **pool vỡ**: future hợp lệ của request khác nhận `BrokenProcessPool`, `submit` sau đó cũng vỡ [CONFIRMED §4.5] | Kill rồi respawn, cần registry và lock | Kill trong `finally`, luôn chạy |
| Concurrency | 1 semaphore, nhưng `/pdf` gọi 3 lần nên có thể bị 503 **giữa chừng** | Hàng đợi nội bộ của pool không giới hạn | Checkout/checkin worker | 1 semaphore non-blocking theo request |
| Windows | spawn chạy được | spawn chạy được | spawn chạy được, cần lifespan khởi động/tắt | spawn chạy được [CONFIRMED] |
| Bộ nhớ | ~35 MB/process cộng dữ liệu, chỉ khi có request | N × ~35 MB thường trực | N × ~35 MB thường trực, có thể phình dần | ~35 MB/process cộng dữ liệu, chỉ khi có request |
| Startup latency | ~0,5 s × 3 cho `/pdf` (≈1,5 s) | ~0 khi pool đã ấm | ~0 | **~0,5 s/request** (`/pdf` từ 0,16 s lên 0,70 s) [CONFIRMED] |
| Maintainability | Tốt | Kém (dùng API riêng tư, phải dựng lại pool) | Kém nhất (vòng đời, health của worker nhàn rỗi, recycle) | Tốt: 1 module ~70 dòng, không có trạng thái toàn cục ngoài semaphore |
| Độ phức tạp | Thấp nhưng phải truyền `deadline` qua các hàm | Trung bình, nhiều bẫy | Cao (~120+ dòng) | Thấp và trung bình |

P4 là P1 mở rộng: một process phục vụ **nhiều lời gọi tuần tự của cùng một request** qua `Pipe`, rồi bị kill. P4 lấy ưu điểm của P1 (cô lập sạch, kill đơn giản) và sửa hai điểm yếu của P1: `/pdf` chỉ spawn một lần, và mỗi request giữ đúng một slot.

## 3. Phương án đề xuất: P4 "worker session"

### 3.1 Ranh giới

- **Không** cô lập ở route. Route vẫn mỏng, giữ `def`, không đổi.
- **Không** đưa cả service (có `HTTPException`) vào process con, vì con sẽ phải import FastAPI (+0,58 s) [CONFIRMED: `import fastapi 0.584`].
- Ranh giới đặt **quanh lời gọi extractor và engine**, nhưng phạm vi session thuộc về service. Service mở một session cho mỗi request, gọi `run(extract_pdf_bytes, …)` và `run(diff_words, …)`. Việc ánh xạ lỗi theo tên tệp (`read_document`) và kiểm `TEXT_TOO_LONG` vẫn chạy ở process chính, giữ nguyên thứ tự hiện tại.
- Hàm chạy trong process con chỉ import `pdfplumber` hoặc `difflib`.

### 3.2 Thay đổi theo file

| File | Thay đổi | Số dòng diff đo trên bản sao |
|---|---|---|
| `app/core/config.py` | `COMPARISON_TIMEOUT_SECONDS = 30.0`, `MAX_ACTIVE_WORKERS = 4` | 2 |
| `app/core/worker.py` (**mới**) | `worker_session()`, `worker_main()`, 3 exception | 73 dòng |
| `app/extractors/pdf_extractor.py` | `extract_pdf_bytes(data, max_pages)` = `extract_pdf(BytesIO(data), max_pages)` | 6 |
| `app/services/document_service.py` | tách `read_document(filename, file_stream, run)` (ánh xạ lỗi cũ giữ nguyên); `extract_document` = validate + `with worker_session() as run` | 13 |
| `app/services/comparison_service.py` | `compare_text` và `compare_document` bọc trong `with worker_session() as run:` | 28 |
| `app/main.py` | 2 handler: `WorkerBusyError` → 503, `WorkerTimeoutError` → 422 (body phẳng như D4) | 18 |
| `tests/test_comparison_service.py` | 1 test đổi đích monkeypatch `extract_document` → `read_document` | 2 |

Lõi `app/core/worker.py` (đã chạy và qua toàn bộ test):

```python
WORKER_CONTEXT = multiprocessing.get_context("spawn")
worker_slots = threading.BoundedSemaphore(MAX_ACTIVE_WORKERS)

def worker_main(connection, timeout_seconds):
    # Tự thoát nếu tiến trình cha chết trước khi kịp kill.
    faulthandler.dump_traceback_later(timeout_seconds + 5, exit=True)
    while True:
        function, args = connection.recv()
        try:
            result = ("ok", function(*args))
        except Exception as error:
            result = ("error", error)
        connection.send(result)

@contextmanager
def worker_session():
    # Một request = một slot = một tiến trình = một hạn chót.
    if not worker_slots.acquire(blocking=False):
        raise WorkerBusyError()
    try:
        timeout_seconds = COMPARISON_TIMEOUT_SECONDS
        deadline = time.monotonic() + timeout_seconds
        connection, child_connection = WORKER_CONTEXT.Pipe()
        process = WORKER_CONTEXT.Process(
            target=worker_main, args=(child_connection, timeout_seconds), daemon=True)
        process.start()
        child_connection.close()

        def run(function, *args):
            try:
                connection.send((function, args))
                if not connection.poll(max(0, deadline - time.monotonic())):
                    raise WorkerTimeoutError()
                status, value = connection.recv()
            except (EOFError, OSError) as error:
                raise WorkerCrashedError() from error
            if status == "error":
                raise value
            return value

        try:
            yield run
        finally:
            process.kill()
            process.join()
            process.close()
            connection.close()
    finally:
        worker_slots.release()
```

`compare_document` sau khi sửa:

```python
validate_pdf_stream(old…); validate_pdf_stream(new…)        # rẻ, ở process chính
with worker_session() as run:
    old_document = read_document(old_filename, old_file_stream, run)
    new_document = read_document(new_filename, new_file_stream, run)
    … build_document_text, check_text_length (process chính) …
    changes = run(diff_words, old_data["fulltext"], new_data["fulltext"])
… span_to_page_locations (process chính, O(n·pages), rẻ) …
```

### 3.3 IPC

- Truyền **bytes** (`file_stream.read()`), không truyền `UploadFile`, file handle hay đường dẫn tạm. Ứng dụng không tạo file tạm nào nên không phải dọn file tạm.
- Hai tệp được gửi **tuần tự**. Đỉnh bộ nhớ thêm ở process chính khoảng 2 × 15 MiB cho mỗi tệp đang gửi (bytes cộng buffer pickle), ở process con khoảng 15 MiB cho mỗi tệp cộng đối tượng pdfminer.
- Với `MAX_ACTIVE_WORKERS = 4`: trường hợp xấu nhất ≈ 4 × (35 MB + ~60 MB) ≈ 400 MB. Đây là ước lượng [HYPOTHETICAL], chưa đo đỉnh RSS.
- Kết quả trả về là `list[dict]`/`str`, picklable. Đã đo 2 M ký tự trả về trong 0,49 s [CONFIRMED].

### 3.4 Timeout và kill

- Hạn chót tính cho cả phiên, bắt đầu sau khi body đã upload xong và đã validate. Mọi `poll` dùng thời gian còn lại.
- Hết giờ thì `WorkerTimeoutError`, và `finally` gọi `kill()` (TerminateProcess) rồi `join()`.
- Vì sao `kill()` vô điều kiện cả khi thành công: process con là vòng lặp vô hạn chờ job nên không tự thoát. Gọi `kill` lên process đã xong không ném lỗi [CONFIRMED §4.1].
- Lưới an toàn thứ hai: `faulthandler.dump_traceback_later(timeout + 5, exit=True)` trong process con. Watchdog này chạy ở mức C nên vẫn `_exit` được khi main thread kẹt trong `resolve1`. Nó xử lý trường hợp server chết đột ngột (process con "mồ côi") [CONFIRMED §4.2].
- `daemon=True` để khi server tắt bình thường, `atexit` của multiprocessing giết process con.

### 3.5 Giới hạn tải và mã lỗi

| Tình huống | HTTP | Body | Lý do |
|---|---|---|---|
| Đủ `MAX_ACTIVE_WORKERS` request đang xử lý | **503** | `{"error_code":"SERVER_BUSY","detail":…}` + `Retry-After: 5` | Hàng đợi chờ = **0**: request không giữ thread của threadpool và không chiếm RAM khi chờ. Lỗi do quá tải nên retry có ích. |
| Hết 30 s | **422** | `{"error_code":"PROCESSING_TIMEOUT","detail":"Xử lý vượt quá 30 giây"}` | Cùng họ với `PDF_TOO_MANY_PAGES`/`TEXT_TOO_LONG`: đầu vào vượt giới hạn tài nguyên, retry với cùng input vô ích. Vì không có thời gian chờ hàng đợi, thời gian đo được gần như chỉ phụ thuộc input. Tôi loại 504 vì 504 là ngữ nghĩa gateway: proxy hoặc client có thể tự retry, và monitoring đếm nó là lỗi hạ tầng. |
| Process con chết không gửi kết quả (bị OS kill, crash C) | 500 | mặc định `Internal Server Error` | Khớp phase-a-report: lỗi server giữ 500. Không thêm `error_code` mới. |
| `MemoryError`/`OSError` ném trong process con | 500 | như hiện tại | Exception được pickle và ném lại nguyên kiểu [CONFIRMED §4.1, §4.4] |
| `InvalidPDFError`/`PDFPageLimitError` | 400/422 | như hiện tại | Ném lại trong process chính, `read_document` ánh xạ như cũ |

Hai handler mới đặt trong `main.py`, cạnh handler D4. Lý do: `core/worker.py` không import FastAPI, và không phải lặp `try/except` ở 3 service.

### 3.6 Route: giữ `def`

- Thread của threadpool AnyIO chặn ở `poll()`. Vì admission non-blocking, tối đa `MAX_ACTIVE_WORKERS` (4/40) thread bị giữ.
- Chuyển sang `async def` sẽ phải bọc `run_in_threadpool` hoặc viết lại bằng asyncio subprocess, tức đổi nhiều code mà không lợi gì.
- `/health` đã là `async def` (D15), đo được 1–2 ms trong lúc worker treo [CONFIRMED §4.4].

## 4. Bằng chứng prototype

Lệnh chạy bằng `C:/Users/Admin/contract-diff/.venv/Scripts/python` với `PYTHONDONTWRITEBYTECODE=1`, bọc `timeout 60`, script có `faulthandler.dump_traceback_later(≤55, exit=True)`.

**4.1 [CONFIRMED] Primitive P1 (`iso-claude\exp1.py`, `worker.py`)**

```text
pid trivial                        0.54s  27400
extract valid fixture              0.60s  2
invalid pdf                        0.71s  raised InvalidPDFError: Tệp PDF hỏng hoặc cần mật khẩu
MemoryError propagates             0.55s  raised MemoryError: fake
crash os._exit(3)                  0.50s  raised WorkerCrashedError:
R-LOOP pdf timeout=3               3.02s  raised WorkerTimeoutError:
R-CPU diff timeout=3               3.13s  raised WorkerTimeoutError:
15MiB bytes in                     0.48s  15728640
2M-char result out                 0.49s  2000000
after kill: valid again            0.47s  [{'type': 'replace', ...
active_children: []
```

Phiên bản đầu dùng `join(1)` trước `kill`, nên R-LOOP mất 4,03 s, chậm hơn timeout 1 s. Bài học: khi timeout phải kill ngay. Thiết kế cuối kill vô điều kiện.

**4.2 [CONFIRMED] Process con mồ côi tự chết (`exp2.py`)**: process cha bị `os._exit(0)` lúc 1,5 s khi process con đang trong vòng R-LOOP (timeout 3 → watchdog 8 s).

```text
child pids: [27520]
--- parent da chet; t~0   python.exe  27520 ... 35,052 K
--- t~3s                  python.exe  27520 ... 35,052 K
--- t~9s                  INFO: No tasks are running which match the specified criteria.
exp2.err: Timeout (0:00:08)!  (stack: pdfminer/pdftypes.py:114 resolve1 ...)
```

Như vậy không có watchdog thì process con mồ côi sẽ quay 100% CPU mãi. Một process con tốn khoảng 35 MB.

**4.3 [CONFIRMED] Server uvicorn thật (`exp3.py` + `proto_app.py`, P1, 2 slot, timeout 3 s)**

```text
t= 1.20s 3rd request while 2 slots busy: 503 {"detail":{"error_code":"SERVER_BUSY"}} 5
hang 0 t= 3.58s 504 ...PROCESSING_TIMEOUT   (prototype cũ dùng 504; thiết kế cuối là 422)
hang 1 t= 3.58s 504 ...PROCESSING_TIMEOUT
t= 4.40s after timeout, text: 200 {"changes":1} 0.54s
t= 7.88s R-CPU text: 504 ... 3.48s
t= 8.83s valid extract: 200 {"pages":2} 0.95s
```

Spawn dưới `python -m uvicorn` chạy được. Mỗi lần health dùng kết nối httpx mới mất khoảng 350 ms ngay cả lúc server rảnh (baseline 358 ms; keep-alive chỉ 1–4 ms), nên con số đó là chi phí của client, không phải server.

**4.4 [CONFIRMED] Thiết kế cuối áp dụng trên bản sao repo (`iso-claude\repo\`)**

```text
$ python -m pytest -q   (92 test cũ, 1 test đổi đích monkeypatch)
92 passed in 12.91s          # gốc: 92 passed in 2.38s
```

Nếu không đổi test đó thì nó fail, vì `monkeypatch.setattr` theo chuỗi yêu cầu thuộc tính `extract_document` tồn tại:

```text
FAILED tests/test_comparison_service.py::test_compare_document_checks_both_files_before_extracting
AttributeError: 'module' object at app.services.comparison_service has no attribute 'extract_document'
```

Bộ acceptance `repo\tests\test_isolation.py` (timeout hạ còn 2 s, 7 test):

```text
loop extract 2.02s
...health 2 ms
.loop2MB 422 new temp entries: set()
...
7 passed in 11.70s
toàn bộ: 99 passed in 21.78s ; tasklist python.exe: none
```

Latency `/pdf` trên fixture thật: **0,16 s → 0,70 s** (durations của pytest, gốc so với bản sao).

**4.5 [CONFIRMED] P2 thất bại (`exp4.py`, `ProcessPoolExecutor(2, max_tasks_per_child=10)`)**

```text
result(timeout) raised TimeoutError; hung.running() = True
cancel() on running future: False
other: BrokenProcessPool            # request hợp lệ khác bị hỏng lây
new submit after kill: BrokenProcessPool
```

**[HYPOTHETICAL]**
- P1 với `/pdf` tốn ≈ 1,5–1,8 s (suy ra từ 3 lần spawn × 0,5–0,6 s đo ở §4.1).
- Đỉnh RSS ở §3.3 chưa đo.

## 5. Edge cases và failure modes

1. **Process con kẹt trước `recv()`** (treo khi khởi động, ví dụ lúc import): trên Windows `connection.send` một message lớn chặn cho đến khi process con đọc, mà lúc này chưa có `poll` deadline hay watchdog. Rủi ro thấp, [HYPOTHETICAL]. Nếu muốn đóng hẳn: process cha dùng `threading.Timer(deadline, process.kill)`, khoảng 3 dòng.
2. **Process con chết trong khi khởi động hoặc giữa chừng**: `send` ném `BrokenPipeError`, `recv` ném `EOFError`, cả hai thành `WorkerCrashedError` rồi 500 [CONFIRMED với `os._exit(3)`].
3. **Exception không pickle được trong process con**: lời gọi `send` của process con ném lỗi, process con chết, process cha nhận EOF và trả 500. `extract_pdf` đã quy mọi lỗi về `InvalidPDFError`/`OSError`/`MemoryError`, đều picklable. Chuỗi `__cause__` mất khi pickle; log phía process chính chỉ thấy exception ngoài cùng.
4. **Slot rò khi `Pipe()`/`start()` ném lỗi** (hết handle): đã xử lý vì mọi thứ sau `acquire` nằm trong `try/finally release`. Nhưng nếu `start()` ném thì `kill()` trong `finally` trong chưa chạy tới (`start` nằm ngoài khối `try` trong), nên an toàn.
5. **Client ngắt kết nối**: Starlette không hủy endpoint `def`. Thread vẫn chờ tới hạn rồi kill. Thời gian bị chặn trên ≤ 30 s.
6. **Chạy `uvicorn --workers N`**: semaphore là của từng process, nên trần thực tế là N × `MAX_ACTIVE_WORKERS`. Cần ghi tài liệu.
7. **Ctrl+C trên Windows**: process con nhận `KeyboardInterrupt` (không bị bắt vì chỉ bắt `Exception`) và thoát, request đang chạy trả 500 lúc tắt server. Chấp nhận được.
8. **Nhiều tải nặng song song**: 4 diff cùng chạy trên 16 CPU vẫn ổn. Nếu máy quá tải, một tài liệu hợp lệ có thể vượt 30 s và nhận 422. Xem điểm yếu §9.
9. **R-BOMB về bộ nhớ**: chỉ bị chặn **thời gian**, không bị chặn RAM. Muốn giới hạn RAM trên Windows phải dùng Job Object, ngoài phạm vi. Process con chết vì OOM thì trả 500.
10. **Upload lớn rồi nhận 503**: body đã được nhận đủ (≤ 31 MiB) trước khi tới endpoint. Admission không tiết kiệm băng thông, chỉ tiết kiệm CPU và RAM của process con.
11. **File tạm**: ứng dụng không tạo file tạm. Spooled temp file của Starlette (> 1 MiB) được dọn sau request [CONFIRMED: `new temp entries: set()` với PDF lặp 2 MiB].

## 6. Ảnh hưởng tương thích

- **Không đổi**: mọi response 200, 400/413/422 hiện có, 413 tầng transport, 422 validation của `/text` (không spawn vì Pydantic chặn trước route), `/health`, chữ ký route, `response_model`.
- **Thêm vào hợp đồng**: `503 SERVER_BUSY` (+`Retry-After`) và `422 PROCESSING_TIMEOUT` trên `/text`, `/pdf`, `/extract`. Cần cập nhật phase-a-report và v2 §3.2.
- **Hành vi đổi**:
  - Latency nền tăng khoảng 0,5 s cho mỗi request nặng.
  - `MemoryError` trong process con được ném lại ở process chính, vẫn 500.
  - Một bộ nhớ đầy ở process con không còn làm chết server.
- **API nội bộ**: `extract_pdf` giữ nguyên, nên các unit test gọi trực tiếp vẫn chạy trong process chính. Thêm `read_document` và `extract_pdf_bytes`. 1 test đổi đích monkeypatch (giữ ý nghĩa: "không trích xuất trước khi validate cả hai tệp").
  - Phương án thay thế để không phải sửa test nào: `extract_document(filename, file_stream, run=None)`. Tôi không chọn vì phải rẽ nhánh theo `run is None`, khó đọc hơn.

## 7. Chiến lược test

- **Không bao giờ chạy tác vụ treo trong process pytest**: R-LOOP và R-CPU chỉ chạy trong process con. Process pytest chỉ chờ bằng `poll(deadline)`, nên tự thân đã có chặn trên.
- **Lớp bảo vệ thêm**:
  - `monkeypatch.setattr(worker, "COMPARISON_TIMEOUT_SECONDS", 2)` (cùng kiểu test hiện có patch `document_service.MAX_PDF_PAGES`).
  - Watchdog trong process con (timeout + 5 s).
  - Khuyến nghị thêm `faulthandler_timeout = 120` vào cấu hình pytest để có stack trace nếu treo. Đây là tính năng sẵn có của pytest, không thêm `pytest-timeout`.
- **Acceptance** (đã viết và chạy, 7 test, ~11,7 s):
  1. PDF tự tham chiếu ở `/extract` trả 422 `PROCESSING_TIMEOUT` trong < timeout + 1,5 s, sau đó PDF hợp lệ vẫn 200.
  2. PDF tự tham chiếu ở vị trí `new_file` của `/pdf` cũng trả 422.
  3. `/text` pathological (`"a b "*8500`) trả 422.
  4. Slot đầy: hạ semaphore còn 1 → 503 + `Retry-After`, `/health` 200 trong 2 ms trong lúc worker treo.
  5. Không còn file tạm mới sau timeout.
  6. Process con crash → `WorkerCrashedError`.
  7. `MemoryError` giữ nguyên kiểu.
- **Kiểm orphan**: fixture `client` assert `multiprocessing.active_children() == []` sau mỗi test.
- **Thời gian suite**: 2,4 s → ~13 s (92 test) và ~22 s (99 test). Nếu thấy chậm: gom các test chỉ kiểm validation để không gọi tới worker. **Không** thêm chế độ "in-process" cho test, vì như vậy test không còn kiểm tra cô lập.
- **Kiểm thủ công trên uvicorn thật**: kịch bản `exp3.py` (server subprocess + httpx). Nên đưa vào phụ lục đồ án làm minh chứng, không đưa vào CI.

## 8. Độ phức tạp

- **Code mới**: khoảng 73 dòng (`core/worker.py`) cộng khoảng 70 dòng diff ở 5 file. Chỉ dùng thư viện chuẩn (`multiprocessing`, `threading`, `contextlib`, `faulthandler`), không thêm dependency.
- **Khái niệm sinh viên cần giải thích khi bảo vệ**: spawn, Pipe/pickle, `poll` + `kill`, semaphore, context manager. Mỗi khái niệm có bằng chứng thực nghiệm ở §4.
- **Lệch so với coding style**:
  - 3 exception class rỗng (tiền lệ D11 `InvalidPDFError`).
  - Dùng `@contextmanager` của stdlib (không phải decorator tự viết).
  - Closure `run` (mới với codebase, nhưng ngắn).

## 9. Điểm yếu của chính phương án

1. **Thêm khoảng 0,5 s cho mỗi request** do spawn trên Windows (interpreter + import pdfplumber). P3 (worker ấm) tránh được nhưng phức tạp gấp đôi và rò trạng thái. Nếu sau này cần latency thấp, nâng cấp được mà không đổi service, vì chỉ phải thay ruột `worker_session`.
2. **422 cho timeout là một lựa chọn có tranh cãi**: khi máy quá tải, tài liệu hợp lệ cũng có thể nhận 422. 504 hoặc 503 cũng có lý; cần tác giả chốt.
3. **Hàng đợi = 0**: chịu tải đột biến kém. Hai người dùng demo cùng bấm khi có 4 request nặng sẽ nhận 503 ngay.
4. **Không giới hạn RAM** (R-BOMB về bộ nhớ vẫn mở), không phải sandbox.
5. **Lỗ §5.1**: `send` chặn khi process con kẹt lúc khởi động, chưa có deadline.
6. **Hạn chót không tính thời gian upload**; v2 chỉ nói "xử lý" nên phù hợp, nhưng cần ghi rõ.
7. **Suite test chậm hơn khoảng 5 lần** và phụ thuộc thời gian thực (ngưỡng `< timeout + 1,5 s`). Trên máy CI yếu cần nới ngưỡng.
8. **Semaphore theo từng process server**: chạy nhiều worker uvicorn thì trần thực tế nhân lên.
