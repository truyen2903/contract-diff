# Isolation Round 1 — Codex

## 1. Problem understanding

**Đề xuất: một process `spawn` cho mỗi request xử lý, tối đa 2 process, không có hàng đợi; cô lập toàn bộ lời gọi service.** Truyền đường dẫn tệp riêng của từng job, dùng JSON trên đĩa để trả kết quả, tránh deadlock do pipe đầy.

Đã đọc brief, Phase A report, coding style, D1–D22 và điều chỉnh sau review, cùng các route, service, extractor, engine và tests được yêu cầu. Không sửa hoặc tạo tệp.

Các điểm quyết định từ code hiện tại:

- `extract_pdf()` có thể treo ngay trong `count_pdf_pages()`, trước `pdfplumber.open()`. Chỉ cô lập `read_page_texts()` là thiếu.
- `compare_document()` thực hiện hai lần extraction, ghép văn bản, diff và ánh xạ vị trí. Cần đặt toàn bộ chuỗi này trong **một job**, dùng chung một deadline.
- `/text` cũng phải vào worker, kể cả đầu vào vượt qua validation.
- `/health` đã là `async def`; giữ nguyên.
- Timeout của thread hoặc Future không chấm dứt phép tính. Phải kết thúc process rồi xác nhận process đã thoát.
- Process isolation bảo vệ khả năng phục hồi trước parser treo; **không phải OS sandbox**, cũng chưa giải quyết triệt để R-BOMB.

Phạm vi 30 giây được đề xuất là **ngân sách xử lý một job**, gồm startup worker, extraction, mapping, diff và ghi kết quả. Không bao gồm thời gian client upload, chuẩn bị tệp đầu vào và gửi response qua mạng. Đây cần là diễn giải được ghi rõ trong hợp đồng timeout.

## 2. Ma trận so sánh

Đánh giá dưới đây là nhận định thiết kế cho dự án hiện tại.

| Tiêu chí | Process/request (`multiprocessing.Process`) | Pool thường trực (`ProcessPoolExecutor` / `Pool`) | Worker thường trực tự quản qua pipe/queue |
|---|---|---|---|
| Correctness | Một job độc lập; ít trạng thái tồn dư | Chia sẻ vòng đời, lỗi pool ảnh hưởng nhiều job | Đúng nếu giao thức, ownership và restart được thiết kế đầy đủ |
| Hard timeout | Giữ handle process, terminate trực tiếp | Timeout Future không đủ; cần hủy toàn pool hoặc cơ chế khác | Kill worker đang sở hữu job |
| Worker termination | Chỉ ảnh hưởng request đó | API công khai của executor hủy toàn pool | Có thể kill từng worker |
| Concurrency | Giới hạn trước khi spawn | Phải chặn trước `submit`; không dựa vào hàng đợi nội bộ | Tự quản số worker, dispatch và queue |
| Windows | `spawn`, target phải import được | Hỗ trợ `spawn`; chịu chi phí khởi động pool | Hỗ trợ nhưng phải quản lý pipe và handle |
| Memory overhead | Interpreter/import mới cho mỗi job; giải phóng khi thoát | Giữ RAM nền; có thể tích lũy bộ nhớ giữa job | Giữ RAM nền; cần chính sách recycle |
| Startup latency | Trả chi phí mỗi request | Thấp sau warm-up | Thấp sau warm-up và handshake |
| Maintainability | Tốt nhất nếu IPC đơn giản | API ngắn nhưng recovery sau timeout phức tạp | Cần duy trì giao thức và state machine |
| Độ phức tạp | Thấp–vừa | Vừa–cao khi yêu cầu hard timeout | Cao nhất; khó phù hợp đồ án một sinh viên |

Python 3.14 có `terminate_workers()` và `kill_workers()`, nhưng chúng tác động lên toàn bộ executor và executor không tiếp tục nhận job được. `max_tasks_per_child` là recycle sau khi task hoàn thành, không phải timeout cho task đang treo. [Tài liệu executor](https://docs.python.org/3.14/library/concurrent.futures.html).

Phương án lai “mỗi slot là một pool một worker” giảm phạm vi ảnh hưởng, nhưng vẫn phải quản lý thay pool, Future lỗi và IPC. Chưa có lợi thế đủ lớn để chọn ở vòng đầu.

## 3. Phương án đề xuất

### 3.1. Ranh giới và module

Giữ các hàm hiện tại là hàm xử lý đồng bộ, được worker gọi trực tiếp.

| Thành phần đề xuất | Trách nhiệm |
|---|---|
| `app/services/isolation_service.py` | Các wrapper cho ba endpoint; chuẩn bị input; spawn, deadline, termination, nhận kết quả và cleanup |
| `app/workers/processing_worker.py` | Target module-level `run_job(...)`; chọn đúng một trong ba thao tác được phép |
| `app/core/processing_limit.py` | ASGI admission gate cho ba endpoint xử lý |
| `app/core/config.py` | Timeout 30 s, worker limit 2, queue limit 0 |
| `app/main.py` | Đăng ký admission gate và cleanup worker khi shutdown |

Các wrapper đề xuất: `compare_text_isolated`, `extract_document_isolated`, `compare_document_isolated`.

Luồng gọi:

```text
Admission gate → FastAPI validation → route def → isolated service
  → chuẩn bị input → spawn worker
      → compare_text / extract_document / compare_document
      → ghi JSON kết quả → thoát
  → join có deadline → nhận kết quả hoặc terminate
  → đóng handle, xóa tệp → trả dict / HTTPException
```

Worker gọi service gốc, không gọi wrapper isolation, tránh spawn đệ quy. Không tạo process lúc import module.

`/pdf` dùng **một worker cho toàn bộ `compare_document()`**, không spawn riêng hai extraction và diff. Như vậy hai lần extraction không thể mỗi lần tiêu thụ thêm 30 giây.

### 3.2. IPC và bộ nhớ

**Chọn đường dẫn tệp, không truyền `UploadFile`, stream hay file handle.**

- Parent gọi `validate_pdf_stream()` cho cả hai PDF trước khi parse bất kỳ PDF nào.
- Copy vào thư mục job riêng ngoài repository bằng chunk, ví dụ 64 KiB; đóng tệp trước khi spawn.
- Tên lưu trữ do server sinh; filename người dùng chỉ là metadata.
- Worker mở lại đường dẫn bằng `with open(...)`.
- `/text` ghi request JSON riêng, thay vì đưa chuỗi lớn vào tham số `spawn`.
- Tham số process chỉ gồm operation, đường dẫn, metadata nhỏ và các giới hạn hiệu lực.

Với hai PDF tối đa 15 MiB:

- Mỗi job có thêm tối đa **30 MiB đầu vào trên đĩa**.
- Không tạo thêm bản sao 30 MiB trong parent và bản pickle tương ứng chỉ để truyền process.
- Multipart có thể đã spool một bản khác: riêng dữ liệu đầu vào có thể chiếm gần **60 MiB đĩa/job**, chưa tính output.
- Parser vẫn có thể tăng RAM lớn hơn nhiều kích thước PDF.

Worker ghi envelope JSON vào `result.part`, đóng tệp rồi `os.replace()` thành `result.json`. Parent chỉ đọc khi worker đã thoát thành công. Không có `Queue`/pipe chứa output lớn, không có feeder thread cần flush trước khi `join()`.

JSON tránh việc parent unpickle đối tượng do worker trả về. Tuy nhiên, đây không phải ranh giới bảo mật chống worker đã bị khai thác.

### 3.3. Deadline, terminate và cleanup

1. Ngay trước `Process.start()`, đặt `deadline = monotonic() + 30`.
2. Sau startup, `join(max(0, deadline - monotonic()))`.
3. Nếu còn sống: ghi nhận timeout, gọi `terminate()`, `join(1)`.
4. Nếu vẫn sống: gọi `kill()`, `join(1)`.
5. Chỉ khi xác nhận process đã thoát mới `close()` và xóa thư mục job.
6. Không có `join()` vô hạn, kể cả trong nhánh lỗi.

Trên Windows, `terminate()` dùng `TerminateProcess`; `kill()` không phải mức cưỡng chế mạnh hơn như SIGKILL trên POSIX. Không trông chờ `finally` trong worker để cleanup. [Tài liệu multiprocessing](https://docs.python.org/3.14/library/multiprocessing.html).

**30 giây là thời điểm bắt đầu cưỡng chế dừng**, response timeout có thể thêm thời gian xác nhận thoát và cleanup. Không nên quảng bá response luôn đến trong đúng 30,000 giây.

Worker cài watchdog dự phòng trước khi import thư viện nặng, với deadline muộn hơn parent một khoảng nhỏ. Watchdog này giúp worker không chạy vô hạn nếu parent chết; parent vẫn là bên chịu trách nhiệm timeout bình thường.

Nếu terminate/kill không xác nhận được process chết:

- Không nhả slot rồi tạo worker thay thế, làm vượt giới hạn.
- Giữ handle trong registry và đánh dấu slot không dùng được.
- Trả lỗi server, ghi log; shutdown thử cleanup lại.
- Không tuyên bố đã đạt tiêu chí “không còn orphan”.

### 3.4. Admission và route

**Khởi đầu với `MAX_PROCESSING_WORKERS = 2`, `MAX_PENDING_REQUESTS = 0`.** Đây là cấu hình thận trọng, chưa phải kết quả capacity planning.

- ASGI gate nhận slot trước FastAPI đọc/parse body cho ba endpoint xử lý.
- Hết slot: trả ngay **503 `PROCESSING_BUSY`**, có thể kèm `Retry-After: 1`.
- Health, OpenAPI và route khác không lấy slot.
- Giữ body-limit middleware hiện tại; quy định rõ thứ tự middleware.
- Slot chỉ được trả sau khi supervisor hoàn tất cleanup. Disconnect không được làm bỏ mặc worker.

**Giữ ba route là `def`.** Với admission 2, tối đa hai thread chờ process, thay vì 40 thread bị chiếm bởi parser. `/health` tiếp tục `async def`.

Đổi sang `async def` nhưng gọi `join()` trực tiếp sẽ chặn event loop. Offload lại sang thread không đem lợi ích rõ rệt ở quy mô này.

Giới hạn trên là **mỗi process API**. Chạy nhiều Uvicorn worker sẽ nhân số worker xử lý. Đề xuất triển khai ban đầu với một process API; không suy ra cần 16 worker chỉ vì máy có 16 CPU logic.

### 3.5. Mã lỗi và envelope

Envelope nội bộ chỉ có hai nhánh: success chứa result, hoặc business error chứa status/detail. Không truyền exception object.

| Trường hợp | HTTP / body đề xuất |
|---|---|
| Input sai, PDF hỏng, quá size/trang/text | Giữ nguyên 400/413/422 và mã hiện có |
| Validation `/text` | Giữ 422 FastAPI, bỏ trường `input` như hiện tại |
| Quá hạn job | **504 `PROCESSING_TIMEOUT`** |
| Không còn slot | **503 `PROCESSING_BUSY`** |
| Worker crash, `MemoryError`, `OSError`, output thiếu/hỏng, startup lỗi | **500 `PROCESSING_FAILED`** |

Các mã mới dùng body phẳng `{"error_code": "...", "detail": "..."}`. Không trả traceback hay đường dẫn tạm ra client.

Worker chỉ chuyển tiếp business error đã biết; lỗi ngoài dự kiến là processing failure. Không mở rộng `except Exception → PDF hỏng` ra toàn bộ job. Đặc biệt, giữ nguyên quyết định D10 sửa: lỗi I/O và bộ nhớ không thành 400.

## 4. Bằng chứng prototype

### [CONFIRMED] Hard termination, recovery và health

Chạy trên Python **3.14.3**, Windows, start method **spawn**, 16 CPU logic. Prototype chỉ tồn tại trong bộ nhớ; worker và runner đều có watchdog.

Lệnh dưới đây là prototype đã chạy. `exec` chỉ là scaffold để không phải tạo module thử nghiệm; implementation thật dùng target module-level.

```powershell
@'
import faulthandler, subprocess, sys
faulthandler.dump_traceback_later(30, exit=True)
program = r'''
import faulthandler, multiprocessing as mp, time
from fastapi.testclient import TestClient
from app.main import app
faulthandler.dump_traceback_later(20, exit=True)
pdf = b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n3 0 R\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n136\n%%EOF\n'
job = """
import faulthandler
from io import BytesIO
faulthandler.dump_traceback_later(6, exit=True)
from app.services.comparison_service import compare_text, compare_document
from app.extractors.pdf_extractor import extract_pdf
ready.send('ready'); ready.close()
if mode == 'pdf': extract_pdf(BytesIO(pdf), 100)
elif mode == 'diff': compare_text('a b '*8500, 'b a '*8500)
else:
    assert compare_text('a b', 'a  b')['is_token_identical']
    with open('tests/fixtures/contract_old.pdf','rb') as a, open('tests/fixtures/contract_new.pdf','rb') as b:
        assert len(compare_document('old.pdf',a,'new.pdf',b)['changes']) == 5
"""
ctx=mp.get_context('spawn')
with TestClient(app) as client:
    for mode in ('pdf','diff','valid'):
        r,w=ctx.Pipe(False)
        p=ctx.Process(target=exec,args=(job,{'mode':mode,'pdf':pdf,'ready':w}))
        start=time.monotonic(); p.start(); w.close()
        try:
            assert r.poll(3) and r.recv() == 'ready'
            hstart=time.monotonic(); response=client.get('/api/v1/health')
            assert response.status_code == 200 and response.json() == {'status':'ok'}
            health_ms=round((time.monotonic()-hstart)*1000,1)
            p.join(max(0,(6 if mode=='valid' else 1.5)-(time.monotonic()-start)))
            expired=p.is_alive()
            if expired:
                p.terminate(); p.join(1)
                if p.is_alive(): p.kill(); p.join(1)
            assert not p.is_alive() and expired == (mode!='valid')
            if mode=='valid': assert p.exitcode == 0
            print(mode,'timeout='+str(expired),'exit='+str(p.exitcode),
                  'health_ms='+str(health_ms),
                  'elapsed='+str(round(time.monotonic()-start,3)),flush=True)
        finally:
            if p.is_alive(): p.kill(); p.join(1)
            if not p.is_alive(): p.close()
            r.close()
print('active_children='+str(len(mp.active_children())),flush=True)
faulthandler.cancel_dump_traceback_later()
'''
r=subprocess.run([sys.executable,'-B','-c',program],
                 capture_output=True,text=True,timeout=25)
print(r.stdout,end=''); print(r.stderr,end='')
print('prototype_exit='+str(r.returncode))
faulthandler.cancel_dump_traceback_later()
'@ | .venv/Scripts/python.exe -B -
```

Output:

```text
pdf timeout=True exit=-15 health_ms=4.2 elapsed=1.513
diff timeout=True exit=-15 health_ms=2.0 elapsed=1.524
valid timeout=False exit=0 health_ms=1.9 elapsed=1.571
active_children=0
prototype_exit=0
```

PDF dựng là 279 byte, cùng cấu trúc tự tham chiếu của CR-AG-001. Hai workload được cắt bởi parent trước watchdog 6 giây.

**Giới hạn bằng chứng:** health được gọi trên app hiện tại khi process con chạy workload. Chưa phải acceptance test của endpoint isolation hoàn chỉnh; giao thức tệp và admission gate chưa được implementation.

### [CONFIRMED] Hai bẫy IPC/pool

Một prototype riêng, cũng chạy qua `python -B -c` trong subprocess có timeout 25 giây, thực hiện:

```python
r, w = ctx.Pipe(False)
p = ctx.Process(target=exec, args=(
    'conn.send_bytes(b"x" * (2*1024*1024))', {'conn': w}))
p.start(); w.close(); p.join(1)
print("2MiB_pipe_join_before_read_alive=" + str(p.is_alive()))
p.terminate(); p.join(1); p.close(); r.close()

e = ProcessPoolExecutor(max_workers=1, mp_context=ctx)
f = e.submit(time.sleep, 8)
try:
    f.result(timeout=1.5)
except TimeoutError:
    print("future_timeout_running=" + str(f.running()),
          "live_workers=" + str(len(mp.active_children())))
e.kill_workers()
for child in mp.active_children():
    child.join(2)
```

Output quan sát:

```text
2MiB_pipe_join_before_read_alive=True
future_timeout_running=True live_workers=1
after_kill_workers_children=0
fresh_pool_result=3
prototype_exit=0
```

Không đọc pipe rồi `join()` trước có thể giữ worker đang chờ ghi, dù phép tính đã xong. Đây là lý do chọn result file.

### [CONFIRMED] Startup/RAM và baseline

Ba lần spawn rồi import `comparison_service`, đo bằng `perf_counter` và Windows `GetProcessMemoryInfo`:

| Lần | Đến khi import xong | Working set | Private memory |
|---|---:|---:|---:|
| 1 | 1.219 ms | 51,8 MiB | 42,0 MiB |
| 2 | 1.261 ms | 51,8 MiB | 42,3 MiB |
| 3 | 1.161 ms | 52,2 MiB | 42,7 MiB |

Các số thời gian trên là **1.161–1.261 mili giây**, tức khoảng **1,16–1,26 giây**. Đây là ba mẫu trên môi trường sandbox, chưa phải benchmark throughput hoặc peak RAM khi parse PDF.

Bộ test hiện tại:

```powershell
@'
import faulthandler, pytest
faulthandler.dump_traceback_later(45, exit=True)
raise SystemExit(pytest.main(['-q','--capture=sys','-p','no:cacheprovider']))
'@ | .venv/Scripts/python.exe -B -
```

```text
92 passed in 2.75s
```

Capture mặc định của pytest cần tệp tạm, không dùng được trong sandbox này; `--capture=sys` cho phép kiểm chứng trong bộ nhớ.

**[HYPOTHETICAL]** Chưa đo IPC bằng tệp, cleanup trên Windows sau kill, giới hạn hai request, shutdown/reload hoặc timeout production 30 giây. Các phần đó phải qua acceptance tests trước khi đóng R-TIMEOUT.

## 5. Edge cases & failure modes

| Tình huống | Cách xử lý |
|---|---|
| Worker thoát mà thiếu `result.json` | 500, cleanup; không chờ kết quả vô hạn |
| Worker chết giữa lúc ghi | Bỏ `result.part`; không parse JSON dở |
| Worker lỗi sau khi ghi result | Exit code khác 0 thắng; không trả success |
| Process vừa thoát khi parent terminate | Kiểm tra lại handle/exit status, không biến race thành lỗi input |
| Client disconnect | Supervisor tiếp tục terminate/join/cleanup; không nhả slot sớm |
| Temp disk đầy, antivirus giữ tệp | 500; cleanup có số lần retry hữu hạn, ghi nhận phần còn sót |
| Output `/extract` rất lớn | Có thể làm parent tốn RAM khi đọc/validation; còn thuộc R-BOMB |
| API bị kill đột ngột | Worker watchdog giới hạn thời gian sống; temp có thể còn, cần sweep thận trọng khi startup |
| Nhiều API process | Giới hạn bị nhân lên; cấu hình triển khai phải tính tổng |
| Hai client upload rất chậm | Có thể chiếm cả hai slot; cần chính sách upload timeout riêng nếu phục vụ Internet |

Không xóa thư mục job còn hoạt động khi sweep. Không dùng filename người dùng làm đường dẫn cleanup. Không giả định terminate sẽ giết process hậu duệ; thiết kế worker này không spawn thêm process.

## 6. Compatibility impact

- Giữ schema success, `is_identical`, `is_token_identical`, warnings, spans và page locations.
- Giữ các mã lỗi Phase A, gồm ngoại lệ 413 transport và validation 422.
- Không thêm giới hạn token, không bật `autojunk`, không thêm trần text cho `/extract`.
- Giữ việc kiểm size/magic cả hai PDF trước extraction.
- Thêm 500/503/504 có mã nghiệp vụ; cần cập nhật OpenAPI và tài liệu lỗi.
- Route vẫn mỏng, service trả dict; engine/extractor không thêm phụ thuộc isolation.

**Điểm dễ làm hỏng tests trên Windows:** monkeypatch không tự truyền sang process `spawn`. Hai API test đang sửa `document_service.MAX_UPLOAD_FILE_BYTES` và `MAX_PDF_PAGES`.

Parent phải truyền **giới hạn hiệu lực** cho worker bằng tham số nội bộ; các hàm service nhận override cần thiết, mặc định vẫn dùng constant hiện tại. Không truyền giá trị giới hạn từ HTTP client. Các unit test gọi service/extractor trực tiếp vẫn kiểm tra logic tại parent.

Ngoại lệ coding style hợp lý: ASGI middleware cần interface class; không vì vậy xây thêm hệ thống class cho job, repository hay executor.

## 7. Testing strategy

| Acceptance test | Điều cần chứng minh |
|---|---|
| PDF tự tham chiếu | Endpoint trả 504 đúng mã; PID worker đã chết |
| Diff pathological | Đầu vào lặp, khác token; timeout thực sự dừng process |
| Recovery sau timeout/crash | Request hợp lệ kế tiếp trả đúng năm thay đổi |
| Health khi hai worker treo | Health liên tục trả 200 trong giới hạn CI hợp lý |
| Admission | Hai job chạy; request thứ ba nhận 503 ngay, không spawn worker thứ ba |
| Kiểm body sớm | Khi gate đầy, không đọc body và không tạo tệp job |
| Cleanup | Không còn PID worker, handle mở hoặc tệp job sau timeout bình thường |
| IPC/output | Kết quả lớn không gây join deadlock; JSON thiếu/hỏng thành 500 |
| Compatibility | 92 tests hiện tại vẫn pass sau tích hợp |
| Shutdown/disconnect | Không nhả slot trước cleanup; không còn worker sau shutdown bình thường |

Quy tắc bảo vệ:

- Mọi acceptance test có PDF gây treo chạy trong **harness subprocess**, không gọi trực tiếp trong process pytest chính.
- Harness có timeout ngoài; mỗi worker còn có watchdog riêng. Timeout ngoài đơn thuần không bảo đảm giết process cháu.
- Hạ processing timeout test xuống khoảng **5 giây**, đủ dư cho startup Windows đã đo; không dùng 30 giây cho mọi test.
- Kiểm tra giới hạn thời gian bằng khoảng dung sai, không bằng số mili giây chính xác.
- Chờ marker “đã vào workload” để phân biệt timeout parser với lỗi startup.
- Thêm test worker lỗi ngay lúc khởi động, `MemoryError`, output dở và lỗi cleanup.
- Test IPC bằng tệp phải dùng thư mục test riêng; phiên review này chưa chạy phần đó.
- Không sửa test bằng cách bỏ isolation hoặc giả worker cho toàn bộ acceptance suite.

## 8. Complexity

Ước lượng, chưa phải số dòng implementation:

- Supervisor và worker entrypoint: khoảng 150–230 dòng.
- Admission gate, lifecycle và wiring: khoảng 70–120 dòng.
- Acceptance tests: khoảng 150–250 dòng.

Không cần dependency mới. Chia review thành phần lifecycle/IPC, rồi tích hợp endpoint và acceptance tests. Tránh abstraction hỗ trợ nhiều backend isolation khi dự án chỉ chọn một backend.

Chi phí startup khoảng một giây/request là đáng kể; cần chấp nhận công khai. Chỉ chuyển sang worker thường trực khi benchmark thực tế chứng minh chi phí này cản trở mục tiêu sử dụng.

## 9. Điểm yếu của chính phương án

1. **Latency và throughput:** startup lặp lại; hai slot cho phép ít request đồng thời.
2. **I/O bổ sung:** copy PDF và ghi result làm tăng đĩa tạm; cleanup cần kiểm chứng trên Windows.
3. **RAM chưa được giới hạn cứng:** PDF bomb vẫn có thể ảnh hưởng cả máy trước deadline. Muốn đóng R-BOMB cần cơ chế giới hạn tài nguyên phù hợp, chẳng hạn Windows Job Objects.
4. **Parent vẫn xử lý output:** JSON decode và response validation của `/extract` lớn chưa được bảo vệ bởi timeout worker.
5. **Không bảo đảm realtime:** OS startup, scheduling và I/O bất thường có thể làm vượt thời gian response dự kiến.
6. **Parent crash:** watchdog giúp worker tự kết thúc nhưng không thay thế cleanup tệp của parent.
7. **Bằng chứng còn giới hạn:** đã chứng minh termination, recovery và baseline tests; chưa thể tuyên bố thiết kế hoàn chỉnh đã đóng R-LOOP/R-CPU/R-TIMEOUT trước khi tích hợp và chạy acceptance suite.