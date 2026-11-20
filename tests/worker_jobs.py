"""Job nhẹ chạy trong worker con của test cách ly (process spawn import module này theo tên)."""

import os
import time


class SideError(ValueError):
    pass


def echo(*args):
    return args


def sleep_then_echo(seconds, value):
    time.sleep(seconds)
    return value


def hang():
    while True:
        time.sleep(1)


def exit_abruptly():
    os._exit(3)


def raise_memory_error():
    raise MemoryError()


def raise_os_error():
    raise OSError("disk error")


def raise_side_error():
    error = SideError("bad input")
    error.side = "new"
    raise error


def large_result(size):
    return "x" * size


def file_sizes(*paths):
    return [os.path.getsize(path) for path in paths]
