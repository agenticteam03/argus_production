"""Phase 20 (X-4): the frozen-row executor dispatches through the reviewed HTTP client to the real gateway listener,
with a fresh precheck read from the target and a verification sampled after the action."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace

import pytest

from argus.actions.cards import ActionCard
from argus.actions.execution import ActionExecutor
from argus.actions.gateway_client import HttpActionGateway
from argus.actions.live import LivePrecheck, LiveVerification, status_from_observation
from argus.actions.remediation import RemediationRefused, freeze_proposal
from argus.domain.model import IncidentStatus, Observation, TargetRef
from services.action_gateway.core import ActionGateway, ActionJournal
from services.action_gateway.server import make_handler
from test_phase18_remediation import NOW, TARGET, agreed, candidate
from test_phase19_gateway import ROUTE, FakeProxy

TOKEN = "a" * 40                     # low entropy on purpose: a fake secret
PAIR = ("container.start", TARGET)
FULL_ID = "c" * 64
CARD = ActionCard.from_dict({
    "name": "container.start", "model_name": "start_container", "executor": "action-gateway",
    "route": "/containers/{name}/start", "parameters": {}, "identity_fields": ["container_id"],
    "preconditions": ['state == "exited" or state == "created"'], "useful_when": [], "not_useful_when": [],
    "verify": {"signal": "up", "expected": 1, "window_sec": 30}, "rollback": "container.stop", "sources": []})


@pytest.fixture
def listener(tmp_path):
    proxy = FakeProxy()
    core = ActionGateway("vm-166", TOKEN, ActionJournal(tmp_path / "journal.db"), proxy, released={PAIR: ROUTE})
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(core))
    Thread(target=server.serve_forever, daemon=True).start()
    token = tmp_path / "action_token"
    token.write_text(TOKEN, encoding="utf-8")
    yield HttpActionGateway(f"http://127.0.0.1:{server.server_address[1]}", token), proxy
    server.shutdown()


def _approved(tmp_path, at):
    from argus.adapters.outbound.sqlite_store import SqliteStore

    store = SqliteStore(str(tmp_path / "action.db"))
    proposal = freeze_proposal(candidate(), at=at)
    store.add_action_proposal(proposal)
    agreed(store, proposal, at)
    store.add_action_approval("appr_live", proposal.id, proposal.digest, at, proposal.expires_at)
    assert store.answer_action_approval("appr_live", proposal.digest, "operator", "approved", at)
    return store, proposal


class Rows:
    """The rows LivePrecheck and LiveVerification read, over a real store."""

    def __init__(self, store, *, incident_status=IncidentStatus.running, evidence_version=1):
        self.store, self.incident_status, self.evidence_version = store, incident_status, evidence_version

    def get_incident(self, incident_id):
        return SimpleNamespace(id=incident_id, status=self.incident_status)

    def evidence_state(self, incident_id):
        return self.evidence_version, None

    def __getattr__(self, name):
        return getattr(self.store, name)


def _precheck(rows, *, values=None, observed_at=None, firing=True, lease_clear=True):
    status = {"id": FULL_ID[:12], "container_id": "cache-1", "state": "exited", **(values or {})}
    return LivePrecheck(rows=rows, inventory=SimpleNamespace(version=lambda: "inventory-1"),
                        policy_version="policy-1", cards={"container.start": CARD},
                        read_status=lambda target: (status, observed_at or NOW),
                        detector_firing=lambda incident: firing, host_lease_clear=lambda host: lease_clear)


def test_the_executor_sends_one_action_through_the_real_gateway_and_verifies_it(tmp_path, listener):
    client, proxy = listener
    at = datetime.now(timezone.utc).replace(microsecond=0)
    store, proposal = _approved(tmp_path, at)
    try:
        rows = Rows(store, evidence_version="evidence-1")
        check = _precheck(rows, observed_at=at)(proposal, at)
        executor = ActionExecutor(store, client, gate_open=frozenset({PAIR}), daily_host_cap=2)
        action = executor.execute("appr_live", check, at=at)
        assert action["state"] == "confirmed"
        assert proxy.calls == [(ROUTE, action["id"])]
        assert executor.execute("appr_live", check, at=at)["id"] == action["id"]     # never sent twice
        assert len(proxy.calls) == 1

        later = at + timedelta(seconds=20)
        verification = LiveVerification(rows=rows, read_signal=lambda signal, target: ("healthy", later),
                                        detector_firing=lambda incident: False)
        assert executor.verify(action["id"], verification(action["id"], later), at=later) == "recovered_verified"
    finally:
        store._db.close()


def test_a_gateway_refusal_is_a_definite_failure_without_a_proxy_call(tmp_path, listener):
    client, proxy = listener
    at = datetime.now(timezone.utc).replace(microsecond=0)
    store, proposal = _approved(tmp_path, at)
    try:
        check = _precheck(Rows(store, evidence_version="evidence-1"), observed_at=at)(proposal, at)
        proxy.current_identity = {"container_id": "replaced"}                  # recreated after the approval
        action = ActionExecutor(store, client, gate_open=frozenset({PAIR}), daily_host_cap=2).execute(
            "appr_live", check, at=at)
        assert action["state"] == "failed" and proxy.calls == []
    finally:
        store._db.close()


def test_the_executor_still_refuses_any_other_gateway():
    class RealLooking:
        def dispatch(self, action_id, proposal):
            return "confirmed"

        def status(self, action_id):
            return "confirmed"

    with pytest.raises(ValueError, match="gateway"):
        ActionExecutor(object(), RealLooking(), gate_open=frozenset(), daily_host_cap=1)


def test_the_precheck_reads_identity_preconditions_and_versions_fresh(tmp_path):
    store, proposal = _approved(tmp_path, NOW)
    try:
        rows = Rows(store, evidence_version="evidence-1")
        check = _precheck(rows)(proposal, NOW)
        assert check.target_identity == {"container_id": "cache-1"}
        assert (check.inventory_version, check.policy_version, check.evidence_version) == (
            "inventory-1", "policy-1", "evidence-1")
        assert check.observed_at == NOW
        assert check.incident_open and check.class_detected and check.action_preconditions_met
        assert check.host_lease_clear

        assert not _precheck(rows, values={"state": "running"})(proposal, NOW).action_preconditions_met
        assert not _precheck(rows, firing=False)(proposal, NOW).class_detected
        assert not _precheck(rows, lease_clear=False)(proposal, NOW).host_lease_clear
        assert _precheck(rows, values={"container_id": "other"})(proposal, NOW).target_identity == {
            "container_id": "other"}
        assert _precheck(Rows(store, evidence_version=2))(proposal, NOW).evidence_version == "2"
        assert not _precheck(Rows(store, incident_status=IncidentStatus.closed))(proposal, NOW).incident_open
        with pytest.raises(RemediationRefused, match="identity"):
            _precheck(rows, values={"container_id": None})(proposal, NOW)
    finally:
        store._db.close()


def test_the_precheck_refuses_a_capability_without_a_card(tmp_path):
    store, proposal = _approved(tmp_path, NOW)
    try:
        live = _precheck(Rows(store))
        live.cards = {}
        with pytest.raises(RemediationRefused, match="card"):
            live(proposal, NOW)
    finally:
        store._db.close()


def test_the_verification_samples_the_predicted_signal_and_the_detector(tmp_path, listener):
    client, _ = listener
    at = datetime.now(timezone.utc).replace(microsecond=0)
    store, proposal = _approved(tmp_path, at)
    try:
        rows = Rows(store, evidence_version="evidence-1")
        action = ActionExecutor(store, client, gate_open=frozenset({PAIR}), daily_host_cap=2).execute(
            "appr_live", _precheck(rows, observed_at=at)(proposal, at), at=at)
        asked = []

        def read_signal(signal, target):
            asked.append((signal, target))
            return "healthy", at + timedelta(seconds=5)

        sample = LiveVerification(rows=rows, read_signal=read_signal, detector_firing=lambda incident: True)(
            action["id"], at + timedelta(seconds=6))
        assert asked == [("dependency_probe_min", "vm-166/container:argus-lab-api")]
        assert (sample.signal, sample.target, sample.actual) == (
            "dependency_probe_min", "vm-166/container:argus-lab-api", "healthy")
        assert sample.detector_cleared is False
        assert LiveVerification(rows=rows, read_signal=lambda *_: None,
                                detector_firing=lambda incident: False)(action["id"], at) is None
    finally:
        store._db.close()


def test_a_status_observation_gives_its_values_and_measured_time():
    def obs(**changes):
        base = dict(observation_id="obs_1", status="ok", capability="container.status",
                    target=TargetRef.parse(TARGET), host="vm-166", executor="target", source_time=NOW,
                    collected_at=NOW + timedelta(seconds=1), values={"state": "exited", "container_id": FULL_ID},
                    model_text="state=exited")
        return Observation(**{**base, **changes})

    assert status_from_observation(obs()) == ({"state": "exited", "container_id": FULL_ID}, NOW)
    assert status_from_observation(obs(source_time=None))[1] == NOW + timedelta(seconds=1)
    for bad in (obs(status="error"), obs(capability="container.logs")):
        with pytest.raises(RemediationRefused):
            status_from_observation(bad)


def test_the_target_reports_the_full_container_id_the_gateway_compares(tmp_path, monkeypatch):
    from test_op005_young_restarts import _exporter

    service = _exporter(tmp_path, monkeypatch)
    monkeypatch.setattr(service, "djson", lambda path: {
        "Id": FULL_ID, "Created": "2026-10-09T07:57:00Z", "State": {"Status": "exited", "Running": False},
        "HostConfig": {}, "Config": {}})
    status = service.inspect("argus-lab-cache")
    assert status["container_id"] == FULL_ID          # the proxy's identity is Docker's full Id
    assert status["id"] == FULL_ID[:12]               # the short id stays for existing readers
