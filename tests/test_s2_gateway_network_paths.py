"""Exercise the HTTP proxy handler's network body path without a Docker daemon."""
from __future__ import annotations

import io
import json
from types import SimpleNamespace

from services.action_gateway.socket_proxy import SocketProxyPolicy, make_proxy_handler


class _Socket:
    def __init__(self, request):
        self.reader = io.BytesIO(request)
        self.writer = io.BytesIO()

    def makefile(self, mode, *_args, **_kwargs):
        return self.reader if "r" in mode else self.writer

    def sendall(self, value):
        self.writer.write(value)

    def close(self):
        pass


def _post(policy, body, *, length=None):
    action_id = "act_0123456789abcdef0123456789abcdef"
    body = body if isinstance(body, bytes) else body.encode()
    declared = len(body) if length is None else length
    request = (b"POST /networks/argus-lab-app/connect HTTP/1.0\r\n"
               + f"Content-Length: {declared}\r\nX-Argus-Action-Id: {action_id}\r\n\r\n".encode()
               + body)
    sock = _Socket(request)
    handler = make_proxy_handler(policy)
    handler(sock, ("127.0.0.1", 12345), SimpleNamespace())
    return sock.writer.getvalue()


def test_proxy_handler_reads_exact_network_body_and_forwards_it():
    calls = []

    def docker_call(method, path, action_id, body=None):
        calls.append((method, path, action_id, body))
        if method == "GET":
            return 200, json.dumps({"Id": "a" * 64}).encode()
        return 204, b""

    released = {("network.restore", "vm-166/container:argus-lab-app"): {
        "route": "POST /containers/argus-lab-app/network-restore",
        "connect_network": "argus-lab-app", "disconnect_network": "argus-lab-other",
    }}
    policy = SocketProxyPolicy("vm-166", released, docker_call)
    body = json.dumps({"Container": "a" * 64}, separators=(",", ":")).encode()
    response = _post(policy, body)
    assert b"204 No Content" in response
    assert calls[-1] == ("POST", "/networks/argus-lab-app/connect",
                         "act_0123456789abcdef0123456789abcdef", body)


def test_proxy_handler_rejects_truncated_network_body():
    released = {("network.restore", "vm-166/container:argus-lab-app"): {
        "route": "POST /containers/argus-lab-app/network-restore",
        "connect_network": "argus-lab-app", "disconnect_network": "argus-lab-other",
    }}
    policy = SocketProxyPolicy("vm-166", released, lambda *_args: (200, b"{}"))
    assert b"400 Bad Request" in _post(policy, b"{}", length=10)
