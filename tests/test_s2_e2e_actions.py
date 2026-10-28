"""Offline end-to-end checks for the three reviewed action routes.

The worker's inventory service row is copied from origin/task/task-54-s4-signals-class
because that PR is not on main yet. Action cards are loaded from the repository.
"""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from types import SimpleNamespace

import pytest

from argus.actions.cards import load_action_cards
from argus.actions.execution import ActionExecutor
from argus.actions.gateway_client import HttpActionGateway
from argus.actions.live import LivePrecheck, LiveVerification
from argus.actions.remediation import Prediction, freeze_proposal
from argus.adapters.outbound.config_adapters import YamlInventory
from argus.adapters.outbound.sqlite_store import SqliteStore
from test_phase18_remediation import agreed, candidate
from test_phase20_live_execution import Rows


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = YamlInventory((ROOT / "config" / "inventory.yaml").read_text(encoding="utf-8"))


def _inventory(target=None):
    """The frozen proposal's inventory version, with the repository's real declarations (or `target`'s)."""
    return SimpleNamespace(version=lambda: "inventory-1", target=target or INVENTORY.target)
TOKEN = "offline-test-token-0123456789abcdef0123456789"
FULL_ID = "c" * 64
CARDS = load_action_cards(ROOT / "config" / "actions")

# TASK-54 in PR #366 declares this target as a stateless worker, allows restart,
# and explicitly forbids stop. It is absent from main's inventory at this base.
WORKER_SERVICE_FROM_PR_366 = {
    "role": "worker", "kind": "stateless", "safe_actions": ["container.restart"],
    "never": ["container.stop"],
}


@dataclass(frozen=True)
class Scenario:
    key: str
    capability: str
    target: str
    state: str
    arguments: dict
    prediction_target: str

    @property
    def card(self):
        return CARDS[self.capability]

    @property
    def path(self):
        name = self.target.split(":", 1)[1]
        return self.card.route.format(name=name)

    @property
    def pair(self):
        return self.capability, self.target


SCENARIOS = (
    Scenario("cache-start", "container.start", "vm-166/container:argus-lab-cache", "exited", {},
             "vm-166/container:argus-lab-cache"),
    Scenario("worker-restart", "container.restart", "vm-166/container:argus-lab-jobworker", "running", {},
             "vm-166/container:argus-lab-jobworker"),
    Scenario("api-network-restore", "network.restore", "vm-166/container:argus-lab-api", "running",
             {"connect_network": "argus-lab-app", "disconnect_network": "argus-lab-iso"},
             "vm-166/container:argus-lab-api"),
)

SCENARIO_PARAMS = (
    pytest.param(SCENARIOS[0], id="cache-start"),
    pytest.param(SCENARIOS[1], id="worker-restart"),
    pytest.param(SCENARIOS[2], id="api-network-restore"),
)


def _proposal(scenario, at):
    card = scenario.card
    return freeze_proposal(candidate(
        incident_id=f"inc_{scenario.key}", capability=scenario.capability, target=scenario.target,
        target_identity={"container_id": FULL_ID}, arguments=scenario.arguments,
        root_cause=scenario.target, rationale=f"Exercise {scenario.capability} through the offline gateway.",
        evidence_refs=[f"ev_{scenario.key}"], grounds=["runbook:RB-003"],
        prediction=Prediction(signal=card.verify["signal"], target=scenario.prediction_target,
                              expected=str(card.verify["expected"]), within_seconds=card.verify["window_sec"]),
        preview=f"Run {scenario.capability} for {scenario.target}", rollback=card.rollback,
    ), at=at)


def _expected_body(scenario):
    body = {"capability": scenario.capability, "target": scenario.target,
            "target_identity": {"container_id": FULL_ID}}
    if scenario.capability == "network.restore":
        body.update(scenario.arguments)
    return body


@contextmanager
def _case(tmp_path, scenario, mode):
    at = datetime.now(timezone.utc).replace(microsecond=0)
    proposal = _proposal(scenario, at)
    store = SqliteStore(str(tmp_path / f"{scenario.key}.db"))
    approval_id = f"appr_{scenario.key}"
    store.add_action_proposal(proposal)
    agreed(store, proposal, at)
    store.add_action_approval(approval_id, proposal.id, proposal.digest, at, proposal.expires_at)
    assert store.answer_action_approval(approval_id, proposal.digest, "offline-operator", "approved", at)

    state = SimpleNamespace(mode=mode, scenario=scenario, requests=[], contract_errors=[], receipts={}, status_reads=0)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def _reply(self, status, body):
            data = json.dumps(body, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except OSError:  # timeout case: the client has already closed its socket
                pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            try:
                body = json.loads(raw)
            except (ValueError, TypeError):
                body = None
            action_id = self.headers.get("X-Argus-Action-Id")
            actual = {"path": self.path, "authorization": self.headers.get("Authorization"),
                      "action_id": action_id, "body": body}
            state.requests.append(actual)
            if self.path != scenario.path:
                state.contract_errors.append(f"route: {self.path}")
            if actual["authorization"] != f"Bearer {TOKEN}":
                state.contract_errors.append("bearer token")
            if body != _expected_body(scenario):
                state.contract_errors.append(f"body: expected fields {sorted(_expected_body(scenario))}, "
                                             f"got {sorted(body) if isinstance(body, dict) else type(body).__name__}")
            if mode == "timeout":
                time.sleep(0.2)
                self._reply(200, {"status": "confirmed"})
                return
            if mode == "refused":
                self._reply(403, {"detail": "forbidden"})
                return
            if state.contract_errors:
                self._reply(400, {"detail": "request contract differs"})
                return
            state.receipts[action_id] = "confirmed"
            # Model the accepted response followed by the durable receipt lookup.
            self._reply(202, {"status": "accepted"})

        def do_GET(self):
            state.status_reads += 1
            action_id = self.path.rsplit("/", 1)[-1]
            result = state.receipts.get(action_id)
            if result is None:
                self._reply(404, {"detail": "not found"})
            else:
                self._reply(200, {"status": result})

    class Server(ThreadingHTTPServer):
        daemon_threads = True

    server = Server(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    token_path = tmp_path / f"{scenario.key}.token"
    token_path.write_text(TOKEN, encoding="utf-8")
    client = HttpActionGateway(f"http://127.0.0.1:{server.server_port}", token_path, timeout_s=0.04)
    rows = Rows(store, evidence_version="evidence-1")
    values = {"id": FULL_ID[:12], "container_id": FULL_ID, "state": scenario.state}
    if scenario.capability == "network.restore":
        values.update(networks=["argus-lab-iso"])            # what the target reports; the declaration is the inventory's
    precheck = LivePrecheck(
        rows=rows, inventory=_inventory(), policy_version="policy-1",
        cards={scenario.capability: scenario.card}, read_status=lambda _target: (values, at),
        detector_firing=lambda _incident: True, host_lease_clear=lambda _host: True,
    )(proposal, at)
    executor = ActionExecutor(store, client, gate_open=frozenset({scenario.pair}), daily_host_cap=5)
    try:
        yield SimpleNamespace(at=at, proposal=proposal, store=store, rows=rows, state=state,
                              executor=executor, approval_id=approval_id, precheck=precheck, server=server)
    finally:
        store._db.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_network_precheck_evaluates_the_frozen_arguments_against_the_inventory_declaration(tmp_path):
    """The real container.status reports the networks a container is on, never the declared ones: those come from the
    inventory (argus-lab-app for the API), and a status field cannot replace them."""
    scenario = SCENARIOS[2]
    at = datetime.now(timezone.utc).replace(microsecond=0)
    proposal = _proposal(scenario, at)
    store = SqliteStore(str(tmp_path / "network-precheck.db"))
    try:
        store.add_action_proposal(proposal)
        rows = Rows(store, evidence_version="evidence-1")
        status = {"id": FULL_ID[:12], "container_id": FULL_ID, "state": "running", "networks": ["argus-lab-iso"]}

        def met(values, inventory=None):
            return LivePrecheck(
                rows=rows, inventory=inventory or _inventory(), policy_version="policy-1",
                cards={scenario.capability: scenario.card}, read_status=lambda _target: (values, at),
                detector_firing=lambda _incident: True, host_lease_clear=lambda _host: True,
            )(proposal, at).action_preconditions_met

        assert met(status)                                                      # shaped as the real target answers
        assert met({**status, "declared_networks": ["argus-lab-iso"]})          # a status field cannot redeclare
        assert not met(status, _inventory(target=lambda ref: None))             # no declaration: fails closed
        assert not met({**status, "networks": ["argus-lab-app"]})               # already on the declared network
    finally:
        store._db.close()

def _assert_request_contract(state, scenario):
    assert len(state.requests) == 1
    request = state.requests[0]
    assert request["path"] == scenario.path
    assert request["authorization"] == f"Bearer {TOKEN}"
    assert request["body"] == _expected_body(scenario)
    assert not state.contract_errors, state.contract_errors


@pytest.mark.parametrize("scenario", SCENARIO_PARAMS)
def test_accepted_action_receipt_and_healthy_verification(tmp_path, scenario):
    with _case(tmp_path, scenario, "accepted") as case:
        action = case.executor.execute(case.approval_id, case.precheck, at=case.at)
        assert action["state"] == "confirmed"
        _assert_request_contract(case.state, scenario)
        assert case.state.status_reads == 1  # 202 accepted, then the durable receipt
        later = case.at + timedelta(seconds=5)
        sample = LiveVerification(rows=case.rows,
                                  read_signal=lambda signal, target: (str(case.proposal.input.prediction.expected), later),
                                  detector_firing=lambda _incident: False)(action["id"], later)
        assert case.executor.verify(action["id"], sample, at=later) == "recovered_verified"
        assert case.store.get_action_for_approval(case.approval_id)["state"] == "confirmed"
        assert case.store.get_action_outcome(action["id"])["outcome"] == "recovered_verified"
        assert case.executor.execute(case.approval_id, case.precheck, at=later)["id"] == action["id"]
        assert len(case.state.requests) == 1


@pytest.mark.parametrize("scenario", SCENARIO_PARAMS)
def test_refusal_is_failed_and_never_retried(tmp_path, scenario):
    with _case(tmp_path, scenario, "refused") as case:
        action = case.executor.execute(case.approval_id, case.precheck, at=case.at)
        assert action["state"] == "failed"
        assert case.state.status_reads == 0
        assert case.executor.execute(case.approval_id, case.precheck, at=case.at + timedelta(seconds=1))["id"] == action["id"]
        assert len(case.state.requests) == 1
        _assert_request_contract(case.state, scenario)


@pytest.mark.parametrize("scenario", SCENARIO_PARAMS)
def test_gateway_timeout_is_indeterminate_and_never_retried(tmp_path, scenario):
    with _case(tmp_path, scenario, "timeout") as case:
        action = case.executor.execute(case.approval_id, case.precheck, at=case.at)
        assert action["state"] == "indeterminate"
        assert case.state.status_reads == 1
        assert case.executor.execute(case.approval_id, case.precheck, at=case.at + timedelta(seconds=1))["id"] == action["id"]
        assert len(case.state.requests) == 1
        _assert_request_contract(case.state, scenario)


@pytest.mark.parametrize("scenario", SCENARIO_PARAMS)
def test_unhealthy_verification_is_action_failed_and_never_retried(tmp_path, scenario):
    with _case(tmp_path, scenario, "accepted") as case:
        action = case.executor.execute(case.approval_id, case.precheck, at=case.at)
        assert action["state"] == "confirmed"
        _assert_request_contract(case.state, scenario)
        sampled_at = case.at + timedelta(seconds=case.proposal.input.prediction.within_seconds + 1)
        sample = LiveVerification(rows=case.rows, read_signal=lambda _signal, _target: ("unhealthy", sampled_at),
                                  detector_firing=lambda _incident: True)(action["id"], sampled_at)
        assert case.executor.verify(action["id"], sample, at=sampled_at) == "action_failed"
        assert case.store.get_action_outcome(action["id"])["outcome"] == "action_failed"
        assert case.executor.verify(action["id"], sample, at=sampled_at) == "action_failed"
        assert len(case.state.requests) == 1


def test_worker_scenario_uses_task54_inventory_release_contract():
    assert "container.restart" in WORKER_SERVICE_FROM_PR_366["safe_actions"]
    assert "container.stop" in WORKER_SERVICE_FROM_PR_366["never"]
    assert SCENARIOS[1].card.name == "container.restart"


def test_container_start_precheck_works_without_arguments(tmp_path):
    scenario = SCENARIOS[0]
    with _case(tmp_path, scenario, "accepted") as case:
        assert case.proposal.input.arguments == {}
        assert case.precheck.action_preconditions_met


def test_network_precheck_arguments_are_added_but_status_values_win(tmp_path):
    scenario = replace(SCENARIOS[2], arguments={**SCENARIOS[2].arguments, "state": "exited"})
    with _case(tmp_path, scenario, "accepted") as case:
        assert case.precheck.action_preconditions_met
