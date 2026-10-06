"""Tiny HTTP service used only by the disposable RB-002 practice lab."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json


HOST = "0.0.0.0"
PORT = 8080


class PracticeHandler(BaseHTTPRequestHandler):
    server_version = "RB002Practice/1.0"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path == "/":
            self._send_json(
                200,
                {
                    "service": "rb-002-practice-api",
                    "message": "The practice service accepted your request.",
                },
            )
            return

        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
            return

        self._send_json(404, {"error": "not found", "path": self.path})

    def _send_json(self, status: int, payload: dict[str, str]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        print(f"client={self.client_address[0]} {format % args}", flush=True)


if __name__ == "__main__":
    print(f"practice-api listening on {HOST}:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), PracticeHandler).serve_forever()
