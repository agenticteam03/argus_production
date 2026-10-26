"""A second exact-path ACL stands between the gateway and the host Docker socket."""
from __future__ import annotations

import json
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from services.action_gateway.socket_proxy import ProxyRefused, SocketProxyPolicy, make_proxy_handler
from test_phase19_gateway import ACTION_ID, ROUTE, TARGET


def test_empty_socket_proxy_allows_no_docker_call():
    calls = []
    policy = SocketProxyPolicy("vm-166", {}, lambda *args: calls.append(args))
    with pytest.raises(ProxyRefused, match="not released"):
        policy.forward("GET", "/containers/argus-lab-cache/json")
    with pytest.raises(ProxyRefused, match="not released"):
        policy.forward("POST", "/containers/argus-lab-cache/start", action_id=ACTION_ID)
    assert calls == []


def test_socket_proxy_only_forwards_inspect_and_the_exact_released_route():
    calls = []

    def docker_call(method, path, action_id):
        calls.append((method, path, action_id))
        return 200, b'{"Id":"cache-1"}'

    policy = SocketProxyPolicy("vm-166", {("container.start", TARGET): ROUTE}, docker_call)
    for method, path, action_id in (
        ("GET", "/containers/argus-v18-agent/json", None),
        ("GET", "/containers/argus-lab-cache/json?all=1", None),
        ("POST", "/containers/argus-lab-cache/start", None),
        ("POST", "/containers/argus-lab-cache/stop", ACTION_ID),
        ("POST", "/containers/argus-lab-cache/start?x=1", ACTION_ID),
        ("DELETE", "/containers/argus-lab-cache", ACTION_ID),
    ):
        with pytest.raises(ProxyRefused):
            policy.forward(method, path, action_id=action_id)
    assert calls == []
    assert policy.forward("GET", "/containers/argus-lab-cache/json") == (200, b'{"Id":"cache-1"}')
    assert policy.forward("POST", "/containers/argus-lab-cache/start", action_id=ACTION_ID) == (200, b"")
    assert calls == [("GET", "/containers/argus-lab-cache/json", None),
                     ("POST", "/containers/argus-lab-cache/start", ACTION_ID)]


def test_proxy_http_listener_denies_other_docker_paths():
    calls = []

    def docker_call(method, path, action_id):
        calls.append((method, path, action_id))
        return 204, b""

    policy = SocketProxyPolicy("vm-166", {("container.start", TARGET): ROUTE}, docker_call)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_proxy_handler(policy))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def send(method, path, action_id=None):
        headers = {"X-Argus-Action-Id": action_id} if action_id else {}
        try:
            with urlopen(Request(base + path, data=b"" if method == "POST" else None,
                                 headers=headers, method=method), timeout=3) as response:
                return response.status
        except HTTPError as exc:
            return exc.code

    try:
        assert send("GET", "/containers/argus-v18-agent/json") == 403
        assert send("POST", "/containers/argus-lab-cache/start") == 403
        assert send("POST", "/containers/argus-lab-cache/stop", ACTION_ID) == 403
        assert calls == []
        assert send("POST", "/containers/argus-lab-cache/start", ACTION_ID) == 204
        assert calls == [("POST", "/containers/argus-lab-cache/start", ACTION_ID)]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_proxy_only_returns_the_identity_field_from_docker_inspect():
    raw = json.dumps({"Id": "cache-1", "Config": {"Env": ["PASSWORD=do-not-expose"]}}).encode()
    policy = SocketProxyPolicy("vm-166", {("container.start", TARGET): ROUTE},
                               lambda method, path, action_id: (200, raw))
    code, body = policy.forward("GET", "/containers/argus-lab-cache/json")
    assert code == 200 and json.loads(body) == {"Id": "cache-1"}
    assert b"PASSWORD" not in body
