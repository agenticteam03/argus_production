"""The gateway rechecks identity before a write and only talks to its proxy transport."""
from __future__ import annotations

import pytest

from services.action_gateway.core import NotSent
from services.action_gateway.unix_transport import GatewayProxyTransport
from test_phase19_gateway import ACTION_ID, IDENTITY, ROUTE, TARGET


def test_gateway_proxy_transport_reads_identity_twice_then_sends_exact_route():
    calls = []

    def request(method, path, headers):
        calls.append((method, path, headers))
        if method == "GET":
            return 200, b'{"Id":"cache-1"}'
        return 204, b""

    proxy = GatewayProxyTransport(request)
    assert proxy.identity(TARGET) == IDENTITY
    assert proxy.execute(ROUTE, ACTION_ID, IDENTITY) == "confirmed"
    assert [call[:2] for call in calls] == [
        ("GET", "/containers/argus-lab-cache/json"),
        ("GET", "/containers/argus-lab-cache/json"),
        ("POST", "/containers/argus-lab-cache/start"),
    ]
    assert calls[-1][2]["X-Argus-Action-Id"] == ACTION_ID


def test_gateway_proxy_transport_never_writes_after_identity_changes():
    calls = []

    def request(method, path, headers):
        calls.append(method)
        return 200, b'{"Id":"replaced"}'

    proxy = GatewayProxyTransport(request)
    with pytest.raises(NotSent, match="identity changed"):
        proxy.execute(ROUTE, ACTION_ID, IDENTITY)
    assert calls == ["GET"]


@pytest.mark.parametrize("code, result", [(204, "confirmed"), (304, "confirmed"), (404, "failed"), (409, "failed")])
def test_docker_304_already_in_the_requested_state_is_a_definite_result(code, result):
    """Docker answers 304 to `start` on a running container: the requested state holds; nothing is ambiguous."""
    def request(method, path, headers):
        return (200, b'{"Id":"cache-1"}') if method == "GET" else (code, b"")

    assert GatewayProxyTransport(request).execute(ROUTE, ACTION_ID, IDENTITY) == result


def test_a_docker_server_error_stays_ambiguous():
    def request(method, path, headers):
        return (200, b'{"Id":"cache-1"}') if method == "GET" else (500, b"")

    with pytest.raises(ConnectionError):
        GatewayProxyTransport(request).execute(ROUTE, ACTION_ID, IDENTITY)
