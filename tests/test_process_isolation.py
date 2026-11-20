"""Acceptance test cho process isolation (R-LOOP, R-CPU, R-TIMEOUT).

Workload gây treo chỉ chạy trong worker con; test hạ timeout xuống TIMEOUT giây.
"""

import multiprocessing
import multiprocessing.connection
import pickle
import sys
import tempfile
import threading
import time
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import worker_jobs
from app.core import worker
from app.core.worker import WorkerBusyError, WorkerCrashedError, WorkerTimeoutError, run_in_worker
from app.main import app


TIMEOUT = 2
# Thời gian tối đa từ lúc hết hạn tới khi request trả về (kill + join + dọn dẹp).
GRACE = 1.5
FIXTURES = Path(__file__).resolve().parent / "fixtures"

# /Pages trỏ tới object 3, object 3 trỏ chính nó: pdfminer lặp vô hạn khi đếm trang.
SELF_REFERENCING_PDF = (
    b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n3 0 R\nendobj\n"
    b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n"
    b"0000000115 00000 n \ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n136\n%%EOF\n"
)
PATHOLOGICAL_OLD = "a x " * 120_000
PATHOLOGICAL_NEW = "a y " * 120_000


@pytest.fixture(autouse=True)
def isolated_worker(monkeypatch, tmp_path):
    monkeypatch.setattr(worker, "COMPARISON_TIMEOUT_SECONDS", TIMEOUT)
    monkeypatch.setattr(worker, "worker_slots", threading.BoundedSemaphore(2))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    yield tmp_path
    assert multiprocessing.active_children() == []
    assert list(tmp_path.iterdir()) == []
    # Mọi slot đã được trả: BoundedSemaphore không cho release vượt giá trị ban đầu.
    with pytest.raises(ValueError):
        worker.worker_slots.release()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def worker_startup(monkeypatch, tmp_path_factory):
    """Chạy code trong sitecustomize của worker con, trước khi code của ta chạy."""
    def run(code):
        directory = tmp_path_factory.mktemp("startup")
        (directory / "sitecustomize.py").write_text(code)
        monkeypatch.setenv("PYTHONPATH", str(directory))
    return run


@pytest.fixture
def stalled_startup(worker_startup):
    return lambda seconds: worker_startup(f"import time\ntime.sleep({seconds})\n")


def timed(function, *args, **kwargs):
    start = time.monotonic()
    try:
        return function(*args, **kwargs), time.monotonic() - start
    except Exception as error:
        return error, time.monotonic() - start


def post_extract(client, data):
    return client.post("/api/v1/documents/extract", files={"file": ("a.pdf", data, "application/pdf")})


def post_pdf(client, old_data, new_data):
    return client.post(
        "/api/v1/comparisons/pdf",
        files={
            "old_file": ("old.pdf", old_data, "application/pdf"),
            "new_file": ("new.pdf", new_data, "application/pdf"),
        },
    )


def assert_error(response, status_code, error_code):
    assert response.status_code == status_code, response.text
    assert response.json() == {"error_code": error_code, "detail": response.json()["detail"]}


# ── run_in_worker ────────────────────────────────────────

def test_run_in_worker_returns_result():
    assert run_in_worker(worker_jobs.echo, "Bên A", 3) == ("Bên A", 3)


def test_run_in_worker_passes_files_as_paths():
    streams = [BytesIO(b"old"), BytesIO(b"new data")]
    streams[1].seek(4)

    assert run_in_worker(worker_jobs.file_sizes, files=streams) == [3, 8]


def test_run_in_worker_reraises_expected_error_with_side():
    with pytest.raises(worker_jobs.SideError) as error_info:
        run_in_worker(worker_jobs.raise_side_error, expected_errors=(worker_jobs.SideError,))

    assert error_info.value.side == "new"


def test_run_in_worker_unexpected_value_error_is_failure():
    with pytest.raises(WorkerCrashedError):
        run_in_worker(worker_jobs.raise_side_error)


@pytest.mark.parametrize("job", [
    worker_jobs.exit_abruptly,
    worker_jobs.raise_memory_error,
    worker_jobs.raise_os_error,
], ids=["exit", "memory-error", "os-error"])
def test_run_in_worker_reports_failure(job):
    error, elapsed = timed(run_in_worker, job)

    assert isinstance(error, WorkerCrashedError)
    # Crash phải được thấy ngay, không đợi tới deadline.
    assert elapsed < TIMEOUT


def test_startup_crash_is_failure_not_timeout(worker_startup):
    # Worker chết trước khi nhận đầu pipe (parent còn giữ bản sao, không có EOF):
    # phải nhận ra qua sentinel của process.
    worker_startup("import os\nos._exit(7)\n")

    error, elapsed = timed(run_in_worker, worker_jobs.echo, "x")

    assert isinstance(error, WorkerCrashedError)
    assert elapsed < TIMEOUT


def test_result_after_deadline_is_timeout(monkeypatch):
    # Timer có thể chạy trễ (vd. decode giữ GIL); kết quả xong sau deadline vẫn là timeout.
    original_loads = pickle.loads

    def slow_loads(data):
        time.sleep(TIMEOUT + 0.2)
        return original_loads(data)

    monkeypatch.setattr(worker, "kill_on_timeout", lambda process, timed_out: None)
    monkeypatch.setattr(worker.pickle, "loads", slow_loads)

    with pytest.raises(WorkerTimeoutError):
        run_in_worker(worker_jobs.echo, "late")


def test_no_worker_spawned_after_deadline(monkeypatch):
    spawned = []
    monkeypatch.setattr(worker, "COMPARISON_TIMEOUT_SECONDS", 0)
    monkeypatch.setattr(worker.spawn_context, "Process", lambda *args, **kwargs: spawned.append(1))

    with pytest.raises(WorkerTimeoutError):
        run_in_worker(worker_jobs.echo, files=[BytesIO(b"%PDF-")])
    assert spawned == []


def test_timer_start_failure_still_cleans_up(monkeypatch):
    class FailingTimer(threading.Timer):
        def start(self):
            raise RuntimeError("can't start new thread")

    monkeypatch.setattr(worker.threading, "Timer", FailingTimer)

    with pytest.raises(WorkerCrashedError):
        run_in_worker(worker_jobs.hang, files=[BytesIO(b"%PDF-")])


def test_kill_error_does_not_leak_slot(monkeypatch):
    def failing_kill(self):
        raise PermissionError("access denied")

    monkeypatch.setattr(type(worker.spawn_context.Process()), "kill", failing_kill)

    assert run_in_worker(worker_jobs.echo, "ok") == ("ok",)


def test_no_result_decoded_after_deadline(monkeypatch):
    # Dữ liệu có sẵn nhưng đã quá hạn: không đọc/decode (kết quả tới 32 MiB) rồi mới bỏ.
    original_wait = multiprocessing.connection.wait
    decoded = []

    def late_wait(objects, timeout=None):
        time.sleep(TIMEOUT + 0.2)
        return original_wait(objects, 0)

    monkeypatch.setattr(worker, "kill_on_timeout", lambda process, timed_out: None)
    monkeypatch.setattr(worker.multiprocessing.connection, "wait", late_wait)
    monkeypatch.setattr(worker.pickle, "loads", lambda data: decoded.append(data))

    with pytest.raises(WorkerTimeoutError):
        run_in_worker(worker_jobs.echo, "late")
    assert decoded == []


@pytest.mark.skipif(sys.platform != "win32", reason="đo handle bằng API Windows")
def test_no_handle_leak_per_request():
    # Request bình thường không được để lại handle (pipe, process) trong API process.
    import ctypes
    from ctypes import wintypes

    count = wintypes.DWORD()
    process_handle = ctypes.windll.kernel32.GetCurrentProcess()

    def handle_count():
        ctypes.windll.kernel32.GetProcessHandleCount(process_handle, ctypes.byref(count))
        return count.value

    run_in_worker(worker_jobs.echo, "warm-up")
    before = handle_count()
    for _ in range(5):
        run_in_worker(worker_jobs.echo, "ok")

    assert handle_count() - before < 5


@pytest.mark.skipif(sys.platform != "win32", reason="pipe bootstrap của spawn trên Windows")
def test_bootstrap_data_fits_pipe_buffer(monkeypatch):
    # start() ghi dữ liệu bootstrap vào pipe (~4 KiB) trước khi có handle để kill;
    # dữ liệu nhỏ thì start() không chặn kể cả khi worker kẹt lúc khởi động (U5).
    from multiprocessing import popen_spawn_win32, reduction

    written = []

    def measuring_dump(obj, file, protocol=None):
        data = reduction.ForkingPickler.dumps(obj, protocol)
        written.append(len(data))
        file.write(data)

    monkeypatch.setattr(popen_spawn_win32.reduction, "dump", measuring_dump)

    run_in_worker(worker_jobs.echo, "x" * 100_000)

    assert len(written) == 2
    assert sum(written) < 3072


def test_run_in_worker_limits_result_size(monkeypatch):
    monkeypatch.setattr(worker, "MAX_WORKER_RESULT_BYTES", 1000)

    assert run_in_worker(worker_jobs.large_result, 500) == "x" * 500
    with pytest.raises(WorkerCrashedError):
        run_in_worker(worker_jobs.large_result, 5000)


def test_run_in_worker_kills_hung_job():
    error, elapsed = timed(run_in_worker, worker_jobs.hang)

    assert isinstance(error, WorkerTimeoutError)
    assert TIMEOUT <= elapsed < TIMEOUT + GRACE


def test_timeout_is_not_crash_or_builtin_timeout():
    assert not issubclass(WorkerTimeoutError, OSError)
    assert not issubclass(WorkerTimeoutError, WorkerCrashedError)


@pytest.mark.parametrize("payload", ["x", "x" * 2_000_000], ids=["small", "large"])
def test_startup_stall_is_killed(stalled_startup, payload):
    # Payload lớn không được làm Process.start() chặn khi worker chưa đọc pipe (U5).
    stalled_startup(60)

    error, elapsed = timed(run_in_worker, worker_jobs.echo, payload, files=[BytesIO(b"%PDF-")])

    assert isinstance(error, WorkerTimeoutError)
    assert elapsed < TIMEOUT + GRACE


def test_deadline_covers_startup_and_job(stalled_startup):
    # Mỗi bước < TIMEOUT nhưng tổng > TIMEOUT: deadline không được reset giữa các bước.
    stalled_startup(TIMEOUT * 0.6)

    error, elapsed = timed(run_in_worker, worker_jobs.sleep_then_echo, TIMEOUT * 0.6, "ok")

    assert isinstance(error, WorkerTimeoutError)
    assert elapsed < TIMEOUT + GRACE


def test_busy_worker_slots_reject_without_spawning(monkeypatch):
    monkeypatch.setattr(worker, "worker_slots", threading.BoundedSemaphore(1))
    worker.worker_slots.acquire()
    try:
        with pytest.raises(WorkerBusyError):
            run_in_worker(worker_jobs.hang)
        assert multiprocessing.active_children() == []
    finally:
        worker.worker_slots.release()


def test_next_request_works_after_kill_and_crash():
    with pytest.raises(WorkerTimeoutError):
        run_in_worker(worker_jobs.hang)
    with pytest.raises(WorkerCrashedError):
        run_in_worker(worker_jobs.exit_abruptly)

    assert run_in_worker(worker_jobs.echo, "ok") == ("ok",)


# ── API ──────────────────────────────────────────────────

@pytest.mark.parametrize("position", ["extract", "old", "new"])
def test_self_referencing_pdf_times_out(client, make_pdf, position):
    valid = make_pdf(["Hello"])
    start = time.monotonic()
    if position == "extract":
        response = post_extract(client, SELF_REFERENCING_PDF)
    elif position == "old":
        response = post_pdf(client, SELF_REFERENCING_PDF, valid)
    else:
        response = post_pdf(client, valid, SELF_REFERENCING_PDF)

    assert time.monotonic() - start < TIMEOUT + GRACE
    assert_error(response, 504, "PROCESSING_TIMEOUT")
    assert "retry-after" not in response.headers


def test_pathological_text_diff_times_out(client):
    start = time.monotonic()
    response = client.post(
        "/api/v1/comparisons/text",
        json={"old_text": PATHOLOGICAL_OLD, "new_text": PATHOLOGICAL_NEW},
    )

    assert time.monotonic() - start < TIMEOUT + GRACE
    assert_error(response, 504, "PROCESSING_TIMEOUT")


def test_identical_text_skips_worker(client, monkeypatch):
    monkeypatch.setattr(worker, "worker_slots", threading.BoundedSemaphore(1))
    worker.worker_slots.acquire()
    try:
        response = client.post(
            "/api/v1/comparisons/text",
            json={"old_text": PATHOLOGICAL_OLD, "new_text": PATHOLOGICAL_OLD},
        )
    finally:
        worker.worker_slots.release()

    assert response.status_code == 200
    assert response.json()["changes"] == []


def test_valid_request_after_timeout(client):
    assert post_extract(client, SELF_REFERENCING_PDF).status_code == 504

    old_data = (FIXTURES / "contract_old.pdf").read_bytes()
    new_data = (FIXTURES / "contract_new.pdf").read_bytes()
    response = post_pdf(client, old_data, new_data)

    assert response.status_code == 200
    assert len(response.json()["changes"]) == 5


def test_health_and_busy_while_all_slots_hang(client):
    responses = []
    threads = [
        threading.Thread(target=lambda: responses.append(post_extract(client, SELF_REFERENCING_PDF)))
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    # Chờ cả hai request giữ slot (không còn slot trống).
    deadline = time.monotonic() + TIMEOUT
    while len(multiprocessing.active_children()) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    try:
        start = time.monotonic()
        health = client.get("/api/v1/health")
        health_elapsed = time.monotonic() - start

        start = time.monotonic()
        busy = post_extract(client, SELF_REFERENCING_PDF)
        busy_elapsed = time.monotonic() - start
    finally:
        for thread in threads:
            thread.join(TIMEOUT + GRACE + 5)

    assert health.status_code == 200 and health_elapsed < 0.2
    assert_error(busy, 503, "SERVER_BUSY")
    assert busy.headers["retry-after"] == "5"
    assert busy_elapsed < 0.5
    assert sorted(response.status_code for response in responses) == [504, 504]


@pytest.mark.parametrize("error, status_code, error_code", [
    (WorkerBusyError(), 503, "SERVER_BUSY"),
    (WorkerTimeoutError(), 504, "PROCESSING_TIMEOUT"),
    (WorkerCrashedError(), 500, "PROCESSING_FAILED"),
])
def test_worker_errors_have_flat_body(client, monkeypatch, make_pdf, error, status_code, error_code):
    def failing_run(*args, **kwargs):
        raise error

    monkeypatch.setattr("app.services.document_service.run_in_worker", failing_run)
    monkeypatch.setattr("app.services.comparison_service.run_in_worker", failing_run)

    responses = [
        post_extract(client, make_pdf(["x"])),
        post_pdf(client, make_pdf(["x"]), make_pdf(["y"])),
        client.post("/api/v1/comparisons/text", json={"old_text": "a", "new_text": "b"}),
    ]

    for response in responses:
        assert_error(response, status_code, error_code)
