# Isolation Code Review — Codex

**Kết luận: Request changes.** Có lỗi làm mất slot vĩnh viễn khi khởi động timer thất bại, sai thứ tự kiểm tra `TEXT_TOO_LONG`, và khoảng hở khi kiểm deadline. U5 chưa có đủ bằng chứng cho trường hợp chính `Process.start()` bị kẹt.

Review chỉ đọc; không sửa file, commit hay để lại tác vụ nền.

## Đánh giá 8 yêu cầu

| # | Yêu cầu | Kết quả | Bằng chứng |
|---|---|---|---|
| 1 | Deadline thống nhất, không reset | **FAIL** | Một deadline được tạo tại `app/core/worker.py:111`, nhưng timer chỉ bắt đầu sau `start()` tại dòng 135. Dòng 146 chỉ kiểm cờ timer, không kiểm lại đồng hồ. E4 trả thành công sau 0,223 s với timeout 0,03 s. |
| 2 | Pipe riêng, không tái dùng sau lỗi | **PASS** | Mỗi lần gọi tạo Pipe mới tại `worker.py:124`; đầu con đóng trong `finally` tại dòng 134; không có pool hay IPC dùng lại. |
| 3 | Kiểm soát kích thước kết quả IPC | **PASS** | `worker.py:139` dùng `recv_bytes(MAX_WORKER_RESULT_BYTES)`; trần 32 MiB tại `config.py:10`. Đã đối chiếu mã `PipeConnection._get_more_data` của Python đang cài: kiểm kích thước trước khi đọc phần còn lại. Đây là giới hạn byte truyền, không phải giới hạn RAM sau unpickle. |
| 4 | Thu hồi worker và quản lý slot an toàn | **FAIL** | Luồng bình thường có `kill → join → close → release`, nhưng lỗi timer/reaper và exception trước `try` làm mất quyền quản lý tài nguyên; E2, E5, E7. |
| 5 | Startup stall trước/sau `start()` trả về | **FAIL** | `tests/test_process_isolation.py:149` kiểm interpreter stall với bootstrap nhỏ; chưa buộc chính `start()` phải chặn. Timer tại `worker.py:135` không bảo vệ được dòng 131. E6 xác nhận bằng fault-injection. |
| 6 | Giữ response contract | **FAIL** | `jobs.py:20` parse cả hai PDF trước khi kiểm độ dài tại dòng 30. E1 qua API trả 400 cho `new` hỏng dù `old` đã vượt giới hạn và phải fail-fast bằng 422. |
| 7 | Coding style và phạm vi | **PASS** | Job, điều phối worker và HTTP handler được tách rõ; không thêm dependency. Các exception phục vụ hợp đồng lỗi có lý do. Không thấy vấn đề phong cách đủ mức chặn merge trong phạm vi được giao. |
| 8 | Acceptance, regression, Uvicorn thật | **FAIL — thiếu bằng chứng đầy đủ** | Chạy được **49 test regression**. Suite đầy đủ dừng trước collection vì sandbox không cho tạo file tạm. H1 là bằng chứng do brief cung cấp, chưa được tôi tái chạy; acceptance còn thiếu các nhánh lỗi ownership nêu dưới. |

## Findings

`[CONFIRMED]` nghĩa là đã tái hiện; với fault-injection, kết luận chỉ áp dụng cho nhánh lỗi được tiêm. `[REASONED]` nghĩa là suy luận từ mã và vòng đời CPython.

| ID | Severity | file:dòng | Kịch bản lỗi cụ thể | Đề xuất sửa tối thiểu |
|---|---|---|---|---|
| F1 | **High** | `app/core/worker.py:135`, `:157` | **[CONFIRMED — E5]** Worker đã khởi động, nhưng `Timer.start()` ném `RuntimeError`. Exception được bắt, rồi `finally` gọi `timer.join()` trên thread chưa chạy. `join()` ném tiếp, nên dòng 158 không chạy: worker không bị dừng, slot không trả và file tạm không được dọn. Hai lần lỗi có thể làm mọi request cần worker nhận 503 vĩnh viễn. | Ghi nhận timer đã khởi động thành công; chỉ join khi phù hợp. Đặt `stop_worker()` trong một `finally` độc lập để lỗi xử lý timer không bỏ qua cleanup. |
| F2 | **Medium** | `app/core/worker.py:111`, `:113`, `:114` | **[CONFIRMED — E2]** Slot đã acquire nhưng chưa vào `try`. Tiêm `MemoryError` hoặc `KeyboardInterrupt` khi tạo `threading.Event()` đều để semaphore mất một slot vĩnh viễn, dù chưa tạo worker. | Bắt đầu vùng bảo vệ ownership ngay sau acquire; mọi khởi tạo có thể ném lỗi phải nằm trong vùng được cleanup. |
| F3 | **High** | `app/core/jobs.py:20`, `:28` | **[CONFIRMED — E1]** `old` vượt giới hạn text nhưng `new` vẫn được parse trước. Với `new` hỏng, API trả **400 `INVALID_OR_ENCRYPTED_PDF` của new**, thay vì **422 `TEXT_TOO_LONG` của old**. **[REASONED]** Nếu `new` tự tham chiếu, lỗi xác định được của old sẽ thành timeout 504 và giữ slot hết ngân sách. | Trong cùng vòng lặp mỗi phía: extract → build text → kiểm giới hạn ngay, rồi mới xử lý phía tiếp theo. Thêm test old quá dài kết hợp new hỏng/new treo. |
| F4 | **Medium** | `app/core/worker.py:139`, `:146`, `:155` | **[CONFIRMED — E4]** Cờ timer phụ thuộc lịch chạy thread. Khi unpickle giữ GIL qua deadline, parent có thể kiểm thấy cờ chưa set rồi cancel timer và trả thành công quá hạn. Payload pickle 16.018.217 byte, dưới trần hiện tại, đã trả thành công sau **0,223 s** với timeout **0,03 s**. | Kiểm thêm `time.monotonic() >= deadline` sau decode và trước quyết định trả kết quả. Việc này bảo đảm phân loại 504; khoảng hở thời gian decode vẫn cần được ghi nhận theo U1. |
| F5 | **Medium** | `app/core/worker.py:131`, `:135`; `tests/test_process_isolation.py:149` | **[CONFIRMED bằng fault-injection — E6; REASONED với OS thật]** Timer chưa tồn tại trong lúc `Process.start()` chạy. Tiêm startup chậm 0,25 s với timeout 0,02 s khiến hàm chỉ trả sau 0,251 s. Args nhỏ giảm nguy cơ nhưng không tạo chặn trên; CPython còn truyền `prep_data`, gồm `sys.path` và `sys.argv`. | Thêm acceptance thực sự làm `start()` chặn. Muốn tuyên bố đóng U5 cần cơ chế giám sát startup có ownership rõ; trước đó phải giữ U5 mở. |
| F6 | **Medium** | `app/core/worker.py:92`, `:96`, `:98` | **[CONFIRMED — E3, E7]** `kill()` ném lỗi thì không còn cleanup/handoff. Nếu join hết hạn và khởi động reaper thất bại vì không tạo được thread, hàm thoát mà không có reaper quản lý worker; slot cũng không bao giờ được trả sau khi worker chết. | Giữ worker trong danh sách ownership trước khi handoff; chỉ đánh dấu bàn giao khi thành công. Có đường xử lý lỗi kill và reaper-start; không release sớm khi worker còn sống. |

## Bằng chứng thực thi

Các thí nghiệm chạy trong bộ nhớ, từ thư mục tạm ngoài repo, với `-B`, `PYTHONDONTWRITEBYTECODE=1` và watchdog 10–15 s; không tạo worker thật trong fault-injection.

- **E1:** Dùng PDF thật dựng trong bộ nhớ, gọi API qua `TestClient`; thay transport worker bằng lời gọi inline. Giới hạn 10 ký tự, old có 11 ký tự, new hỏng → **400**, detail chỉ `new.pdf`.
- **E2:** Tiêm lỗi tại `threading.Event()` → `slot_free=False` cho cả `MemoryError` và `KeyboardInterrupt`.
- **E3/E7:** Tiêm lỗi `kill()` và lỗi khởi động reaper → slot vẫn bị giữ, không có handoff thành công.
- **E4:** Dùng `pickle.loads` thật, transport/process giả và kéo dài khoảng chuyển thread để tái hiện lịch chạy timer trễ → `SUCCESS_AFTER_DEADLINE`.
- **E5:** Tiêm lỗi `Timer.start()` → `cannot join thread before it is started`; `killed=False`, `closed=False`, `slot_free=False`.
- **E6:** Tiêm độ trễ trong `Process.start()` → timeout 0,02 s nhưng thời gian thực 0,251 s.

Các lệnh kiểm thử, đều dùng `.venv/Scripts/python.exe -B`:

| Lệnh | Kết quả |
|---|---|
| `-m pytest -q -p no:cacheprovider` — watchdog ngoài 55 s | Dừng trước collection: `FileNotFoundError: No usable temporary directory`; **không kết luận test fail do code**. |
| `pytest.main(['-q','-s','-p','no:cacheprovider','-o','faulthandler_timeout=20','tests/test_text_diff.py','tests/test_text_mapping.py'])` | **21 passed**, 0,06 s. |
| Cùng cấu hình trên, `tests/test_comparison_service.py`, lọc `extract_pdf or validate_pdf_stream or config_values_follow_plan_v2 or checks_both_files_before_extracting or compare_text_identical` | **28 passed, 6 deselected**, 0,89 s. |

## Kết luận về các rủi ro

- **R-LOOP:** H1 trong brief chứng minh đường chạy thông thường kill được PDF treo, giữ health phản hồi và phục hồi request sau đó. Có thể xác nhận biện pháp giảm thiểu hoạt động; **chưa đóng hoàn toàn** khi ownership và startup còn các nhánh lỗi trên.
- **R-CPU:** Tác vụ diff đã chuyển sang process riêng; acceptance cho pathological text có trong mã. **Chưa đủ bằng chứng độc lập để đóng**, vì acceptance đó không chạy được trong sandbox này.
- **R-TIMEOUT:** **Chưa đóng**: còn khoảng trước `start()` trả về và trường hợp trả thành công sau deadline.

Thứ tự `timer.cancel() → timer.join() → stop_worker()` xử lý đúng race callback đang chạy trong đường bình thường: callback kết thúc trước khi đóng handle process. Trên Windows hiện tại, CPython cũng xử lý `kill()` khi process đã thoát; tôi không thấy bằng chứng về lỗi tái sử dụng handle trong đường này.

Chuyển job/args sang `job.pickle` là điều chỉnh có cơ sở, nhưng không tự chứng minh U5. Rủi ro còn lại gồm handle rò khi bootstrap bị kill, file chứa PDF/text tồn tại sau hard-kill API theo H1, RAM chưa có trần cứng, và thời gian decode/serialize ở parent ngoài khả năng cưỡng chế của worker. Job Object tiếp tục thuộc bước sau theo phạm vi đã chốt.