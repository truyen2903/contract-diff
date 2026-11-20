# Process Isolation — Code Review Brief (adversarial, độc lập)

Bạn là reviewer **chỉ đọc**. Không sửa, tạo hay xóa file trong repo. Không commit. Không chạy tác vụ nền.
Được chạy thí nghiệm ngắn (mỗi cái < 60 s, có `timeout`/watchdog, dọn process con) trong thư mục tạm ngoài repo.
Được chạy test với: `PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider` (~40 s, 116 test).

## Phạm vi
Thiết kế đã chốt: `docs/implementation/process-isolation-design.md` (U1–U5 đã được tác giả quyết: Pipe + Timer, file tạm cho PDF; admission trong service; `MAX_ACTIVE_WORKERS = 2`; Job Object để bước sau; U5 phải có acceptance test).

File mới/đổi trong lượt này:
- `app/core/config.py` (3 hằng mới), `app/core/jobs.py` (mới), `app/core/worker.py` (mới)
- `app/services/document_service.py`, `app/services/comparison_service.py`, `app/main.py` (3 handler)
- `tests/test_process_isolation.py`, `tests/worker_jobs.py` (mới), `tests/test_comparison_service.py` (đổi đích monkeypatch, thêm assert config), `pytest.ini` (mới)

Khác biệt so với bản thiết kế (có bằng chứng, cần bạn phản biện):
- **Job và args đi qua file `job.pickle` trong thư mục tạm, không qua Pipe.** Thí nghiệm: khi worker kẹt lúc interpreter khởi động, `connection.send()` payload 2 MB chặn mãi **kể cả sau `kill()`**. Lý do: trên Windows `reduce_pipe_connection` nhân bản handle đầu con **vào chính process cha** (`DupHandle(pid=os.getpid())`), chỉ chuyển sang con khi con unpickle. Con chết trước bước đó thì cha vẫn giữ một đầu ghi nên không có broken pipe. Đồng thời `Process.start()` chặn 20 s nếu args lớn và con kẹt khởi động (args 10 B: 0,05 s). Pipe giờ chỉ dùng cho kết quả.
- Bản sao handle đó bị rò (1 handle/lần worker kẹt lúc khởi động). Đã ghi nhận, chưa xử lý.

## Yêu cầu của tác giả cần kiểm (đánh giá từng mục PASS/FAIL kèm bằng chứng)
1. Deadline thống nhất, không reset giữa các bước.
2. Mỗi request một Pipe riêng, không tái dùng IPC sau crash/timeout.
3. Kiểm soát kích thước kết quả qua IPC.
4. Chỉ release slot khi worker đã được thu hồi hoặc reaper quản lý an toàn.
5. Startup stall trước và sau khi `Process.start()` trả về.
6. Không phá response contract của endpoint hiện có.
7. Giữ coding style (`docs/implementation/coding-style-profile.md`) và phạm vi.
8. Acceptance, regression và kịch bản Uvicorn thật (kết quả H1 bên dưới).

**Trọng tâm:** race condition giữa `threading.Timer`, `Process.kill()`, `Pipe.close()`, `Process.join()`, `Process.close()` và `semaphore.release()`. Ví dụ cần xét: timer callback chạy song song với `finally`; kill trên process đã thoát/đã close (tái dùng handle); `poll` trả True vì EOF; kết quả đến đúng lúc hết hạn; exception giữa `acquire` và `try`; `start()` ném lỗi; reaper; `BaseException` (KeyboardInterrupt) trong cha.

## Kết quả H1 (Orchestrator đã chạy, uvicorn thật, timeout 30 s)
`python -m uvicorn` và `uvicorn.exe` cho kết quả như nhau:
- `/pdf` fixture 200, 5 thay đổi, 0,7–0,8 s.
- 2 PDF tự tham chiếu chiếm 2 slot: `/health` 200 trong 2,5 ms; request thứ ba 503 `SERVER_BUSY`, `Retry-After: 5`, 3 ms.
- Hai request treo nhận 504 `PROCESSING_TIMEOUT` sau 30,5 s. Không còn worker hay thư mục tạm sau đó. Request hợp lệ ngay sau đó 200.
- Hard-kill API khi worker đang treo: worker mồ côi tự thoát sau 33,2–33,4 s (watchdog). **Thư mục tạm (PDF upload + job.pickle) còn lại trên đĩa.**

## Định dạng báo cáo (Markdown, tiếng Việt, ≤ ~150 dòng)
`# Isolation Code Review — <Agent>`
- Bảng 8 yêu cầu: PASS/FAIL + bằng chứng (file:dòng, lệnh đã chạy).
- Findings: `ID | Severity (Critical/High/Medium/Low) | file:dòng | kịch bản lỗi cụ thể | đề xuất sửa tối thiểu`. Ghi rõ [CONFIRMED] (đã chạy) hay [REASONED] (suy luận).
- Kết luận: R-LOOP, R-CPU, R-TIMEOUT có được đóng bằng bằng chứng không? Rủi ro còn lại.
