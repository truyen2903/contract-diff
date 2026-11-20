# Process Isolation — Thiết kế khuyến nghị (đóng R-LOOP, R-CPU, R-TIMEOUT)

Trạng thái: **đã triển khai theo quyết định U1–U5 của tác giả; qua 2 vòng code review (Codex, Claude, Antigravity). Chưa commit.** Khác biệt khi triển khai: §8. Kết quả kiểm thử và rủi ro: `phase-a-report.md`.
Bằng chứng và tranh luận: `reviews/process-isolation-debate.md` (tóm tắt) và `reviews/iso-round{1,2,3}-*.md` (nguyên văn).

> Process isolation ở đây bảo vệ **tính sẵn sàng** của API (kill được tác vụ treo, cách ly crash). Nó **không phải OS-level sandbox**: worker chạy cùng tài khoản, cùng quyền filesystem/mạng, RAM không bị giới hạn cứng (R-BOMB vẫn mở).

## 1. Dữ kiện nền đã kiểm chứng

| # | Dữ kiện | Nguồn |
|---|---|---|
| F1 | `Future.result(timeout)` hết hạn nhưng worker `ProcessPoolExecutor` vẫn sống; kill một worker làm pool vỡ (`BrokenProcessPool`) cho request khác | Orchestrator, Claude R1 §4.5, Antigravity R1 §4 |
| F2 | `Process.kill()` (`TerminateProcess`) dừng được worker kẹt R-LOOP (exitcode −15) | Orchestrator, cả 3 agent |
| F3 | Spawn + import extractor/engine ≈ 0,47–0,6 s; nếu import cả service (FastAPI) ≈ 1,1 s | Orchestrator, Claude R2 E1, Codex R2 E2 |
| F4 | `send`/`recv` của Pipe có thể chặn ngoài `poll`; `threading.Timer(deadline, kill)` ở parent gỡ được (`BrokenPipeError` sau 2,01 s) | Codex R2 E1, Claude R2 E2 |
| F5 | Timer kill **chỉ** gỡ được `recv` nếu parent đã `close()` đầu pipe phía con sau `start()` | Claude R3 E3 |
| F6 | Windows: `unlink` file tạm khi worker còn sống hoặc ngay sau `kill()` trước `join()` → `PermissionError [WinError 32]`; sau `join()` thì thành công | Antigravity R1 §4 |
| F7 | Monkeypatch ở pytest **không** sang được worker `spawn` | Codex R2 E3 |
| F8 | Watchdog `faulthandler.dump_traceback_later(t, exit=True)` trong worker kết thúc được worker mồ côi đang kẹt R-LOOP sau khi parent chết | Claude R1 §4.2 |
| F9 | Truyền PDF 15 MiB bằng bytes qua Pipe tăng đỉnh RAM ~+42 MiB (parent+child), file tạm chép theo khối 64 KiB ~+2 MiB | Antigravity R3 |
| F10 | `span_to_page_locations` trường hợp xấu (100 trang × 50 000 change) ≈ 2,2 s CPU — không được để ở parent | Antigravity R3 |

## 2. So sánh phương án

| Tiêu chí | Process-per-request | Persistent pool (`ProcessPoolExecutor`/`Pool`) | Dedicated subprocess worker / pool có giám sát |
|---|---|---|---|
| Correctness | Process sạch mỗi request | Đúng khi không timeout | Đúng nếu giao thức/ownership/restart đầy đủ; rủi ro rò trạng thái nhỏ |
| Hard timeout | Có: timer → `kill()` | **Không** (F1) | Có: kill đúng worker |
| Worker termination | Chỉ ảnh hưởng request đó | Kill một worker phá cả pool | Kill + respawn từng slot |
| Concurrency | Semaphore chặn spawn | Hàng đợi nội bộ không giới hạn | Tự quản slot |
| Windows | `spawn` chạy được | Được, nhưng `shutdown` để worker treo sống | Được; cần Job Object để chống orphan |
| Memory | ~35–50 MiB/worker, chỉ khi có request | N × ~39 MiB thường trực | N × ~39 MiB thường trực + recycle |
| Startup latency | ~0,5 s/request (F3) | ~0 khi ấm | ~0,8 s một lần; **mất ấm sau mỗi kill** và trong test |
| Maintainability | Tốt (~80–100 LOC) | Dễ viết, sai về bản chất | Kém nhất (~150 LOC vòng đời + `ctypes`) |
| Độ phức tạp | Thấp–vừa | Thấp nhưng không giải bài toán | Cao |
| Kết luận | **Chọn** | **Loại** | Cửa thoát khi benchmark H3b fail |

## 3. Phương án khuyến nghị

**Process-per-request, một job thuần cho mỗi request, đặt sau interface `run_in_worker` để có thể đổi ruột sang pool có giám sát mà không sửa service.**

### 3.1 Ranh giới
- **Parent (FastAPI):** validation HTTP, `validate_pdf_stream` cho **cả hai** PDF trước mọi parse, fast-path `/text` khi `old_text == new_text`, admission, chép file tạm, snapshot giới hạn hiệu lực, ánh xạ lỗi miền → `HTTPException`, kiểm deadline, cleanup.
- **Worker (không import FastAPI):** đúng **một** lời gọi hàm thuần cho mỗi request:
  - `/extract`: `extract_pdf_file(path, max_pages)` → `list[dict]`
  - `/pdf`: `compare_pdf_files(old_path, new_path, max_pages, max_text_chars)` → extract ×2 (fail-fast `TEXT_TOO_LONG` ngay sau tệp `old`), `build_document_text`, `diff_words`, `span_to_page_locations` (F10) → `(old_pages, new_pages, changes)`
  - `/text`: `diff_words(old_text, new_text)`
- Lỗi miền trả về có ghi **phía** (`old`/`new`) để parent gắn đúng tên tệp vào `detail`: `InvalidPDFError`, `PDFPageLimitError`, `TextTooLongError`. `MemoryError`/`OSError` không bị đổi thành 400 (giữ D10).

### 3.2 IPC
- **Vào:** PDF chép từ `UploadFile.file` theo khối 64 KiB sang thư mục tạm riêng của request (`tempfile.mkdtemp()`), đóng tệp trước khi spawn; worker nhận **đường dẫn** + giới hạn (tham số nhỏ, không bao giờ truyền `UploadFile`/file handle). Text `/text` gửi qua Pipe sau khi worker chạy.
- **Ra:** kết quả qua `Pipe` (`poll(remaining)` rồi `recv`). Không dùng `result.json` (Codex giữ quan điểm khác — xem §5).
- Parent `close()` đầu pipe phía con ngay sau `start()` (F5).

### 3.3 Deadline, kill, cleanup (`app/core/worker.py`)
```text
acquire slot (non-blocking) ──fail──► WorkerBusyError (503)
deadline = monotonic() + COMPARISON_TIMEOUT_SECONDS          # một ngân sách cho cả request
Pipe(); Process(target=worker_main, daemon=True); start(); close(child end)
Timer(remaining, on_timeout).start()      # on_timeout: timed_out.set(); process.kill()
send(job) → poll(remaining) → recv()
  EOFError/OSError/BrokenPipe: timed_out? → WorkerTimeoutError (504) : WorkerCrashedError (500)
  recv ok nhưng timed_out đã set → WorkerTimeoutError
finally: timer.cancel(); process.kill(); process.join(5)
         nếu vẫn sống → giữ slot, giao cho reaper thread join rồi mới nhả slot
         close pipe; xóa thư mục tạm (sau join — F6); release slot
```
- Worker: lệnh đầu tiên trong `worker_main` là `faulthandler.dump_traceback_later(timeout + 5, exit=True)` (F8); module worker không import nặng ở top-level.
- `WorkerTimeoutError` kế thừa `Exception` (không phải `TimeoutError`, vì `TimeoutError ⊂ OSError`).
- Args truyền vào `Process` chỉ gồm đường dẫn/số → `start()` không chặn vì payload bootstrap lớn.

### 3.4 Admission
- `BoundedSemaphore(MAX_ACTIVE_WORKERS).acquire(blocking=False)` **trong service**, sau khi body đã nhận và validate rẻ; hàng đợi chờ = 0.
- Đề xuất mặc định `MAX_ACTIVE_WORKERS = 2` (bảo thủ, vì RAM worker chưa có trần cứng); nâng lên 4 sau khi acceptance đo peak RSS — **chưa thống nhất** (§5).
- Giới hạn tính **theo từng API process**; chạy nhiều Uvicorn worker sẽ nhân lên — ghi tài liệu.

### 3.5 Hợp đồng lỗi (bổ sung, không đổi các mã Phase A)

| Tình huống | HTTP | `error_code` | Ghi chú |
|---|---|---|---|
| Input sai / PDF hỏng / quá size, trang, text | 400/413/422 | như Phase A | không đổi |
| Hết ngân sách 30 s | **504** | `PROCESSING_TIMEOUT` | **không** `Retry-After` (cùng input sẽ timeout lại) |
| Hết slot | **503** | `SERVER_BUSY` | `Retry-After: 5` |
| Worker crash, EOF bất thường, `MemoryError`/`OSError` | **500** | `PROCESSING_FAILED` | body phẳng D4; không lộ traceback/đường dẫn tạm |

Route xử lý giữ `def` (tối đa `MAX_ACTIVE_WORKERS` thread chờ); `/health` giữ `async def`.

### 3.6 Chống orphan
- **Bắt buộc:** watchdog trong worker (orphan sống tối đa ≈ timeout + 5 s nếu API bị hard-kill).
- **Khuyến nghị (bước riêng sau khi lõi qua acceptance):** Windows Job Object `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` qua `ctypes` (handle không kế thừa, đủ `argtypes`/`restype`, kiểm mọi giá trị trả về). Bắt buộc hay không — **chưa thống nhất** (§5).

## 4. Dependency graph (thứ tự triển khai)

```text
[1] app/core/config.py  (COMPARISON_TIMEOUT_SECONDS, MAX_ACTIVE_WORKERS)
        │
[2] app/core/jobs.py    (hàm thuần: extract_pdf_file, compare_pdf_files; TextTooLongError)
        │                 phụ thuộc: extractors/pdf_extractor, engines/text_diff, engines/text_mapping
[3] app/core/worker.py  (run_in_worker, worker_main, WorkerBusy/Timeout/CrashedError)
        │
[4] app/services/document_service.py, comparison_service.py  (temp file, run_in_worker, map lỗi)
        │
[5] app/main.py         (handler 503/504/500)
        │
[6] tests: cập nhật test phụ thuộc monkeypatch + tests/test_process_isolation.py + pytest.ini
        │
[7] (tùy chọn/khuyến nghị) Windows Job Object trong worker.py + harness API hard-kill
        │
[8] docs: phase-a-report.md (hợp đồng lỗi, rủi ro), coding-style-profile (ngoại lệ có chủ đích)
```

## 5. Vấn đề chưa thống nhất (cần tác giả quyết)

| # | Vấn đề | Lập trường | Đề xuất Orchestrator |
|---|---|---|---|
| U1 | Kết quả qua Pipe hay `result.json` | Claude + Antigravity: Pipe + timer; Codex: file, vì decode ở parent không bị deadline bảo vệ | Pipe + timer. Cả `json.loads` lẫn unpickle đều chạy ở parent ngoài deadline; output do code của ta sinh, tuyến tính. Ghi rõ đây là khoảng hở còn lại. |
| U2 | Admission: gate ASGI trước body (Codex) vs trong service (Claude, Antigravity) | Gate trước body tiết kiệm băng thông nhưng mở lỗ slowloris giữ slot | Trong service. Giới hạn kết nối thuộc tầng server (`uvicorn --limit-concurrency`, body limit có sẵn). |
| U3 | Số slot 2 (Codex) hay 4 (Claude, Antigravity) | Chưa đo peak RSS của toàn pipeline | 2 mặc định, cấu hình được; nâng sau khi đo |
| U4 | Job Object bắt buộc (Codex) / khuyến nghị (Antigravity) / tùy chọn (Claude) | Watchdog đã chặn trên ≈ 35 s; cửa sổ spawn → assign chưa được chứng minh | Bước [7] riêng, sau lõi. Bắt buộc nếu bạn yêu cầu worker chết **ngay** cùng API. |
| U5 | Cửa sổ startup trước khi `start()` trả handle (Codex: NEEDS EXPERIMENT) | Args nhỏ nên khó chặn, nhưng chưa có thí nghiệm | Viết acceptance test riêng; chưa tuyên bố đóng |

## 6. Danh sách file cần sửa

| File | Thay đổi |
|---|---|
| `app/core/config.py` | `COMPARISON_TIMEOUT_SECONDS = 30.0`, `MAX_ACTIVE_WORKERS = 2` |
| `app/core/jobs.py` (mới) | hàm job thuần + `TextTooLongError`; không import FastAPI |
| `app/core/worker.py` (mới) | `run_in_worker`, `worker_main`, 3 exception, semaphore, timer, watchdog, cleanup |
| `app/services/document_service.py` | `extract_document`: validate → chép file tạm → `run_in_worker(extract_pdf_file, …)` → map lỗi |
| `app/services/comparison_service.py` | `compare_text`: fast-path + `run_in_worker(diff_words, …)`; `compare_document`: validate ×2 → file tạm → `run_in_worker(compare_pdf_files, …)` → map lỗi theo phía |
| `app/main.py` | handler `WorkerBusyError`→503, `WorkerTimeoutError`→504, `WorkerCrashedError`→500 |
| `tests/test_comparison_service.py` | đổi đích monkeypatch của `test_compare_document_checks_both_files_before_extracting` (giữ ý nghĩa) |
| `tests/test_process_isolation.py` (mới) | acceptance (§7) |
| `pytest.ini` (mới) | `faulthandler_timeout`, `faulthandler_exit_on_timeout = true` |
| `docs/implementation/phase-a-report.md` | hợp đồng lỗi 503/504/500, cập nhật rủi ro |

Không đổi: route, schema response, `pdf_extractor.py`, `text_diff.py`, `text_mapping.py`, `requirements.txt` (chỉ stdlib).

## 7. Kế hoạch kiểm thử

Quy tắc an toàn: workload treo **chỉ** chạy trong worker con; process pytest chỉ chờ ở điểm có chặn trên. Test hạ timeout bằng `monkeypatch.setattr(config/worker, "COMPARISON_TIMEOUT_SECONDS", 2)` — có hiệu lực vì deadline do parent đọc và thi hành (F7). `pytest.ini` bật `faulthandler_timeout` + `exit_on_timeout` làm lưới thứ hai. Fixture kiểm `multiprocessing.active_children() == []` sau mỗi test.

| # | Acceptance test (yêu cầu bắt buộc) | Kỳ vọng |
|---|---|---|
| A1 | PDF tự tham chiếu tại `/extract`, `/pdf` (vị trí `old` và `new`) | 504 `PROCESSING_TIMEOUT` trong < timeout + 1,5 s; PID worker đã chết |
| A2 | `/text` pathological (`"a b "*8500` vs biến thể) | 504 trong < timeout + 1,5 s |
| A3 | Worker bị kill (A1) / crash (`os._exit`) rồi gửi request hợp lệ | request sau 200, `/pdf` fixture đúng 5 thay đổi |
| A4 | Request hợp lệ (fixture, tiếng Việt, owner-only encrypted) | kết quả giống hệt trước isolation |
| A5 | Health trong khi mọi slot bị PDF treo chiếm | `/health` 200 trong < 200 ms |
| A6 | Không orphan / file tạm | sau timeout: `active_children()==[]`, thư mục tạm (monkeypatch sang `tmp_path`) rỗng |
| A7 | Hết slot | request thêm nhận 503 `SERVER_BUSY` + `Retry-After` tức thì, không spawn thêm |
| A8 | Phân loại lỗi | PDF hỏng → 400; `MemoryError`/`OSError` trong worker → 500 `PROCESSING_FAILED`; timeout → 504 |
| A9 | Pipe-end regression (F5) | timeout vẫn kích hoạt khi worker treo trước khi gửi kết quả |
| A10 | Startup stall (U5) | worker treo trong bootstrap vẫn bị kill trước deadline |
| A11 | Regression | 92 test hiện có pass (+ test mới); ghi thời gian suite (dự kiến ~13–25 s) |
| H1 | Harness thủ công (không chạy trong CI): uvicorn thật, hard-kill API khi worker đang treo | worker tự thoát ≤ timeout + 5 s (hoặc ngay nếu có Job Object) |

Benchmark H3b (cặp PDF 20 trang đại diện, gồm HTTP + spawn mỗi request) chạy sau khi tích hợp; p95 ≥ 3 s là điều kiện xem xét chuyển sang pool có giám sát.

## 8. Triển khai — khác biệt so với thiết kế (có bằng chứng)

Quyết định của tác giả: U1 Pipe + Timer, PDF vào qua file tạm; U2 admission trong service; U3 `MAX_ACTIVE_WORKERS = 2`; U4 Job Object để bước hardening riêng (chưa làm); U5 phải có acceptance test.

| # | Thiết kế | Triển khai | Lý do / bằng chứng |
|---|---|---|---|
| D1 | Text `/text` và job gửi qua Pipe sau `start()` | Job + args ghi vào `job.pickle` trong thư mục tạm của request; Pipe (`duplex=False`) **chỉ** chở kết quả | Thí nghiệm U5: worker kẹt lúc khởi động làm `send` 2 MB chặn mãi **kể cả sau `kill()`**, vì trên Windows `reduce_pipe_connection` nhân bản handle đầu con vào chính parent (`DupHandle(pid=os.getpid())`) cho tới khi con unpickle. `Process.start()` với args 100 KB chặn 20 s khi con kẹt (args 10 B: 0,05 s). |
| D2 | `poll(remaining)` + EOF | `multiprocessing.connection.wait([connection, process.sentinel], remaining)` | Cùng nguyên nhân D1: worker crash trước khi nhận đầu pipe không tạo EOF → trước khi sửa trả 504 sau 30 s (review vòng 1: Claude F1, Antigravity F2). |
| D3 | Thứ tự lỗi `/pdf` như Phase A | Fail-fast: extract → ghép → kiểm `TEXT_TOO_LONG` cho `old` rồi mới parse `new` | Đúng §3.1; review vòng 1 (Codex F3, Antigravity F7). |
| D4 | Worker trả lỗi miền | `run_in_worker(..., expected_errors=...)`; `ValueError` khác → 500 `PROCESSING_FAILED` | Review vòng 1 (Antigravity F6). |
| D5 | Kiểm `timed_out` sau `recv` | Kiểm thêm đồng hồ trước khi đọc và sau khi decode; không spawn khi đã hết hạn | Timer có thể trễ khi decode giữ GIL (Codex F4); spawn vô ích sau deadline (Antigravity F8); decode 32 MiB vô ích (Antigravity vòng 2). |
| D6 | `finally` cleanup | Timer chỉ được ghi nhận sau khi `start()` thành công; `kill()` lỗi được bỏ qua và `join` quyết định; slot trả trong `finally` của `release_worker`, thư mục tạm xóa trước tiên | Review vòng 1: cả ba agent (Timer.start lỗi, kill lỗi). |
| D7 | Trần kết quả chưa định | `MAX_WORKER_RESULT_BYTES = 32 MiB` qua `recv_bytes(maxlength)` | Đo: diff tăng bậc hai, trong 30 s kết quả lớn nhất ≈ 1–2 MiB (Claude e9, đo của Orchestrator). |

U5 sau triển khai: worker kẹt **sau** khi `start()` trả về → kill đúng hạn (test, payload 1 B và 2 MB); crash lúc khởi động → 500 ngay. Kẹt **trước** khi `start()` trả về chỉ được loại trừ khi dữ liệu bootstrap < buffer pipe ~4 KiB (đo 1,5 KiB; test canh `< 3 KiB`) — U5 **đóng có điều kiện**.

Mutation `child_connection.close()`: sau D2, bỏ dòng này không còn test nào bắt (handle tự đóng khi hàm trả về). Dòng được giữ để `recv_bytes` đang đọc dở thấy EOF nếu worker bị kill giữa lúc gửi kết quả; Claude vòng 2 không tái hiện được treo trong trường hợp này.
