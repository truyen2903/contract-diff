# Process Isolation — Round 2 Brief (Cross-Examination)

Chỉ đọc trong repo (không sửa/tạo/xóa, không git ghi). Prototype chỉ ngoài repo; mọi thí nghiệm có thể treo phải có watchdog và kết thúc < 60 s; dọn sạch process con.

Đọc ba báo cáo Round 1 (đề bài: `docs/implementation/reviews/isolation-brief.md`):
- `docs/implementation/reviews/iso-round1-codex.md` — process-per-request chạy toàn bộ job; file tạm vào + `result.json` ra; 2 slot, hàng đợi 0; 504/503/500.
- `docs/implementation/reviews/iso-round1-claude.md` — "worker session": 1 process/request, nhiều lời gọi tuần tự qua Pipe (chỉ extractor/engine trong worker); bytes qua Pipe; 4 slot, hàng đợi 0; timeout → **422**; kill vô điều kiện; watchdog trong worker.
- `docs/implementation/reviews/iso-round1-antigravity.md` — pool thường trực có giám sát (lazy-start, handshake, recycle 50 task); file tạm; 4 worker + 8 chờ; mượn slot theo từng bước; Windows Job Object `KILL_ON_JOB_CLOSE`; 504/503/500.

Dữ kiện Orchestrator đã đo (watchdog bảo vệ): `Future.result(timeout)` hết hạn nhưng worker vẫn sống; `Process.kill()` dừng được worker kẹt R-LOOP (exitcode −15); spawn + import pdfplumber ≈ 0,6 s.

## Nhiệm vụ
Phản biện **hai báo cáo không phải của bạn**; bảo vệ hoặc tự sửa phương án của mình. Lấy lập trường rõ cho các điểm bất đồng:

1. **Mô hình:** spawn mỗi request (Codex/Claude) vs pool thường trực (Antigravity). Độ trễ ~0,5–1,2 s/request có chấp nhận được với đồ án (H3b v2: E2E < 3 s cho PDF 20 trang)? Rò trạng thái/độ phức tạp của pool thường trực có đáng?
2. **Ranh giới worker:** toàn bộ service/job (Codex) vs chỉ extractor/engine (Claude, AG). Ảnh hưởng `HTTPException`/FastAPI import trong worker, monkeypatch trong test (spawn không thấy monkeypatch), số test phải sửa.
3. **Slot theo request vs theo bước:** AG mượn slot 3 lần cho `/pdf` (có thể 504 sau khi đã extract xong) vs 1 slot/request.
4. **IPC:** bytes qua Pipe vs file tạm vào vs `result.json` ra. Deadlock pipe khi `join()` trước `recv()`; `send` chặn khi con chưa đọc; khóa file Windows khi unlink trước join; RAM 2×15 MiB.
5. **Mã lỗi timeout:** 504 vs 422 `PROCESSING_TIMEOUT`; mã cho crash (500 có `error_code` `PROCESSING_FAILED` hay 500 mặc định?).
6. **Admission:** số slot (2/4), hàng đợi 0 hay có chờ (8)? Chặn ở ASGI gate trước khi đọc body (Codex) hay trong service (Claude/AG)?
7. **Chống orphan khi API chết:** watchdog `faulthandler` trong worker (Codex/Claude) vs Windows Job Object `ctypes` (AG). Có cần cả hai? Độ phức tạp `ctypes`?
8. **Hard-timeout coverage:** khoảng hở chưa có deadline (send chặn lúc khởi động, startup treo, `recv` sau `poll` với message lớn, đọc/parse `result.json` ở parent).
9. **Kế hoạch test:** thời gian suite (92 test: 2,4 s → 13–20 s?), cách hạ timeout trong test khi worker spawn không thấy monkeypatch, kiểm orphan/temp file.

## Định dạng (Markdown, tiếng Việt, ≤ ~250 dòng)
Mỗi phản biện: **Issue ID** ISO-<CX|CL|AG>-NNN · **Target** · **Severity** · **Claim** · **Evidence** ([CONFIRMED] lệnh+output / [HYPOTHETICAL]) · **Counterexample** · **Recommendation** · **Confidence**. Tối đa ~12 issue, theo severity.
Cuối: **Self-correction** và **Lập trường 9 điểm** (một dòng mỗi điểm).
Tiêu đề: `# Isolation Round 2 — <Agent>`.
