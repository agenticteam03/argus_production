"""Phase 19 (ACR-0019 §3.9): the worker's client of the action gateway, against the real gateway listener.

The client sends the frozen proposal's exact route, target and identity with the worker-only token and the action ID;
a refusal is a definite `failed` (nothing was sent), a duplicate or an ambiguous answer is left to `status`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from argus.actions.gateway_client import HttpActionGateway
from argus.actions.remediation import RemediationRefused, freeze_proposal
from services.action_gateway.core import ActionGateway, ActionJournal
from services.action_gateway.server import make_handler
from test_phase18_remediation import candidate
from test_phase19_gateway import ACTION_ID, ROUTE, TARGET, FakeProxy

TOKEN = "a" * 40                     # low entropy on purpose: a fake secret


@pytest.fixture
def gateway(tmp_path):
    proxy = FakeProxy()
    core = ActionGateway("vm-166", TOKEN, ActionJournal(tmp_path / "journal.db"), proxy,
                         released={("container.start", TARGET): ROUTE})
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(core))
    Thread(target=server.serve_forever, daemon=True).start()
    token = tmp_path / "action_token"
    token.write_text(TOKEN, encoding="utf-8")
    yield f"http://127.0.0.1:{server.server_address[1]}", token, proxy
    server.shutdown()


def _proposal(**changes):
    return freeze_proposal(candidate(**changes), at=datetime.now(timezone.utc))


def test_the_released_action_is_sent_once_and_its_status_read_back(gateway):
    url, token, proxy = gateway
    client = HttpActionGateway(url, token)
    assert client.dispatch(ACTION_ID, _proposal()) == "confirmed"
    assert proxy.calls == [(ROUTE, ACTION_ID)]
    assert client.status(ACTION_ID) == "confirmed"
    with pytest.raises(RemediationRefused, match="already accepted"):
        client.dispatch(ACTION_ID, _proposal())                      # never twice: the executor reads the status
    assert proxy.calls == [(ROUTE, ACTION_ID)]
    assert client.status("act_" + "f" * 32) is None


def test_a_refused_action_is_failed_and_never_reaches_the_proxy(gateway, tmp_path):
    url, token, proxy = gateway
    restart = _proposal(capability="container.restart")
    assert HttpActionGateway(url, token).dispatch(ACTION_ID, restart) == "failed"            # not released
    wrong = tmp_path / "wrong"
    wrong.write_text("b" * 40, encoding="utf-8")
    assert HttpActionGateway(url, wrong).dispatch("act_" + "1" * 32, _proposal()) == "failed"   # wrong token
    assert proxy.calls == []


def test_an_ambiguous_answer_is_left_to_the_status(gateway):
    url, token, proxy = gateway
    proxy.fail_after_call = True
    client = HttpActionGateway(url, token)
    with pytest.raises(ConnectionError):
        client.dispatch(ACTION_ID, _proposal())
    assert client.status(ACTION_ID) == "received"                    # the executor records `indeterminate`


def test_the_token_comes_from_a_file_and_never_shows(tmp_path):
    short = tmp_path / "short"
    short.write_text("x" * 8, encoding="utf-8")
    with pytest.raises(ValueError, match="action token"):
        HttpActionGateway("http://gateway", short)
    with pytest.raises(ValueError, match="action token"):
        HttpActionGateway("http://gateway", tmp_path / "missing")
    good = tmp_path / "good"
    good.write_text(TOKEN + "\n", encoding="utf-8")
    client = HttpActionGateway("http://gateway", good)
    assert TOKEN not in repr(client) and TOKEN not in str(vars(client).get("base_url", ""))


def test_only_a_catalogue_route_for_a_host_qualified_container_is_built(tmp_path):
    token = tmp_path / "t"
    token.write_text(TOKEN, encoding="utf-8")
    client = HttpActionGateway("http://gateway", token)
    assert client.route_for(_proposal()) == "/containers/argus-lab-cache/start"
    with pytest.raises(RemediationRefused):
        client.route_for(_proposal(capability="docker.prune_build_cache"))


def test_the_client_has_no_model_or_harness_import_path():
    import argus.actions.gateway_client as module
    source = Path(module.__file__).read_text(encoding="utf-8")
    for forbidden in ("argus.adapters.outbound.llm", "argus.tooling", "openai", "argus.adapters.outbound.judge"):
        assert forbidden not in source


def test_each_hop_waits_longer_than_the_one_below_and_longer_than_a_docker_restart():
    """S4: a restart took 10.7 s (Docker waits up to 10 s to stop, then starts) and a 10 s wait reported it as ambiguous."""
    import inspect

    from argus.actions.gateway_client import HttpActionGateway
    from services.action_gateway.unix_transport import (DOCKER_TIMEOUT_S, PROXY_TIMEOUT_S, DockerSocketClient,
                                                        UnixRequester)
    client_s = inspect.signature(HttpActionGateway.__init__).parameters["timeout_s"].default
    assert 10 < DOCKER_TIMEOUT_S < PROXY_TIMEOUT_S < client_s
    assert DockerSocketClient("/nonexistent").request.timeout_s == DOCKER_TIMEOUT_S
    assert UnixRequester("/nonexistent").timeout_s == PROXY_TIMEOUT_S
