# Process Isolation — Round 3 Brief (Rebuttal)

Chỉ đọc trong repo. Thí nghiệm (nếu cần) tối đa 2 cái, mỗi cái có watchdog và < 30 s, không chạy tác vụ nền, dọn process con.

Đọc `docs/implementation/reviews/iso-round2-cross.md` (ba báo cáo Round 2; ID dùng tiền tố tác giả `CX/`, `CL/`, `AG/`).

## Đã hội tụ (không cần tranh luận lại, chỉ phản đối nếu có bằng chứng mới)
- 1 slot cho mỗi request, giữ từ đầu tới khi worker đã chết và cleanup xong; hàng đợi chờ = 0; đầy → 503 + `Retry-After`.
- Worker không import FastAPI; `HTTPException`/ánh xạ HTTP ở parent; các giới hạn hiệu lực (`max_pages`, timeout, …) truyền tường minh từ parent (monkeypatch không sang `spawn`).
- Deadline do **parent** thi hành, một ngân sách 30 s cho cả request; kill thật bằng `Process.kill()` (`TerminateProcess`) rồi `join` hữu hạn; `Future.result(timeout)` bị loại.
- Watchdog `faulthandler.dump_traceback_later(timeout + ε, exit=True)` trong worker.
- Worker crash → 500 `PROCESSING_FAILED` (body phẳng); `MemoryError`/`OSError` không thành 400.
- Route xử lý giữ `def`; `/health` giữ `async def`.

## Điểm còn mở — lấy lập trường cuối (ACCEPT / REJECT / PARTIAL / NEEDS EXPERIMENT, kèm lý do/bằng chứng)
- **O1 Mô hình:** spawn mỗi request (Codex, Claude) vs pool thường trực có giám sát (Antigravity, vì H3b < 3 s và Phase B sẽ nạp thêm scipy/sklearn). Có nên "spawn trước, giữ interface `worker_session` để đổi ruột sang pool khi benchmark H3b fail"?
- **O2 Phạm vi một lần gọi worker:** một lời gọi chạy toàn pipeline thuần (extract ×2 + ghép + kiểm giới hạn + diff + mapping — Codex) vs session nhiều lời gọi tuần tự tới extractor/engine, ánh xạ lỗi/kiểm độ dài/mapping ở parent (Claude, Antigravity).
- **O3 IPC:** file vào + `result.json` (Codex) vs bytes qua Pipe (Claude) vs file tạm vào + Pipe ra (Antigravity). Đối chiếu CX/ISO-CL-001 (send/recv chặn ngoài `poll`) với CL E2 (`threading.Timer(deadline, kill)` gỡ được `send` đang chặn) và WinError 32 khi unlink trước `join`.
- **O4 Cơ chế thi hành deadline:** `threading.Timer(remaining, kill)` (Claude, Antigravity) vs `join(remaining)` + file result (Codex). Phân biệt timeout vs crash ra sao (cờ `fired`)?
- **O5 Mã lỗi timeout:** 504 `PROCESSING_TIMEOUT` (Codex, Antigravity) vs 422 `PROCESSING_TIMEOUT` (Claude). Có kèm `Retry-After` không?
- **O6 Admission:** chặn ở ASGI gate trước khi đọc body (Codex) vs trong service sau khi parse/validate (Claude, Antigravity); 2 hay 4 slot.
- **O7 Job Object:** bắt buộc trên Windows (Codex, Antigravity) vs tùy chọn, watchdog là đủ cho spawn mỗi request (Claude).

## Định dạng (Markdown, tiếng Việt, ≤ ~150 dòng)
`# Isolation Round 3 — <Agent>`; mục "Phản hồi phản biện nhắm vào tôi" (mỗi dòng: `ID — ACCEPT/REJECT/PARTIAL/NEEDS EXPERIMENT — lý do`); mục "Lập trường O1–O7".
