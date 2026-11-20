# Isolation Code Review vòng 2 — Claude

Tóm tắt: các finding chức năng của tôi ở vòng 1 (F1, F2, F3, F8) đã được sửa và tôi đã chạy lại để xác nhận. Không tìm thấy lỗi race mới. R-LOOP, R-CPU, R-TIMEOUT đều đóng được bằng bằng chứng.

Tôi chỉ đọc repo, không sửa file nào. Thí nghiệm nằm trong `C:\Users\Admin\AppData\Local\Temp\claude\7a81e431fe1166c9\3ae8a7db-bd9c-402e-b3dc-61914ab153f4\scratchpad\cr-claude\`; sau khi chạy không còn process nào của tôi, các thư mục `crcl-*` đã xóa. Các process python còn thấy (PID 38484/17076, 37480/38092) là của agent hoặc dự án khác.
Suite: `PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider` cho **124 passed in 42.30s**.

## 1. Trạng thái các finding vòng 1 của tôi

| ID | Trạng thái | Bằng chứng |
|---|---|---|
| F1: crash lúc bootstrap bị trả 504 sau 30 s | **FIXED** | `worker.py:83-96` chờ cả `[connection, process.sentinel]`. e2 chạy lại: 3/3 lần `WorkerCrashedError` sau **0,04–0,06 s** (vòng 1 là `WorkerTimeoutError` sau 3,0 s). Có test `test_startup_crash_is_failure_not_timeout`. |
| F2: `Timer.start()` lỗi làm rò slot và worker | **FIXED** | `:166-169` chỉ gán `timer` sau khi `start()` thành công. e5 chạy lại: trả `WorkerCrashedError`, 0 child, 0 file tạm, còn đủ 2/2 slot. |
| F3: `kill()` ném lỗi (exit 259) làm rò slot | **FIXED** | `kill_worker` bắt `OSError` (`:69-74`), `release_worker` trả slot trong `finally` (`:109-110`). e12 chạy lại (`os._exit(259)`): `WorkerCrashedError`, 0 file tạm, 2/2 slot, không còn child. |
| F4: rò handle khi startup stall/crash | NOT FIXED (đã chấp nhận) | e2: handle count tăng **+1 mỗi lần** crash lúc bootstrap. Gốc vẫn là `DupHandle(pid=os.getpid())`. Hậu quả chức năng đã hết nhờ F1. |
| F5: không có watchdog trong bootstrap; thư mục tạm còn lại sau hard-kill | NOT FIXED (đã chấp nhận) | `:43` vẫn là điểm đầu tiên bật watchdog. H1 vòng 2 vẫn còn thư mục tạm. |
| F6: biên 4 KB của bootstrap | **PARTIAL** | Xem N1: test mới chỉ đo phần prep_data. |
| F7: kết quả sát deadline bị trả 504 | NOT FIXED (đã chấp nhận) | Nay còn thêm kiểm tra `monotonic() > deadline` sau decode (`:92`), nên quy tắc được áp dụng nhất quán. |
| F8: khe giữa acquire và try | **FIXED** | Biến khởi tạo ở `:138-139`, `try` nằm ngay sau `acquire` (`:140-142`). Giữa hai điểm này không còn câu lệnh nào. |
| F9: không có log | NOT FIXED (đã chấp nhận) | — |

Hồi quy: e4 chạy lại (stress 3 thread × 30 s, timeout 0,8 s) cho 23 ok, 41 timeout, **0 exception lạ, 0 child, 0 file tạm, 2/2 slot**. e8 (nhánh reaper, `JOIN_TIMEOUT_SECONDS=0`) cho 8/8 lần đi qua reaper, slot và file tạm sạch.

## 2. Bản sửa có tạo race mới không

| Kịch bản | Kết luận | Lý do / bằng chứng |
|---|---|---|
| Chỉ sentinel sẵn sàng, sau đó gọi `connection.poll()` | An toàn | `poll(timeout=0.0)` (`connection.py:259`) dùng `PeekNamedPipe`. Có 3 trường hợp: (a) worker đã gửi xong rồi thoát: `WriteFile` đã hoàn tất trước khi process thoát nên dữ liệu đã nằm trong pipe, `poll` thấy được. (b) Pipe gãy: `BrokenPipeError`, bị bắt ở `:174` thành `failed`, rồi `timed_out` quyết định 504 hay 500. (c) Crash lúc bootstrap: không có dữ liệu nên trả `failed` (e2). |
| Dữ liệu đến sau `wait` | An toàn | Message lớn hơn buffer làm `send` của worker chặn tới khi parent đọc, nên worker không thể thoát trước. Message nhỏ thì đã vào buffer trước khi thoát. Worker chỉ có thể chết giữa chừng khi bị timer kill, mà khi đó `timed_out` đã được set nên kết quả là 504. |
| Worker bị kill lúc đang `send` dở | An toàn | r2_trace (kill ở 1,5 s khi worker đang chặn trong `send` 20 MB, parent đọc trễ có chủ đích): message dở **biến mất** (`poll` → False), kết quả là `failed` rồi `WorkerTimeoutError`, không treo. Có giữ `child_connection.close()` hay không thì kết quả như nhau. |
| `process.sentinel` sau `close()` | An toàn | Sentinel chỉ được dùng trong `wait_for_result`, trước `stop_worker`. `close()` chỉ chạy sau khi `exitcode` đã có giá trị. |
| Timer bắn sau khi `wait_for_result` đã trả `ok` | An toàn | Lúc đó deadline đã qua. `:178` thấy `timed_out` nên trả 504, nhất quán với kiểm tra ở `:92`. Worker bị kill sau khi đã gửi xong là vô hại. |
| `release_worker` trả slot trong `finally` | An toàn | Chỉ được gọi khi `exitcode` đã có giá trị hoặc khi chưa spawn (`:119-128`). Nếu `close()` hay `rmtree` lỗi thì slot vẫn được trả, nhưng worker đã chết nên không vi phạm yêu cầu 4. |
| `remaining(deadline) > 0` rồi `Timer(remaining)` | An toàn | Nếu hết hạn ngay giữa lúc kiểm tra và lúc start, Timer có interval 0 sẽ kill ngay và trả 504. |

**Finding mới**

| ID | Severity | file:dòng | Vấn đề | Đề xuất |
|---|---|---|---|---|
| N1 | Low [CONFIRMED] | `tests/test_process_isolation.py:196-202` | Test chỉ đo `prep_data` (980 B). `start()` thực tế còn ghi thêm `SpawnProcess` khoảng 608 B (chứa đường dẫn `job.pickle`, nên dài thêm theo `%TEMP%`). r2_boot (bọc `popen_spawn_win32.reduction.dump`) đo được **tổng 1.588 B**. Ngưỡng 2048 cho riêng prep_data không phản ánh đúng biên thật khoảng 4 KB. Test cũng chỉ đo `argv`/`sys.path` của pytest, không đo của uvicorn. | Đo tổng cả hai lần `dump` bằng cách bọc `reduction.dump` như r2_boot, assert tổng < 4096 (hoặc < 3072 để còn biên). |
| N2 | Info [CONFIRMED + REASONED] | `worker.py:160-165` | Xác nhận ghi chú của Orchestrator: mutation bỏ `close()` không bị test bắt, và r2_trace cho thấy trường hợp kill lúc `send` dở cũng không treo. Dòng này chỉ còn bảo vệ một cửa sổ rất hẹp: giữa `PeekNamedPipe` và `ReadFile(left)` + `GetOverlappedResult(True)` không có timeout (`connection.py:368-373`). Nếu parent còn giữ đầu ghi thì parent treo vĩnh viễn, vì timer chỉ bắn một lần. | Giữ dòng `close()`. Nên sửa comment cho đúng cửa sổ trên. Không thể tái hiện được một cách tất định. |
| N3 | Info [REASONED] | `tests/...:187-193` | `test_kill_error_does_not_leak_slot` chỉ kiểm worker tự thoát. Trường hợp `kill()` lỗi trên worker đang treo sẽ đi vào reaper `join()` vô hạn và mất slot vĩnh viễn. Điều này đúng với yêu cầu 4 nhưng là mất năng lực xử lý; hành vi này đã được ghi là rủi ro chấp nhận. | Ghi tài liệu, không cần sửa. |

## 3. Kết luận
- **R-LOOP: đóng.** PDF tự tham chiếu ở 3 vị trí trả 504 (test). H1 vòng 2: 504 sau 30,55 s, request sau đó vẫn chạy được.
- **R-CPU: đóng.** `test_pathological_text_diff_times_out` pass. Kill cứng hoạt động, e4 không có rò rỉ.
- **R-TIMEOUT: đóng.** Một deadline duy nhất (`:143`), dùng chung cho Timer, `wait` và kiểm tra sau decode. Không spawn khi đã hết hạn. Thời gian phản hồi tối đa là deadline + `join(5)`.
- **Rủi ro còn lại:**
  - Rò 1 handle mỗi lần crash hoặc stall lúc bootstrap (F4).
  - Worker mồ côi kẹt trong bootstrap không có chặn trên, và thư mục tạm (PDF hợp đồng) còn lại sau hard-kill API (F5). Cần Job Object và dọn `contractdiff-*` khi khởi động.
  - U5 chỉ "đóng có điều kiện": bootstrap 1,6 KB so với buffer khoảng 4 KB (N1).
  - Reaper không start được, hoặc `kill()` thất bại trên worker đang treo, thì mất slot vĩnh viễn.
  - Kết quả sát deadline bị trả 504 (F7).
  - Unpickle kết quả ở parent (U1).
  - R-BOMB (RAM worker không có trần cứng).
  - Không có log (F9).
  - Slot được tính theo từng API process.
