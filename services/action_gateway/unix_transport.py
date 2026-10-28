"""Unix-socket clients for gateway -> proxy and proxy -> Docker.

Only the proxy container is intended to mount Docker's socket. The gateway gets
the proxy socket and an action token after a separately reviewed release.
"""
from __future__ import annotations

import http.client
import json
import re
import socket

from services.action_gateway.core import NotSent

# Each hop waits longer than the one below it, and the bottom one longer than a restart: Docker waits up to 10 s for
# the container to stop before it kills it, then starts it. With 10 s here, the S4 rehearsal's restart (10.7 s) was
# done but reported as ambiguous. The Argus client waits longer still (argus/actions/gateway_client.py).
DOCKER_TIMEOUT_S = 20                 # proxy -> Docker
PROXY_TIMEOUT_S = 25                  # gateway -> proxy


class _UnixHTTP(http.client.HTTPConnection):
    def __init__(self, path, timeout):
        super().__init__("localhost", timeout=timeout)
        self.path = path

    def connect(self):
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.settimeout(self.timeout)
        conn.connect(self.path)
        self.sock = conn


class UnixRequester:
    def __init__(self, socket_path, timeout_s: float = PROXY_TIMEOUT_S):
        self.socket_path, self.timeout_s = socket_path, timeout_s

    def __call__(self, method, path, headers=None, body=None):
        conn = _UnixHTTP(self.socket_path, self.timeout_s)
        try:
            conn.request(method, path, body=body, headers=headers or {})
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
        self.request = UnixRequester(socket_path, DOCKER_TIMEOUT_S)

    def __call__(self, method, path, action_id, body=None):
        headers = {"X-Argus-Action-Id": action_id} if action_id else {}
        if body is None:
            return self.request(method, path, headers)
        return self.request(method, path, headers, body)


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
            raise NotSent("target identity changed before execution")
        code, _ = self.request("POST", route.removeprefix("POST "), {"X-Argus-Action-Id": action_id})
        if 200 <= code < 300 or code == 304:     # 304: Docker's "already started/stopped", the requested state holds
            return "confirmed"
        if 400 <= code < 500:
            return "failed"
        raise ConnectionError("ambiguous Docker proxy result")

    def _network_step(self, target, network, verb, action_id, expected_identity):
        match = re.fullmatch(r"[a-z0-9-]+/container:(argus-lab-[A-Za-z0-9_.-]+)", target)
        if match is None or not re.fullmatch(r"argus-lab-[A-Za-z0-9_.-]+", network):
            raise ValueError("invalid network action target")
        if self._container_identity(match[1]) != expected_identity:
            raise NotSent("target identity changed before network action")
        container_id = expected_identity.get("container_id")
        if not isinstance(container_id, str) or not re.fullmatch(r"[0-9a-f]{64}", container_id):
            raise ValueError("invalid frozen container identity")
        path = f"/networks/{network}/{verb}"
        body = json.dumps({"Container": container_id}, separators=(",", ":")).encode()
        headers = {"X-Argus-Action-Id": action_id, "Content-Type": "application/json",
                   "Content-Length": str(len(body))}
        code, _ = self.request("POST", path, headers, body)
        if 200 <= code < 300:
            return "confirmed"
        if 400 <= code < 500:
            return "failed"
        raise ConnectionError("ambiguous Docker network result")

    def connect_network(self, target, network, action_id, expected_identity):
        return self._network_step(target, network, "connect", action_id, expected_identity)

    def disconnect_network(self, target, network, action_id, expected_identity):
        return self._network_step(target, network, "disconnect", action_id, expected_identity)
