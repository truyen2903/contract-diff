# Phase A Brief — Existing API Hardening (đề bài chung cho Round 1)

Repository: `C:\Users\Admin\contract-diff` (nhánh `main`, có thay đổi chưa commit của tác giả — KHÔNG được sửa).
Bạn là reviewer **chỉ đọc**. Không sửa, tạo, xóa file trong repository. Không chạy `git` lệnh ghi. Có thể chạy lệnh đọc và chạy Python/pytest để kiểm chứng (dùng `.venv\Scripts\python.exe`).

## Tài liệu bắt buộc
- Coding style profile: `docs/implementation/coding-style-profile.md` (trong repo).
- Kế hoạch v2 và phản biện (không có trên working tree `main`; đã xuất ra đây, chỉ đọc):
  `C:/Users/Admin/AppData/Local/Temp/claude/7a81e431fe1166c9/3ae8a7db-bd9c-402e-b3dc-61914ab153f4/scratchpad/plandocs/`
  - `ke-hoach-trien-khai-do-an-v2.md` (ưu tiên; đặc biệt §1.1, §3.2, §3.3 đoạn đầu, §7.1, §9 Câu 8, §10)
  - `ke-hoach-trien-khai-do-an.md` (v1)
  - `phan-bien/codex-phuong-phap-ky-thuat.md` (F03, F04)
  - `phan-bien/antigravity-argon-hoi-dong.md`

## Mã nguồn liên quan
`app/main.py`, `app/api/router.py`, `app/api/routes/{health,comparisons,documents}.py`, `app/schemas/{comparison,document}.py`, `app/services/{comparison_service,document_service}.py`, `app/engines/{text_diff,text_mapping}.py`, `app/extractors/pdf_extractor.py`, `tests/*.py`, `tests/fixtures/*.pdf`, `requirements.txt`.

Trạng thái baseline: `.venv\Scripts\python.exe -m pytest -q` → 5 passed (chỉ test endpoint `/pdf` happy path + thiếu field).

## Bài toán
Thiết kế phương án **hardening tối thiểu nhưng đúng** cho 4 endpoint:

1. `GET /api/v1/health` — `health.py` hiện rỗng, chưa đăng ký router.
2. `POST /api/v1/comparisons/text`
3. `POST /api/v1/comparisons/pdf`
4. `POST /api/v1/documents/extract`

Phải trả lời cụ thể:
- **is_identical vs token equality**: `compare_text` trả `is_identical = old_text == new_text` nhưng `changes = diff_words(...)` theo token `\S+`. Khi chỉ khác khoảng trắng: `is_identical=False`, `changes=[]`. Kế hoạch v2 đề xuất thêm `is_token_identical` (§3.3, §10 mục 2) — v2 §9 Câu 8 lại gọi là `is_exact_match`. Chọn phương án nào, giữ tương thích ngược ra sao? `/pdf` có cần trường tương tự không?
- **Validation văn bản**: chuỗi chỉ khoảng trắng; giới hạn độ dài (`MAX_TEXT_CHARS = 500_000` theo v2) — trả 422?
- **Upload an toàn**: giới hạn dung lượng (15 MB/tệp → 413), số trang (100 → 422), kiểm tra magic bytes `%PDF-`, tệp 0 byte, PDF hỏng, PDF mã hóa (→ 400 `{"error_code": "INVALID_OR_ENCRYPTED_PDF", "detail": ...}` theo v2 §3.2). Lưu ý: FastAPI/Starlette `UploadFile` đã spool cả body trước khi handler chạy — kiểm tra kích thước ở đâu thì có ý nghĩa? Định dạng lỗi `{"error_code", "detail"}` có xung đột với dạng `{"detail": ...}` mặc định của FastAPI/HTTPException không?
- **Vị trí đặt logic** (route/service/extractor/`app/core/config.py` mới?) theo coding style profile.
- **Timeout 30s** (v2 §3.2) — có nên làm ở Phase A không?
- `needs_review` và warning `EMPTY_TEXT`/`NULL_CHARACTER`: hành vi hiện tại có đúng không?
- Bug khác bạn tìm thấy trong 4 endpoint (ví dụ `text_mapping.build_document_text` dựa vào `page_number == 1` để quyết định separator; `span_to_page_locations` với span nằm trọn trong separator `"\n\n"`; trang rỗng; v.v.). Phân biệt **confirmed** (đã chạy chứng minh) và **hypothetical**.
- Chiến lược test (unit + integration), bao gồm: happy path, input rỗng, thiếu field, khoảng trắng, Unicode tiếng Việt, PDF không hợp lệ, PDF mã hóa, quá dung lượng, sai đuôi file, biên, tương thích response; với thuật toán: giống nhau, chèn, xóa, thay, khoảng trắng, cụm lặp, đảo điều khoản, trang rỗng.

**Ngoài phạm vi**: `/structured`, parser, aligner, entity extractor, OCR, LLM. Không đề xuất thư viện nặng. Không đổi kiến trúc.

## Định dạng báo cáo bắt buộc (Markdown, tiếng Việt)
1. Problem understanding
2. Current implementation (có file:line)
3. Proposed solution (cụ thể tới tên hàm/schema/status code)
4. Technical rationale
5. Edge cases
6. Security considerations
7. Compatibility impact
8. Testing strategy
9. Complexity assessment
10. Potential weaknesses (của chính phương án bạn)

Mỗi nhận định ghi rõ **[CONFIRMED]** (kèm lệnh/kết quả đã chạy) hoặc **[HYPOTHETICAL]**. Không nhận xét chung chung.
