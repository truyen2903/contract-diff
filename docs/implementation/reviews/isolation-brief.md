# Process Isolation Brief — Round 1 (đề bài chung)

Bạn là reviewer **chỉ đọc**: không sửa/tạo/xóa file trong repository, không git ghi. Chỉ **thiết kế** — chưa có code nào được viết cho phần này.

## Bối cảnh (đọc trước)
- `docs/implementation/phase-a-report.md` (hợp đồng API hiện tại + rủi ro mở R-LOOP, R-CPU, R-TIMEOUT, R-BOMB)
- `docs/implementation/coding-style-profile.md`
- `docs/implementation/reviews/round3-consensus.md` (quyết định D1–D22 + mục 4)
- Code: `app/main.py`, `app/api/routes/*.py`, `app/services/*.py`, `app/extractors/pdf_extractor.py`, `app/engines/*.py`, `app/core/config.py`, `tests/`
- Môi trường: Windows 11, Python 3.14.3, FastAPI 0.143.3, Starlette 1.8.0, 16 CPU logic, `multiprocessing` start method mặc định = `spawn`. Route hiện là `def` đồng bộ (threadpool AnyIO, 40 thread).

## Rủi ro cần đóng
- **R-LOOP (Critical):** PDF ~290 byte có object tự tham chiếu trong cây `/Pages` → `pdfminer.pdftypes.resolve1` lặp vô hạn (đã xác minh cả code gốc). Mẫu: `docs/implementation/reviews/code-review-antigravity.md` CR-AG-001.
- **R-CPU (High):** `diff_words` (`SequenceMatcher(autojunk=False)`): `/text` 34 000 ký tự `"a b "` lặp ~34 s.
- **R-TIMEOUT (High):** chưa có hard timeout 30 s (v2 §3.2).

## Bài toán
Thiết kế cô lập xử lý PDF (`extract_pdf`) và text diff (`diff_words`) khỏi process FastAPI. So sánh **ít nhất 3 phương án**:
1. Process-per-request (mỗi request một `multiprocessing.Process`, join(timeout) rồi terminate/kill).
2. Persistent worker pool (`ProcessPoolExecutor` / `multiprocessing.Pool`, có/không `max_tasks_per_child`).
3. Dedicated subprocess worker (một hoặc vài process sống lâu, giao tiếp qua pipe/queue, tự khởi động lại khi bị kill).
(Có thể đề xuất thêm phương án lai.)

Tiêu chí: correctness, hard timeout, worker termination, concurrency, Windows compatibility, memory overhead, startup latency, maintainability, độ phức tạp.

## Ràng buộc bắt buộc
- Hard timeout 30 s phải **thực sự kết thúc** xử lý bị treo. Lưu ý: `Future.result(timeout)` **không** giết worker; `ProcessPoolExecutor` không có API kill một task. Phương án được chọn phải chỉ ra cơ chế terminate/kill thực tế và chứng minh (prototype ngoài repo nếu được).
- PDF độc hại không làm treo API server; text diff tốn CPU bị giới hạn thời gian.
- Worker lỗi được dọn dẹp, hệ thống tiếp tục phục vụ request mới.
- Giới hạn số worker và số request đang chờ (chống DoS) — trả lỗi gì khi đầy?
- Không truyền `UploadFile`/file handle qua ranh giới process (spawn trên Windows). Truyền gì (bytes? đường dẫn file tạm?) và chi phí bộ nhớ ra sao (tối đa 2 × 15 MiB)?
- Không phá API response contract hiện tại (xem phase-a-report). Phân biệt rõ: invalid input (400/413/422 hiện có), processing failure (worker crash/MemoryError → ?), timeout (→ mã gì? 504? 422? `error_code` gì?).
- Không coi process isolation là OS-level sandbox.
- Giữ coding style, không overengineering (đồ án 1 sinh viên).
- Đặt ranh giới ở đâu: route, service, hay quanh `extract_pdf`/`diff_words`? Có cô lập toàn bộ `compare_document` (extract ×2 + diff) trong một lần gọi worker không? Timeout tính cho cả request hay từng bước?
- Route nên giữ `def` hay đổi `async def`? Ảnh hưởng threadpool khi chờ worker?
- Test: làm sao viết acceptance test chạy PDF gây treo **luôn có timeout bảo vệ** (không bao giờ chạy trong process pytest chính không giới hạn)? Thời gian test suite (timeout 30 s trong test → cần cấu hình hạ timeout)?

## Acceptance tests bắt buộc (thiết kế cách kiểm)
PDF tự tham chiếu không làm treo server; text diff pathological bị cắt bởi timeout; worker bị kill không làm treo request sau; request hợp lệ vẫn đúng; health phản hồi trong khi worker treo; không còn orphan process hay file tạm sau timeout; 92 test hiện có vẫn pass.

**An toàn khi thử nghiệm:** mọi prototype chạy PDF gây treo phải có watchdog (vd. `faulthandler.dump_traceback_later(…, exit=True)` hoặc chạy trong subprocess có `timeout`). File tạm/prototype chỉ đặt ngoài repo (scratchpad của bạn).

## Định dạng báo cáo (Markdown, tiếng Việt, ngắn gọn ≤ ~350 dòng)
1. Problem understanding · 2. Ma trận so sánh ≥3 phương án (theo 9 tiêu chí) · 3. Phương án đề xuất (chi tiết: module/hàm, luồng gọi, IPC, timeout, kill, cleanup, giới hạn hàng đợi, mã lỗi) · 4. Bằng chứng prototype ([CONFIRMED] lệnh + output / [HYPOTHETICAL]) · 5. Edge cases & failure modes · 6. Compatibility impact · 7. Testing strategy · 8. Complexity · 9. Điểm yếu của chính phương án.
