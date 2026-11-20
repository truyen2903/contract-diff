# Process Isolation — Code Review vòng 2 (kiểm chứng bản sửa)

Quy tắc như vòng 1 (`isolation-code-review-brief.md`): chỉ đọc repo, thí nghiệm ngắn có timeout/watchdog ngoài repo, không tác vụ nền.

Đọc ba báo cáo vòng 1: `isolation-code-review-{codex,claude,antigravity}.md`. Code đã sửa: `app/core/worker.py`, `app/core/jobs.py`, `app/services/{document,comparison}_service.py`, `tests/test_process_isolation.py`, `tests/test_comparison_service.py`. Suite hiện tại: **124 passed** (`PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider`, ~42 s). H1 chạy lại với code mới, cả `python -m uvicorn` và `uvicorn.exe`: kết quả như vòng 1 (504 sau 30,55 s; `/health` 2,1–2,4 ms; 503 sau 3 ms; worker mồ côi tự thoát sau 33,5–33,8 s; thư mục tạm còn lại sau khi API bị hard-kill).

## Ánh xạ finding → bản sửa (hãy kiểm từng dòng)

| Finding vòng 1 | Bản sửa | Test mới |
|---|---|---|
| Timer.start lỗi → rò slot/worker (CX F1, CL F2, AG F1) | Chỉ gán `timer` sau khi `start()` thành công | `test_timer_start_failure_still_cleans_up` |
| Khe acquire→try (CX F2, CL F8, AG F5a) | Khởi tạo biến trước `acquire`; `try` ngay sau `acquire` | — |
| Startup crash → 504 sau 30 s (CL F1, AG F2) | `wait_for_result`: `multiprocessing.connection.wait([connection, process.sentinel])`; chỉ sentinel và không có dữ liệu → `failed` | `test_startup_crash_is_failure_not_timeout` |
| `kill()` ném lỗi → rò slot (CX F6, CL F3, AG F4, AG F10a) | `kill_worker` bắt `OSError`; `release_worker` trả slot trong `finally` | `test_kill_error_does_not_leak_slot` |
| Thành công sau deadline (CX F4) | Kiểm `time.monotonic() > deadline` sau decode | `test_result_after_deadline_is_timeout` |
| Spawn khi đã hết hạn (AG F8) | Kiểm `remaining(deadline) > 0` trước khi tạo Pipe/Process | `test_no_worker_spawned_after_deadline` |
| `TEXT_TOO_LONG` không fail-fast (CX F3, AG F7) | `compare_pdf_files` kiểm độ dài ngay sau từng tệp | `test_compare_document_rejects_long_old_text_before_parsing_new` |
| `ValueError` lạ → 500 text/plain (AG F6) | `run_in_worker(..., expected_errors=...)`; `invalid` ngoài danh sách → `WorkerCrashedError` | `test_run_in_worker_unexpected_value_error_is_failure` |
| Bootstrap > 4 KiB làm `start()` chặn (CX F5, CL F6, AG F3) | **Không sửa cơ chế**; thêm test canh bất biến dữ liệu bootstrap < 2 KiB; U5 giữ trạng thái "đóng có điều kiện" | `test_bootstrap_data_fits_pipe_buffer` |
| `Pipe` duplex thừa (AG F10b) | `Pipe(duplex=False)` | — |
| Không sửa (ghi rủi ro): rò handle khi startup stall/crash (CL F4), thư mục tạm sau hard-kill API (CL F5, AG F9), reaper không start được → giữ slot, `BaseException` giữa `finally`, kết quả sát deadline → 504 (CL F7), không log (CL F9) | | |

Ghi chú trung thực của Orchestrator: sau khi chờ trên sentinel, mutation "bỏ `child_connection.close()`" **không còn bị test nào bắt**. Dòng này được giữ cho trường hợp worker bị kill giữa lúc gửi kết quả (parent đang `recv_bytes` dở), nhưng chưa có test tái hiện.

## Yêu cầu
1. Mỗi finding vòng 1 của **bạn**: FIXED / NOT FIXED / PARTIAL, kèm bằng chứng (dòng code, lệnh đã chạy).
2. Bản sửa có tạo lỗi mới không? Trọng tâm vẫn là race giữa Timer, kill, close, join, sentinel và `release`. Ví dụ: `connection.poll()` sau khi chỉ sentinel sẵn sàng; dữ liệu đến sau `wait`; `process.sentinel` sau `close()`.
3. Kết luận cuối: R-LOOP, R-CPU, R-TIMEOUT có đóng được bằng bằng chứng không? Liệt kê rủi ro còn lại.

Định dạng: Markdown tiếng Việt, ≤ ~80 dòng, bắt đầu bằng `# Isolation Code Review vòng 2 — <Agent>`.
