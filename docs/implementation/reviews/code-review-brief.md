# Code Review Brief — Phase A implementation (adversarial review trên code thực tế)

Bạn là reviewer **chỉ đọc**: không sửa/tạo/xóa file trong repo, không git ghi. Được chạy lệnh đọc và Python/pytest (`PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`), mỗi lệnh < 60 giây; file tạm chỉ được đặt ngoài repo.

Đánh giá **độc lập** (không có báo cáo review của agent khác).

## Đầu vào
- Quyết định đã chốt: `docs/implementation/reviews/round3-consensus.md` (D1–D22). Đánh giá xem code có đúng quyết định không và quyết định có sai ở đâu khi gặp code thật.
- Coding style profile: `docs/implementation/coding-style-profile.md`.
- Thay đổi: `git diff -- app tests` + file mới `app/core/config.py`, `app/schemas/health.py`, `tests/conftest.py`, `tests/test_text_mapping.py`; phần thêm cuối `tests/test_comparisons_api.py` (từ comment `# ── Phase A`).
- **Lưu ý phạm vi tác giả:** các thay đổi sau có sẵn từ trước, do tác giả repo viết, không thuộc implementation này: `app/api/routes/comparisons.py` (fallback filename, format), `requirements.txt`, `PageLocation`/`old_locations`/`new_locations` trong `app/schemas/comparison.py`, việc dùng `build_document_text`/`span_to_page_locations` trong `comparison_service.py`, toàn bộ `app/engines/text_mapping.py` trừ dòng separator, 5 test đầu của `tests/test_comparisons_api.py`. Vẫn được báo lỗi trong đó nếu ảnh hưởng 4 endpoint, nhưng ghi rõ là pre-existing.
- Kết quả hiện tại: `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider` → 83 passed (hãy tự chạy lại).

## Trọng tâm theo vai trò
- **Codex:** logic correctness, error handling, type consistency, hành vi FastAPI (middleware order, exception handler, multipart, status codes), edge cases thuật toán, performance, độ phủ test (test nào chưa thực sự chứng minh điều nó tuyên bố?).
- **Claude:** tuân thủ coding style profile, kiến trúc nhất quán, maintainability, readability, thay đổi tối thiểu (có gì thừa / overengineering?), nhất quán tài liệu.
- **Antigravity:** adversarial inputs (PDF bất thường, multipart lạ, Unicode), security, giả định sai, data corruption, failure propagation (lỗi nào còn ra 500 hoặc bị dán nhãn sai?), tác động tới tính hợp lệ nghiên cứu (Baseline 1 có bị đổi hành vi không?).

## Định dạng (Markdown, tiếng Việt)
`# Code Review — <Agent>`. Mỗi finding:
**ID:** CR-<CX|CL|AG>-NNN · **Severity:** Critical/High/Medium/Low · **File:line** · **Vấn đề** · **Bằng chứng** ([CONFIRMED] kèm lệnh + output, hoặc [HYPOTHETICAL]) · **Đề xuất sửa**.
Cuối báo cáo: "Kết luận: có/không còn Critical/High".
Không nhận xét chung chung. Tối đa ~12 finding, sắp theo severity.
