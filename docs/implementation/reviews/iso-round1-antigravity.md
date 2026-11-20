# Isolation Round 1 — Antigravity

## 1. Problem understanding

Hệ thống `ContractDiff` (Windows 11, Python 3.14.3, FastAPI 0.143.3, Starlette 1.8.0, 16 CPU logic, `multiprocessing` mặc định `spawn`) hiện thực thi trực tiếp `extract_pdf` ([pdf_extractor.py](file:///C:/Users/Admin/contract-diff/app/extractors/pdf_extractor.py)) và `diff_words` ([text_diff.py](file:///C:/Users/Admin/contract-diff/app/engines/text_diff.py)) trong cùng tiến trình FastAPI trên threadpool đồng bộ AnyIO (40 thread). Vì Python không thể chấm dứt cưỡng bức một thread đang chạy CPU/C-loop, ba rủi ro mở từ Phase A ([phase-a-report.md](file:///C:/Users/Admin/contract-diff/docs/implementation/phase-a-report.md)) vẫn còn nguyên:

- **R-LOOP (Critical):** PDF ~290 byte có object tự tham chiếu (`3 0 obj 3 0 R endobj`) trong `/Pages` làm `pdfminer.pdftypes.resolve1` lặp vô hạn 100% CPU, giữ vĩnh viễn 1 thread/request; 40 request × 290 B (~12 KB) treo sạch threadpool.
- **R-CPU (High):** `SequenceMatcher(autojunk=False)` siêu tuyến tính (~34 s với 34 000 ký tự `"a b "` lặp).
- **R-TIMEOUT (High):** Chưa có hard timeout 30 s (`COMPARISON_TIMEOUT_SECONDS = 30.0`, v2 §3.2) có khả năng **kết thúc thực sự** tác vụ quá hạn.
- **R-BOMB (Medium):** PDF nhỏ (vd. 808 B chứa CIDFont `/W [0 2000000 500]`) khuếch đại CPU/RAM.

**Nguyên tắc biên giới:** Cô lập tiến trình (process isolation) ở đây nhằm bảo vệ **tính sẵn sàng** (hard timeout, kill sạch, cách ly crash), **không phải OS-level sandbox** (worker vẫn chạy dưới cùng tài khoản OS, không chặn truy cập filesystem/mạng hay cạn RAM toàn máy nếu không thêm cơ chế giới hạn ở tầng hệ điều hành).

---

## 2. Ma trận so sánh 4 phương án (và điểm gãy của từng thiết kế)

So sánh 3 phương án cơ bản và 1 phương án lai đề xuất (**PA4 — Supervised Independent Worker Pool**):

| Tiêu chí | PA1: Process-per-request (`mp.Process` mỗi request) | PA2: `ProcessPoolExecutor` / `mp.Pool` | PA3: Dedicated Single Subprocess Worker (`Popen` + stdin/stdout) | PA4 (Đề xuất): Supervised Independent Worker Pool (N worker 1-to-1 `Pipe` + lazy-spawn) |
|---|---|---|---|---|
| **Correctness** | Tốt nếu đọc `Pipe` trước `join`; **sai/treo** nếu `join()` trước `recv()` trên payload > 64 KB. | **Không đạt** (không đóng R-LOOP/R-TIMEOUT). | Tốt cho 1 request; **gãy framing** nếu thư viện in rác ra `stdout`. | Tốt: tách biệt 1-to-1 `Pipe`, ánh xạ tường minh ngoại lệ nghiệp vụ và lỗi hệ thống. |
| **Hard timeout** | **Đạt** (`conn.poll(t)` → `kill()`). | **THẤT BẠI**: `Future.result(t)` chỉ ném `TimeoutError`, **không giết worker**. | **Đạt** (`kill()` + respawn). | **Đạt** (`conn.poll(remaining)` → `kill()` chỉ đúng slot treo). |
| **Worker termination** | Sạch từng request, không ảnh hưởng request khác. | **THẤT BẠI**: không có API kill 1 task; hack kill 1 worker gây `BrokenProcessPool` cho task lành mạnh. | Giết sạch 1 worker nhưng không có đồng thời. | **Đạt**: `kill()` + `join()` từng slot độc lập; 0 ảnh hưởng tới slot khác. |
| **Concurrency** | Cao (cần semaphore chặn spawn-storm). | Tốt khi bình thường, sụp hoàn toàn sau N× R-LOOP. | **Rất kém (= 1)**: Head-of-Line blocking toàn server. | **Tốt** (`MAX_WORKERS = 2..4` + hàng đợi chặn trên). |
| **Windows compatibility** | Cần cẩn thận thứ tự `kill→join→unlink`; `spawn` nặng; cần Job Object tránh orphan. | Kém: `shutdown(wait=False)` vẫn để worker treo sống và có thể kẹt `atexit`. | Khó truyền fd riêng trên Windows; cần tránh `stdout` framing và cần Job Object. | **Tốt**: dùng `mp.get_context("spawn")` + `Pipe` 1-to-1 + `kill→join→unlink` + Job Object. |
| **Memory overhead** | 0 MB khi rảnh; bùng nổ nếu spawn đồng thời (39 MB/process) + copy `bytes`. | N × ~39 MB cố định + tích lũy nếu không `max_tasks`. | Thấp (1 × ~39 MB); tích lũy cache `pdfminer` theo thời gian. | Kiểm soát được: 0 MB trước request đầu (lazy), tối đa `N × ~39 MB` + recycle `max_tasks`. |
| **Startup latency** | **Rất tệ trên Windows**: ~845 ms/PDF, ~364 ms/text **mọi request** (`[CONFIRMED]`). | Tốt khi ấm (~80 ms PDF / ~0,3 ms text). | Tốt khi ấm (~80 ms / ~0,3 ms), ~800 ms lần đầu/sau kill. | **Tốt**: ~800 ms **một lần** (lazy), các request sau ~82 ms PDF / ~0,3 ms text (`[CONFIRMED]`). |
| **Maintainability** | Cao (~60 LOC), ít trạng thái chia sẻ. | Cao (stdlib), nhưng phải vá hack nội bộ nên thực tế dễ vỡ. | Trung bình (~100 LOC), giao thức framing dễ lỗi biên. | Trung bình (~150 LOC stdlib thuần), trạng thái đóng gói gọn trong 1 module. |
| **Độ phức tạp** | Thấp. | Thấp (nhưng không giải được bài toán). | Trung bình. | Trung bình (phù hợp đồ án 1 sinh viên, không thêm thư viện ngoài). |

**Điểm gãy cốt lõi (Adversarial Challenge) cho từng phương án:**
- **PA1 (Process-per-request):** (1) **Pipe deadlock** nếu gọi `p.join(timeout)` trước `conn.recv()` với kết quả > buffer OS (~64 KB) — đã chứng minh treo trên payload 512 KB; (2) **Chi phí `spawn` quá lớn trên Windows**: ~845 ms để import `pdfplumber` mỗi lần gọi → nếu tách 3 bước trong `/pdf` mất >2,0 s chỉ để khởi chạy Python (đốt 2/3 ngân sách 3,0 s của giả thuyết H3b trong kế hoạch v2 §1.4) và kéo dài test suite 92 test lên ~25–30 s; (3) Spawn-storm CPU khi nhiều request ngắn ập tới.
- **PA2 (`ProcessPoolExecutor` / `mp.Pool`):** **Bị loại (Disqualified).** `Future.result(timeout)` không dừng tiến trình con: chỉ 2 file `R-LOOP` (580 byte) làm kẹt vĩnh viễn pool 2 worker. Ép kill qua thuộc tính riêng `ex._processes` phá vỡ `BrokenProcessPool`, giết oan các request hợp lệ đang chạy song song (`[CONFIRMED]`). `max_tasks_per_child` chỉ recycle *sau khi tác vụ hoàn tất*, vô hiệu với vòng lặp vô hạn.
- **PA3 (Dedicated Single Worker):** (1) **Head-of-Line blocking**: 1 PDF `R-LOOP` giữ worker suốt 30 s sẽ chặn đứng mọi request `/text` (vốn chỉ cần 0,3 ms); (2) **Hỏng giao thức `stdout`**: bất kỳ thư viện nào in cảnh báo ra `stdout` làm vỡ JSON framing (`[CONFIRMED]`); (3) **Rò rỉ cache** (`pdfminer.cmapdb.CMapDB._cmap_cache`) nếu không tái tạo định kỳ.
- **PA4 (Supervised Independent Worker Pool):** Phức tạp trạng thái vòng đời hơn PA1, cần `ready` handshake, Job Object cho Windows và `max_tasks` recycle (phân tích chi tiết điểm yếu ở Mục 9).

---

## 3. Phương án đề xuất: Supervised Independent Worker Pool (PA4)

### 3.1. Kiến trúc module & Ranh giới cô lập
Giữ nguyên [pdf_extractor.py](file:///C:/Users/Admin/contract-diff/app/extractors/pdf_extractor.py) và [text_diff.py](file:///C:/Users/Admin/contract-diff/app/engines/text_diff.py) là hàm thuần in-process (không phá bất kỳ unit test nào đang gọi trực tiếp chúng). Chỉ thêm **1 module mới**: `app/services/worker_pool.py` (stdlib thuần: `multiprocessing`, `queue`, `threading`, `tempfile`, `ctypes` cho Windows Job Object).

```text
app/core/config.py            + COMPARISON_TIMEOUT_SECONDS = 30.0
                              + MAX_WORKERS = 4  (hoặc min(4, max(2, cpu//4)))
                              + MAX_PENDING_REQUESTS = 8
                              + MAX_TASKS_PER_WORKER = 50
                              + WORKER_STARTUP_TIMEOUT_SECONDS = 10.0

app/services/worker_pool.py   [MỚI, ~150 LOC]
  ├─ _worker_main(conn)       # Vòng lặp worker ở module độc lập (không import app.main)
  ├─ _WorkerSlot              # 1 Process + 1 Pipe 1-to-1 + tasks_done + kill/join/ensure_started
  ├─ _WorkerPool              # queue.Queue[_WorkerSlot] + BoundedSemaphore + Windows Job Object
  ├─ run_in_worker(op, payload, timeout) -> Any
  └─ shutdown_worker_pool()   # Gọi trong FastAPI lifespan shutdown & atexit

app/services/document_service.py    # extract_document(..., deadline=None) -> ghi temp file -> run_in_worker("extract_pdf", ...)
app/services/comparison_service.py  # compare_text -> fast-path == -> run_in_worker("diff_words", ...)
                                    # compare_document -> 1 deadline chung 30s cho toàn request
app/main.py                         # Gắn lifespan gọi shutdown_worker_pool() khi tắt app
```

### 3.2. Luồng gọi, ranh giới `compare_document` & Route `def` vs `async def`
- **Ngân sách timeout tính cho CẢ REQUEST (`deadline = time.monotonic() + COMPARISON_TIMEOUT_SECONDS`):** Không cấp 30 s riêng cho từng bước (vì `/pdf` có thể kéo tới 90 s, vi phạm v2 §3.2). Trong `compare_document`, một `deadline` duy nhất được truyền qua 2 lần `extract_document(..., deadline=deadline)` và bước `diff_words(..., timeout=remaining)`; luôn kiểm `remaining = deadline - time.monotonic() <= 0` trước khi chạy bước tiếp theo.
- **Tại sao không gộp toàn bộ `compare_document` thành 1 lệnh worker duy nhất?**
  1. Vì PA4 dùng worker ấm sẵn, IPC chỉ tốn **~0,3 ms/lần**, không bị phạt cold-start như PA1.
  2. Giữ `compare_document` gọi `extract_document(...)` và `check_text_length(...)` tại [comparison_service.py](file:///C:/Users/Admin/contract-diff/app/services/comparison_service.py) **bảo toàn 100%** các test hiện có monkeypatch `comparison_service.extract_document` và `comparison_service.MAX_TEXT_CHARS`, đồng thời fail-fast sau khi trích xuất `old_document` nếu đã vượt `MAX_TEXT_CHARS` (khắc phục CR-AG-006).
  3. Truyền `max_pages = MAX_PDF_PAGES` từ [document_service.py](file:///C:/Users/Admin/contract-diff/app/services/document_service.py) làm tham số tường minh sang worker → `monkeypatch.setattr(document_service, "MAX_PDF_PAGES", 2)` tiếp tục hoạt động chính xác.
- **Giữ route `def` (đồng bộ) cho `/text`, `/extract`, `/pdf`; giữ `async def` cho `/health` (D15):**
  - Đổi service sang `async def` sẽ phá vỡ 34 unit test gọi đồng bộ trực tiếp trong [test_comparison_service.py](file:///C:/Users/Admin/contract-diff/tests/test_comparison_service.py).
  - Rủi ro cạn 40 thread AnyIO được chặn ngay đầu `run_in_worker`: `BoundedSemaphore(MAX_WORKERS + MAX_PENDING_REQUESTS)` (`4 + 8 = 12 << 40`) dùng `acquire(blocking=False)`. Request thứ 13 trả `503` tức thì (< 1 ms), **không bao giờ** giữ quá 12 thread. `/api/v1/health` chạy trên event loop nên luôn phản hồi tức thì.

### 3.3. IPC, Truyền dữ liệu & Chi phí bộ nhớ
**Tuyệt đối không truyền `UploadFile` hay file handle qua ranh giới `spawn` trên Windows.**
- **PDF (`/extract`, `/pdf`):** Sau khi `validate_pdf_stream` (rẻ, tại parent) qua cổng, parent sao chép `file_stream` theo từng khối 64 KiB (`shutil.copyfileobj(..., length=65536)`) ra tệp tạm `tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")`, **đóng tệp** trước khi gửi đường dẫn `str` (~80 byte) + `max_pages` qua `Pipe`.
  - **Chi phí RAM:** Parent chỉ tốn buffer **64 KiB** (thay vì giữ đồng thời `UploadFile` + `bytes` 15 MiB + pickle buffer 15 MiB + bản sao bên worker = 45–60 MiB/tệp, tức 90–120 MiB/request `/pdf` × 4 worker ≈ **360–480 MiB**). Worker mở file trực tiếp và seek trên đĩa.
  - **Độ trễ:** Chỉ **26,1 ms** cho PDF 14 MiB (`[CONFIRMED]`, hơn Pipe bytes đúng 4,8 ms).
- **Text (`/text` & bước diff của `/pdf`):** `old_text`, `new_text` đã ở dạng `str` trong RAM (≤ 500 000 ký tự × 2). Thêm fast-path `if old_text == new_text: return []` ở parent (0,01 ms, tránh IPC). Nếu khác nhau, gửi `(old_text, new_text)` qua `Pipe` sau khi worker đã gửi tín hiệu `"ready"` (khởi động xong và đang đứng chờ `conn.recv()`, nên gửi 2 × 500k ký tự không bị kẹt pipe buffer — `[CONFIRMED]` 163,5 ms cả diff).

### 3.4. Giao thức IPC, Timeout, Kill, Cleanup & Chống Orphan
1. **Khởi động lười (Lazy-start) + Handshake `"ready"`:** Slot chỉ `spawn` ở lần gọi đầu tiên hoặc sau khi bị kill/recycle. Worker import `pdf_extractor`/`text_diff` rồi gửi `"ready"`; parent đợi bằng `conn.poll(WORKER_STARTUP_TIMEOUT_SECONDS)` (tránh treo vô hạn khi boot).
2. **Chờ có hạn thời gian (không deadlock):** Parent gọi `conn.send((op, payload))`, tính `remaining = deadline - time.monotonic()`, gọi `conn.poll(remaining)`. Chỉ khi `poll()` trả `True` mới gọi `conn.recv()`.
3. **Hard Kill & Thứ tự dọn dẹp bắt buộc trên Windows:**
   - Khi `poll()` trả `False` (quá hạn): đóng `conn` → gọi `proc.kill()` (`TerminateProcess` trên Windows, ngắt tức thì mọi vòng lặp vô hạn) → **bắt buộc `proc.join(timeout=3.0)`** → đánh dấu `slot.proc = None` rồi trả `slot` về hàng đợi → **sau khi `run_in_worker` thoát mới `os.unlink(tmp_path)` trong `finally` của `extract_document`**. (Nếu unlink trước `join()`, Windows ném `PermissionError WinError 32`.)
   - Khi worker tự sập (`os._exit`, segfault, OOM): `poll()` trả `True` → `conn.recv()` ném `EOFError` → parent gọi `proc.join(timeout=3.0)` **trước** khi đọc `proc.exitcode`, dọn slot, ném `WorkerCrashedError`.
   - **Tái tạo định kỳ:** Đủ `MAX_TASKS_PER_WORKER` (50) tác vụ → gửi sentinel `None`, `join(0.5)` (nếu không thoát thì `kill()`), đặt `slot.proc = None`.
4. **Chống orphan process:**
   - `lifespan` của FastAPI gọi `shutdown_worker_pool()` khi tắt server bình thường.
   - Trên Windows (`sys.platform == "win32"`), gắn mỗi worker mới vào một **Windows Job Object** với cờ `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` (~30 dòng `ctypes`). Nếu parent bị giết đột ngột (`TerminateProcess` / Task Manager), Windows kernel tự động tiêu diệt mọi worker con (`[CONFIRMED]`). Nếu chạy trong môi trường không cho gán Job Object, log cảnh báo và fallback về `lifespan` + `atexit`.

### 3.5. Bảng mã lỗi HTTP & Bảo toàn API Contract
Giữ nguyên 100% mã lỗi Phase A (`400 INVALID_OR_ENCRYPTED_PDF`, `413 PAYLOAD_TOO_LARGE`, `422 PDF_TOO_MANY_PAGES`, `422 TEXT_TOO_LONG`, `422` FastAPI cho `/text`, `413` transport). Bổ sung 3 tình huống mới theo đúng body phẳng D4 (`{"error_code", "detail"}`) qua `http_error` hiện có:

| Tình huống | HTTP | `error_code` | Ghi chú |
|---|---|---|---|
| Vượt `COMPARISON_TIMEOUT_SECONDS` (khi đang chạy hoặc chờ hàng đợi) | **504** | `PROCESSING_TIMEOUT` | Tách biệt rõ với lỗi validation 422 và client timeout 408; kèm tên tệp nếu timeout tại bước extract. |
| Quá tải (`MAX_WORKERS + MAX_PENDING_REQUESTS` đã đầy) | **503** | `SERVER_BUSY` | Kèm header `Retry-After: 5`; từ chối tức thì không giữ thread AnyIO. |
| Worker crash (`EOFError`/exit ≠ 0), `MemoryError`, `OSError` không phải lỗi PDF | **500** | `PROCESSING_FAILED` | Không bao giờ dán nhãn nhầm thành `400 INVALID_OR_ENCRYPTED_PDF` (đúng D10 sửa đổi). |

Worker bắt tường minh `InvalidPDFError` và `PDFPageLimitError`, gửi `("err", "InvalidPDFError", msg)` / `("err", "PDFPageLimitError", msg)` để parent ném lại đúng lớp ngoại lệ → `document_service` giữ nguyên ánh xạ 400 / 422.

---

## 4. Bằng chứng prototype

Toàn bộ thí nghiệm được chạy ngoài repo (thư mục scratch riêng), có watchdog `faulthandler.dump_traceback_later(..., exit=True)`, với `PYTHONDONTWRITEBYTECODE=1` trên Windows 11 / Python 3.14.3.

### `[CONFIRMED]` 1 — Cold spawn (PA1), Pipe deadlock (PA1), Failure modes của `ProcessPoolExecutor` (PA2) & Tempfile lock Windows
Lệnh: `$env:PYTHONDONTWRITEBYTECODE='1'; .venv\Scripts\python.exe <scratch>\bench_options.py`
```text
=== 1. SPAWN LATENCY & MEMORY (Windows 11 / Python 3.14.3) ===
mp.Process(spawn) diff_words cold: 363.9 ms (exit=0)
mp.Process(spawn) extract_pdf run 1: 837.5 ms, pages=2, worker_rss=38.7 MB
mp.Process(spawn) extract_pdf run 2: 852.8 ms, pages=2, worker_rss=38.8 MB
subprocess.run import pdfplumber: 589.3 ms (rc=0)

=== 2. OPTION 1 FAILURE MODE: join()-before-recv() PIPE DEADLOCK ===
join(1.5s) before recv() on 512KB payload: alive=True, elapsed=1.51s (DEADLOCKED=True)
After recv(524288 bytes): alive=False, exitcode=0

=== 3. OPTION 2 FAILURE MODES: ProcessPoolExecutor ===
R-LOOP task 1: TimeoutError raised
R-LOOP task 2: TimeoutError raised
After 2x TimeoutError: pool workers alive=2/2 ([29576, 13556])
Valid task on 2-worker pool STARVED -> TimeoutError! Pool permanently wedged.
Healthy sibling task CRASHED with BrokenProcessPool: A process in the process pool was terminated abruptly while the future was running or pending.

=== 4. WINDOWS TEMP FILE LOCK ON KILL ===
Unlink while child alive: PermissionError (32)
Unlink immediately after kill() before join(): PermissionError (32)
Unlink after join(): SUCCEEDED
```

### `[CONFIRMED]` 2 — Prototype PA4: Warm latency, IPC 14 MiB, R-LOOP kill + song song lành mạnh, Pathological diff, Crash recovery & Backpressure
Lệnh: `$env:PYTHONDONTWRITEBYTECODE='1'; .venv\Scripts\python.exe <scratch>\proto_supervised_pool.py`
```text
=== A. WARM LATENCY (Supervised Persistent Worker) ===
Cold first extract_file (lazy start): 802.8 ms, pages=2
Warm extract_file (5 runs): min=76.5ms, avg=88.3ms
Warm diff_words   (5 runs): min=0.29ms, avg=0.33ms

=== B. IPC BENCHMARK: 15 MiB bytes over Pipe vs Temp File Path ===
14 MiB valid PDF via Pipe bytes: 21.3 ms (pages=1, parent_rss=63.7MB)
14 MiB valid PDF via TempFile  : 26.1 ms (pages=1)

=== C. OPTION 3 ADVERSARIAL FAILURE MODE: RSS BLOAT AFTER CIDFONT BOMB ===
Persistent worker RSS before CIDFont bomb: 35.8 MB
Persistent worker RSS after  CIDFont bomb (after gc.collect): 37.2 MB (took 0.88s, delta=+1.4 MB)

=== D. ISOLATION PROOF: R-LOOP + HEALTHY CONCURRENT + PATHOLOGICAL DIFF + CRASH + BUSY ===
Concurrent R-LOOP vs Healthy: loop=TimeoutError in 1.02s | healthy=OK (2 pages) in 81.8ms | loop_tempfile_unlinked=True
Recovery after R-LOOP kill: changes=1 in 0.4ms
Pathological diff_words (34k chars): killed by TimeoutError in 1.03s
Worker crash handled: Worker crashed (exitcode=None)
After crash recovery: changes=1
Bounded admission (cap=3, 5 concurrent): ['SERVER_BUSY', 'SERVER_BUSY', 'ok', 'ok', 'ok']
```

### `[CONFIRMED]` 3 — Windows Job Object chống orphan, PA3 `stdout` framing corruption & IPC 500k×2 text
Lệnh: `<scratch>\proto_windows_edge.py` và `<scratch>\proto_pipe_large.py`
```text
Without Job Object: parent killed -> child_pid=26428 still_alive(ORPHAN)=True
With Job Object (set=1, assign=1): parent killed -> child_pid=26484 still_alive=False
JSON framing CORRUPTED by stray stdout print: JSONDecodeError: Expecting value: line 1 column 1 (char 0)
500k x2 Vietnamese text over Pipe: status=ok, changes=1, time=163.5 ms
5000 changes response over Pipe: status=ok, changes=5000, time=8384.8 ms
```

### `[HYPOTHETICAL]` (chưa thực nghiệm trực tiếp trong phiên này)
- Tương tác với `uvicorn --reload` (WatchFiles tạo thêm tiến trình reloader trung gian trên Windows; cần kiểm thử thủ công rằng Job Object không gây lỗi gán job lồng nhau và reload tắt sạch worker).
- Mức tăng RSS tích lũy của `pdfminer.cmapdb.CMapDB._cmap_cache` sau >100 hợp đồng PDF tiếng Việt có nhiều bảng font CMap đa dạng (chưa chạy trên corpus T1; đã dự phòng bằng `MAX_TASKS_PER_WORKER = 50`).

---

## 5. Edge cases & Failure modes cần chặn khi cài đặt

1. **`TimeoutError` là lớp con của `OSError` trong Python 3:** Đã thực sự vấp lỗi này ở lần chạy đầu của prototype (`except OSError` nuốt mất `TimeoutError` và đổi thành `Worker IPC broken`). **Bắt buộc** đặt `except TimeoutError: raise` trước `except OSError:`.
2. **`proc.exitcode` vẫn là `None` ngay tại thời điểm `EOFError`:** Đã quan sát trực tiếp trong prototype (`Worker crashed (exitcode=None)`). Phải gọi `proc.join(timeout=3.0)` **trước** khi đọc `proc.exitcode` để ghi log chính xác.
3. **Bẫy `spawn` re-import trên Windows:** Hàm đích `_worker_main` bắt buộc nằm trong `app/services/worker_pool.py` và tuyệt đối không import `app.main`, tránh tiến trình con khởi tạo lại FastAPI/middleware khi `spawn`.
4. **Đĩa tạm (`%TEMP%`) đầy hoặc lỗi ghi tệp tạm:** Bọc bước ghi `NamedTemporaryFile` trong `try/except`: nếu lỗi giữa chừng phải đóng và `unlink` tệp dở dang ngay, sau đó để lỗi `OSError` trả 500 (không để rác đĩa).
5. **Quá hạn ngay trong hàng đợi hoặc trong pha cold-start:** Nếu `slots.get(timeout=remaining)` hết giờ hoặc `remaining <= 0` sau khi lấy được slot, trả 504 ngay mà không gửi việc cho worker.
6. **File `R-LOOP` nằm ở `new_file` sau khi `old_file` đã xong:** Khối `finally` phải dọn sạch tệp tạm của cả hai phía; chỉ trả `504 PROCESSING_TIMEOUT` khi bước nào hết ngân sách tổng 30 s.
7. **Thứ tự tắt khi `shutdown_worker_pool()` gọi lúc có request đang chạy:** Đặt cờ `_shutting_down`, từ chối request mới bằng 503, và `close(kill=True)` mọi slot để server tắt trong < 1 s (không treo khi `Ctrl+C`).

---

## 6. Compatibility impact

- **API Contract 200 / 400 / 413 / 422:** Không thay đổi bất kỳ trường response hay mã lỗi Phase A nào. Chỉ thêm `504 PROCESSING_TIMEOUT`, `503 SERVER_BUSY`, `500 PROCESSING_FAILED` cho các tình huống mới.
- **Tương thích với 92 test hiện có:**
  - `test_text_diff.py`, `test_text_mapping.py`: không chạm tới worker → giữ nguyên tốc độ và hành vi.
  - `test_comparison_service.py`: các unit test gọi trực tiếp `extract_pdf(...)` (kể cả `FailingStream` và `monkeypatch` lên `pdfplumber.page.Page`) chạy in-process 100% như cũ; các test gọi `extract_document`/`compare_document` tương thích hoàn toàn nhờ truyền `MAX_PDF_PAGES` làm tham số và giữ lời gọi `extract_document`/`MAX_TEXT_CHARS` ở `comparison_service.py`.
  - `test_comparisons_api.py`: giữ nguyên 100% không cần sửa; tuy nhiên vì fixture `client` là function-scoped (`with TestClient(app):`) và `lifespan` tắt pool sau mỗi test, ~18–20 test gọi worker sẽ lazy-spawn lại 1 worker mỗi test → tổng thời gian chạy 92 test tăng từ ~2,5 s lên ước tính ~16–20 s (`[HYPOTHETICAL]`, chấp nhận được cho CI/đồ án).

---

## 7. Testing strategy (Acceptance tests bắt buộc)

**Quy tắc an toàn tuyệt đối:** Mọi test có đầu vào gây treo (`R-LOOP` PDF 290 B hoặc `diff_words` 34k ký tự `"a b "`) **CHỈ** được gọi qua API hoặc `run_in_worker` với timeout hạ thấp (`monkeypatch.setattr(config_mod, "COMPARISON_TIMEOUT_SECONDS", 1.0)`), và **luôn có lớp bảo vệ thứ hai độc lập** (fixture bật `faulthandler.dump_traceback_later(15, exit=True)` trong test hoặc chạy lời gọi client trong thread kèm `join(timeout=10)` assert không treo). Không bao giờ gọi trực tiếp `extract_pdf(BytesIO(LOOP_PDF))` trong tiến trình `pytest` chính.

**7 nhóm acceptance test thiết kế mới (`tests/test_process_isolation.py`, cấu hình `timeout = 1.0 s`, `MAX_WORKERS = 2`, `MAX_PENDING = 1`):**
1. **`R-LOOP` không treo server:** Gửi PDF tự tham chiếu 290 B tới `/api/v1/documents/extract` và `/api/v1/comparisons/pdf` (cả vị trí `old_file` lẫn `new_file`) → nhận `504` (`error_code == "PROCESSING_TIMEOUT"`) trong `< 3 s`.
2. **`R-CPU` bị cắt bởi timeout:** Gửi `{"old_text": "a b " * 8500, "new_text": "a c " * 8500}` tới `/api/v1/comparisons/text` → nhận `504 PROCESSING_TIMEOUT` trong `< 3 s`.
3. **Phục hồi sau kill & sau worker crash:** Ngay sau test `R-LOOP` (worker bị `kill()`) và sau một tác vụ giả lập `os._exit(139)` (trả `500`), gọi lại `/extract`, `/pdf` (cặp `contract_old.pdf`/`contract_new.pdf`), `/text` → đều trả `200 OK` khớp chính xác kết quả Baseline 1.
4. **Liveness `/health` khi toàn bộ worker bị treo:** Chiếm hết `MAX_WORKERS = 2` bằng 2 request `R-LOOP` trên 2 thread nền (timeout `2.0 s`), đồng thời gọi `GET /api/v1/health` → trả `200 {"status": "ok"}` trong `< 200 ms`.
5. **Backpressure chống DoS:** Với `MAX_WORKERS=1, MAX_PENDING=1`, gửi 3 request đồng thời → ít nhất 1 request bị từ chối tức thì với `503 SERVER_BUSY` + header `Retry-After`.
6. **Không còn orphan process & tệp tạm:** `monkeypatch` thư mục tạm của worker sang `tmp_path`, ghi lại danh sách PID của các slot trước khi trigger `R-LOOP` timeout → sau khi nhận `504`, xác minh PID cũ đã chết (`OpenProcess`/`GetExitCodeProcess != 259`) và `list(tmp_path.iterdir()) == []`; sau khi đóng `TestClient`, mọi worker PID đều đã thoát.
7. **Hồi quy toàn bộ:** Chạy toàn bộ 92 test cũ + test mới với `PYTHONDONTWRITEBYTECODE=1`; tổng thời gian suite mục tiêu `< 30 s`.

---

## 8. Complexity

- **Phạm vi thay đổi tối thiểu:** 1 module mới (`app/services/worker_pool.py`, ~150 dòng) + chỉnh sửa nhỏ (~10–25 dòng/tệp) tại [config.py](file:///C:/Users/Admin/contract-diff/app/core/config.py), [document_service.py](file:///C:/Users/Admin/contract-diff/app/services/document_service.py), [comparison_service.py](file:///C:/Users/Admin/contract-diff/app/services/comparison_service.py), [main.py](file:///C:/Users/Admin/contract-diff/app/main.py).
- **Zero dependency mới:** 100% thư viện chuẩn Python (`multiprocessing`, `queue`, `threading`, `tempfile`, `ctypes`), không đụng `requirements.txt`, không cần Redis/Celery/broker ngoài.
- **Đúng `coding-style-profile.md`:** Tầng route vẫn mỏng 3–5 dòng; engine/extractor thuần không phụ thuộc FastAPI; service vẫn trả `dict` thuần; cấu trúc lỗi phẳng giữ nguyên D4.

---

## 9. Điểm yếu của chính phương án đề xuất (Self-Critique)

1. **Không phải sandbox bảo mật & vẫn hở RAM trên `R-BOMB` đa luồng:** Process isolation chỉ bảo vệ tiến trình API khỏi treo CPU/crash; 4 request `R-BOMB` (CIDFont `/W [0 200000000 500]`) chạy đồng thời trên 4 worker vẫn có thể chiếm cạn RAM máy chủ trước khi hết 30 s. Để đóng triệt để cần gắn thêm `JOB_OBJECT_LIMIT_PROCESS_MEMORY` (trên Windows Job Object, ví dụ 512 MB/worker) — nhưng đặt ngưỡng quá thấp lại có nguy cơ làm OOM oan PDF hợp lệ 100 trang nhiều ảnh.
2. **Không hủy sớm khi client ngắt kết nối (hệ quả của giữ route `def`):** Nếu client đóng kết nối TCP sau 1 s, worker vẫn chạy cho tới khi xong hoặc hết 30 s mới bị kill, làm lãng phí slot khi bị spam kết nối rồi hủy. Đổi toàn bộ sang `async def` + `asyncio.create_subprocess_exec` giải được điểm này nhưng phá tương thích các unit test đồng bộ hiện có và tăng mạnh độ phức tạp.
3. **Độ phức tạp vòng đời cao hơn PA1 và biên hẹp ở `conn.recv()`:** Tự quản lý `_WorkerSlot` (lazy start, `ready` handshake, `max_tasks` recycle, Job Object `ctypes`) nhiều nhánh lỗi hơn PA1. Ngoài ra, `conn.recv()` sau `conn.poll(remaining)` về lý thuyết không có timeout riêng nếu worker bị đóng băng giữa lúc ghi một thông điệp lớn nhiều MB (thực tế hiếm vì `Connection.send` ghi nguyên khối từ buffer đã pickle, nhưng vẫn là điểm hở lý thuyết trừ khi đổi sang ghi kết quả ra tệp tạm).
4. **Rủi ro đợi hàng đợi lại giữa 3 bước của `compare_document`:** Vì tách `extract(old)` → `extract(new)` → `diff_words` thành 3 lần mượn slot để giữ tương thích test, dưới tải bão hòa một request `/pdf` đã trích xuất xong 2 tệp vẫn có thể phải xếp hàng chờ lại ở bước `diff_words` và dính 504. (Có thể nâng cấp sau bằng context manager mượn 1 slot cho cả request nếu đo thấy nghẽn thực tế.)
5. **Tác động tới thời gian chạy `TestClient` function-scoped:** Đóng/mở `lifespan` ở mỗi test API tạo thêm ~15 s chi phí khởi động lại worker cho bộ test hiện tại nếu không nâng phạm vi fixture trong các tệp test mới.
