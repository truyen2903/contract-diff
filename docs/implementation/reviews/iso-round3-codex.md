# Isolation Round 3 — Codex

Giữ **spawn mỗi request, một job chạy toàn pipeline thuần, file đầu vào + file kết quả**, sau interface `worker_session`. Sửa hai thiếu sót của đề xuất cũ: deadline phải bắt đầu từ admission; `join(remaining)` không tự bảo vệ startup và xử lý kết quả tại parent. **Chưa đủ bằng chứng đóng R-TIMEOUT toàn request.**

Đã đọc brief, toàn bộ `iso-round2-cross.md`, đề xuất Codex Round 1 và mã/tests liên quan. Phiên này chỉ đọc, không ghi file; chạy **1 thí nghiệm trong bộ nhớ**, có watchdog, không để lại worker hoặc timer.

## Phản hồi phản biện nhắm vào tôi

- **CL/ISO-CX-001 — PARTIAL —** Chấp nhận lỗi import FastAPI, tuần tự hóa `HTTPException` và monkeypatch không sang spawn. Đã sửa từ Round 2 thành pipeline thuần, truyền giới hạn hiệu lực. Các lỗi này không chứng minh cần giữ ghép text/mapping tại parent.
- **CL/ISO-CX-002 — PARTIAL —** Gate trước body không có timeout upload có thể bị chiếm vô hạn. Chấp nhận lỗi; không chấp nhận chuyển gate xuống service là đủ: khi đó upload/parse/spool trước admission vẫn chưa được giới hạn về số request.
- **CL/ISO-CX-003 — PARTIAL —** Chấp nhận Pipe đọc trước join hoạt động được và file có chi phí đĩa/cleanup. Bác bỏ nhận định khoảng hở chỉ do join sai thứ tự: CX E1 và CL E2 đều xác nhận `send` có thể chặn; thí nghiệm mới xác nhận kill worker không ngắt decode đang chạy ở parent.
- **CL/ISO-CX-004 — PARTIAL —** Đồng ý không gửi `Retry-After` cho timeout và không khuyến khích tự retry. Không đổi sang 422: queue bằng 0 vẫn có tranh chấp CPU, startup và I/O; hết deadline không chứng minh input sai.
- **CL/ISO-CX-005 — PARTIAL —** Đồng ý bỏ `terminate → kill` trên Windows, dùng trực tiếp `kill()` rồi join hữu hạn. Không bỏ ownership khi chưa xác nhận chết; không xây registry phức tạp, nhưng vẫn phải giữ handle/slot để thu hồi sau.
- **CL/ISO-CX-006 — ACCEPT —** Chi phí suite cần đo lại và timeout acceptance cần hạ có cấu hình. Số 12,9 giây của Claude là bằng chứng cho prototype đó, không phải số đo cho phương án của tôi; không suy ra bắt buộc thu hẹp ranh giới worker.
- **AG/ISO-CX-001 — ACCEPT —** Luồng Round 1 thực sự để upload nằm ngoài ngân sách và có thể giữ hai slot vô hạn. Sửa bằng deadline tuyệt đối từ admission và giới hạn thời gian nhận body; chỉ tăng lên bốn slot không sửa lỗi này.
- **AG/ISO-CX-002 — PARTIAL —** Chấp nhận phạt import nguyên service. CX E2 đã đo pipeline thuần gồm extraction, ghép, diff và mapping khoảng 0,93–0,95 giây trên PDF tổng hợp. Không dùng số đó để xác nhận H3b hoặc loại pool cho tương lai.
- **AG/ISO-CX-003 — PARTIAL —** Chấp nhận kill trực tiếp và tự thu hồi slot khi process đã chết, thay vì vô hiệu hóa vĩnh viễn. Độ trễ AV/kernel cụ thể vẫn là giả thuyết chưa đo; không được nhả slot chỉ vì `join(3)` đã trả về.
- **AG/ISO-CX-004 — PARTIAL —** Chấp nhận nguy cơ hai bộ service phân kỳ và đường gọi production bỏ qua isolation. Chọn service công khai luôn đi qua supervisor, tái sử dụng một pipeline thuần; gom cấu hình hiệu lực thành payload nội bộ, không thêm hàng loạt override chỉ để giữ test.
- **AG/ISO-CX-005 — ACCEPT —** Watchdog không tương đương worker chết cùng API, cũng chưa bảo vệ bootstrap trước entrypoint. Windows Job Object phải bắt buộc nếu công bố bảo đảm này; không chấp nhận fallback chỉ log cảnh báo rồi tiếp tục coi là đạt.
- **AG/ISO-CX-006 — PARTIAL —** Chấp nhận lỗ parse JSON ở parent, chi phí file và thứ tự cleanup trên Windows. Pipe + timer cũng chưa bảo vệ decode tại parent; chuyển IPC không tự đóng R-TIMEOUT.
- **CX/ISO-CX-001 — ACCEPT —** Giữ tự phản biện: startup, nhận kết quả và response validation phải được xét riêng. Không thêm trần `/extract` trái D13 để né vấn đề output lớn.

## Bằng chứng kiểm chứng thêm

**E3.1 — CONFIRMED: kill worker không ngắt unpickle đang chạy ở parent.**

Chạy `.venv/Scripts/python.exe -B -`; script chỉ nằm trong bộ nhớ. Harness gọi interpreter con với `timeout=15`; watchdog harness/runner/worker lần lượt 18/12/6 giây. Worker spawn gửi đối tượng có bước unpickle `sleep(0.9)`; sau khi `poll()` báo sẵn sàng, parent đặt timer kill sau 0,2 giây rồi gọi `recv()`.

```text
decode_deadline_s=0.200 recv_elapsed_s=0.901 fired=True worker_alive=False
active_children=0 timer_alive=False
experiment_exit=0
```

Đây là **fault injection tổng hợp**, không phải payload `list[dict]` hợp lệ hay benchmark ứng dụng. Nó bác bỏ bảo đảm tổng quát “kill worker bao toàn bộ `recv()`”: dữ liệu đã nhận có thể đang được giải mã hoàn toàn tại parent.

**E3.2 — CONFIRMED bằng đọc mã runtime, không chạy thêm thí nghiệm:**

- `multiprocessing.connection.Connection.recv()` nhận buffer rồi gọi `_ForkingPickler.loads()` trong parent.
- Trên Windows, `Process.start()` chỉ gán `_popen` sau khi constructor `Popen` trả về; constructor thực hiện `CreateProcess` và ghi dữ liệu bootstrap. Timer đặt **sau** `start()` không thể bảo vệ chính lời gọi đó đang chặn.
- `popen_spawn_win32.py` đặt `kill = terminate`; mã cũng yêu cầu chờ process được signal trước khi kết luận đã thoát.
- `Timer.cancel()` không chờ callback đang chạy kết thúc. Cần đồng bộ callback với completion/cleanup.
- Body-limit middleware hiện tại giới hạn byte, không có deadline cho `await receive()`.

## Lập trường O1–O7

### O1 — ACCEPT: spawn trước, giữ interface để thay implementation

Chọn **một process/request** cho phiên bản đầu, sau `worker_session(deadline, limits)`. Chưa triển khai sẵn pool, recycle hoặc cơ chế warm-up.

H3b vẫn phải đo trên corpus hợp đồng 20 trang đại diện, gồm HTTP, startup mỗi request, IPC và toàn pipeline. “Warm-run” của API không được loại startup mà kiến trúc vẫn thực hiện mỗi request.

Chuyển sang pool có giám sát khi benchmark cho thấy startup là nguyên nhân đáng kể khiến không đạt mục tiêu và pool thực sự cải thiện. Phase B nạp scipy/sklearn là lý do đo lại, chưa phải bằng chứng bắt buộc chọn pool ngay.

### O2 — ACCEPT: một lời gọi chạy toàn pipeline thuần

Worker thực hiện extraction ×2, ghép văn bản, kiểm giới hạn text `/pdf`, diff, mapping và chuẩn bị output. Mapping hiện không phụ thuộc FastAPI; chi phí phụ thuộc output nên nên nằm trong process có thể kill.

Parent giữ validation HTTP và kiểm size/magic rẻ của **cả hai PDF trước extraction**, snapshot giới hạn hiệu lực, admission và ánh xạ mã lỗi nghiệp vụ sang HTTP. Worker trả mã lỗi/context thuần, không trả `HTTPException`.

Service production phải luôn qua isolation; unit test có thể gọi các hàm thuần trực tiếp. Điều chỉnh đích monkeypatch khi cần, giữ nguyên ý nghĩa kiểm thử; không hứa trước “chỉ sửa một test”.

### O3 — PARTIAL: giữ file vào + file kết quả, sửa đường nhận output

Chọn file đầu vào, tham số spawn nhỏ; tránh đưa PDF lớn vào cả bootstrap lẫn Pipe. Worker ghi `result.part`, đóng rồi publish `result.json`; parent chỉ nhận success khi worker thoát sạch và output hoàn chỉnh.

Chấp nhận Pipe + timer là phương án khả thi, đặc biệt để gỡ I/O đang chặn như CL E2. Không chấp nhận coi `poll → recv` hoặc timer kill là bằng chứng deadline cho decode ở parent.

Với file kết quả, chuyển validation/serialization theo response schema vào worker; đường trả response nên chuyển tiếp JSON đã xác thực, tránh parse và validate lại toàn bộ tại parent. Đây là thay đổi nội bộ cần nghiệm thu schema, lỗi output và cleanup; chưa phải khả năng đã được chứng minh.

Thứ tự Windows: **kill khi cần → join hữu hạn → xác nhận chết → đóng handle → unlink → nhả slot**. File không tự bảo vệ mọi I/O tại parent và không tự giải quyết R-BOMB.

### O4 — PARTIAL: giữ join có deadline; timer không phải bảo đảm toàn request

Với file kết quả, dùng `join(remaining)` để chờ worker; hết ngân sách thì `kill()` và join hữu hạn. Với Pipe, cần supervisor/timer độc lập với luồng IPC. Mọi pha cùng nhận một deadline monotonic, không cấp lại 30 giây.

Phân loại bằng trạng thái được đồng bộ:

- Timeout thắng khi supervisor chuyển request sang `TIMED_OUT`; đặt `fired` trước khi kill.
- Crash quan sát được trước deadline, chưa có quyết định timeout → 500 `PROCESSING_FAILED`.
- Không nhận success nếu supervisor đã timeout hoặc ngân sách đã hết.
- Cancel và join timer hữu hạn trước khi đóng/tái sử dụng tài nguyên; `Event` riêng lẻ không giải quyết mọi race.

**Startup stall — NEEDS EXPERIMENT.** CL E2 chứng minh gỡ blocked send; không chứng minh kill được process khi `Process.start()` chưa trả handle cho supervisor. Cần thiết kế ownership và acceptance riêng cho cửa sổ này. Tương tự, kiểm deadline sau decode chỉ phát hiện quá hạn, không ngắt được decode.

### O5 — ACCEPT: 504 `PROCESSING_TIMEOUT`, không `Retry-After`

Giữ 504 làm quy ước API cho hết ngân sách xử lý; không coi đây là lựa chọn HTTP duy nhất. Không dùng 422 để suy diễn tài liệu vô hiệu từ wall-clock timeout.

Không kèm `Retry-After` cho timeout; tài liệu client phải tránh tự động gửi lại cùng input. Khi đầy slot vẫn trả 503 cùng `Retry-After` theo phần đã hội tụ.

### O6 — ACCEPT có điều kiện: gate trước body, khởi đầu hai slot

Giữ gate trước body cho ba endpoint xử lý, queue bằng 0; khi đầy không gọi `receive`. Body-limit hiện tại tiếp tục áp dụng cho request được nhận.

Điều kiện bắt buộc: deadline bắt đầu ngay khi nhận slot, thời gian nhận body bị giới hạn bằng ngân sách còn lại; không reset timeout sau mỗi chunk. Disconnect/cancellation không được nhả slot khi supervisor còn worker hoặc cleanup chưa xong.

Chọn **hai slot cho một API process** trước khi có số đo capacity. Bốn slot chưa có bằng chứng về peak memory của toàn pipeline; cũng không sửa Slowloris. Tính trần trên tổng số API process, không chỉ từng semaphore.

### O7 — ACCEPT: Job Object bắt buộc trên Windows, cộng watchdog

Dùng `KILL_ON_JOB_CLOSE`, handle Job không kế thừa sang worker; kiểm kết quả từng WinAPI. Nếu không gán được Job, từ chối khởi chạy xử lý, kill/reap process đã tạo; không âm thầm fallback.

Watchdog vẫn cần đặt trước import nặng, nhận thời gian hiệu lực từ parent. Nó là dự phòng, không thay Job Object.

**Cửa sổ spawn → assign còn phải kiểm chứng.** Có Job Object không tự chứng minh worker đã thuộc Job ngay từ lúc sinh ra. Phải thử API chết trước entrypoint và trước assignment; chưa đóng cửa sổ này thì chưa công bố bảo đảm không orphan tức thì.

## Điều kiện nghiệm thu còn thiếu

- Startup stall; timeout trong upload/IPC/output; completion sát deadline và race timer/cleanup.
- R-LOOP, pathological diff, crash rồi recovery; health khi cả hai slot đang bận.
- Gate đầy không đọc body; upload nhỏ giọt hết ngân sách và thu hồi được slot.
- Kill/join chưa xác nhận chết: giữ ownership, thu hồi lại khi chết; không vượt trần worker.
- API bị hard-kill ở các pha bootstrap/assignment; xác minh PID, handle và temp, không chỉ `active_children()`.
- Output `/extract` lớn, lỗi đĩa/khóa file, tương thích schema và các lỗi Phase A; benchmark H3b và suite tích hợp thực tế.

Các số đo Round 2 là bằng chứng tham khảo. Phiên này không chạy lại suite và không tuyên bố đã triển khai hoặc đóng R-TIMEOUT/R-BOMB.