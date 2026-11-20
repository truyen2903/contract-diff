# Isolation Round 2 — Claude

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
