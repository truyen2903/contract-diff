# Phase A — Existing API Hardening: báo cáo

Quy trình và bằng chứng: `reviews/` (Round 1–3 + consensus + code review; isolation: thiết kế, phản biện, 2 vòng code review). Style: `coding-style-profile.md`. Thiết kế isolation: `process-isolation-design.md`.

**Trạng thái: CHƯA đánh dấu Done.** R-LOOP và R-CPU đã đóng bằng bằng chứng kiểm thử. R-TIMEOUT đóng **có điều kiện** (C1, C2 bên dưới): 2/3 reviewer (Codex, Antigravity) không công nhận đóng vô điều kiện. Phase A chỉ được đánh dấu Done khi tác giả chấp nhận C1 và C2.

## Hợp đồng API sau Phase A

| Endpoint | Thành công | Lỗi |
|---|---|---|
| `GET /api/v1/health` | 200 `{"status":"ok"}`; `async def`, vẫn trả lời khi mọi worker bận/treo | — |
| `POST /api/v1/comparisons/text` | 200 + `is_identical` (nguyên văn), **`is_token_identical`** (mới, = `changes == []`) | 422 dạng FastAPI `{"detail":[{type,loc,msg,...}]}` (không còn trường `input`) cho thiếu field, sai kiểu, rỗng/chỉ khoảng trắng, > 500 000 ký tự; 503/504/500 như bảng dưới |
| `POST /api/v1/documents/extract` | 200 (không đổi) | xem bảng mã lỗi |
| `POST /api/v1/comparisons/pdf` | 200 (không đổi) | xem bảng mã lỗi; cả hai tệp được kiểm size/magic trước khi parse |

Response 200 và mọi mã lỗi Phase A giống từng byte trước/sau isolation (14 kịch bản so khớp JSON, A4).

Mã lỗi nghiệp vụ (body phẳng `{"error_code": ..., "detail": ...}`):

| HTTP | `error_code` | Khi nào |
|---|---|---|
| 400 | `INVALID_OR_ENCRYPTED_PDF` | 0 byte; không bắt đầu bằng `%PDF-` ở byte 0; PDF hỏng/không mở được; cần mật khẩu người dùng; 0 trang |
| 413 | `PAYLOAD_TOO_LARGE` | một tệp > 15 MiB |
| 422 | `PDF_TOO_MANY_PAGES` | > 100 trang (đếm dừng sớm, không dựng mọi trang) |
| 422 | `TEXT_TOO_LONG` | `/pdf`: văn bản ghép (kể cả separator `"\n\n"`) của một tệp > 500 000 ký tự; kiểm `old` xong mới parse `new` |
| 503 | `SERVER_BUSY` | **mới** — đã có `MAX_ACTIVE_WORKERS` (2) worker chạy; header `Retry-After: 5`; không xếp hàng |
| 504 | `PROCESSING_TIMEOUT` | **mới** — quá 30 s cho cả phần xử lý (spawn, trích xuất, diff, ánh xạ); worker bị kill; **không** `Retry-After` |
| 500 | `PROCESSING_FAILED` | **mới** — worker crash, `MemoryError`/`OSError` trong worker, kết quả vượt 32 MiB, lỗi nội bộ không phải lỗi input |

Ngoại lệ có chủ đích:
- **413 tầng transport** (body request > 31 MiB, `RequestBodyLimitMiddleware` của Starlette) **không có `error_code`**: `text/plain "Content Too Large"` khi có `Content-Length`, `{"detail":"Content Too Large"}` khi chunked.
- 422 validation của `/text` theo dạng FastAPI, không có `error_code`.
- PDF mã hóa **mở được bằng mật khẩu rỗng** (chỉ owner password) được chấp nhận (200).
- PDF có byte rác trước `%PDF-` (vd. BOM) bị từ chối dù pdfplumber đọc được.
- Thay đổi hành vi nhỏ: `/pdf` với `old` quá dài **và** `new` hỏng trước đây trả 400 (`new`), nay 422 `TEXT_TOO_LONG` (`old`), theo thiết kế fail-fast.

## Process isolation (đóng R-LOOP, R-CPU, R-TIMEOUT)

Mỗi request xử lý chạy trong một process `spawn` riêng (`app/core/worker.py`, job thuần ở `app/core/jobs.py`); parent giữ deadline 30 s và kill bằng `Process.kill()`. Chi tiết và khác biệt so với thiết kế: `process-isolation-design.md` §8.

Vận hành:
- Chạy bằng `uvicorn app.main:app` (hoặc `python -m uvicorn`). Script tự dựng app ở cấp module mà không có `if __name__ == "__main__"` sẽ bị `spawn` chạy lại trong worker.
- Giới hạn slot tính **theo từng API process**: N Uvicorn worker → tối đa 2N worker xử lý.
- Process isolation **không phải sandbox**: worker cùng quyền, RAM không có trần cứng.

Bằng chứng (đã chạy, không suy luận):

| Kiểm thử | Kết quả |
|---|---|
| Pytest toàn bộ | **126 passed**, ~44 s (92 test Phase A + 34 test isolation/fail-fast) |
| A1 PDF tự tham chiếu (`/extract`, `/pdf` old, `/pdf` new), timeout 2 s | 504 trong < 3,5 s |
| A2 `/text` pathological 480 000 ký tự | 504 trong < 3,5 s |
| A3 request hợp lệ sau kill/crash | 200, `/pdf` fixture đúng 5 thay đổi |
| A5/A7 cả 2 slot bị PDF treo chiếm | `/health` 200 < 200 ms; request thứ ba 503 + `Retry-After` < 0,5 s, không spawn |
| A6 sau mỗi test isolation | không còn child process, thư mục tạm rỗng, đủ slot (fixture autouse) |
| A8 phân loại lỗi | PDF hỏng 400; `MemoryError`/`OSError`/`os._exit`/`ValueError` lạ 500; quá hạn 504 |
| A10/U5 worker kẹt hoặc crash lúc interpreter khởi động | kẹt → 504 đúng hạn (payload 1 B và 2 MB); crash → 500 trong ~0,05 s |
| Deadline thống nhất | startup 1,2 s + job 1,2 s với timeout 2 s → 504 |
| Nhánh lỗi cleanup | `Timer.start()` lỗi, `kill()` lỗi, kết quả/decode sau deadline, hết hạn trước spawn: không rò slot/worker/file tạm |
| H1 Uvicorn thật (`python -m uvicorn` và `uvicorn.exe`, timeout 30 s; `evidence/h1_uvicorn.py`) | `/pdf` 200 0,7 s; 2 PDF treo → 504 sau 30,55 s; `/health` 2–3 ms; request thứ ba 503 sau 3 ms; không còn worker/thư mục tạm; request sau đó 200; hard-kill API → worker mồ côi tự thoát sau 32,8–33,8 s |

## Rủi ro

| ID | Mức | Trạng thái | Mô tả |
|---|---|---|---|
| R-LOOP | Critical | **Đóng** | PDF tự tham chiếu bị kill sau 30 s (504), API và request kế tiếp không bị ảnh hưởng. Bản thân pdfminer vẫn lặp vô hạn trong worker. |
| R-CPU | High | **Đóng** | `diff_words` chạy trong worker và bị kill khi quá hạn. Thuật toán vẫn siêu tuyến tính: input bệnh lý nhận 504 thay vì kết quả. |
| R-TIMEOUT | High | **Đóng có điều kiện** | C1: `Process.start()` chạy trước Timer; không chặn chỉ khi dữ liệu bootstrap (hiện ~1,5 KiB) nhỏ hơn buffer pipe ~4 KiB — có test canh `< 3 KiB`, nhưng `sys.path`/`PYTHONPATH` rất dài khi triển khai có thể phá. C2: chép file tạm và decode kết quả (≤ 32 MiB) ở parent không kill được; kết quả quá hạn vẫn bị trả 504. Thời gian phản hồi tối đa ≈ 30 s + `join` 5 s. |
| R-TEMP | Medium | Mở (mới) | API bị hard-kill khi đang xử lý → thư mục `%TEMP%/contractdiff-*` (PDF hợp đồng, `job.pickle` chứa văn bản `/text`) **còn lại trên đĩa** (H1). Hướng xử lý: dọn thư mục quá hạn khi khởi động và/hoặc Job Object. |
| R-ORPHAN | Low | Mở (mới) | Worker mồ côi tự thoát ≤ timeout + 5 s nhờ watchdog, nhưng watchdog chỉ bật khi `worker_main` bắt đầu: worker kẹt trong bootstrap lúc API chết không có chặn trên. Bước [7] Job Object (chưa làm, phải đánh giá lại trước khi triển khai Windows production). |
| R-HANDLE | Low | Mở (mới) | Mỗi lần worker kẹt/crash trước khi nhận đầu pipe rò 1 handle trong API process (`DupHandle` của `multiprocessing` trên Windows). |
| R-SLOT | Low | Mở (mới) | Nếu worker còn sống mà `kill()` lỗi, hoặc không tạo được thread reaper, slot bị giữ vĩnh viễn (cố ý: không bao giờ trả slot khi worker chưa chết). `KeyboardInterrupt` giữa `finally` cũng có thể giữ slot. |
| R-BOMB | Medium | Mở | PDF nhỏ có stream nén lớn / CIDFont `/W [0 2000000 500]` tốn CPU/RAM. CPU nay bị chặn bởi timeout; RAM worker vẫn không có trần (decode kết quả ở parent thêm tối đa vài lần 32 MiB). |
| — | Info | Chấp nhận | Kết quả đến sát deadline bị trả 504; parent không log timeout/crash (traceback worker chỉ ra stderr); benchmark H3b (p95 với PDF 20 trang) chưa chạy. |

## Đề xuất sửa kế hoạch v2 (thuộc quyền tác giả)
- §3.2: ngoại lệ thực tế là `PdfminerException`/`MalformedPDFException`/lỗi Python thuần; 413 transport không có `error_code`; "15 MB" = 15 MiB; giới hạn ký tự `/text` trả 422 dạng FastAPI; thêm 503 `SERVER_BUSY`, 504 `PROCESSING_TIMEOUT`, 500 `PROCESSING_FAILED`.
- §7.1, §9 Câu 8: dùng `is_identical` (không phải `is_exact_match`); bỏ bất biến reconstruction (phản ví dụ `compare_text("a b","  x a b") == compare_text("a b","a x b  ")`).
- §7.3/§10: môi trường thực tế Python 3.14.3.
