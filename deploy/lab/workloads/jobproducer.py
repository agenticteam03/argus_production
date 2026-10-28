"""Push one lab job per second into the shared Redis list."""

import os
import socket
import threading
import uuid


def rpush(host, key, value):
    parts = ("RPUSH", key, value)
    request = f"*{len(parts)}\r\n" + "".join(f"${len(part)}\r\n{part}\r\n" for part in parts)
    with socket.create_connection((host, 6379), timeout=3) as sock:
        sock.sendall(request.encode())
        response = sock.makefile("rb").readline()
        if not response.startswith(b":"):
            raise RuntimeError("Redis RPUSH failed")


def producer_loop(host, stop_event, *, retry_wait=0.5, interval=1):
    while not stop_event.is_set():
        try:
            rpush(host, "lab:jobs", str(uuid.uuid4()))
        except (OSError, RuntimeError):
            stop_event.wait(retry_wait)
            continue
        stop_event.wait(interval)


def main():
    host = os.environ.get("CACHE_HOST", "argus-lab-cache")
    producer_loop(host, threading.Event())


if __name__ == "__main__":
    main()
