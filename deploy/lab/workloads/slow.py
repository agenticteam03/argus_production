"""SC-08 (T-0029): an upstream that answers every request after DELAY_S seconds, longer than the proxy's
proxy_read_timeout, so argus-lab-nginx answers 504 Gateway Timeout. Its own requests succeed (200) when awaited."""
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def delay_s(env=os.environ) -> float:
    return float(env.get("DELAY_S", "5"))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        time.sleep(delay_s())
        body = b"slow but fine\n"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"slow: {self.command} {self.path} answered after {delay_s():g} s", flush=True)


if __name__ == "__main__":
    print(f"slow: listening on 8080, every answer after {delay_s():g} s", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
