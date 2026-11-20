# Isolation Code Review — Claude

Tôi chỉ đọc repo, không sửa file nào. Thí nghiệm chạy trong `C:\Users\Admin\AppData\Local\Temp\claude\7a81e431fe1166c9\3ae8a7db-bd9c-402e-b3dc-61914ab153f4\scratchpad\cr-claude\` (e2–e12), mỗi cái có `timeout` và watchdog `faulthandler` 55 s. Sau thí nghiệm, `tasklist` không còn python nào do tôi tạo, các thư mục `crcl-*` trong %TEMP% đã xóa.
Test suite: `PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider` cho **116 passed in 38.07s**. Cùng lúc có một pytest khác do agent khác khởi chạy từ PowerShell (PID 34628/37724), có thể làm nhiễu số đo thời gian.

## 1. Bảng 8 yêu cầu

| # | Yêu cầu | Kết quả | Bằng chứng |
|---|---|---|---|
| 1 | Deadline thống nhất | **PASS** | `worker.py:111` tính `deadline` đúng 1 lần, ngay sau khi lấy slot. Timer (`:135`) và `poll` (`:137`) cùng dùng `remaining(deadline)`. Test `test_deadline_covers_startup_and_job` pass. Phần chép file/pickle trước `start()` cũng nằm trong ngân sách. |
| 2 | Pipe riêng, không tái dùng IPC | **PASS** | Mỗi lời gọi tạo `Pipe()` mới (`:124`) và đóng ở `release_worker` (`:76`). e4: 3 thread chạy liên tục 30 s, timeout 0,8 s, job ngủ ngẫu nhiên 0–0,8 s, payload 1 B hoặc 100 KB. Kết quả: 17 ok, 45 `WorkerTimeoutError`, **0 exception lạ, 0 child còn sống, 0 thư mục tạm, cả 2 slot đã trả**. |
| 3 | Kiểm soát kích thước kết quả | **PASS** | `recv_bytes(MAX_WORKER_RESULT_BYTES)` (`:139`). CPython `connection.py:364-371` (`_get_more_data`) kiểm `len(buf)+left > maxsize` **trước khi** đọc phần còn lại, nên parent không cấp phát vượt trần. e9: `diff_words` tăng bậc hai (8.000 change mất 23,8 s, 182 B/change). Trong 30 s, kết quả `/pdf` lớn nhất chỉ cỡ 1,6 MiB, nên 32 MiB là dư. |
| 4 | Chỉ release slot khi worker đã được thu hồi | **PASS** (an toàn), có lỗi rò slot F2, F3 | Slot chỉ được trả sau `join` có `exitcode` (`:93-100`) hoặc trong reaper (`:85-87`). e8 (`JOIN_TIMEOUT_SECONDS=0`): reaper chạy 8/8 lần, slot về 2, không còn child hay file tạm. Không có đường nào trả slot sớm, nhưng có hai đường **không bao giờ trả** slot (F2, F3). |
| 5 | Startup stall trước/sau `start()` | **PASS**, có điều kiện (F1, F6) | `test_startup_stall_is_killed[small/large]` pass. e3: pipe bootstrap của `popen_spawn_win32.py:55` chứa tối đa khoảng 4 KB (ghi 4096 B xong ngay, 8192 B bị chặn khi không có reader). prep_data đo được khoảng 0,9 KB nên còn biên. Crash **trong** bootstrap bị xếp nhầm thành timeout (F1). |
| 6 | Không phá response contract | **PASS** (trừ F3) | 3 handler phẳng `main.py:36-58`. `test_worker_errors_have_flat_body` và `test_comparisons_api` pass. Fast-path text giống nhau giữ nguyên (`comparison_service.py:9`). |
| 7 | Coding style và phạm vi | **PASS** | Hàm module-level, không thêm `__init__.py`, import tuyệt đối, giữ nguyên `pages= run_in_worker` cũ. Ghi chú nhỏ: `worker.py` có khoảng 12 dòng comment và docstring, nhiều hơn mức "tối thiểu" của profile §7, nhưng đều giải thích bất biến không hiển nhiên nên chấp nhận được. |
| 8 | Acceptance/regression/H1 | **PASS** | 116/116 pass. H1 của Orchestrator khớp thiết kế. Còn thiếu test cho: crash lúc bootstrap, `Timer.start()` lỗi, nhánh reaper, ngoại lệ trong cleanup. |

## 2. Phân tích race (trọng tâm)

| Kịch bản | Kết luận | Lý do (CPython 3.14) |
|---|---|---|
| Timer callback chạy song song với `finally` | An toàn | `timer.cancel()` rồi `timer.join()` (`:154-157`) xong mới gọi `stop_worker`, nên `kill()` của timer không thể chạy sau `close()`. |
| `kill` trên process đã thoát hoặc đã close | An toàn (trừ exit 259, xem F3) | `Popen.terminate` dùng **handle**, không dùng PID (`popen_spawn_win32.py:126-144`), nên không bị tái dùng PID. Handle chỉ đóng trong `close()`, và `close()` chỉ chạy khi `poll()` đã có returncode (`process.py:186-191`). `_check_closed` chặn kill sau khi close. |
| `_cleanup()` của thread khác (gọi trong `start()`) chạy cùng lúc với `close()` | An toàn | `process.py:61-65` lấy `p._popen` một lần. `close()` chỉ chạy sau `join()`, khi `returncode` đã được cache, nên `poll()` trả ngay mà không chạm vào handle đã đóng. |
| `poll` trả True vì EOF | An toàn | `PeekNamedPipe` hoặc `recv` ném `BrokenPipeError`/`EOFError`, bị bắt ở `:142`. Cờ `timed_out` được set **trước** `kill()` (`:68-71`), nên timeout không bị dán nhãn nhầm thành crash. |
| Kết quả đến đúng lúc hết hạn | Chấp nhận được (F7) | Timer bắn trong lúc `recv`, kết quả hợp lệ bị bỏ và trả 504. Đây là lựa chọn bảo thủ. |
| Ngoại lệ giữa `acquire` (`:109`) và `try` (`:114`) | Rủi ro không đáng kể (F8) | Giữa hai dòng chỉ có `monotonic()`, các phép gán và `Event()`. Async exception chỉ tới main thread, còn endpoint sync chạy trong threadpool. |
| `start()` ném lỗi | An toàn | `child_connection.close()` nằm trong `finally` (`:133-134`). `_popen` chưa được gán nên `pid is None`, và `release_worker` vẫn trả slot. Nếu `CreateProcess` đã chạy nhưng `dump` lỗi: `whandle` bị đóng (`with open(wfd)`), con gặp EOF ở bootstrap và tự thoát. |
| `BaseException` trong cha | Phần lớn an toàn | `except Exception` (`:142`) không bắt `BaseException`, nên `finally` ngoài vẫn dọn dẹp. Riêng `KeyboardInterrupt` rơi đúng vào lúc đang chạy `finally` thì rò slot, nhưng khi đó API cũng đang tắt. |
| Reaper | An toàn | e8 như ở bảng trên. `join()` không timeout là đúng: `TerminateProcess` đã được gọi trước đó. |

## 3. Findings

| ID | Severity | file:dòng | Kịch bản lỗi | Đề xuất sửa tối thiểu |
|---|---|---|---|---|
| F1 | **Medium** [CONFIRMED] | `app/core/worker.py:137` | Worker chết khi interpreter đang bootstrap, trước khi unpickle `child_connection`. Ví dụ: import `__main__`/`sitecustomize` lỗi, thiếu RAM. Lúc đó parent vẫn giữ bản sao đầu ghi, vì `reduce_pipe_connection` gọi `DupHandle(pid=os.getpid())` (`connection.py:1190-1194`, `reduction.py:106-117`). Hậu quả: không có EOF, `poll` chờ hết deadline, trả **504 sau 30 s thay vì 500 ngay**, và slot bị giữ 30 s. e2 (`sitecustomize` gọi `os._exit(7)`, timeout 3 s): 3/3 lần `WorkerTimeoutError` sau 3,0 s. Job crash bình thường cho `WorkerCrashedError` sau 0,24 s. | Chờ trên cả sentinel: `ready = multiprocessing.connection.wait([connection, process.sentinel], remaining(deadline))`. Nếu chỉ sentinel sẵn sàng và `not connection.poll(0)` thì coi là `failed`. Cách này cũng bỏ được việc phụ thuộc vào EOF. Thêm test bằng fixture `stalled_startup` với `os._exit`. |
| F2 | **Medium** [CONFIRMED] | `worker.py:135-136`, `:154-157` | `timer.start()` ném `RuntimeError` (hết thread hoặc tài nguyên). Lúc đó `timer` đã khác `None`, nên `timer.join()` trong `finally` ném "cannot join thread before it is started" và **`stop_worker` không chạy**. Kết quả: rò slot vĩnh viễn, worker vẫn sống (tới watchdog 35 s), còn thư mục tạm, và lỗi gốc bị che. e5: còn 1/2 slot, child sống, còn `contractdiff-*`. | Chỉ gán `timer` sau khi đã start: `t = threading.Timer(...); t.start(); timer = t`. Hoặc trong `finally` dùng `if timer is not None and timer.ident is not None`. |
| F3 | Low [CONFIRMED] | `worker.py:92` | Cleanup không chịu được ngoại lệ. Worker thoát với mã 259 (`STILL_ACTIVE`) thì `kill()` ném `PermissionError` (`popen_spawn_win32.py:130-137`) và thoát khỏi `finally`. Kết quả: rò slot, còn thư mục tạm, trả 500 dạng không phẳng. e12: còn 1/2 slot, còn file tạm, thêm lỗi atexit. Xác suất thấp, nhưng cho thấy **mọi** ngoại lệ trong `stop_worker` đều làm rò slot. | `try: process.kill() except OSError: pass`, rồi dựa vào `join` và `exitcode` như hiện tại. |
| F4 | Low [CONFIRMED] | `worker.py:124-134` | Xác nhận khai báo của tác giả: rò 1 handle cho mỗi lần stall hoặc crash lúc bootstrap. e11: handle count 145→149 sau 4 lần stall, 0 sau 3 lần chạy bình thường. Cùng gốc với F1. | Sửa F1 là đủ để chặn hậu quả về chức năng. Phần rò handle thì ghi tài liệu, hoặc sau này chuyển sang `Listener`/`Client` có authkey. |
| F5 | Low [REASONED] | `worker.py:42` | Watchdog chỉ bật khi đã vào `worker_main`. Worker mồ côi kẹt trong bootstrap (API bị hard-kill) không có chặn trên. H1 chỉ đo trường hợp treo trong job. Thư mục tạm của worker mồ côi (PDF hợp đồng và `job.pickle`) còn lại trên đĩa (H1). | Bước [7] Job Object. Khi API khởi động (lifespan), quét và xóa các `contractdiff-*` cũ hơn `timeout + grace`. |
| F6 | Low [CONFIRMED buffer / REASONED risk] | `worker.py:131` | U5 chỉ đóng khi dữ liệu bootstrap (prep_data + process_obj) nhỏ hơn khoảng 4 KB. Nếu `sys.path`/`argv` lớn (PYTHONPATH dài), `start()` sẽ chặn khi con stall, **trước khi** Timer được bật và khi chưa có handle để kill. | Ghi rõ bất biến này. Có thể thêm assert kích thước bootstrap trong test U5. |
| F7 | Info [REASONED] | `worker.py:146` | Kết quả đến ở sát deadline vẫn bị trả 504. | Ghi tài liệu, không cần sửa. |
| F8 | Info [REASONED] | `worker.py:109-114` | Có khe nhỏ giữa `acquire` và `try`. | Đưa `acquire` xuống ngay trước `try`. |
| F9 | Info | `worker.py` | Không có log khi timeout hoặc crash; parent không ghi gì cả. Traceback của worker chỉ in ra stderr. | Có thể để sau. |

Về khác biệt so với thiết kế (job đi qua `job.pickle` thay vì Pipe): **đồng ý**. Khi đọc CPython tôi thấy nhận định của tác giả đúng. Payload đi qua Pipe không thể gửi an toàn trước khi con lấy được handle. Args lớn làm vượt buffer bootstrap khoảng 4 KB, nên `start()` chặn (e3). Trên Windows, `job.pickle` nằm trong thư mục tạm của chính user, nên rủi ro tiêm pickle không vượt quá rủi ro sẵn có khi cùng user.

## 4. Kết luận

- **R-LOOP: đóng.** PDF tự tham chiếu ở cả 3 vị trí (extract/old/new) trả 504 trong `TIMEOUT + 1,5 s`. H1 với uvicorn thật cho 504 sau 30,5 s, và request hợp lệ ngay sau đó trả 200.
- **R-CPU: đóng.** `test_pathological_text_diff_times_out` pass. Theo e9, `diff_words` tăng bậc hai nên kill cứng là cách duy nhất chặn được.
- **R-TIMEOUT: đóng.** Một deadline cho cả request (yêu cầu 1). Thời gian phản hồi tối đa là deadline + `join(5)`.
- **Rủi ro còn lại:** F1 và F2 (Medium, nên sửa trước khi commit, mỗi cái khoảng 3–5 dòng kèm test); worker mồ côi trong bootstrap và file tạm còn lại (F5, chờ Job Object và dọn khi khởi động); rò handle (F4); biên bootstrap 4 KB (F6); R-BOMB vẫn mở (RAM worker không có trần); unpickle kết quả ở parent nằm ngoài deadline (U1, đã chấp nhận); giới hạn slot tính theo từng API process.
