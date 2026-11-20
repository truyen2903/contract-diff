# Isolation Round 3 — Claude

Tôi chỉ đọc repo. Thí nghiệm mới (E3) chạy trong `C:\Users\Admin\AppData\Local\Temp\claude\7a81e431fe1166c9\3ae8a7db-bd9c-402e-b3dc-61914ab153f4\scratchpad\iso-claude2\`, có watchdog 25 s và `timeout 30`. Sau đó `tasklist` không còn `python.exe` nào, và không còn file tạm `.pdf` nào trong thư mục đó.

## Bằng chứng mới

**E3 [CONFIRMED]: session theo request với input file tạm, kết quả qua Pipe, `threading.Timer(timeout, kill)`.** Script là `e3b_session.py`. Worker bật watchdog trước khi import `pdfplumber`. Hai tệp được extract tuần tự trong cùng một process. Timeout là 3 s.

```text
valid x2   ('OK', 0.687)            unlink ok ×2
loop @new  ('TIMEOUT', 3.013)       unlink ok ×2   # R-LOOP ở new_file, kill → join → unlink, không WinError 32
children []
```

**Lỗi tôi tự vấp ở lần chạy đầu (`e3_session.py`):** parent **chưa `close()` đầu Pipe phía con** sau `start()`. Timer có kill con, nhưng `recv` của parent vẫn chặn cho tới khi watchdog runner kích hoạt ở 25 s. Lý do: parent vẫn giữ đầu pipe bên kia nên pipe không bao giờ báo EOF. Bản Round 1 của tôi có `child_connection.close()`. E3 cho thấy dòng này là **điều kiện cần** để timer kill có tác dụng, không phải chi tiết dọn dẹp. Phải có test hồi quy cho nó.

## Phản hồi phản biện nhắm vào tôi

**Từ Codex (CX/…):**
- **CX/ISO-CL-001 (send/recv chặn ngoài `poll`) — PARTIAL.**
  - Phần send/recv bị chặn: timer kill ở parent gỡ được (CL E2: `BrokenPipeError` sau 2,01 s; E3: timeout 3,01 s). Điều kiện là parent đã đóng đầu pipe phía con.
  - Phần còn hở là CPU unpickle ở parent sau khi `recv` xong. Timer không ngắt được bước này. Kết quả là `list[dict]`/`str` do code của chính ta sinh ra, nên chi phí tuyến tính và nhỏ (2 M ký tự cả vòng mất 0,49 s).
  - Tôi thêm một kiểm tra sau `recv`: nếu `fired` đã bật thì trả timeout. Không coi đây là blocker.
- **CX/ISO-CL-002 (ownership khi tạo worker, `join()` vô hạn) — ACCEPT.**
  - Khởi tạo `process = None` rồi đặt `Pipe()`/`start()` trong khối `try`. `finally` gồm: hủy timer, `kill()`, `join(5)`, đóng cả hai đầu pipe, xóa file tạm, nhả slot.
  - Nếu sau `join(5)` worker vẫn sống: giao handle cho một reaper thread. Thread này `join()` rồi mới nhả slot. Không nhả slot trước khi worker chết, và cũng không khóa slot vĩnh viễn như AG/ISO-CX-003 cảnh báo.
- **CX/ISO-CL-003 (admission trong service không chặn được tài nguyên upload) — REJECT** gate ASGI chiếm processing slot. Lý do:
  - Gate đó mở ra lỗ slowloris: 2 kết nối nhỏ giọt khóa cả 2 slot (AG/ISO-CX-001; Codex tự nêu ở §5).
  - Upload đã có trần ở `RequestBodyLimitMiddleware`. Starlette spool phần > 1 MiB ra đĩa (Round 1 §5.11).
  - Nếu cần giới hạn tổng số kết nối, dùng tùy chọn có sẵn `uvicorn --limit-concurrency` (trả 503), không trộn với processing slot. [HYPOTHETICAL: chưa đo trên app này.]
- **CX/ISO-CL-004 (ranh giới extractor/engine quá hẹp) — PARTIAL.**
  - Đồng ý nguyên tắc: mọi bước có độ phức tạp **siêu tuyến tính** hoặc phụ thuộc kích thước output không có trần phải chạy trong worker.
  - Giữ ở parent các bước tuyến tính, rẻ, gắn với HTTP: ánh xạ lỗi theo tên tệp, `check_text_length`, `build_document_text`. Đặt ở parent thì giữ được fail-fast giữa hai lần extract, và monkeypatch vẫn có tác dụng.
  - `span_to_page_locations` có thể chuyển vào worker bằng cách đổi thành `run(diff_and_map, …)`. Đây là đổi ruột, interface session không đổi.
- **CX/ISO-CL-005 (422 cho timeout) — ACCEPT.** Đổi sang **504 `PROCESSING_TIMEOUT`**, không kèm `Retry-After`. Lập luận về CPU tranh chấp và giám sát 5xx là đúng: không có queue cũng không làm thời gian chỉ phụ thuộc input. Crash trả 500 `PROCESSING_FAILED` (đã hội tụ).
- **CX/ISO-AG-004 (harness test) — PARTIAL.**
  - Workload treo chỉ chạy trong process con. Process pytest chỉ chờ ở các điểm có chặn trên (timer/poll).
  - Thêm `faulthandler_timeout` và `faulthandler_exit_on_timeout = true` (Codex xác nhận option này có, mặc định False) để pytest tự thoát nếu treo.
  - Kiểm orphan sau khi API bị kill chạy bằng script harness riêng (exp2), không đưa vào CI. Đồng ý `active_children()` không đủ cho kịch bản đó.

**Từ Antigravity (AG/…):**
- **AG/ISO-CL-001 (send chặn, `join()` không timeout) — ACCEPT.** Khắc phục bằng timer kill và `join(5)` như trên. Không cần bắt tay `"ready"`, vì timer bao cả pha khởi động.
- **AG/ISO-CL-002 (422, crash 500 mặc định) — ACCEPT.** 504 và 500 `PROCESSING_FAILED`, như trên.
- **AG/ISO-CL-003 (RAM của Pipe bytes, đo được 3× ở parent và 2× ở con) — ACCEPT.** Số đo `GetProcessMemoryInfo` của AG thay cho ước lượng [HYPOTHETICAL] của tôi. Chuyển input PDF sang **file tạm** (copy từng khối 64 KiB, đóng tệp trước khi gửi đường dẫn). Thứ tự kill → join → unlink chạy đúng trên Windows (E3).
- **AG/ISO-CL-004 (sửa 1 test; thiếu fast-path) — ACCEPT.**
  - Dùng `extract_document(filename, file_stream, *, run=None)`; khi `run is None` thì tự mở session. Như vậy **không phải sửa test cũ nào**, đổi lại thêm một nhánh `if`.
  - Fast-path `if old_text == new_text` ở parent, trước khi mượn slot. Hai chuỗi giống hệt thì chắc chắn không có thay đổi, nên kết quả không đổi. Cần một test so khớp với kết quả `diff_words` để xác nhận.
- **AG/ISO-CX-005 (chỉ dùng watchdog, không dùng Job Object; watchdog không bao pha bootstrap) — PARTIAL.**
  - Đồng ý có khoảng hở bootstrap. Thu hẹp nó bằng cách: module worker không import nặng ở top-level, và `dump_traceback_later` là lệnh đầu tiên trong `worker_main`.
  - Khoảng hở còn lại chỉ gây hại khi API chết **đúng lúc** con đang khởi động. Trong lúc đó con chưa chạy R-LOOP, và khi API còn sống thì timer của parent vẫn kill được con.
  - Job Object chỉ rút thời gian sống của orphan từ ≤ 35 s xuống 0. Đó là hardening nên có, nhưng không phải điều kiện để đóng R-TIMEOUT (xem O7).

## Lập trường O1–O7

- **O1 Mô hình — ACCEPT "spawn trước, giữ interface `worker_session`".**
  - Số đo: Codex E2 cho pipeline thuần với PDF 20 trang tổng hợp là 0,93–0,95 s. `/pdf` trên fixture là 0,70 s (Round 1). E3 là 0,69 s. Spawn theo ranh giới thuần tốn khoảng 0,47 s (CL E1). Như vậy còn khoảng 2 s trong ngân sách H3b 3 s.
  - Pool thường trực mất trạng thái ấm sau mỗi lần kill, và mất cả ở fixture test scope function. Nó cũng kéo theo bắt buộc phải có Job Object.
  - Tiêu chí đổi sang pool: benchmark H3b trên corpus thật, gồm HTTP và spawn mỗi request, cho p95 ≥ 3 s. Hoặc Phase B import scipy/sklearn trong worker làm spawn > 1 s. Khi đó chỉ thay ruột `worker_session`, vẫn một worker cho mỗi request.
- **O2 Phạm vi lời gọi — PARTIAL, giữ session nhiều lời gọi.**
  - Quy tắc: việc siêu tuyến tính hoặc có output không trần đi vào worker. Việc tuyến tính gắn với HTTP hoặc giới hạn ở lại parent.
  - Mỗi lời gọi là một hàm thuần cố định; giới hạn hiệu lực (`max_pages`) truyền tường minh.
  - Mapping chuyển vào worker được nếu đo thấy tốn. Một lời gọi pipeline của Codex là trường hợp riêng của session (một lần `run`), nên hai hướng tương thích.
- **O3 IPC — file tạm cho input PDF, Pipe cho text, control và kết quả** (hội tụ với AG).
  - Input dùng file: RAM giảm theo số đo của AG; E3 xác nhận unlink sau join không lỗi.
  - Kết quả **không** dùng `result.json`: đọc và parse JSON ở parent cũng nằm ngoài deadline, giống `recv`, lại thêm I/O đĩa và rủi ro khóa tệp. Pipe với timer đã đủ.
  - Yêu cầu bắt buộc: đóng đầu pipe phía con ngay sau `start()` (E3).
- **O4 Thi hành deadline — `threading.Timer(remaining, kill)` ở parent, cộng `poll(remaining)`.**
  - Phân biệt timeout và crash: `EOFError`/`OSError` khi cờ `fired` đã bật là 504; khi cờ chưa bật là 500. Nếu `recv` thành công nhưng `fired` đã bật thì vẫn trả 504.
  - `join(remaining)` của Codex chỉ bảo vệ pha chờ, không gỡ được `send` hay `start` đang chặn.
- **O5 Mã lỗi — ACCEPT 504 `PROCESSING_TIMEOUT`, không kèm `Retry-After`** (cùng input thì timeout lại). 503 `SERVER_BUSY` kèm `Retry-After`. 500 `PROCESSING_FAILED`.
- **O6 Admission — kiểm trong service sau khi parse và validate, `acquire(blocking=False)`, 4 slot, queue 0.**
  - REJECT gate ASGI giữ processing slot (lỗ slowloris).
  - Giới hạn kết nối hoặc upload tổng thuộc tầng server (`--limit-concurrency`, body limit có sẵn).
  - Lý do chọn 4 thay vì 2: máy có 16 CPU, worker khoảng 35–50 MB, và input dùng file giảm RAM ở parent. Có thể hạ xuống 2 nếu đo peak RAM thấy cần.
- **O7 Job Object — PARTIAL: hardening khuyến nghị cho Windows, không phải điều kiện để đóng R-TIMEOUT.**
  - Watchdog là bắt buộc (lệnh đầu tiên trong worker), đặt chặn trên ≤ timeout + 5 s cho orphan.
  - Job Object (`KILL_ON_JOB_CLOSE`, `ctypes` có đủ `argtypes`/`restype`, handle không kế thừa sang con) thêm sau khi lõi đã qua acceptance. Khi gán thất bại phải ghi rõ trong tài liệu là mức bảo đảm giảm còn "≤ 35 s", không chỉ log.
  - Nếu tác giả yêu cầu worker phải chết ngay cùng API thì chuyển thành bắt buộc.
