import json

import pytest

from services.action_gateway.core import ActionGateway, ActionJournal, GatewayRefused, NotSent, validated_pairs
from services.action_gateway.server import _parse_post_body
from services.action_gateway.socket_proxy import ProxyRefused, SocketProxyPolicy
from services.action_gateway.unix_transport import GatewayProxyTransport


HOST = "vm-166"
TARGET = "vm-166/container:argus-lab-app"
ROUTE = "POST /containers/argus-lab-app/network-restore"
ACTION = "act_0123456789abcdef0123456789abcdef"
IDENTITY = {"container_id": "a" * 64}
RELEASE = {
    ("network.restore", TARGET): {
        "route": ROUTE,
        "connect_network": "argus-lab-frontend",
        "disconnect_network": "argus-lab-backend",
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


def _dispatch(gateway, *, action_id=ACTION, identity=IDENTITY,
              connect="argus-lab-frontend", disconnect="argus-lab-backend"):
    return gateway.dispatch("secret", action_id, "network.restore", TARGET, ROUTE, identity,
                            connect_network=connect, disconnect_network=disconnect)


def test_network_restore_runs_connect_then_disconnect_and_journals_both(tmp_path):
    gateway, journal, proxy = _gateway(tmp_path)

    assert _dispatch(gateway) == "confirmed"
    assert [call[0:3] for call in proxy.calls] == [
        ("connect", TARGET, "argus-lab-frontend"),
        ("disconnect", TARGET, "argus-lab-backend"),
    ]
    assert journal.events(ACTION) == ["received", "connect", "disconnect", "confirmed"]


def test_network_restore_refuses_names_that_differ_from_release(tmp_path):
    gateway, _, proxy = _gateway(tmp_path)

    with pytest.raises(GatewayRefused):
        _dispatch(gateway, connect="argus-lab-other")
    assert proxy.calls == []


def test_worker_body_rejects_extra_keys():
    body = {"capability": "network.restore", "target": TARGET, "target_identity": IDENTITY,
            "connect_network": "argus-lab-frontend", "disconnect_network": "argus-lab-backend", "extra": True}

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
        "route": ROUTE, "connect_network": network, "disconnect_network": "argus-lab-backend",
    }}

    with pytest.raises(GatewayRefused):
        ActionGateway(HOST, "secret", ActionJournal(str(tmp_path / f"{network}.db")), FakeProxy(),
                      released=released)


def test_network_release_can_be_validated_twice():
    assert validated_pairs(HOST, validated_pairs(HOST, RELEASE))[("network.restore", TARGET)]["route"] == ROUTE


@pytest.mark.parametrize("network", ["frontend", "argus-v18-core", "argus-lab-"])
def test_network_release_requires_nonempty_lab_network_names(network):
    released = {("network.restore", TARGET): {
        "route": ROUTE, "connect_network": network, "disconnect_network": "argus-lab-backend",
    }}
    with pytest.raises(GatewayRefused):
        validated_pairs(HOST, released)


def test_network_release_refuses_same_network_for_both_steps():
    released = {("network.restore", TARGET): {
        "route": ROUTE, "connect_network": "argus-lab-app", "disconnect_network": "argus-lab-app",
    }}
    with pytest.raises(GatewayRefused):
        validated_pairs(HOST, released)


def test_worker_uses_hyphenated_network_restore_route():
    body = {"capability": "network.restore", "target": TARGET, "target_identity": IDENTITY,
            "connect_network": "argus-lab-frontend", "disconnect_network": "argus-lab-backend"}
    assert _parse_post_body(ROUTE.removeprefix("POST "), json.dumps(body).encode()) == body
    with pytest.raises(ValueError):
        _parse_post_body(ROUTE.replace("network-restore", "network.restore").removeprefix("POST "),
                         json.dumps(body).encode())


def test_network_transport_builds_exact_body_and_rechecks_identity():
    calls = []

    def request(method, path, headers=None, body=None):
        calls.append((method, path, headers, body))
        return (200, json.dumps({"Id": "a" * 64}).encode()) if method == "GET" else (204, b"")
    transport = GatewayProxyTransport(request)
    assert transport.connect_network(TARGET, "argus-lab-frontend", ACTION, IDENTITY) == "confirmed"
    assert calls[-1][0:2] == ("POST", "/networks/argus-lab-frontend/connect")
    assert calls[-1][3] == b'{"Container":"' + b"a" * 64 + b'"}'
    mismatch = GatewayProxyTransport(lambda *_args, **_kwargs: (200, json.dumps({"Id": "b" * 64}).encode()))
    with pytest.raises(NotSent, match="identity changed"):
        mismatch.disconnect_network(TARGET, "argus-lab-backend", ACTION, IDENTITY)


def test_load_config_accepts_only_hyphenated_network_restore_route(tmp_path):
    from services.action_gateway.run import load_config

    config = {"host": HOST, "released": [{"capability": "network.restore", "target": TARGET,
               "route": ROUTE, "connect_network": "argus-lab-frontend",
               "disconnect_network": "argus-lab-backend"}]}
    path = tmp_path / "gateway.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    assert load_config(path)[1][("network.restore", TARGET)]["route"] == ROUTE
    config["released"][0]["route"] = ROUTE.replace("network-restore", "network.restore")
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(GatewayRefused):
        load_config(path)


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
    path = "/networks/argus-lab-frontend/connect"
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
        ("/networks/argus-lab-frontend/connect", ACTION, b'{"Container":"' + b"a" * 64 + b'"}'),
        ("/networks/argus-lab-backend/disconnect", ACTION, b'{"Container":"' + b"a" * 64 + b'"}'),
    ]
    assert journal.events(ACTION) == ["received", "connect", "disconnect", "confirmed"]


def test_socket_proxy_supports_two_targets_sharing_network():
    second_target = "vm-166/container:argus-lab-backend"
    second_release = {("network.restore", second_target): {
        "route": "POST /containers/argus-lab-backend/network-restore",
        "connect_network": "argus-lab-frontend", "disconnect_network": "argus-lab-backend-net",
    }}
    calls = []

    def docker_call(method, path, action_id, body=None):
        calls.append((method, path, action_id, body))
        if method == "GET":
            target_id = "b" * 64 if "argus-lab-backend/" in path else "a" * 64
            return 200, json.dumps({"Id": target_id}).encode()
        return 204, b""

    released = dict(RELEASE)
    released.update(second_release)
    policy = SocketProxyPolicy(HOST, released, docker_call)
    path = "/networks/argus-lab-frontend/connect"
    body = json.dumps({"Container": "b" * 64}, separators=(",", ":")).encode()
    assert policy.forward("POST", path, action_id=ACTION, body=body) == (204, b"")
    assert calls[-1] == ("POST", path, ACTION, body)
    assert len(policy.network_paths[path]) == 2
