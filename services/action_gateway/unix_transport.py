"""Unix-socket clients for gateway -> proxy and proxy -> Docker.

Only the proxy container is intended to mount Docker's socket. The gateway gets
the proxy socket and an action token after a separately reviewed release.
"""
from __future__ import annotations

import http.client
import json
import re
import socket


class _UnixHTTP(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("localhost", timeout=10)
        self.path = path

    def connect(self):
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.settimeout(self.timeout)
        conn.connect(self.path)
        self.sock = conn


class UnixRequester:
    def __init__(self, socket_path):
        self.socket_path = socket_path

    def __call__(self, method, path, headers=None):
        conn = _UnixHTTP(self.socket_path)
        try:
            conn.request(method, path, headers=headers or {})
            response = conn.getresponse()
            body = response.read(1_000_001)
            if len(body) > 1_000_000:
                raise ValueError("Unix proxy response exceeds the limit")
            return response.status, body
        finally:
            conn.close()


class DockerSocketClient:
    """The socket-proxy process's only route to Docker; never constructed by the gateway process."""

    def __init__(self, socket_path):
        self.request = UnixRequester(socket_path)

    def __call__(self, method, path, action_id):
        headers = {"X-Argus-Action-Id": action_id} if action_id else {}
        return self.request(method, path, headers)


class GatewayProxyTransport:
    def __init__(self, request):
        self.request = request

    def _container_identity(self, name):
        code, raw = self.request("GET", f"/containers/{name}/json", {})
        if code != 200:
            raise ValueError("target identity unavailable")
        try:
            value = json.loads(raw)["Id"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError("target identity unavailable") from exc
        if not isinstance(value, str) or not value:
            raise ValueError("target identity unavailable")
        return {"container_id": value}

    def identity(self, target):
        match = re.fullmatch(r"[a-z0-9-]+/container:(argus-lab-[A-Za-z0-9_.-]+)", target)
        if match is None:
            raise ValueError("invalid target")
        return self._container_identity(match[1])

    def execute(self, route, action_id, expected_identity):
        match = re.fullmatch(r"POST /containers/(argus-lab-[A-Za-z0-9_.-]+)/(start|stop|restart|pause|unpause)", route)
        if match is None:
            raise ValueError("invalid exact route")
        if self._container_identity(match[1]) != expected_identity:
            raise ValueError("target identity changed before execution")
        code, _ = self.request("POST", route.removeprefix("POST "), {"X-Argus-Action-Id": action_id})
        if 200 <= code < 300:
            return "confirmed"
        if 400 <= code < 500:
            return "failed"
        raise ConnectionError("ambiguous Docker proxy result")
