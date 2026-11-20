# Round 3 Brief — Rebuttal (Phase A)

Chỉ đọc (không sửa/tạo/xóa file trong repo, không git ghi). Được chạy `python -c`/pytest (`-p no:cacheprovider`, `PYTHONDONTWRITEBYTECODE=1`), mỗi lệnh < 60 giây.

Đọc `docs/implementation/reviews/round2-cross-examination.md` (ghép 3 báo cáo Round 2; ID dùng tiền tố tác giả `CX/`, `CL/`, `AG/`).

Phần lớn bất đồng đã hội tụ qua self-correction ở Round 2 (đã chốt: handler có điều kiện cho body phẳng `{"error_code","detail"}`; giữ `is_identical` + thêm `is_token_identical` chỉ ở `/text`; không thêm cờ equality cho `/pdf`; validator `str.strip()`; filename giữ là metadata; PDF 0 trang → 400; exception hẹp trong extractor, ánh xạ HTTP ở service; không `CID_FONT_ERROR`; sửa `EMPTY_TEXT` khi trang chỉ có NUL; không hard timeout; fast path equality trước `diff_words`).

## Việc của bạn
1. Trả lời **mọi** phản biện Round 2 nhắm vào bạn mà bạn chưa xử lý trong self-correction, mỗi mục một dòng: `ID — ACCEPT | REJECT | PARTIAL | NEEDS EXPERIMENT — lý do/bằng chứng`.
2. Lấy lập trường cuối cùng, có bằng chứng, cho **8 điểm mở** dưới đây (ACCEPT/REJECT/PARTIAL/NEEDS EXPERIMENT với đề xuất cụ thể):

- **O1 — PDF mã hóa mở được bằng mật khẩu rỗng (owner-only):** từ chối (`pdf.doc.encryption is not None`, Codex) hay chấp nhận (Claude, Antigravity)? Lưu ý brief Phase A chỉ nói "PDF mã hóa" và v2 §3.2 nêu `PDFPasswordIncorrect`.
- **O2 — Giới hạn body:** (a) `starlette.middleware.body_limit.RequestBodyLimitMiddleware` có sẵn, trần toàn cục (Claude); (b) ASGI limiter tự viết trần toàn cục 31 MiB (Codex); (c) tự viết, trần theo path 31/16/4 MiB (Antigravity — xem phản biện CL/ADV-CL-004: JSON `ensure_ascii=True` của 2×500k ký tự tiếng Việt = 6.000.032 byte). Một hay hai mã lỗi 413?
- **O3 — Magic bytes:** byte 0 (Codex, Antigravity; phản ví dụ polyglot AG/ADV-CL-006) hay 1024 byte đầu (Claude)?
- **O4 — Đếm trang:** AG/ADV-CX-002 khẳng định `PDF.close()` duyệt `self.pages` nên `islice(PDFPage.create_pages(pdf.doc), 101)` bên trong `with pdfplumber.open(...)` vẫn dựng toàn bộ trang khi thoát `with`; đề xuất tiền kiểm bằng `PDFDocument(PDFParser(stream), password="")` trước `pdfplumber.open`. Hãy kiểm chứng và chốt cách đếm.
- **O5 — Phạm vi bắt lỗi parser:** AG/ADV-CL-002, AG/ADV-CX-003 cho thấy `MalformedPDFException` (không là con của `PdfminerException`), `TypeError` (`/Rotate /Invalid`), `IndexError` (`/CropBox [0 0]`) → 500. CX self-correction 3: `PdfminerException` có thể bọc `OSError`. Chốt tập ngoại lệ ánh xạ sang 400 sao cho không che lỗi lập trình/hạ tầng một cách vô lý (ví dụ: bắt hẹp ở quanh lời gọi thư viện chứ không quanh code của mình?).
- **O6 — Admission guard cho `diff_words`:** có thêm trần token/độ phức tạp ở Phase A không (Codex, Antigravity muốn có nhưng chưa có ngưỡng đã kiểm chứng; Claude: không, chỉ fast path + ghi rủi ro)? Nếu có: con số, cách tính, áp cho `/text` và `/pdf`, và bằng chứng không từ chối hợp đồng thực tế ≤ 100 trang. Có áp `MAX_TEXT_CHARS` lên fulltext của `/pdf` không?
- **O7 — Health:** có `HealthResponse(status: Literal["ok"])` + `prefix="/health"` + route `""` (Codex, Antigravity) hay không schema (Claude)?
- **O8 — Vị trí kiểm tra kích thước/magic:** trong `document_service.extract_document` (dùng chung `/extract` và `/pdf`) bằng `seek/tell` — có ai phản đối không? `/pdf` có cần kiểm tra rẻ (size+magic) cả hai file trước khi trích xuất file đầu?

## Định dạng (Markdown, tiếng Việt)
`# Round 3 — <Agent> rebuttal`, mục "Phản hồi phản biện", mục "Lập trường O1–O8". Ngắn gọn, có bằng chứng; ghi [CONFIRMED] kèm lệnh/output khi chạy thử.
