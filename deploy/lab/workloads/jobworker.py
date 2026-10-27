"""Redis-backed lab worker with an observable processing freeze fault."""

import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


QUEUE_KEY = "lab:jobs"


class RedisList:
    """Tiny RESP client for the Redis list commands used by this workload."""

    def __init__(self, host="argus-lab-cache", port=6379):
        self.host = host
        self.port = port

    def command(self, *parts):
        payload = f"*{len(parts)}\r\n" + "".join(f"${len(str(p))}\r\n{p}\r\n" for p in parts)
        with socket.create_connection((self.host, self.port), timeout=3) as sock:
            sock.sendall(payload.encode())
            stream = sock.makefile("rb")
            prefix = stream.read(1)
            line = stream.readline().rstrip(b"\r\n")
            if prefix == b"-":
                raise RuntimeError(line.decode(errors="replace"))
            if prefix == b":":
                return int(line)
            if prefix == b"$":
                size = int(line)
                if size < 0:
                    return None
                value = stream.read(size)
                stream.read(2)
                return value.decode()
            if prefix == b"*":
                count = int(line)
                values = []
                for _ in range(count):
                    stream.read(1)  # bulk-string marker
                    size = int(stream.readline().rstrip(b"\r\n"))
                    value = stream.read(size).decode()
                    stream.read(2)
                    values.append(value)
                return values
            raise RuntimeError("unexpected Redis response")

    def blpop(self, key, timeout=1):
        result = self.command("BLPOP", key, timeout)
        return tuple(result) if result is not None else None

    def llen(self, key):
        return self.command("LLEN", key)

    def rpush(self, key, value):
        return self.command("RPUSH", key, value)


class WorkerState:
    def __init__(self, freeze_file="/tmp/freeze"):
        self.freeze_file = freeze_file
        self.processed = 0
        self.last_processed = 0
        self.lock = threading.Lock()
        self.frozen = False

    def is_frozen(self):
        return self.frozen or os.path.exists(self.freeze_file)


def worker_loop(redis, state, stop_event, freeze_wait=0.1):
    while not stop_event.is_set():
        if state.is_frozen():
            stop_event.wait(freeze_wait)
            continue
        item = redis.blpop(QUEUE_KEY, timeout=1)
        if item is None:
            continue
        if state.is_frozen():
            redis.rpush(QUEUE_KEY, item[1])
            stop_event.wait(freeze_wait)
            continue
        with state.lock:
            state.processed += 1
            state.last_processed = time.time()


def make_handler(redis, state):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok\n")
                return
            if self.path in ("/fault/freeze", "/fault/unfreeze"):
                state.frozen = self.path == "/fault/freeze"
                if not state.frozen:
                    try:
                        os.remove(state.freeze_file)
                    except FileNotFoundError:
                        pass
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"frozen\n" if state.frozen else b"unfrozen\n")
                return
            if self.path == "/metrics":
                with state.lock:
                    processed = state.processed
                    last = state.last_processed
                body = ("# TYPE argus_lab_jobs_processed_total counter\n"
                        f"argus_lab_jobs_processed_total {processed}\n"
                        "# TYPE argus_lab_queue_depth gauge\n"
                        f"argus_lab_queue_depth {redis.llen(QUEUE_KEY)}\n"
                        "# TYPE argus_lab_last_processed_timestamp_seconds gauge\n"
                        f"argus_lab_last_processed_timestamp_seconds {last}\n")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; version=0.0.4")
                self.end_headers()
                self.wfile.write(body.encode())
                return
            self.send_error(404)

        def log_message(self, *_args):
            return

    return Handler


def main():
    redis = RedisList(os.environ.get("CACHE_HOST", "argus-lab-cache"))
    state = WorkerState()
    stop_event = threading.Event()
    threading.Thread(target=worker_loop, args=(redis, state, stop_event), daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), make_handler(redis, state)).serve_forever()


if __name__ == "__main__":
    main()
