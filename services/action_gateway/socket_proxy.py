"""Second exact-path ACL, between the gateway service and Docker's Unix socket."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler

from services.action_gateway.core import ACTION_ID, validated_pairs


class ProxyRefused(ValueError):
    """A Docker route or target was not released for this host."""


class SocketProxyPolicy:
    def __init__(self, host, released, docker_call):
        self.host, self.released, self.docker_call = host, validated_pairs(host, released), docker_call
        self._inspect_paths = {"/containers/" + target.split(":", 1)[1] + "/json"
                               for _, target in self.released}
        self._write_paths = {route.removeprefix("POST ") for route in self.released.values()}

    def forward(self, method, path, *, action_id=None):
        if not self.released:
            raise ProxyRefused("route and target are not released")
        if method == "GET" and path in self._inspect_paths and action_id is None:
            code, raw = self.docker_call(method, path, None)
            if code != 200:
                return code, b""
            if len(raw) > 1_000_000:
                raise ProxyRefused("Docker inspect response exceeds the limit")
            try:
                identity = json.loads(raw)["Id"]
            except (ValueError, KeyError, TypeError) as exc:
                raise ProxyRefused("Docker inspect omitted the identity") from exc
            if not isinstance(identity, str) or not identity:
                raise ProxyRefused("Docker inspect omitted the identity")
            return 200, json.dumps({"Id": identity}, separators=(",", ":")).encode()
        if method == "POST" and path in self._write_paths and action_id and ACTION_ID.fullmatch(action_id):
            code, _ = self.docker_call(method, path, action_id)
            return code, b""  # Docker may return sensitive details; only the status crosses the proxy.
        raise ProxyRefused("Docker route or target is not released")


def make_proxy_handler(policy):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def _forward(self, method):
            if method == "POST" and self.headers.get("Content-Length", "0") != "0":
                self.send_error(400)
                return
            try:
                code, body = policy.forward(method, self.path,
                                            action_id=self.headers.get("X-Argus-Action-Id"))
            except ProxyRefused:
                self.send_error(403)
                return
            except Exception:
                self.send_error(502)
                return
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._forward("GET")

        def do_POST(self):
            self._forward("POST")

    return Handler
