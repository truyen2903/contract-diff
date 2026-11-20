"""Chạy job trong một process riêng để kill được khi quá hạn (R-LOOP, R-CPU, R-TIMEOUT).

Đây không phải sandbox: worker chạy cùng quyền và RAM không bị giới hạn.
Worker con import module này khi khởi động nên không import thư viện nặng ở top-level.
"""

import faulthandler
import multiprocessing
import multiprocessing.connection
import os
import pickle
import shutil
import tempfile
import threading
import time
import traceback

from app.core.config import COMPARISON_TIMEOUT_SECONDS, MAX_ACTIVE_WORKERS, MAX_WORKER_RESULT_BYTES

# Worker mồ côi (API bị kill đột ngột) tự thoát sau timeout + WATCHDOG_GRACE_SECONDS.
WATCHDOG_GRACE_SECONDS = 5
JOIN_TIMEOUT_SECONDS = 5
COPY_CHUNK_BYTES = 64 * 1024

spawn_context = multiprocessing.get_context("spawn")
worker_slots = threading.BoundedSemaphore(MAX_ACTIVE_WORKERS)


class WorkerBusyError(Exception):
    pass


class WorkerTimeoutError(Exception):
    # Không kế thừa TimeoutError vì TimeoutError là một OSError.
    pass


class WorkerCrashedError(Exception):
    pass


def worker_main(connection, job_path, timeout):
    faulthandler.dump_traceback_later(timeout + WATCHDOG_GRACE_SECONDS, exit=True)
    with open(job_path, "rb") as job_file:
        job, args = pickle.load(job_file)
    try:
        result = ("ok", job(*args))
    except ValueError as error:
        # Có thể là lỗi do input; parent quyết định dựa trên expected_errors.
        result = ("invalid", error)
    except Exception:
        traceback.print_exc()
        result = ("failed", None)
    connection.send(result)


def remaining(deadline):
    return max(0.0, deadline - time.monotonic())


def copy_to_temp(file_stream, directory, index):
    path = os.path.join(directory, f"{index}.pdf")
    file_stream.seek(0)
    with open(path, "wb") as temp_file:
        shutil.copyfileobj(file_stream, temp_file, COPY_CHUNK_BYTES)
    return path


def kill_worker(process):
    # kill() có thể ném lỗi (vd. process vừa thoát); join phía sau mới quyết định worker đã chết chưa.
    try:
        process.kill()
    except OSError:
        pass


def kill_on_timeout(process, timed_out):
    # Gán cờ trước khi kill: phía chờ thấy worker chết sẽ biết đó là timeout, không phải crash.
    timed_out.set()
    kill_worker(process)


def wait_for_result(process, connection, deadline):
    # Chờ cả sentinel: worker chết trước khi nhận đầu pipe thì pipe không báo EOF
    # (trên Windows parent giữ bản sao đầu pipe phía con tới khi con nhận nó).
    ready = multiprocessing.connection.wait([connection, process.sentinel], remaining(deadline))
    # Kiểm cả đồng hồ: wait trả ngay khi có dữ liệu dù đã quá hạn, và Timer có thể chạy trễ.
    if not ready or time.monotonic() > deadline:
        return "timeout", None
    if connection in ready or connection.poll():
        # Pickle đến từ worker do chính ta tạo (cùng quyền), không phải từ client.
        result = pickle.loads(connection.recv_bytes(MAX_WORKER_RESULT_BYTES))
        if time.monotonic() > deadline:
            # Decode giữ GIL nên Timer có thể không kịp chạy: kết quả sau deadline vẫn là timeout.
            return "timeout", None
        return result
    return "failed", None


def release_worker(process, connection, temp_dir, slots):
    # Chỉ gọi khi worker đã chết (hoặc chưa từng chạy).
    try:
        if temp_dir is not None:
            # Windows khóa file tới khi worker thoát nên chỉ xóa sau join.
            # Xóa trước tiên: file tạm chứa nội dung hợp đồng.
            shutil.rmtree(temp_dir, ignore_errors=True)
        if connection is not None:
            connection.close()
        if process is not None and process.pid is not None:
            process.close()
    finally:
        slots.release()


def reap_worker(process, connection, temp_dir, slots):
    process.join()
    release_worker(process, connection, temp_dir, slots)


def stop_worker(process, connection, temp_dir, slots):
    if process is not None and process.pid is not None:
        kill_worker(process)
        process.join(JOIN_TIMEOUT_SECONDS)
        if process.exitcode is None:
            # Chưa thu hồi được: giữ slot và file tạm cho tới khi worker thật sự chết.
            threading.Thread(
                target=reap_worker, args=(process, connection, temp_dir, slots), daemon=True
            ).start()
            return
    release_worker(process, connection, temp_dir, slots)


def run_in_worker(job, *args, files=(), expected_errors=()):
    """Chạy job(*đường dẫn của files, *args) trong process mới và trả kết quả.

    Một ngân sách COMPARISON_TIMEOUT_SECONDS cho cả lần gọi, tính từ lúc nhận slot.
    Lỗi thuộc expected_errors (lỗi do input) được ném lại nguyên vẹn; lỗi khác là WorkerCrashedError.
    """
    slots = worker_slots
    process = connection = temp_dir = timer = None
    timed_out = threading.Event()
    if not slots.acquire(blocking=False):
        raise WorkerBusyError()
    try:
        deadline = time.monotonic() + COMPARISON_TIMEOUT_SECONDS
        try:
            temp_dir = tempfile.mkdtemp(prefix="contractdiff-")
            paths = [copy_to_temp(stream, temp_dir, index) for index, stream in enumerate(files)]
            # Job đi qua file, không qua args của Process hay Pipe: payload lớn trong args làm
            # start() chặn khi worker kẹt lúc khởi động (chưa có handle để kill); send qua Pipe
            # chặn mãi vì parent còn giữ bản sao đầu pipe phía con (xem wait_for_result).
            job_path = os.path.join(temp_dir, "job.pickle")
            with open(job_path, "wb") as job_file:
                pickle.dump((job, (*paths, *args)), job_file)
            if remaining(deadline) > 0:
                connection, child_connection = spawn_context.Pipe(duplex=False)
                process = spawn_context.Process(
                    target=worker_main,
                    args=(child_connection, job_path, COMPARISON_TIMEOUT_SECONDS),
                    daemon=True,
                )
                try:
                    process.start()
                finally:
                    # Nếu parent giữ đầu pipe phía con, recv_bytes đang đọc dở không thấy EOF
                    # khi worker bị kill giữa lúc gửi kết quả.
                    child_connection.close()
                started_timer = threading.Timer(remaining(deadline), kill_on_timeout, (process, timed_out))
                started_timer.start()
                # Chỉ gán sau khi start thành công: finally không join được thread chưa chạy.
                timer = started_timer
                status, value = wait_for_result(process, connection, deadline)
            else:
                # Hết ngân sách ngay khi chép file: không tạo worker nữa.
                status, value = "timeout", None
        except Exception as error:
            # EOFError khi worker chết, OSError khi kết quả vượt trần.
            status, value = "failed", error

        if status == "timeout" or timed_out.is_set():
            raise WorkerTimeoutError()
        if status == "invalid" and isinstance(value, expected_errors):
            raise value
        if status != "ok":
            raise WorkerCrashedError() from value
        return value
    finally:
        if timer is not None:
            timer.cancel()
            # Đợi callback kill (nếu đang chạy) xong trước khi join và đóng handle của process.
            timer.join()
        stop_worker(process, connection, temp_dir, slots)
