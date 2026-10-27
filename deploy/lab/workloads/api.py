"""SC-03: /health depends on the cache (Redis) being reachable."""
import os
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit


CACHE = os.environ.get("CACHE_HOST", "argus-lab-cache")
FAULT_ENABLED = os.environ.get("FAULT_ENABLE") == "1"


def cache_ok():
    if CACHE in ("", "none"):
        return True
    try:
        with socket.create_connection((CACHE, 6379), timeout=1.5) as connection:
            connection.sendall(b"PING\r\n")
            return connection.recv(16).startswith(b"+PONG")
    except OSError as error:
        print(f"ERROR health: cannot connect to {CACHE}:6379: {error}", file=sys.stderr, flush=True)
        return False


_FAULT_LOCK = threading.Lock()      # one fault at a time: held while a burn runs


def burn_cpu(seconds):
    """Busy loop until a wall-clock deadline, so the lab's CPU quota cannot stretch it past `seconds`."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        pass


def _run_cpu_fault(seconds):
    try:
        burn_cpu(seconds)
    finally:
        _FAULT_LOCK.release()


def start_cpu_fault(seconds):
    """Start a burn in a thread; False (nothing started) while another one is running."""
    if not _FAULT_LOCK.acquire(blocking=False):
        return False
    threading.Thread(target=_run_cpu_fault, args=(seconds,), daemon=True).start()
    return True


def _fault_seconds(query):
    try:
        values = parse_qs(query, keep_blank_values=True, strict_parsing=True)
        if set(values) != {"s"} or len(values["s"]) != 1:
            return None
        seconds = int(values["s"][0])
    except (TypeError, ValueError):
        return None
    return seconds if 1 <= seconds <= 120 else None


class H(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def _reply(self, status, body):
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path)
        if path.path == "/health":
            ok = cache_ok()
            self._reply(200 if ok else 503, b"ok\n" if ok else b"cache unavailable\n")
            return
        if path.path == "/fault/cpu":
            if not FAULT_ENABLED:
                self._reply(404, b"not found\n")
                return
            seconds = _fault_seconds(path.query)
            if seconds is None:
                self._reply(400, b"s must be between 1 and 120\n")
                return
            if not start_cpu_fault(seconds):
                self._reply(409, b"a cpu fault is already running\n")
                return
            self._reply(202, b"cpu fault started\n")
            return
        self._reply(404, b"not found\n")


def make_server(address=("0.0.0.0", 8080)):
    return HTTPServer(address, H)


def main():
    print("api listening on :8080", flush=True)
    make_server().serve_forever()


if __name__ == "__main__":
    main()
