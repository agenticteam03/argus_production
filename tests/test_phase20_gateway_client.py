"""The worker client sends only frozen, released action rows to the journaled gateway."""
from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
import pytest

from argus.actions.gateway_client import GatewayClient, GatewayClientRefused, HttpGatewayRequest
from argus.actions.remediation import freeze_proposal
from test_phase18_remediation import NOW, TARGET, candidate
from test_phase19_gateway import FakeProxy
from services.action_gateway.core import ActionGateway, ActionJournal
from services.action_gateway.server import make_handler


ROUTE = "POST /containers/argus-lab-cache/start"
PAIR = ("container.start", TARGET)
ACTION_ID = "act_" + "a" * 32


def test_gateway_client_sends_only_the_released_frozen_pair():
    seen = []

    def request(method, path, headers, body):
        seen.append((method, path, headers, body))
        return 200, b'{"status":"confirmed"}'

    gateway = GatewayClient(request, lambda: "test-token", released={PAIR: ROUTE})
    proposal = freeze_proposal(candidate(), at=NOW)
    assert gateway.dispatch(ACTION_ID, proposal) == "confirmed"
    assert len(seen) == 1
    method, path, headers, body = seen[0]
    assert method == "POST" and path == "/containers/argus-lab-cache/start"
    assert headers["Authorization"] == "Bearer test-token"
    assert headers["X-Argus-Action-Id"] == ACTION_ID
    assert json.loads(body) == {"capability": "container.start", "target": TARGET,
                                "target_identity": {"container_id": "cache-1"}}


def test_gateway_client_refuses_unreleased_pair_before_network():
    seen = []
    gateway = GatewayClient(lambda *args: seen.append(args) or (200, b""),
                            lambda: "test-token", released={PAIR: ROUTE})
    changed = freeze_proposal(candidate(capability="container.restart"), at=NOW)
    with pytest.raises(GatewayClientRefused):
        gateway.dispatch(ACTION_ID, changed)
    assert seen == []


def test_ambiguous_response_is_queried_by_id_without_second_post():
    methods = []

    def request(method, path, headers, body):
        methods.append((method, path))
        return (503, b"") if method == "POST" else (200, b'{"status":"received"}')

    gateway = GatewayClient(request, lambda: "test-token", released={PAIR: ROUTE})
    with pytest.raises(GatewayClientRefused):
        gateway.dispatch(ACTION_ID, freeze_proposal(candidate(), at=NOW))
    assert gateway.status(ACTION_ID) == "received"
    assert methods == [("POST", "/containers/argus-lab-cache/start"), ("GET", f"/actions/{ACTION_ID}")]


def test_worker_client_and_gateway_listener_exchange_one_journaled_action(tmp_path):
    proxy = FakeProxy()
    journal = ActionJournal(tmp_path / "action-journal.db")
    gateway = ActionGateway("vm-166", "test-token", journal, proxy, released={PAIR: ROUTE})
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(gateway))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = GatewayClient(HttpGatewayRequest("127.0.0.1", server.server_port),
                               lambda: "test-token", released={PAIR: ROUTE})
        proposal = freeze_proposal(candidate(), at=NOW)
        assert client.dispatch(ACTION_ID, proposal) == "confirmed"
        assert client.status(ACTION_ID) == "confirmed"
        assert len(proxy.calls) == 1
        with pytest.raises(GatewayClientRefused):
            client.dispatch(ACTION_ID, proposal)
        assert len(proxy.calls) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        journal.close()
