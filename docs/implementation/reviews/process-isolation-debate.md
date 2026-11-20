# Process Isolation — Debate Summary

Quy trình: Independent Review → Cross-Examination → Rebuttal → Consensus. Thiết kế cuối: `../process-isolation-design.md`.

## Agent và bằng chứng thực thi

| Agent | Công cụ | Ghi chú vận hành |
|---|---|---|
| Codex | `codex exec -s read-only --ephemeral` (codex-cli 0.169.0) | Prototype trong bộ nhớ, có watchdog |
| Claude | Claude Code subagent (general-purpose) | R1 do subagent A; R2 lần đầu thất bại (HTTP 429 hết quota 5 giờ, sau đó stream treo 600 s) → R2/R3 do subagent B, được giao `iso-round1-claude.md` làm lập trường và không đọc `iso-round2-*` trước khi viết R2 |
| Antigravity | `agy --mode plan --sandbox` (1.5.11, Gemini 4 Neon) | R2 lần đầu treo 30 phút ở benchmark nền, không có output → chạy lại với lệnh cấm tác vụ nền |

Sau mỗi lần chạy: `git status --porcelain` giống snapshot trước vòng (`scratchpad/status-before-iso.txt`), `tasklist` không còn `python.exe`.

Tài liệu nguyên văn: `isolation-brief.md`, `iso-round1-{codex,claude,antigravity}.md`, `isolation-round2-brief.md`, `iso-round2-{codex,claude,antigravity}.md` (ghép: `iso-round2-cross.md`), `isolation-round3-brief.md`, `iso-round3-{codex,claude,antigravity}.md`.

## Round 1 — đề xuất độc lập

| | Codex | Claude | Antigravity |
|---|---|---|---|
| Mô hình | 1 process/request, chạy toàn job | "worker session": 1 process/request, nhiều lời gọi | Pool thường trực có giám sát (lazy, recycle 50) |
| Ranh giới | toàn service | extractor/engine | extractor/engine, mượn slot theo bước |
| IPC | file vào + `result.json` ra | bytes qua Pipe | file tạm vào + Pipe ra |
| Timeout | 504 | 422 | 504 |
| Slot / hàng đợi | 2 / 0, gate ASGI | 4 / 0, service | 4 / 8, service |
| Orphan | watchdog | watchdog | Job Object |
| Prototype | kill R-LOOP/R-CPU + health 2–4 ms | 99 test pass trên bản sao repo | pool ấm 82 ms/PDF; P2 vỡ `BrokenProcessPool` |

## Round 2 — phản biện chéo (vấn đề chính)

| ID | Tác giả → Đích | Mức | Nội dung | Kết quả |
|---|---|---|---|---|
| CX/ISO-CL-001 | Codex → Claude, AG | Critical | `send`/`recv` chặn ngoài `poll` (recv 804 ms khi ngân sách 10 ms) | Claude/AG thêm `threading.Timer(kill)`; CL E2 chứng minh gỡ được `send` |
| CX/ISO-AG-001 | Codex → AG | Critical | Fallback khi không gán Job Object để lọt orphan | AG thêm watchdog song song |
| CL/ISO-AG-001 | Claude → AG | High | Mượn slot 3 lần → 504 sau khi đã extract xong | AG rút lại, chuyển 1 slot/request |
| CL/ISO-CX-001 | Claude → Codex | High | Import service kéo FastAPI (+0,65 s), vỡ monkeypatch | Codex rút: worker chạy pipeline thuần, không FastAPI |
| CL/ISO-AG-002 | Claude → AG | Med-High | Pool mất ấm sau kill và trong test function-scoped | AG chấp nhận "spawn trước" ở R3 |
| AG/ISO-CL-003 | AG → Claude | High | Pipe bytes cho PDF tốn RAM gấp ~22× file tạm | Claude chuyển sang file tạm |
| CX/ISO-CL-005, AG/ISO-CL-002 | → Claude | Medium | 422 cho timeout sai ngữ nghĩa khi máy tải cao | Claude đổi sang 504 |
| CL/ISO-CX-002, AG/ISO-CX-001 | → Codex | Medium | Gate trước body + 2 slot dễ bị slowloris | Codex giữ quan điểm (U2) |

## Round 3 — rebuttal & lập trường cuối

| Điểm | Codex | Claude | Antigravity | Quyết định cuối |
|---|---|---|---|---|
| O1 Mô hình | spawn/request sau interface | spawn/request sau interface | spawn trước, pool khi H3b fail | **Đồng thuận:** spawn mỗi request, interface `run_in_worker` |
| O2 Phạm vi lời gọi | 1 job pipeline thuần | session nhiều lời gọi (tương thích) | 1 job pipeline thuần (mapping 2,2 s CPU) | **1 job thuần mỗi request** |
| O3 IPC | file vào + `result.json` | file vào + Pipe ra | file vào + Pipe ra | **File tạm vào, Pipe ra** (U1) |
| O4 Deadline | `join(remaining)`; timer nếu Pipe | Timer + cờ `fired` | Timer + cờ `timed_out` | **Timer + cờ** |
| O5 Mã timeout | 504, không `Retry-After` | 504, không `Retry-After` | 504, không `Retry-After` | **Đồng thuận** |
| O6 Admission | gate trước body, 2 slot | service, 4 slot | service, 4 slot | **Service**; 2 slot mặc định (U2, U3) |
| O7 Job Object | bắt buộc | hardening tùy chọn | khuyến nghị bậc 1 | **Chưa thống nhất** — bước [7] riêng (U4) |

Phát hiện mới ở Round 3:
- Claude E3: phải `close()` đầu pipe phía con ngay sau `start()`, nếu không timer kill không gỡ được `recv`.
- Codex: cửa sổ startup trước khi `start()` trả handle cần thí nghiệm riêng (U5).
- Antigravity: `span_to_page_locations` trường hợp xấu tốn 2,2 s CPU nên phải nằm trong worker.

## Nguyên tắc ra quyết định
Correctness → Security → API compatibility → Research scope → Maintainability → Coding style → Performance → Effort. Không biểu quyết máy móc: U1 chọn Pipe dù Codex phản đối, vì `result.json` không đóng được khoảng hở decode ở parent mà lại thêm I/O và rủi ro khóa tệp; U3 chọn 2 slot dù 2/3 agent đề xuất 4, vì RAM worker chưa có trần (ưu tiên an toàn).

## Code review sau triển khai (2 vòng, độc lập)

Brief: `isolation-code-review-brief.md`, `isolation-code-review-round2-brief.md`. Báo cáo nguyên văn: `isolation-code-review-{codex,claude,antigravity}.md`, `isolation-code-review-round2-{codex,claude,antigravity}.md`. Sau mỗi vòng: md5 của 15 file code/test không đổi, không còn `python.exe`, không còn `contractdiff-*`. Codex và Antigravity không chạy được toàn bộ suite trong sandbox (không có thư mục tạm ghi được / loopback bị chặn), chỉ chạy 49–77 test không cần `TestClient` cộng thí nghiệm fault-injection; Claude chạy đủ 124/124.

| Vấn đề (vòng 1) | Nêu bởi | Vòng 2 |
|---|---|---|
| `Timer.start()` lỗi → `timer.join()` ném lỗi, bỏ cleanup, rò slot/worker | Codex F1, Claude F2, AG F1 | FIXED (cả ba) |
| Khe giữa `acquire` và `try` | Codex F2, Claude F8, AG F5 | FIXED (cả ba) |
| Worker crash lúc bootstrap → 504 sau 30 s (không EOF do `DupHandle`) | Claude F1, AG F2 | FIXED (Claude, AG; Codex xác nhận E11 trên Windows) |
| `kill()`/`close()` ném lỗi trong cleanup → rò slot | Codex F6, Claude F3, AG F4 | FIXED cho đường thường; PARTIAL theo Codex: `kill()` lỗi **và** reaper không start được → giữ slot (R-SLOT) |
| `TEXT_TOO_LONG` không fail-fast | Codex F3, AG F7 | FIXED |
| Thành công sau deadline; spawn sau deadline | Codex F4, AG F8 | FIXED; vòng 2 AG thêm: không decode khi đã quá hạn → đã sửa |
| `ValueError` lạ → 500 text/plain | AG F6 | FIXED |
| `start()` chặn trước Timer nếu bootstrap > ~4 KiB | Codex F5, Claude F6, AG F3 | Không đổi cơ chế; test canh đo **tổng** dữ liệu bootstrap (Claude N1, AG vòng 2) → R-TIMEOUT đóng có điều kiện |
| Rò handle, thư mục tạm sau hard-kill, orphan kẹt bootstrap | Claude F4/F5, AG F9 | Ghi rủi ro R-HANDLE, R-TEMP, R-ORPHAN |

Bất đồng còn lại về kết luận: Claude coi R-TIMEOUT đã đóng; Antigravity "đóng có điều kiện"; Codex "chưa đóng vô điều kiện" (vì `start()` và phần chép/decode ở parent không bị cưỡng chế). Orchestrator theo lập trường thận trọng: **đóng có điều kiện C1, C2** (`phase-a-report.md`), Phase A chưa đánh dấu Done.

Antigravity vòng 2 cho rằng bỏ `child_connection.close()` sẽ rò handle ở mọi request: Orchestrator kiểm bằng test đếm handle (`test_no_handle_leak_per_request`) với mutation → vẫn pass, vì `Connection.__del__` đóng handle khi hàm trả về. Nhận định này không đúng; test được giữ làm hồi quy chung.
