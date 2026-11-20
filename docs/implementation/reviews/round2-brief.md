# Round 2 Brief — Cross-Examination (Phase A)

Bạn là reviewer **chỉ đọc**: không sửa/tạo/xóa file trong repository, không chạy git lệnh ghi. Được chạy `python -c`/pytest (`-p no:cacheprovider`, `PYTHONDONTWRITEBYTECODE=1`) để kiểm chứng phản ví dụ. Không chạy thí nghiệm dài quá ~60 giây mỗi lệnh.

Đọc cả ba báo cáo Round 1 (đề bài gốc: `docs/implementation/reviews/phase-a-brief.md`; style profile: `docs/implementation/coding-style-profile.md`):
- `docs/implementation/reviews/round1-codex.md`
- `docs/implementation/reviews/round1-claude.md`
- `docs/implementation/reviews/round1-antigravity.md`

Nhiệm vụ: phản biện **hai báo cáo của agent khác** (không phải của bạn). Với mỗi vấn đề:
- Chỉ ra nhận định chưa có bằng chứng, lỗi logic, thiết kế vượt phạm vi/overengineering, nguy cơ breaking change.
- Đưa phản ví dụ cụ thể; nếu khẳng định là CONFIRMED thì ghi lệnh + kết quả bạn đã chạy.
- Đề xuất phương án thay thế nếu cần.
- Nếu báo cáo khác chỉ ra điểm sai trong phương án Round 1 của chính bạn, hãy **bảo vệ bằng bằng chứng hoặc thừa nhận sai** (mục cuối "Self-correction").

Các điểm bất đồng đã biết cần lấy lập trường rõ (không bắt buộc giới hạn ở đây):
1. Dạng body lỗi: handler toàn cục cho top-level `{"error_code","detail"}` (Codex, Antigravity) vs `{"detail": {"error_code","message"}}` không handler (Claude).
2. Middleware ASGI giới hạn body (Codex, Antigravity) vs để reverse proxy (Claude).
3. Magic `%PDF-` ở byte 0 (Codex, Antigravity) vs trong 1024 byte đầu (Claude).
4. PDF mã hóa mở được với mật khẩu rỗng: từ chối (Codex: `pdf.doc.encryption is not None`) vs chấp nhận (Claude).
5. Đếm trang: `PDFPage.create_pages` + `islice` (Codex, Antigravity) vs `len(pdf.pages)` (Claude).
6. Ngân sách token/diff (`MAX_DIFF_TOKEN_PRODUCT` Codex, `MAX_TEXT_TOKENS` Antigravity) vs chỉ ghi nhận rủi ro (Claude) — kèm giới hạn `TEXT_TOO_LONG`/`EXTRACTED_TEXT_TOO_LONG` cho `/pdf`.
7. `/pdf` thêm `is_identical`+`is_token_identical` (Codex) vs không thêm (Claude, Antigravity).
8. Validator khoảng trắng: `str.strip()` (Codex, Claude) vs lọc thêm ZWSP/BOM/NUL (Antigravity).
9. Vệ sinh filename `Path(...).name` (Antigravity) vs giữ metadata (Codex, Claude).
10. PDF 0 trang: 400 (Codex, Antigravity) — Claude không đề cập.
11. Exception: `HTTPException` trong extractor (Codex) vs exception class nhỏ trong extractor (Antigravity) vs `ValueError` + map ở service (Claude).
12. `HealthResponse` schema (Codex, Antigravity) vs không (Claude); prefix router.
13. Warning mới `CID_FONT_ERROR` (Codex) và sửa `EMPTY_TEXT` khi chỉ có NUL (Antigravity).

## Định dạng bắt buộc (Markdown, tiếng Việt)

Mỗi phản biện:

**Issue ID:** ADV-<AGENT>-NNN (ví dụ ADV-CX-001 cho Codex, ADV-CL-001 Claude, ADV-AG-001 Antigravity)
**Target:** Claude / Codex / Antigravity
**Severity:** Critical / High / Medium / Low
**Claim:** Nhận định đang bị phản biện (trích + file:line của báo cáo nếu được).
**Evidence:** Bằng chứng (code file:line, lệnh đã chạy + output, tài liệu).
**Counterexample:** Trường hợp làm phương án thất bại.
**Recommendation:** Cách khắc phục.
**Confidence:** High / Medium / Low.

Không chấp nhận phản biện chung chung ("looks good", "add more tests"). Cuối báo cáo thêm mục **Self-correction** (điểm bạn thừa nhận sai hoặc giữ nguyên kèm lý do) và **Lập trường cho 13 điểm bất đồng** (một dòng mỗi điểm).
