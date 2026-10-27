import json

import pytest

from services.action_gateway.core import ActionGateway, ActionJournal, GatewayRefused, validated_pairs
from services.action_gateway.server import _parse_post_body
from services.action_gateway.socket_proxy import ProxyRefused, SocketProxyPolicy
from services.action_gateway.unix_transport import GatewayProxyTransport


HOST = "vm-166"
TARGET = "vm-166/container:argus-lab-app"
ROUTE = "POST /containers/argus-lab-app/network.restore"
ACTION = "act_0123456789abcdef0123456789abcdef"
IDENTITY = {"container_id": "a" * 64}
RELEASE = {
    ("network.restore", TARGET): {
        "route": ROUTE,
        "connect_network": "frontend",
        "disconnect_network": "backend",
    }
}


class FakeProxy:
    def __init__(self, *, identity=IDENTITY, connect="confirmed", disconnect="confirmed"):
        self.current_identity = identity
        self.connect_result = connect
        self.disconnect_result = disconnect
        self.calls = []

    def identity(self, target):
        return self.current_identity

    def connect_network(self, target, network, action_id, expected_identity):
        self.calls.append(("connect", target, network, action_id, expected_identity))
        if isinstance(self.connect_result, Exception):
            raise self.connect_result
        return self.connect_result

    def disconnect_network(self, target, network, action_id, expected_identity):
        self.calls.append(("disconnect", target, network, action_id, expected_identity))
        if isinstance(self.disconnect_result, Exception):
            raise self.disconnect_result
        return self.disconnect_result


def _gateway(tmp_path, proxy=None, host=HOST):
    journal = ActionJournal(str(tmp_path / "gateway.db"))
    proxy = proxy or FakeProxy()
    gateway = ActionGateway(host, "secret", journal, proxy, released=RELEASE if host == HOST else RELEASE)
    return gateway, journal, proxy


def _dispatch(gateway, *, action_id=ACTION, identity=IDENTITY, connect="frontend", disconnect="backend"):
    return gateway.dispatch("secret", action_id, "network.restore", TARGET, ROUTE, identity,
                            connect_network=connect, disconnect_network=disconnect)


def test_network_restore_runs_connect_then_disconnect_and_journals_both(tmp_path):
    gateway, journal, proxy = _gateway(tmp_path)

    assert _dispatch(gateway) == "confirmed"
    assert [call[0:3] for call in proxy.calls] == [
        ("connect", TARGET, "frontend"),
        ("disconnect", TARGET, "backend"),
    ]
    assert journal.events(ACTION) == ["received", "connect", "disconnect", "confirmed"]


def test_network_restore_refuses_names_that_differ_from_release(tmp_path):
    gateway, _, proxy = _gateway(tmp_path)

    with pytest.raises(GatewayRefused):
        _dispatch(gateway, connect="other")
    assert proxy.calls == []


def test_worker_body_rejects_extra_keys():
    body = {"capability": "network.restore", "target": TARGET, "target_identity": IDENTITY,
            "connect_network": "frontend", "disconnect_network": "backend", "extra": True}

    with pytest.raises(ValueError):
        _parse_post_body(ROUTE.removeprefix("POST "), json.dumps(body).encode())


def test_network_restore_refuses_changed_container_identity(tmp_path):
    proxy = FakeProxy(identity={"container_id": "b" * 64})
    gateway, journal, _ = _gateway(tmp_path, proxy)

    with pytest.raises(GatewayRefused):
        _dispatch(gateway)
    assert journal.status(ACTION) is None


def test_vm095_cannot_release_network_restore(tmp_path):
    with pytest.raises(GatewayRefused):
        ActionGateway("vm-095", "secret", ActionJournal(str(tmp_path / "gateway.db")), FakeProxy(),
                      released=RELEASE)


@pytest.mark.parametrize("network", ["bridge", "host", "none"])
def test_default_networks_cannot_be_released(tmp_path, network):
    released = {("network.restore", TARGET): {
        "route": ROUTE, "connect_network": network, "disconnect_network": "backend",
    }}

    with pytest.raises(GatewayRefused):
        ActionGateway(HOST, "secret", ActionJournal(str(tmp_path / f"{network}.db")), FakeProxy(),
                      released=released)


def test_network_release_can_be_validated_twice():
    assert validated_pairs(HOST, validated_pairs(HOST, RELEASE))[("network.restore", TARGET)]["route"] == ROUTE


def test_connect_failure_never_disconnects(tmp_path):
    gateway, journal, proxy = _gateway(tmp_path, FakeProxy(connect="failed"))

    assert _dispatch(gateway) == "failed"
    assert [call[0] for call in proxy.calls] == ["connect"]
    assert journal.status(ACTION) == "failed"


def test_duplicate_action_id_is_refused(tmp_path):
    gateway, _, _ = _gateway(tmp_path)
    _dispatch(gateway)

    with pytest.raises(GatewayRefused, match="already accepted"):
        _dispatch(gateway)


def test_duplicate_network_step_is_refused(tmp_path):
    _, journal, _ = _gateway(tmp_path)
    journal.accept(ACTION, "network.restore", TARGET, ROUTE, IDENTITY)
    journal.record_step(ACTION, "connect")

    with pytest.raises(GatewayRefused, match="already recorded"):
        journal.record_step(ACTION, "connect")


def test_ambiguous_disconnect_stays_pending_for_human_reconciliation(tmp_path):
    proxy = FakeProxy(disconnect=ConnectionError("lost response"))
    gateway, journal, _ = _gateway(tmp_path, proxy)

    with pytest.raises(ConnectionError):
        _dispatch(gateway)
    assert journal.status(ACTION) == "indeterminate"
    assert journal.events(ACTION) == ["received", "connect"]


def test_socket_proxy_allows_only_exact_released_network_body():
    calls = []

    def docker_call(method, path, action_id, body=None):
        calls.append((method, path, action_id, body))
        if method == "GET":
            return 200, json.dumps({"Id": "a" * 64}).encode()
        return 204, b""

    policy = SocketProxyPolicy(HOST, RELEASE, docker_call)
    path = "/networks/frontend/connect"
    body = json.dumps({"Container": "a" * 64}, separators=(",", ":")).encode()

    assert policy.forward("POST", path, action_id=ACTION, body=body) == (204, b"")
    assert calls[-1] == ("POST", path, ACTION, body)
    with pytest.raises(ProxyRefused):
        policy.forward("POST", path, action_id=ACTION, body=b'{"Container":"' + b"a" * 64 + b'","extra":true}')


def test_gateway_and_fake_docker_complete_both_exact_calls_in_order(tmp_path):
    docker_posts = []

    def fake_docker(method, path, action_id, body=None):
        if method == "GET":
            return 200, json.dumps({"Id": "a" * 64}).encode()
        docker_posts.append((path, action_id, body))
        return 200, b""

    policy = SocketProxyPolicy(HOST, RELEASE, fake_docker)

    def request(method, path, headers=None, body=None):
        return policy.forward(method, path, action_id=(headers or {}).get("X-Argus-Action-Id"), body=body)

    journal = ActionJournal(str(tmp_path / "docker.db"))
    gateway = ActionGateway(HOST, "secret", journal, GatewayProxyTransport(request), released=RELEASE)

    assert _dispatch(gateway) == "confirmed"
    assert docker_posts == [
        ("/networks/frontend/connect", ACTION, b'{"Container":"' + b"a" * 64 + b'"}'),
        ("/networks/backend/disconnect", ACTION, b'{"Container":"' + b"a" * 64 + b'"}'),
    ]
    assert journal.events(ACTION) == ["received", "connect", "disconnect", "confirmed"]
