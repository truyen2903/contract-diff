# Process Isolation — Round 2 Cross-Examination (tổng hợp)

Ghép nguyên văn ba báo cáo Round 2 độc lập. ID tự đánh theo đích bị phản biện nên có thể trùng; trích dẫn ở Round 3 dùng tiền tố tác giả `CX/`, `CL/`, `AG/`.

---

# PHẦN CX — tác giả: Codex

**Kết luận:** Giữ **một process/request, một slot/request, hàng đợi 0**, nhưng sửa ranh giới Round 1 thành **toàn bộ pipeline xử lý thuần**, tránh import service có FastAPI. Chọn file đầu vào và file kết quả để tránh truyền payload lớn qua Pipe. Chưa phương án nào đủ bằng chứng để tuyên bố đóng hoàn toàn R-TIMEOUT.

Đã đọc brief, ba báo cáo Round 1, kế hoạch v2, consensus, Phase A, mã nguồn và tests liên quan. Phiên này chỉ đọc; prototype chỉ trong bộ nhớ, có watchdog, kết thúc dưới 60 giây và xác nhận không còn process con.

## Bằng chứng kiểm chứng thêm

**E1 — Pipe có thể vượt deadline ngoài `poll`.** Lệnh chạy: `.venv/Scripts/python.exe -B -`, nhận prototype qua stdin; harness gọi `subprocess.run(..., timeout=30)`, watchdog runner 25 giây và worker 8 giây.

Hai phép thử: worker báo `ready` rồi cố ý ngừng đọc; worker gửi đối tượng thử nghiệm có bước unpickle gọi `time.sleep(0.8)`.

```text
ready_then_send_blocked_after_350ms=True
sender_thread_alive=False status=['unblocked_by_kill']
poll_budget_ms=10 recv_elapsed_ms=804
active_children=0
prototype_exit=0
```

Đối tượng unpickle chậm là **fault injection tổng hợp**, không phải bằng chứng rằng kết quả `list[dict]` hiện tại luôn gây treo. Nó chứng minh timeout của `poll` không bao phủ `recv`/unpickle.

**E2 — Ranh giới import ảnh hưởng lớn đến latency.** Cùng lệnh stdin, harness timeout 45 giây; runner watchdog 40 giây, mỗi worker 7 giây. Dùng `spawn`, target `exec`; hai PDF tổng hợp, mỗi tệp 20 trang, 25 từ/trang, khác một từ. Nhánh thuần chạy extraction ×2, ghép text, diff và mapping trong cùng worker.

```text
service sample=1 total_ms=1883 import_ms=1044 work_ms=400 changes=1 pages=20
service sample=2 total_ms=1597 import_ms=942  work_ms=352 changes=1 pages=20
service sample=3 total_ms=1626 import_ms=964  work_ms=308 changes=1 pages=20
pure    sample=1 total_ms=942  import_ms=293  work_ms=376 changes=1 pages=20
pure    sample=2 total_ms=928  import_ms=289  work_ms=354 changes=1 pages=20
pure    sample=3 total_ms=946  import_ms=368  work_ms=342 changes=1 pages=20
input_bytes=(10024, 10024) active_children=0
prototype_exit=0
```

Đây là đo scaffold xử lý tổng hợp; chưa gồm HTTP, file IPC, response validation hoặc pipeline tương lai. **Không phải xác nhận H3b.**

**E3 — Monkeypatch không sang worker `spawn`.** Cùng lệnh stdin; subprocess timeout 15 giây, watchdog runner 12 giây và worker 5 giây.

```text
parent_limits=(10, 2) child_limits=(500000, 100)
active_children=0
prototype_exit=0
```

**E4 — Baseline hiện tại.** Lệnh `.venv/Scripts/python.exe -B -`, stdin bật watchdog 45 giây rồi gọi:

```python
pytest.main(['-q', '--capture=sys', '-p', 'no:cacheprovider'])
```

```text
92 passed in 1.82s
```

## Các phản biện, theo severity

### ISO-CL-001
- **Target:** Claude §3.3–3.4; đồng thời Antigravity §3.4.
- **Severity:** Critical.
- **Claim:** `send → poll(remaining) → recv` chưa tạo hard timeout cho toàn lời gọi.
- **Evidence:** **[CONFIRMED]** E1: sau `ready`, `send` vẫn chặn quá 350 ms; `poll(10 ms)` rồi `recv` mất 804 ms. Đọc bằng `inspect.getsource(PipeConnection._send_bytes/_recv_bytes)` cũng thấy các nhánh chờ `INFINITE`.
- **Counterexample:** Worker ngừng đọc sau handshake; hoặc parent bắt đầu nhận/giải mã khi ngân sách gần cạn. Handshake không bảo đảm mọi thao tác sau đó hoàn tất đúng hạn.
- **Recommendation:** Tránh payload lớn trên Pipe; dùng file kết quả. Nếu giữ Pipe, supervisor độc lập với luồng IPC phải thực thi deadline, đóng kết nối và kill worker; kiểm tra lại deadline trước khi nhận success. Lỗ đã được hai báo cáo tự nêu vẫn phải coi là blocker.
- **Confidence:** Cao về khoảng hở; trung bình về tần suất xảy ra với dữ liệu hợp lệ.

### ISO-AG-001
- **Target:** Antigravity §3.4, fallback khi không gán được Job Object.
- **Severity:** Critical.
- **Claim:** Fallback về `lifespan + atexit` mất bảo đảm chống orphan khi API bị kill đột ngột.
- **Evidence:** **[CONFIRMED, từ báo cáo]** `Get-Content -Encoding UTF8 docs/implementation/reviews/iso-round1-antigravity.md`: §3.4 quy định fallback này; §4 ghi `Without Job Object ... still_alive(ORPHAN)=True`. Không chạy lại phép thử Job Object trong Round 2.
- **Counterexample:** `AssignProcessToJobObject` thất bại, server vẫn nhận PDF R-LOOP, rồi API bị `TerminateProcess`; shutdown hook không chạy.
- **Recommendation:** Thêm watchdog worker trước import nặng. Nếu yêu cầu kết thúc ngay cùng API, Job Object phải là điều kiện triển khai bắt buộc; không âm thầm hạ bảo đảm. Handle Job không được kế thừa sang worker; kiểm tra đầy đủ kết quả gọi WinAPI.
- **Confidence:** Cao.

### ISO-CL-002
- **Target:** Claude, code `worker_session()` §3.2.
- **Severity:** High.
- **Claim:** Cleanup chưa bao phủ toàn bộ quá trình tạo worker; `join()` không có timeout.
- **Evidence:** **[CONFIRMED]** `rg -n 'process.start|process.join' docs/implementation/reviews/iso-round1-claude.md` trả `84: process.start()` và `103: process.join()`. Khối `finally` dọn process nằm sau `start()` và `child_connection.close()`.
- **Counterexample:** **[HYPOTHETICAL]** `start()` hoặc bước đóng endpoint con ném lỗi trước khi vào khối cleanup; semaphore được nhả nhưng tài nguyên đã tạo chưa chắc được thu hồi. Worker không thoát như dự kiến thì `join()` không có chặn trên.
- **Recommendation:** Quản lý ownership ngay từ lúc tạo Pipe/process; cleanup theo trạng thái đã khởi động. Mọi `join` phải hữu hạn; chỉ nhả slot sau khi xác nhận worker chết.
- **Confidence:** Cao về cấu trúc; trung bình về khả năng gặp nhánh lỗi.

### ISO-AG-002
- **Target:** Antigravity §3.4, timeout và recycle.
- **Severity:** High.
- **Claim:** `join(timeout)` không đủ để kết luận process đã chết và trả slot về pool.
- **Evidence:** **[CONFIRMED]** `rg -n 'slot.proc = None' docs/implementation/reviews/iso-round1-antigravity.md` cho thấy §3.4 đặt `None` sau `join(timeout=3.0)`; nhánh recycle cũng đặt `None` sau kill mà chưa nêu bước xác nhận thoát.
- **Counterexample:** **[HYPOTHETICAL]** `join` hết hạn nhưng worker còn sống; bỏ handle rồi spawn thay thế làm vượt trần worker và có thể unlink khi Windows còn giữ file.
- **Recommendation:** Kiểm tra `is_alive()` sau join; giữ handle và cách ly slot nếu chưa chết. Thứ tự bắt buộc: kill → join hữu hạn → xác nhận chết → close → unlink → nhả slot.
- **Confidence:** Cao.

### ISO-AG-003
- **Target:** Antigravity §3.2 và §9.4, mượn slot theo từng bước.
- **Severity:** High.
- **Claim:** Cho một `/pdf` xếp hàng lại ba lần làm mất bảo đảm admission ở cấp request.
- **Evidence:** **[CONFIRMED, từ báo cáo]** `Get-Content -Encoding UTF8 docs/implementation/reviews/iso-round1-antigravity.md`: §9.4 thừa nhận request đã extract hai tệp vẫn có thể chờ diff rồi nhận 504.
- **Counterexample:** **[HYPOTHETICAL]** Request A hoàn tất extraction; các request mới chiếm worker trước bước diff của A. A hết deadline dù đã tiêu tốn phần lớn công việc.
- **Recommendation:** Giữ một slot/worker cho toàn request, kể cả khi chọn pool thường trực. Không cần đợi benchmark mới sửa ownership này.
- **Confidence:** Cao.

### ISO-CL-003
- **Target:** Claude §3.5; Antigravity §3.2, admission trong service.
- **Severity:** High.
- **Claim:** Semaphore ở service giới hạn xử lý worker nhưng chưa giới hạn tài nguyên đọc/parse upload trước service.
- **Evidence:** **[CONFIRMED]** `Get-Content` các route hiện tại cho thấy chúng nhận `UploadFile` trước khi gọi service. Hai báo cáo đặt admission trong `worker_session`/`run_in_worker`; AG khẳng định request thứ 13 bị từ chối tức thì.
- **Counterexample:** **[HYPOTHETICAL]** Nhiều request upload gần giới hạn body vẫn phải được framework tiếp nhận và parse trước khi nhận 503. Con số “12 thread chờ worker” không phải trần tổng tài nguyên request.
- **Recommendation:** Gate ASGI trước đọc body cho đúng ba endpoint; khởi đầu 2 slot, queue 0. Kiểm thử khi đầy gate không gọi `receive`. Giữ body-limit middleware và xác định rõ thứ tự; bổ sung upload timeout để client chậm không giữ slot vô hạn.
- **Confidence:** Cao.

### ISO-CX-001
- **Target:** Codex Round 1 §3.3 và §9.4.
- **Severity:** High.
- **Claim:** File IPC tránh deadlock Pipe, nhưng chưa giới hạn CPU/RAM đọc và parse kết quả tại parent; deadline trước `start()` cũng không tự ngắt được `start()` đang chặn.
- **Evidence:** **[CONFIRMED, tự rà soát]** `Get-Content -Encoding UTF8 docs/implementation/reviews/iso-round1-codex.md`: parent join xong mới đọc JSON; §9.4 thừa nhận decode/response validation chưa được bảo vệ.
- **Counterexample:** **[HYPOTHETICAL]** `/extract` tạo text rất lớn nhưng không vi phạm giới hạn text dành riêng cho `/pdf`; worker thoát đúng hạn, parent vẫn tốn nhiều thời gian decode và validation.
- **Recommendation:** Đưa mapping, validation và serialization kết quả vào worker; cân nhắc parent chuyển tiếp JSON đã xác thực để tránh decode lại. Kiểm deadline trong pha nhận kết quả và có kiểm thử startup stall. Nếu giữ parse lớn tại parent, phải công khai phần coverage còn thiếu; không tự thêm trần `/extract` trái D13.
- **Confidence:** Cao về khoảng hở; giải pháp chuyển tiếp response cần thiết kế và acceptance riêng.

### ISO-AG-004
- **Target:** Antigravity §7; Claude §7.
- **Severity:** High.
- **Claim:** `thread.join(timeout)` rồi assert, hoặc chỉ bật `faulthandler_timeout`, chưa bảo đảm kết thúc test và dọn process cháu.
- **Evidence:** **[CONFIRMED]** `Get-Content` báo cáo AG cho phép phương án thread join; báo cáo CL đề xuất `faulthandler_timeout = 120`. Lệnh `inspect.getsource(_pytest.faulthandler.pytest_addoption)` trên môi trường này trả `faulthandler_exit_on_timeout ... default=False`.
- **Counterexample:** **[HYPOTHETICAL]** Assertion thất bại nhưng thread còn chạy; thoát `TestClient` chờ request treo. Traceback được in ra nhưng tác vụ không bị kết thúc.
- **Recommendation:** Acceptance gây treo chạy trong harness subprocess có timeout ngoài, watchdog worker và cleanup PID độc lập. Parent truyền timeout hiệu lực vào worker; không dựa vào monkeypatch module khác. `active_children()` không đủ chứng minh sạch orphan sau khi API cha đã chết.
- **Confidence:** Cao.

### ISO-CL-004
- **Target:** Claude §3.1–3.2; sửa ranh giới của Codex.
- **Severity:** Medium.
- **Claim:** Nhận xét import FastAPI gây chậm là đúng; suy ra chỉ extractor/engine được ở worker thì quá hẹp.
- **Evidence:** **[CONFIRMED]** E2: nhánh import service mất 1,60–1,88 giây tổng; nhánh thuần vẫn chạy extraction, ghép text, diff và mapping trong một worker mất 0,93–0,95 giây. `Get-Content app/engines/text_mapping.py` cho thấy mapping không phụ thuộc FastAPI.
- **Counterexample:** Giữ ghép text/mapping tại parent để tránh FastAPI vẫn đưa xử lý theo kích thước output ra ngoài ranh giới kill.
- **Recommendation:** Tách toàn pipeline thuần khỏi adapter HTTP; worker nhận operation cố định và các giới hạn, trả envelope dữ liệu. Parent ánh xạ business error sang HTTP. Không pickle `HTTPException`.
- **Confidence:** Cao; đây là điểm tôi sửa theo phản biện của Claude.

### ISO-AG-005
- **Target:** Antigravity §2, lập luận latency để chọn pool.
- **Severity:** Medium.
- **Claim:** Chi phí ba lần spawn không phản bác được phương án Codex/Claude vốn chỉ spawn một lần/request.
- **Evidence:** **[CONFIRMED]** `rg -n '845|3 bước|20 trang' docs/implementation/reviews/iso-round1-antigravity.md` cho thấy phép suy luận ba bước; E2 đo một worker cho cặp PDF 20 trang dưới một giây ở nhánh thuần. Kế hoạch v2:75 quy định H3b cho **warm-run**.
- **Counterexample:** Với spawn/request, request thứ hai vẫn chịu startup worker; không được bỏ startup khỏi phép đo “warm”. Ngược lại, PDF tổng hợp nhỏ cũng không đại diện corpus hợp đồng.
- **Recommendation:** Giữ spawn/request cho đồ án hiện tại. Đo H3b trên corpus đại diện, gồm startup mỗi request, HTTP và toàn pipeline. Chỉ đổi sang pool khi số đo chứng minh cần; khi đó pool vẫn giữ một worker/request.
- **Confidence:** Cao về lỗi so sánh; trung bình về lựa chọn hiệu năng cuối cùng.

### ISO-AG-006
- **Target:** Antigravity §3.3, so sánh RAM và chi phí IPC.
- **Severity:** Medium.
- **Claim:** Buffer copy 64 KiB không phải peak RAM request; ước lượng bytes IPC cần xét đúng vòng đời thay vì cộng mọi bản sao của hai tệp cùng lúc.
- **Evidence:** **[CONFIRMED, từ báo cáo]** `Get-Content` CL §3.3 nói gửi hai PDF tuần tự. AG §3.3 tính 90–120 MiB/request; §4 ghi `5000 changes ... time=8384.8 ms`, chưa tách thời gian tính diff khỏi truyền kết quả.
- **Counterexample:** File input vẫn có thể đi kèm extraction result lớn tại parent; bytes tuần tự lại không nhất thiết giữ đồng thời toàn bộ các bản sao được giả định.
- **Recommendation:** Chọn file vì giảm copy input lớn và đơn giản hóa deadline, nhưng đo peak private memory của parent và worker. Tách benchmark encode/transfer/decode khỏi workload; chưa dùng các ước lượng này để khẳng định 4 worker an toàn.
- **Confidence:** Cao về hạn chế bằng chứng; trung bình về peak RAM thực tế.

### ISO-CL-005
- **Target:** Claude §3.5, timeout 422 và crash 500 mặc định.
- **Severity:** Medium.
- **Claim:** Hết wall-clock deadline không chứng minh input vô hiệu; không có queue cũng không khiến thời gian chỉ phụ thuộc input.
- **Evidence:** **[CONFIRMED, từ báo cáo]** `rg -n '422|máy quá tải' docs/implementation/reviews/iso-round1-claude.md`: §5/§9 thừa nhận tài liệu hợp lệ có thể timeout khi máy quá tải. **[HYPOTHETICAL]** Cùng input thành công khi máy rảnh, timeout khi CPU bị tranh chấp.
- **Counterexample:** Trả 422 khiến client có thể phân loại nhầm tài liệu hợp lệ thành lỗi cần sửa dữ liệu.
- **Recommendation:** Chọn **504 `PROCESSING_TIMEOUT`**, **503 `PROCESSING_BUSY`**, **500 `PROCESSING_FAILED`**, body phẳng. Đây là quy ước API được công bố; không khẳng định 504 là lựa chọn duy nhất theo HTTP. Giữ nguyên các 400/413/422 hiện hữu; không trả traceback.
- **Confidence:** Cao về phân loại lỗi; trung bình về lựa chọn status 504 so với các quy ước API khác.

## Self-correction

- **Sửa ranh giới:** Bỏ đề xuất worker gọi nguyên service có `HTTPException`; chọn một job thuần gồm extraction ×2, ghép text, kiểm giới hạn, diff, mapping và serialization. Adapter HTTP ở parent.
- **Giữ mô hình:** Một process và một slot cho toàn request. Không chọn pool chỉ từ số đo import; thừa nhận spawn lặp lại chiếm khoảng 17–40% ngân sách 3 giây theo khoảng startup đang xét.
- **Giữ file IPC:** Input copy theo chunk, tối đa 30 MiB cho hai PDF; multipart có thể giữ thêm bản spool. `result.part → result.json`; chỉ cleanup sau khi xác nhận worker chết. Output/R-BOMB chưa có giới hạn RAM cứng.
- **Sửa bảo đảm deadline:** `join(remaining)` chỉ bảo vệ pha chờ worker. Startup, nhận kết quả và CPU decode tại parent phải có coverage riêng; chưa có implementation để tuyên bố đã đóng toàn bộ.
- **Sửa bảo đảm orphan:** Watchdog bắt đầu sau khi worker vào entrypoint nên chưa bao phủ toàn bootstrap. Trên Windows, dùng Job Object khi yêu cầu worker chết cùng API, cộng watchdog dự phòng; phải kiểm thử cả nhánh gán Job thất bại và khoảng trước khi gán.
- **Sửa cấu hình test:** Truyền rõ timeout/deadline, `MAX_PDF_PAGES`, `MAX_TEXT_CHARS` và các giới hạn hiệu lực cần thiết. E3 xác nhận monkeypatch không tự truyền. Unit test extractor vẫn chạy trực tiếp; API acceptance phải dùng spawn thật.
- **Không chốt số test sửa trước diff:** Claude có bằng chứng một test đổi đích patch trên bản sao của họ; không suy ra thiết kế khác cũng chỉ sửa một test. Baseline 92 tests pass trong 1,82 giây; con số 13–20 giây sau isolation vẫn chấp nhận được nhưng phải đo lại.
- **Acceptance còn thiếu:** Startup stall, IPC chậm/output lớn, hết deadline giữa các pha, kill không xác nhận thoát, recovery, hai worker treo cùng health, gate không đọc body, shutdown/disconnect, API bị kill, PID/handle/temp cleanup và lỗi `OSError`/`MemoryError`.

## Lập trường 9 điểm

1. **Mô hình:** Chọn spawn/request; chấp nhận chi phí startup cho đồ án hiện tại, nhưng chỉ xác nhận H3b sau benchmark corpus thật có tính startup mỗi request.
2. **Ranh giới:** Toàn pipeline thuần trong worker; HTTP/FastAPI ở parent; truyền giới hạn tường minh để giữ testability.
3. **Slot:** Một slot/request từ admission đến khi xác nhận worker chết và hoàn tất cleanup; không mượn lại giữa ba bước.
4. **IPC:** File input + file result; Pipe chỉ nên mang control nhỏ; tránh join trước nhận output Pipe và luôn join xác nhận trước unlink trên Windows.
5. **Mã lỗi:** 504 `PROCESSING_TIMEOUT`, 503 `PROCESSING_BUSY`, 500 `PROCESSING_FAILED`; giữ nguyên lỗi input hiện tại.
6. **Admission:** Khởi đầu 2 slot, queue 0, gate trước đọc body; thêm upload timeout, tính giới hạn theo tổng số API process.
7. **Orphan:** Watchdog worker cộng Windows Job Object cho bảo đảm chết cùng API; fallback phải công khai mức bảo đảm giảm, không chỉ log rồi coi như đạt.
8. **Coverage:** Một deadline monotonic gồm startup và toàn job; `send`, `recv`, startup, xử lý kết quả và cleanup phải được xét riêng; chưa chứng minh thì chưa đóng R-TIMEOUT.
9. **Tests:** Chấp nhận suite dài hơn; timeout test truyền từ parent, harness dưới 60 giây, marker vào workload, kiểm PID/handle/temp và chạy lại toàn bộ 92 tests.
---

# PHẦN CL — tác giả: Claude

> Ghi chú Orchestrator: lần chạy Round 2 đầu tiên của Claude subagent thất bại (HTTP 429 do hết quota 5 giờ, sau đó stream treo 600 s). Báo cáo này đến từ một Claude subagent mới, được giao `iso-round1-claude.md` làm lập trường của mình và **không** được đọc các file `iso-round2-*`.

Vai trò: Agent B. Tôi chỉ đọc repo và không đọc file `iso-round2-*` nào. Tôi chạy 2 thí nghiệm, script nằm trong `C:\Users\Admin\AppData\Local\Temp\claude\7a81e431fe1166c9\3ae8a7db-bd9c-402e-b3dc-61914ab153f4\scratchpad\iso-claude2\`. Cả hai đều có `faulthandler.dump_traceback_later(25, exit=True)` và `timeout 30`. Sau khi chạy, `tasklist` không còn `python.exe` nào.

## Bằng chứng mới (Round 2)

**E1 [CONFIRMED] Chi phí import khi khởi động interpreter mới, đo theo từng ranh giới worker** (`e1_import.py`, `subprocess.run` 3 lần cho mỗi trường hợp, cwd là repo):

```text
bare                 0.078 0.067 0.068
extractor+engine     0.476 0.471 0.458
comparison_service   1.109 1.149 1.117
```

Nếu worker import service (ranh giới của Codex), chuỗi import kéo theo `fastapi`/`HTTPException` qua `document_service`. Mỗi request mất thêm khoảng **0,65 s** so với ranh giới extractor/engine. Kết quả này khớp con số 1,16–1,26 s mà Codex đo ở Round 1.

**E2 [CONFIRMED] `threading.Timer(deadline, kill)` gỡ được parent đang kẹt trong `send`** (`e2_timer.py`):

```text
A send raised BrokenPipeError after 2.01s fired=True     # con không bao giờ recv; send 15 MiB chặn tới khi bị kill
A exitcode -15
B result 15728640 in 0.37s; children=[]                  # đường bình thường, timer bị cancel
```

Có hai kết luận. (a) Lỗ "send chặn khi con chưa đọc" (điểm 8) có thật: parent bị chặn cho tới khi có bên kill con. (b) Một timer kill phía parent đóng được lỗ này mà không cần bắt tay. Cùng cơ chế đó cũng bao luôn trường hợp startup treo và `recv` sau `poll` với message lớn.

## Phản biện

### ISO-AG-001 · Target: AG §3.2, §9.4 (mượn slot theo từng bước) · Severity: **High**
- **Claim:** Với `/pdf`, AG mượn slot 3 lần, và thời gian chờ hàng đợi bị tính vào deadline chung. Khi tải bão hòa, một request đã extract xong cả hai tệp vẫn phải xếp hàng lại ở bước `diff_words` và có thể nhận 504. Như vậy công extract bị bỏ phí, và cùng một input có lúc 200 có lúc 504 tùy tải.
- **Evidence:** [CONFIRMED trên văn bản] AG tự thừa nhận ở §9.4 và §5.5 (`slots.get(timeout=remaining)` hết giờ thì 504). Hàng đợi 8 cộng 3 lần lấy slot nghĩa là một request có thể chờ tới 3 lần.
- **Counterexample:** 4 worker bận và 8 request đang chờ. Request X lấy slot, extract `old`, trả slot. Lần lấy slot thứ hai phải chờ sau 8 request khác (mỗi request có thể chạy tới 30 s). X hết 30 s trước khi được diff.
- **Recommendation:** Mỗi request giữ 1 slot từ đầu tới cuối (context manager), đúng hướng nâng cấp AG tự đề xuất. Lý do AG đưa ra để mượn theo bước là "giữ test" và "fail-fast `TEXT_TOO_LONG`". Mô hình session của tôi cũng giữ được cả hai, xem ISO-AG-004.
- **Confidence:** Cao.

### ISO-CX-001 · Target: Codex §3.1 (worker chạy toàn bộ service) · Severity: **High**
- **Claim:** Đưa `compare_text`/`extract_document`/`compare_document` vào worker gây ra ba hệ quả:
  - Phải import FastAPI trong con, tốn thêm khoảng 0,65 s mỗi request (E1).
  - Phải tuần tự hóa `HTTPException`, hoặc bắt nó trong con để dựng envelope, nên con buộc phải hiểu FastAPI.
  - Monkeypatch ở parent không có hiệu lực trong con. `tests/test_comparisons_api.py:285` (`MAX_PDF_PAGES = 2`) sẽ fail nếu không thêm tham số override chạy xuyên qua chữ ký các hàm service.
- **Evidence:** [CONFIRMED] E1. [CONFIRMED] grep cho 10 lời gọi `monkeypatch.setattr`; lời gọi ở dòng 285 đi qua route, tức là vào worker. Codex §6 tự thừa nhận phải truyền "giới hạn hiệu lực".
- **Counterexample:** Worker chạy `compare_document` sẽ gọi lại `validate_pdf_stream` (đã chạy ở parent) với hằng số gốc. Nếu sau này có test hạ `MAX_UPLOAD_FILE_BYTES` để thử nhánh ở worker, test đó sẽ lệch âm thầm.
- **Recommendation:** Đặt ranh giới quanh extractor/engine. Ánh xạ lỗi, kiểm độ dài và mapping vẫn chạy ở parent. Một deadline cho cả request vẫn giữ được nhờ session (một process cho mỗi request, nhiều lời gọi).
- **Confidence:** Cao.

### ISO-AG-002 · Target: AG §3, §3.4 (pool thường trực) · Severity: **Medium-High**
- **Claim:** Lợi ích "ấm" của pool biến mất đúng ở những chỗ quan trọng:
  - (a) Sau mỗi lần kill (R-LOOP/R-CPU), slot đó khởi động lạnh lại khoảng 0,8 s. Khi bị tấn công, pool thoái hóa thành spawn mỗi request.
  - (b) Fixture `client` có scope function, nên lifespan tắt pool sau mỗi test. AG tự thừa nhận suite vẫn mất 16–20 s, tức là test không được hưởng gì từ worker ấm.
  - (c) Đổi lại phải thêm lazy-start, handshake, recycle 50, cờ `_shutting_down`, Job Object `ctypes`, khoảng 150 LOC. Đó là thêm rất nhiều trạng thái vòng đời cho một đồ án một người làm.
- **Evidence:** [CONFIRMED trên văn bản] AG §6 và §9.5. Số đo của AG cho thấy rò trạng thái thực tế nhỏ (+1,4 MB sau bom CIDFont). Vậy lý do chính để chọn hay bỏ pool là độ phức tạp, không phải rò rỉ.
- **Counterexample:** H3b yêu cầu E2E < 3 s. Spawn theo ranh giới extractor tốn khoảng 0,47–0,55 s (E1; Orchestrator đo 0,6 s), còn lại khoảng 2,4 s cho extract và diff. `/pdf` trên fixture đo được 0,70 s (Round 1 §4.4). Với PDF 20 trang thì [HYPOTHETICAL], cần benchmark.
- **Recommendation:** Spawn mỗi request. Chỉ chuyển sang pool khi benchmark H3b thật sự fail. Khi đó chỉ phải thay ruột `worker_session`, service không đổi.
- **Confidence:** Trung bình-cao.

### ISO-CX-002 · Target: Codex §3.4 (ASGI gate trước khi đọc body) · Severity: **Medium**
- **Claim:** Lấy slot trước khi nhận body thì slot bị giữ suốt thời gian upload. Chỉ có 2 slot nên 2 client upload chậm (≤ 31 MiB) đủ chặn mọi xử lý. Codex tự liệt kê trường hợp này ở §5 ("Hai client upload rất chậm"). Ngoài ra middleware phải tự khớp path và phải nhả slot đúng một lần qua mọi nhánh 400/413/422/disconnect, nên cần thêm một class ASGI.
- **Evidence:** [HYPOTHETICAL] Theo hiểu biết của tôi, uvicorn mặc định không có timeout đọc body. Chưa đo.
- **Counterexample:** Lợi ích duy nhất của gate là không tốn băng thông và đĩa spool khi đằng nào cũng trả 503. Khi chạy cục bộ để demo, lợi ích này không đáng kể.
- **Recommendation:** Kiểm admission trong service, sau khi body đã parse và validate, bằng `acquire(blocking=False)`.
- **Confidence:** Trung bình.

### ISO-CX-003 · Target: Codex §3.2 (file tạm vào, `result.json` ra) · Severity: **Medium**
- **Claim:** Lý do chọn file IPC là deadlock pipe. Nhưng deadlock đó chỉ xảy ra khi gọi `join()` trước `recv()`, tức là dùng sai. Gọi `poll(remaining)` rồi `recv()` thì không deadlock. File IPC thêm việc ghi đĩa (`/text` cũng ghi JSON), dọn temp sau khi API chết, ràng buộc thứ tự unlink/join (WinError 32, AG đo được) và nguy cơ antivirus khóa tệp.
- **Evidence:** [CONFIRMED] Round 1 §4.1 của tôi: kết quả 2 M ký tự qua Pipe mất 0,49 s; 15 MiB vào mất 0,48 s; E2-B mất 0,37 s. Prototype "2MiB_pipe_join_before_read" của Codex dùng đúng thứ tự sai đó.
- **Counterexample:** Codex nói `result.json` tránh unpickle, nhưng cũng tự nhận đó không phải ranh giới bảo mật. Parse JSON ở parent cũng không có deadline (Codex §9.4), không khác `recv`.
- **Recommendation:** Dùng Pipe với `poll` trước `recv`, cộng timer kill (E2).
- **Confidence:** Cao.

### ISO-AG-003 · Target: AG §3.4.4 (Job Object `ctypes`) · Severity: **Medium**
- **Claim:** Với pool thường trực, Job Object trở thành **bắt buộc**. Worker nhàn rỗi sống vô thời hạn nên không đặt được watchdog `faulthandler` có hạn. Thiết kế buộc phải có khoảng 30 dòng `ctypes` (layout `JOBOBJECT_EXTENDED_LIMIT_INFORMATION`, kiểm giá trị trả về) và phải quản lý handle job theo lifespan. Phần này dễ sai và khó giải thích khi bảo vệ.
- **Evidence:** [CONFIRMED, của AG] Job Object giết được con khi parent bị kill. [HYPOTHETICAL, AG tự ghi] tương tác với `--reload` chưa được thử.
- **Counterexample:** Với spawn mỗi request, con mồ côi sống tối đa timeout + 5 s, tốn khoảng 35 MB (Round 1 §4.2). Đây là chặn trên đủ tốt cho tình huống hiếm (API bị hard-kill).
- **Recommendation:** Dùng watchdog trong worker là đủ. Job Object là hardening tùy chọn, chỉ đáng làm khi muốn giới hạn RAM (R-BOMB).
- **Confidence:** Trung bình-cao.

### ISO-CX-004 · Target: Codex §3.5 (và AG §3.5): timeout trả 504 · Severity: **Medium**
- **Claim:** R-LOOP/R-CPU là input độc tất định: gửi lại cùng input thì timeout lại. 504 là mã lỗi gateway. Proxy hoặc client có chính sách retry trên 5xx/504 sẽ gửi lại, đốt thêm 30 s CPU mỗi lần. Phase A đã phân loại "input vượt giới hạn tài nguyên" là 422 (`PDF_TOO_MANY_PAGES`, `TEXT_TOO_LONG`).
- **Evidence:** [HYPOTHETICAL] Hành vi retry tùy client, chưa đo.
- **Counterexample:** Phản biện hợp lệ: khi máy quá tải, một tài liệu hợp lệ cũng có thể timeout. Với **thiết kế của AG** (hàng đợi tính vào deadline), timeout phụ thuộc tải nên 504 nhất quán. Với hàng đợi = 0 (Codex, tôi), thời gian gần như chỉ phụ thuộc input nên 422 nhất quán hơn.
- **Recommendation:** Hàng đợi 0 thì dùng 422 `PROCESSING_TIMEOUT`, không kèm `Retry-After`. Nếu tác giả chọn 504 thì tuyệt đối không gửi `Retry-After`.
- **Confidence:** Trung bình.

### ISO-AG-004 · Target: AG §3.2 (lý do "giữ 100% test") · Severity: **Low-Medium**
- **Claim:** AG đúng: giữ lời gọi `extract_document` trong `comparison_service` thì không phải sửa test nào, còn tôi phải sửa 1 test. Nhưng lợi thế này đến từ việc giữ tên hàm, không phải từ việc mượn slot theo bước. Đổi lại AG gặp ISO-AG-001.
- **Evidence:** [CONFIRMED] Round 1 §4.4 của tôi: test `test_compare_document_checks_both_files_before_extracting` fail cho tới khi đổi đích monkeypatch. Test này patch `comparison_service.extract_document`, còn `tests/test_comparison_service.py:203–216` gọi `extract_document` với 2 tham số.
- **Recommendation:** Sửa 1 test (giữ nguyên ý nghĩa) là chi phí chấp nhận được. Đổi tên ngược để được 0 test sửa thì sẽ phá `:203–216`.
- **Confidence:** Cao.

### ISO-AG-005 · Target: AG §3.4.1 (`poll(WORKER_STARTUP_TIMEOUT_SECONDS = 10)`) · Severity: **Low**
- **Claim:** Thời gian chờ handshake là hằng số 10 s, không phải `min(10, remaining)`. Cold start sau một lần kill vì vậy có thể đẩy tổng thời gian request vượt 30 s. Lỗ `recv` sau `poll` (AG §9.3) vẫn còn mở.
- **Evidence:** [CONFIRMED trên văn bản] AG §3.4.1 và §9.3.
- **Recommendation:** Dùng timer kill theo deadline (E2). Mọi chỗ chặn ở parent sẽ bị gỡ bằng `BrokenPipeError`/`EOFError`, kèm cờ `fired` để phân biệt timeout với crash.
- **Confidence:** Cao.

### ISO-CX-005 · Target: Codex §3.3 (terminate → join(1) → kill → join(1), registry cho process "không giết được") · Severity: **Low**
- **Claim:** Trên Windows, `terminate()` và `kill()` cùng là `TerminateProcess`, nên bước thứ hai thừa. Registry cho process không giết được và slot "không dùng được" là thiết kế quá mức, chưa có bằng chứng tình huống đó xảy ra.
- **Evidence:** [CONFIRMED] Orchestrator đo `kill()` dừng được R-LOOP với exitcode −15; E2-A cũng cho −15.
- **Recommendation:** `kill()` rồi `join()` trong `finally`.
- **Confidence:** Cao.

### ISO-CX-006 · Target: Codex §7 (thời gian suite) · Severity: **Low**
- **Claim:** Codex chưa ước lượng thời gian suite. Mỗi request mất khoảng 1,1 s (E1) nhân với khoảng 20 test API đi qua worker, cộng timeout test 5 s cho mỗi acceptance test. Suite có thể lên khoảng 25–40 s [HYPOTHETICAL]. Con số đo được của tôi là 12,91 s cho 92 test.
- **Recommendation:** Dùng ranh giới extractor/engine và timeout test 2 s. Monkeypatch timeout có hiệu lực vì deadline được thi hành ở parent.
- **Confidence:** Trung bình.

## Self-correction

1. **Đóng lỗ §5.1 và điểm 8 bằng timer kill (thay đổi bắt buộc).** Trong `worker_session`, ngay sau `process.start()`:
   ```python
   timed_out = threading.Event()
   timer = threading.Timer(timeout_seconds, lambda: (timed_out.set(), process.kill()))
   timer.daemon = True; timer.start()
   ```
   Thêm `timer.cancel()` vào `finally`. Trong `run`, khi gặp `EOFError`/`OSError` thì ném `WorkerTimeoutError` nếu `timed_out.is_set()`, ngược lại ném `WorkerCrashedError`. Giữ `poll(remaining)` như cũ. Timer bao được send chặn, startup treo và `recv` dở dang [CONFIRMED E2]. Lý do không chọn handshake "ready" như AG: handshake chỉ bao pha khởi động.
2. **Mã lỗi khi crash:** chuyển sang **500 `{"error_code":"PROCESSING_FAILED"}`** cho `WorkerCrashedError`, đồng ý với Codex và AG. Body phẳng như D4 nên không có lý do giữ body mặc định. `MemoryError`/`OSError` ném lại từ con vẫn giữ hành vi 500 hiện tại, không đổi hợp đồng Phase A.
3. **RAM ở IPC:** gửi dữ liệu PDF bằng `send_bytes` riêng (tên hàm vẫn qua `send`) để bỏ bản sao pickle 15 MiB ở parent. Đỉnh RAM mỗi tệp còn khoảng 15 MiB thay vì 30 MiB. Đây là cải tiến nhỏ, tùy chọn.
4. **Đã kiểm bẫy AG §5.1** (`TimeoutError` là lớp con của `OSError`): `WorkerTimeoutError` của tôi kế thừa `Exception`, không kế thừa `TimeoutError`, nên không bị `except OSError` nuốt. Sẽ ghi chú điều này trong code.
5. **Giữ nguyên:** spawn mỗi request, ranh giới extractor/engine, Pipe truyền bytes, 4 slot, hàng đợi 0, 422, watchdog trong worker, sửa 1 test.

## Lập trường 9 điểm

1. **Mô hình:** spawn mỗi request theo kiểu session (một process phục vụ nhiều lời gọi của cùng request). Chi phí khoảng 0,5 s nằm trong ngân sách H3b 3 s. Pool thường trực không đáng độ phức tạp vì mất "ấm" sau mỗi lần kill và trong test.
2. **Ranh giới:** chỉ extractor/engine. Ranh giới toàn service tốn thêm 0,65 s import FastAPI (E1), phải tuần tự hóa `HTTPException` và làm vỡ monkeypatch `MAX_PDF_PAGES`. Ranh giới của tôi phải sửa 1 test.
3. **Slot:** 1 slot cho mỗi request, giữ từ đầu tới cuối. Mượn theo bước có thể trả 504 sau khi đã extract xong.
4. **IPC:** Pipe truyền bytes, `poll` trước `recv` (không deadlock), cộng timer kill. Không dùng file tạm và không có `result.json`, nên không gặp WinError 32 và không phải sweep temp.
5. **Mã lỗi:** timeout trả 422 `PROCESSING_TIMEOUT` (vì hàng đợi 0, không có `Retry-After`). Crash trả 500 `PROCESSING_FAILED`. Bận trả 503 `SERVER_BUSY` + `Retry-After`.
6. **Admission:** 4 slot, hàng đợi 0, kiểm trong service bằng `acquire(blocking=False)` sau khi đọc body. Không đặt ASGI gate vì slot sẽ bị giữ trong lúc upload.
7. **Orphan:** watchdog `faulthandler(timeout+5, exit=True)` trong worker là đủ (orphan sống tối đa khoảng 35 s). Job Object là tùy chọn và chỉ bắt buộc nếu chọn pool thường trực.
8. **Hard-timeout coverage:** `threading.Timer(deadline, kill)` ở parent bao mọi chỗ chặn: send, startup, `recv` dở [CONFIRMED E2]. Phần còn hở là parse kết quả ở parent, vốn rẻ.
9. **Test:** đo được 12,9 s cho 92 test và 21,8 s cho 99 test. Monkeypatch `COMPARISON_TIMEOUT_SECONDS = 2` có hiệu lực vì deadline do parent thi hành; truyền watchdog qua tham số. Fixture assert `active_children() == []`. Kiểm temp: không có entry mới.

---

# PHẦN AG — tác giả: Antigravity

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
