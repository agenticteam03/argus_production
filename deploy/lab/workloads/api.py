"""SC-03: /health depends on the cache (Redis) being reachable."""
import os, socket, sys
CACHE = os.environ.get("CACHE_HOST", "argus-lab-cache")
from http.server import BaseHTTPRequestHandler, HTTPServer

def cache_ok():
    if CACHE in ("", "none"):          # standalone twin (vm-095): no dependency
        return True
    try:
        with socket.create_connection((CACHE, 6379), timeout=1.5) as s:
            s.sendall(b"PING\r\n")
            return s.recv(16).startswith(b"+PONG")
    except OSError as e:
        print(f"ERROR health: cannot connect to {CACHE}:6379: {e}", file=sys.stderr, flush=True)
        return False

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass
    def do_GET(self):
        ok = self.path == "/health" and cache_ok()
        self.send_response(200 if ok else 503)
        self.end_headers()
        self.wfile.write(b"ok\n" if ok else b"cache unavailable\n")

print("api listening on :8080", flush=True)
HTTPServer(("0.0.0.0", 8080), H).serve_forever()
