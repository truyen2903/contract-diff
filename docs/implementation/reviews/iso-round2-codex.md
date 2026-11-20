# Isolation Round 2 — Codex

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