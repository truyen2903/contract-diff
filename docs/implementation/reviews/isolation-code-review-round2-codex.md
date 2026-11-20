# Isolation Code Review vòng 2 — Codex

**Kết luận: 4 finding FIXED, 2 PARTIAL. Không phát hiện race mới đã xác nhận trong bản sửa. R-TIMEOUT chỉ có thể đóng có điều kiện.**

Review chỉ đọc; không sửa repo, không commit, không để lại process thử nghiệm. Đã đọc brief, thiết kế và ba báo cáo vòng 1.

**Đối chiếu sáu finding của Codex vòng 1**

Các vị trí `worker.py` dưới đây thuộc `app/core/worker.py`. E1–E10 là fault-injection trong bộ nhớ, dùng mã hiện tại và process/transport giả; không phải acceptance với worker thật.

| Finding | Trạng thái | Bằng chứng |
|---|---|---|
| **F1 — Timer.start lỗi làm mất cleanup** | **FIXED** | `worker.py:166–169` chỉ gán `timer` sau `start()` thành công. E1 tiêm `RuntimeError`: nhận `WorkerCrashedError`; worker giả được kill/close, hai đầu Pipe đóng, thư mục được dọn và slot được trả. Test mới tại `tests/test_process_isolation.py:176`. |
| **F2 — exception giữa acquire và try** | **FIXED** | Khởi tạo `Event` trước acquire (`:138–140`), vùng `try` bắt đầu ngay sau nhánh acquire (`:142`); tính deadline nằm trong vùng bảo vệ. E2 tiêm cả `MemoryError` và `KeyboardInterrupt` tại `Event()`: slot vẫn trống. Không bảo đảm chống mọi ngắt bất đồng bộ trong cleanup. |
| **F3 — TEXT_TOO_LONG không fail-fast** | **FIXED** | `app/core/jobs.py:24–27` extract → build text → kiểm giới hạn ngay từng phía. E3: old quá dài trả `TextTooLongError(side="old")`, danh sách parse chỉ chứa old. Test kết hợp old dài/new hỏng tại `tests/test_comparison_service.py:258`. |
| **F4 — decode xong quá hạn vẫn thành công** | **FIXED** | `worker.py:91–94` kiểm đồng hồ sau decode. E4 vô hiệu tác dụng Timer, làm decode mất 0,03 s với timeout 0,01 s: nhận `WorkerTimeoutError`, slot được trả. Điều này sửa phân loại; không cưỡng chế dừng decode ở parent. |
| **F5 — Process.start chưa được giám sát** | **PARTIAL** | Timer vẫn khởi động sau `process.start()` (`:161`, `:166`). E5 tiêm startup chậm: timeout 0,01 s nhưng hàm trả sau **0,080 s**. Test bootstrap tại `tests/test_process_isolation.py:196` chỉ đo preparation data, bỏ authkey và không đo process object; đây là guard cho môi trường test, chưa chứng minh tổng bootstrap của mọi cách triển khai. |
| **F6 — lỗi kill/reaper làm mất ownership** | **PARTIAL** | `kill_worker` bắt `OSError` (`:69–74`); `release_worker` trả slot trong `finally` (`:99–110`). E6a: kill lỗi nhưng worker đã chết → cleanup thành công. **E6b:** worker còn sống, kill lỗi và reaper.start lỗi → `RuntimeError`, slot vẫn bị giữ, không có handoff. E7: connection.close lỗi → slot được trả nhưng process.close và dọn thư mục bị bỏ qua. |

**Kiểm tra các dòng sửa còn lại trong brief**

| Bản sửa | Đánh giá và bằng chứng |
|---|---|
| Startup crash được phát hiện qua sentinel | Đúng hướng, có bằng chứng Windows thật ở E11 bên dưới. `worker.py:86–96`; test mới `test_startup_crash_is_failure_not_timeout`. Rò handle bootstrap vẫn tồn tại như brief đã ghi. |
| Không spawn sau deadline | E10 đặt timeout bằng 0 và buộc Pipe/Process constructor báo lỗi nếu bị gọi: nhận `WorkerTimeoutError`, không gọi constructor, slot được trả. Kiểm tra tại `worker.py:153`. |
| ValueError ngoài danh sách trở thành failure | E9: cùng kết quả `invalid`, `expected_errors=()` → `WorkerCrashedError`; danh sách chứa `ValueError` → ném lại lỗi. Hai service truyền đúng `DOCUMENT_ERRORS`. |
| Pipe một chiều | `worker.py:154` dùng `Pipe(duplex=False)`; không thấy thay đổi sai hướng đọc/ghi. |
| Các rủi ro chủ ý chưa sửa | Xác nhận còn reaper-start failure, cleanup bị `BaseException` ngắt, handle bootstrap rò, dữ liệu tạm sau hard-kill, decode ở parent và thiếu log phía parent. Không coi chúng là regression mới. |

**Race giữa Timer, sentinel và cleanup**

- `timer.cancel() → timer.join() → stop_worker()` tại `worker.py:185–190` vẫn giữ thứ tự đúng: callback kết thúc trước khi process handle được đóng. Timer chỉ kill, không close; không thấy đường chuẩn đọc `process.sentinel` sau `process.close()`.
- Khi chỉ sentinel sẵn sàng, `connection.poll()` tại `:89` mặc định không chờ. E8 mô phỏng ba nhánh: không dữ liệu → `failed`; dữ liệu xuất hiện sau `wait` → đọc thành công; EOF → ngoại lệ để lớp ngoài phân loại.
- **E11 — process và Pipe thật trên Windows:** giữ đầu ghi trong parent, child thoát sớm → `("failed", None)` sau **0,075 s**; child gửi kết quả rồi thoát → đọc đúng kết quả; đóng đầu ghi và child thoát → `EOFError` sau **0,069 s**. Mọi child thử nghiệm đã được chờ và dọn.
- Chưa tái hiện trường hợp kill giữa lúc `recv_bytes` đang đọc dở. Vì vậy **chưa có bằng chứng khép khoảng trống mutation bỏ `child_connection.close()`**; cần giữ dòng `:165` và bổ sung regression cho tình huống này.
- Hai tồn tại cũ cần giữ mở: **F5 — Medium**, thiếu giám sát startup; **F6 — Medium**, thiếu ownership dự phòng khi reaper không khởi động. Sửa tối thiểu F6 là đăng ký worker vào nơi giữ ownership trước handoff và có đường thu hồi khi tạo thread thất bại; không trả slot khi worker còn sống.

**Lệnh và giới hạn kiểm chứng**

- Chạy `PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python -B -m pytest -q -p no:cacheprovider` với supervisor timeout 55 s: dừng **trước collection**, do sandbox không có thư mục tạm ghi được.
- Chạy `pytest.main(...)` qua `.venv/Scripts/python -B -`, thêm `-s`, `-p no:cacheprovider`, watchdog 20 s; chọn `test_text_diff`, `test_text_mapping` và các test service không cần worker: **49 passed, 7 deselected, 0,95 s**. Lượt lọc ban đầu có hai failure do cùng lỗi tạo thư mục tạm; không phải bằng chứng lỗi sản phẩm.
- E1–E11 chạy bằng `.venv/Scripts/python -B -` từ `%LOCALAPPDATA%\Temp`, không tạo file, watchdog 12 s. Fault-injection chỉ chứng minh các nhánh được tiêm.
- **124 passed và H1 là bằng chứng do Orchestrator cung cấp**, chưa được tôi tái chạy thành công trong sandbox này.

**Kết luận về rủi ro**

- **R-LOOP:** có thể đóng cho luồng vận hành đã kiểm chứng theo H1 và acceptance tác giả cung cấp; các nhánh lỗi ownership của F6 vẫn mở.
- **R-CPU:** có thể đóng về chức năng theo acceptance pathological diff trong suite tác giả báo cáo; tôi chưa có lần chạy độc lập acceptance đó ở vòng này.
- **R-TIMEOUT:** **chưa đóng vô điều kiện**. Kết quả decode quá hạn đã được phân loại đúng, nhưng `Process.start()` vẫn có thể chặn trước Timer; chép file, serialize/decode ở parent cũng chưa có khả năng cưỡng chế dừng.
- Rủi ro còn lại: bootstrap lớn hoặc orphan kẹt trước watchdog, rò handle, file hợp đồng tồn đọng sau hard-kill, cleanup không hoàn tất, RAM không có trần cứng và số slot nhân theo số API process.