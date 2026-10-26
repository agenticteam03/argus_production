"""Phase 19 gateway core: no released route exists by default, even in a test image."""
from __future__ import annotations

import sqlite3

import pytest

from services.action_gateway.core import ActionGateway, ActionJournal, GatewayRefused, NotSent


ACTION_ID = "act_" + "a" * 32
TARGET = "vm-166/container:argus-lab-cache"
ROUTE = "POST /containers/argus-lab-cache/start"
IDENTITY = {"container_id": "cache-1"}


class FakeProxy:
    def __init__(self):
        self.calls = []
        self.current_identity = IDENTITY
        self.fail_after_call = False

    def identity(self, target):
        return self.current_identity

    def execute(self, route, action_id, expected_identity):
        if self.current_identity != expected_identity:
            raise NotSent("target identity changed before execution")
        self.calls.append((route, action_id))
        if self.fail_after_call:
            raise ConnectionError("ambiguous proxy response")
        return "confirmed"


def test_empty_gateway_rejects_every_write_before_proxy_call(tmp_path):
    proxy = FakeProxy()
    gateway = ActionGateway("vm-166", "test-secret", ActionJournal(tmp_path / "journal.db"), proxy)
    with pytest.raises(GatewayRefused, match="not released"):
        gateway.dispatch("test-secret", ACTION_ID, "container.start", TARGET, ROUTE, IDENTITY)
    assert proxy.calls == [] and gateway.status("test-secret", ACTION_ID) is None


def test_exact_route_target_identity_and_token_then_durable_single_acceptance(tmp_path):
    proxy = FakeProxy()
    journal_path = tmp_path / "journal.db"
    gateway = ActionGateway("vm-166", "test-secret", ActionJournal(journal_path), proxy,
                            released={("container.start", TARGET): ROUTE})
    for token, action_id, capability, target, route, identity in (
        ("wrong", ACTION_ID, "container.start", TARGET, ROUTE, IDENTITY),
        ("test-secret", "missing", "container.start", TARGET, ROUTE, IDENTITY),
        ("test-secret", ACTION_ID, "container.restart", TARGET, ROUTE, IDENTITY),
        ("test-secret", ACTION_ID, "container.start", "vm-095/container:argus-lab-cache", ROUTE, IDENTITY),
        ("test-secret", ACTION_ID, "container.start", TARGET, ROUTE + "/extra", IDENTITY),
        ("test-secret", ACTION_ID, "container.start", TARGET, ROUTE, {"container_id": "cache-2"}),
    ):
        with pytest.raises(GatewayRefused):
            gateway.dispatch(token, action_id, capability, target, route, identity)
    assert proxy.calls == []
    assert gateway.dispatch("test-secret", ACTION_ID, "container.start", TARGET, ROUTE, IDENTITY) == "confirmed"
    assert proxy.calls == [(ROUTE, ACTION_ID)]
    assert ActionGateway("vm-166", "test-secret", ActionJournal(journal_path), FakeProxy(),
                         released={("container.start", TARGET): ROUTE}).status("test-secret", ACTION_ID) == "confirmed"
    with pytest.raises(GatewayRefused, match="already accepted"):
        gateway.dispatch("test-secret", ACTION_ID, "container.start", TARGET, ROUTE, IDENTITY)
    assert proxy.calls == [(ROUTE, ACTION_ID)]


def test_proxy_ambiguity_is_journaled_and_never_retried(tmp_path):
    proxy = FakeProxy()
    proxy.fail_after_call = True
    gateway = ActionGateway("vm-166", "test-secret", ActionJournal(tmp_path / "journal.db"), proxy,
                            released={("container.start", TARGET): ROUTE})
    with pytest.raises(ConnectionError):
        gateway.dispatch("test-secret", ACTION_ID, "container.start", TARGET, ROUTE, IDENTITY)
    assert gateway.status("test-secret", ACTION_ID) == "received"
    with pytest.raises(GatewayRefused, match="already accepted"):
        gateway.dispatch("test-secret", ACTION_ID, "container.start", TARGET, ROUTE, IDENTITY)
    assert len(proxy.calls) == 1


def test_gateway_refuses_a_configuration_for_its_own_host_or_non_lab_target(tmp_path):
    journal = ActionJournal(tmp_path / "journal.db")
    with pytest.raises(GatewayRefused, match="own host"):
        ActionGateway("vm-095", "test-secret", journal, FakeProxy(),
                      released={("container.start", "vm-095/container:argus-lab-cache"):
                                "POST /containers/argus-lab-cache/start"})
    with pytest.raises(GatewayRefused, match="lab container"):
        ActionGateway("vm-166", "test-secret", journal, FakeProxy(),
                      released={("container.start", "vm-166/container:argus-v18-agent"):
                                "POST /containers/argus-v18-agent/start"})


def test_gateway_core_has_no_model_or_mcp_import_path():
    from pathlib import Path
    import services.action_gateway.core as core

    source = Path(core.__file__).read_text(encoding="utf-8")
    for forbidden in ("argus.adapters.outbound.llm", "argus.tooling.model_harness", "argus.tooling.mcp", "openai"):
        assert forbidden not in source


def test_journal_appends_received_and_result_events_instead_of_rewriting_one_row(tmp_path):
    path = tmp_path / "journal.db"
    gateway = ActionGateway("vm-166", "test-secret", ActionJournal(path), FakeProxy(),
                            released={("container.start", TARGET): ROUTE})
    gateway.dispatch("test-secret", ACTION_ID, "container.start", TARGET, ROUTE, IDENTITY)
    with sqlite3.connect(path) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "action_event" in tables
        assert [row[0] for row in db.execute("SELECT docker_status FROM action_event WHERE action_id=? ORDER BY seq",
                                             (ACTION_ID,))] == ["received", "confirmed"]
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE action_event SET docker_status='failed' WHERE action_id=?", (ACTION_ID,))
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("DELETE FROM action_receipt WHERE action_id=?", (ACTION_ID,))


def test_an_identity_change_before_the_write_is_recorded_as_failed_not_ambiguous(tmp_path):
    proxy = FakeProxy()
    gateway = ActionGateway("vm-166", "test-secret", ActionJournal(tmp_path / "journal.db"), proxy,
                            released={("container.start", TARGET): ROUTE})
    proxy.identity = lambda target: IDENTITY                       # the first read still matches
    proxy.current_identity = {"container_id": "replaced"}          # replaced before the write
    assert gateway.dispatch("test-secret", ACTION_ID, "container.start", TARGET, ROUTE, IDENTITY) == "failed"
    assert gateway.status("test-secret", ACTION_ID) == "failed" and proxy.calls == []
