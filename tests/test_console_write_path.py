"""CON-6: console confirmation proposes through the supervised action path and never acts itself."""
from __future__ import annotations

from threading import Event
from types import SimpleNamespace

import pytest
from pwdlib import PasswordHash

from argus.actions.remediation import FakeActionGateway
from argus.adapters.inbound.http import ACTION_ROLE_PERMISSIONS
from argus.console.config import ConsoleConfig
from argus.console.service import ConsoleService
from argus.domain.model import AuditRecord, EvidenceRecord, IncidentOutcome, IncidentStatus, utcnow
from argus.infrastructure.action_wiring import CandidateProposer, ReviewContext
from argus.orchestration.action_path import OfflineActionPath
from test_console_routes import PRIVATE, login, setup, url
from test_core import incident, make_app as base_make_app  # noqa: F401
from test_phase18_remediation import GOOD_CHECKS
from test_phase19_private_login import _client as private_login_client, _login as private_login

CACHE = "vm-166/container:argus-lab-cache"
WORKER = "vm-166/container:argus-lab-jobworker"
API = "vm-166/container:argus-lab-api"
CLIENT = "vm-166/container:argus-lab-client"
PAIRS = {"cache.restart": ("container.start", CACHE), "worker.restart": ("container.restart", WORKER),
         "net.reconnect": ("network.restore", API)}
CASES = [
    pytest.param("cache restart", "cache.restart", API, "dependency_unavailable", CACHE, "RB-003", "exited",
                 {"container_id": "cache-id", "state": "exited"}, id="cache-start"),
    pytest.param("worker restart", "worker.restart", WORKER, "worker_stalled", WORKER, "RB-022", "running",
                 {"container_id": "worker-id", "state": "running"}, id="worker-restart"),
    pytest.param("net reconnect api", "net.reconnect", CLIENT, "dependency_unavailable", API, "RB-003", "running",
                 {"container_id": "api-id", "state": "running", "networks": ["argus-lab-iso"]},
                 id="api-network-restore"),
]


@pytest.fixture
def app_factory(request):
    return request.getfixturevalue("base_make_app")


def _path(app, *, root_target, live_values, pairs):
    status = {root_target: live_values}
    proposer = CandidateProposer(rows=app.store, inventory=app.inventory, cards=app.action_policy.cards,
                                 gate_open=frozenset(pairs),
                                 read_status=lambda _incident, target: (status[target], utcnow()),
                                 policy_version=app.policy.version)
    context = ReviewContext(rows=app.store, inventory=app.inventory, cards=app.action_policy.cards,
                            runbooks_dir=app.settings.runbooks_dir)
    fake_judge = SimpleNamespace(model="test-judge", last_usage={})

    def judge_model(_packet):
        fake_judge.last_usage = {"input_tokens": 7, "output_tokens": 3}
        return {"verdict": "agree", "checks": GOOD_CHECKS, "reasons": []}

    path = OfflineActionPath(rows=app.store, action_policy=app.action_policy, inventory=app.inventory,
                             proposer=proposer, judge_model=judge_model, judge_model_id="test-judge",
                             judge_context=context, snapshot=lambda *_: None, sample=lambda *_: None,
                             gateway=FakeActionGateway(), gate_open=frozenset(pairs), daily_host_cap=5)
    app.runner.action_path = path
    return path


def _case(factory, monkeypatch, text, command, incident_target, incident_class, root_target, runbook, state,
          live_values):
    app = factory()
    app.action_rows = app.store                         # mount the existing approval routes in this offline fixture
    inc = incident(app, incident_target)
    inc.status, inc.outcome = IncidentStatus.running, IncidentOutcome.diagnosed
    inc.incident_class, inc.root_cause_target = incident_class, root_target
    app.store.update_incident(inc)
    at = utcnow()
    status = dict(live_values)
    app.store.append_evidence(EvidenceRecord(
        evidence_id=f"ev_{command.replace('.', '_')}", incident_id=inc.id, kind="observation",
        capability="container.status", target=root_target, host="vm-166", executor="docker_read",
        caller="strategy:baseline", source_time=at, collected_at=at, status="ok", values={"values": status},
        model_text=f"state={state}").with_hash())
    app.store.append(AuditRecord(audit_id=f"recall_{inc.id}", incident_id=inc.id, at=at, category="tool",
                                 event="recall.passages", actor=None,
                                 detail={"passages": [{"runbook_id": runbook}]}))
    pair = PAIRS[command]
    live = {root_target: {**status}}
    path = _path(app, root_target=root_target, live_values=live[root_target], pairs=set(PAIRS.values()))
    client = setup(app, monkeypatch)
    monkeypatch.setattr(client.app.state.second_factor, "privileged_ready", lambda *_: True)
    monkeypatch.setattr(client.app.state.second_factor, "consume_step_up", lambda *_: None)
    app.store.upsert_principal("writer", "human", "approver", ["lab"],
                               PasswordHash.recommended().hash("a-long-password"))
    auth = login(client, "writer")
    return SimpleNamespace(app=app, incident=inc, client=client, auth=auth, pair=pair, path=path)


@pytest.mark.parametrize("text,command,incident_target,incident_class,root_target,runbook,state,live_values", CASES)
def test_each_write_requires_confirmation_then_reuses_one_normal_proposal(
        app_factory, monkeypatch, text, command, incident_target, incident_class, root_target, runbook, state,
        live_values):
    case = _case(app_factory, monkeypatch, text, command, incident_target, incident_class, root_target, runbook, state,
                 live_values)
    first = case.client.post(url(case.incident, "execute"), headers={**case.auth, **PRIVATE},
                             json={"input": text}).json()
    assert first["status"] == "needs_confirmation" and "approver" in first["output"][0]
    assert case.app.store.latest_action_proposal_for_incident(case.incident.id) is None
    assert case.path.executor.gateway.calls == []

    second = case.client.post(url(case.incident, "execute"), headers={**case.auth, **PRIVATE},
                              json={"input": text, "confirmation": "yes"}).json()
    assert second["status"] == "ok" and second["proposal_id"] and second["approval_id"]
    assert second["judge_verdict"] == "agree" and any("judge: agree (" in line for line in second["output"])
    assert any(f"/api/v1/ops/approvals/{second['approval_id']}" in line for line in second["output"])
    proposal = case.app.store.get_action_proposal(second["proposal_id"])
    assert (proposal.input.capability, proposal.input.target) == case.pair
    assert case.app.store.get_action_approval_for_proposal(proposal.id)["state"] == "pending"
    if command == "net.reconnect":
        assert proposal.input.arguments == {"connect_network": "argus-lab-app", "disconnect_network": "argus-lab-iso"}
    assert case.path.executor.gateway.calls == []              # the approval worker, not the console, dispatches

    third = case.client.post(url(case.incident, "execute"), headers={**case.auth, **PRIVATE},
                             json={"input": text, "confirmation": "yes"}).json()
    assert (third["proposal_id"], third["approval_id"], third["judge_verdict"]) == (
        second["proposal_id"], second["approval_id"], "agree")
    assert case.app.store._q("SELECT COUNT(*) FROM action_proposal WHERE incident_id=?", (case.incident.id,))[0][0] == 1


def test_console_audit_links_both_people_to_the_approval(app_factory, monkeypatch):
    case = _case(app_factory, monkeypatch, *CASES[0].values)

    # The command's author and approver are distinct personal sessions.
    case.app.store.upsert_principal("vera", "human", "approver", ["lab"],
                                    PasswordHash.recommended().hash("a-long-password"))
    proposal_response = case.client.post(url(case.incident, "execute"), headers={**case.auth, **PRIVATE},
                                         json={"input": "cache restart", "confirmation": "yes"}).json()
    approval_id = proposal_response["approval_id"]
    proposal = case.app.store.get_action_proposal(proposal_response["proposal_id"])
    approver = login(case.client, "vera")
    answered = case.client.post(f"/api/v1/ops/approvals/{approval_id}/answer", headers={**approver, **PRIVATE},
                                json={"decision": "approved", "proposal_digest": proposal.digest,
                                      "step_up_token": "offline-step-up"})
    assert answered.status_code == 200, answered.text
    row = next(a for a in case.app.store.list_for(case.incident.id) if a.event == "action.approval_answered")
    assert row.detail["source"] == "operator_console"
    assert row.detail["command_id"] == proposal_response["command_id"]
    assert row.detail["proposal_id"] == proposal.id
    assert row.detail["proposed_by"] == "writer" and row.detail["approved_by"] == "vera"


def test_running_cache_is_rejected_and_the_other_released_pair_is_never_proposed(app_factory, monkeypatch):
    case = _case(app_factory, monkeypatch, "cache restart", "cache.restart", API, "dependency_unavailable", CACHE,
                 "RB-003", "running", {"container_id": "cache-id", "state": "running"})
    result = case.client.post(url(case.incident, "execute"), headers={**case.auth, **PRIVATE},
                              json={"input": "cache restart", "confirmation": "yes"}).json()
    assert result["status"] == "rejected" and "restart on the cache is not released" in result["output"][0]
    assert case.app.store.latest_action_proposal_for_incident(case.incident.id) is None


def test_write_without_propose_action_is_refused_and_stored_in_history(app_factory, monkeypatch):
    app = app_factory()
    app.action_rows = app.store
    client = setup(app, monkeypatch)
    response = client.post(url("inc_not_needed", "execute"), headers={**login(client), **PRIVATE},
                          json={"input": "cache restart"})
    assert response.status_code == 404       # incident lookup occurs before command authorization
    inc = incident(app, API)
    response = client.post(url(inc, "execute"), headers={**login(client), **PRIVATE},
                           json={"input": "cache restart"})
    assert response.status_code == 403 and "needs propose_action" in response.json()["detail"]
    [history] = app.store.console_history(inc.id)
    assert (history["input"], history["command"], history["cls"], history["status"]) == (
        "cache restart", "cache.restart", "write", "rejected")
    assert "needs propose_action" in history["output"]
    assert app.store.latest_action_proposal_for_incident(inc.id) is None
    audit = [row for row in app.store.list_for(inc.id) if row.event in ("console.write.before", "console.write.after")]
    assert [row.event for row in audit] == ["console.write.before", "console.write.after"]
    assert audit[0].actor == audit[1].actor == "olga"
    assert audit[0].detail["command_id"] == audit[1].detail["command_id"]
    assert all(row.detail["source"] == "operator_console" and row.detail["proposal_id"] is None for row in audit)


def test_operator_cannot_get_a_private_approver_login(app_factory, monkeypatch):
    _api, client = private_login_client(app_factory(), monkeypatch)
    assert "propose_action" not in ACTION_ROLE_PERMISSIONS.get("operator", frozenset())
    assert private_login(client, "olga").status_code == 401


def test_closed_incident_refuses_writes_but_still_allows_reads(app_factory, monkeypatch):
    case = _case(app_factory, monkeypatch, "cache restart", "cache.restart", API, "dependency_unavailable", CACHE,
                 "RB-003", "exited", {"container_id": "cache-id", "state": "exited"})
    case.incident.status = IncidentStatus.closed
    case.app.store.update_incident(case.incident)
    case.app.runner.invoke = lambda *_args, **_kwargs: (SimpleNamespace(
        status="ok", model_text="cache state", values={"state": "exited", "health": "none"},
        error_category=None), None)
    write = case.client.post(url(case.incident, "execute"), headers={**case.auth, **PRIVATE},
                             json={"input": "cache restart", "confirmation": "yes"})
    read = case.client.post(url(case.incident, "execute"), headers={**case.auth, **PRIVATE},
                            json={"input": "cache status"})
    assert write.json()["status"] == "rejected" and "closed incident" in write.json()["output"][0]
    assert read.status_code == 200 and read.json()["status"] == "ok"
    assert case.app.store.latest_action_proposal_for_incident(case.incident.id) is None


@pytest.mark.parametrize("text", ["cache restart; worker restart", "worker restart cache", "net reconnect api cache"])
def test_crafted_write_text_cannot_select_another_pair(app_factory, monkeypatch, text):
    case = _case(app_factory, monkeypatch, "worker restart", "worker.restart", WORKER, "worker_stalled", WORKER,
                 "RB-022", "running", {"container_id": "worker-id", "state": "running"})
    response = case.client.post(url(case.incident, "execute"), headers={**case.auth, **PRIVATE},
                                json={"input": text, "confirmation": "yes"})
    assert response.json()["status"] == "rejected"
    assert case.app.store.latest_action_proposal_for_incident(case.incident.id) is None
    assert case.path.executor.gateway.calls == []


def test_pair_not_in_write_gate_cannot_be_reached_by_a_console_command(app_factory, monkeypatch):
    case = _case(app_factory, monkeypatch, "cache restart", "cache.restart", API, "dependency_unavailable", CACHE,
                 "RB-003", "exited", {"container_id": "cache-id", "state": "exited"})
    case.path.executor.gate_open = frozenset({("container.restart", CACHE)})
    response = case.client.post(url(case.incident, "execute"), headers={**case.auth, **PRIVATE},
                                json={"input": "cache restart", "confirmation": "yes"})
    assert response.json()["status"] == "rejected" and "not released in write_gate.open" in response.json()["output"][0]
    assert case.app.store.latest_action_proposal_for_incident(case.incident.id) is None


def test_confirmation_accepts_only_yes_and_never_approves(app_factory, monkeypatch):
    case = _case(app_factory, monkeypatch, "cache restart", "cache.restart", API, "dependency_unavailable", CACHE,
                 "RB-003", "exited", {"container_id": "cache-id", "state": "exited"})
    invalid = case.client.post(url(case.incident, "execute"), headers={**case.auth, **PRIVATE},
                               json={"input": "cache restart", "confirmation": "approved"})
    assert invalid.status_code == 422
    prompt = case.client.post(url(case.incident, "execute"), headers={**case.auth, **PRIVATE},
                              json={"input": "cache restart"}).json()
    confirmed = case.client.post(url(case.incident, "execute"), headers={**case.auth, **PRIVATE},
                                 json={"input": "cache restart", "confirmation": "yes"}).json()
    assert prompt["status"] == "needs_confirmation"
    assert confirmed["status"] == "ok" and case.app.store.get_action_approval_for_proposal(
        confirmed["proposal_id"])["state"] == "pending"
    assert case.path.executor.gateway.calls == []


def test_write_keeps_the_inserted_suggestion_id_in_history(app_factory, monkeypatch):
    case = _case(app_factory, monkeypatch, "cache restart", "cache.restart", API, "dependency_unavailable", CACHE,
                 "RB-003", "exited", {"container_id": "cache-id", "state": "exited"})
    case.app.runner.invoke = lambda *_args, **_kwargs: (SimpleNamespace(
        status="ok", model_text="cache state", values={"state": "exited", "health": "none"},
        error_category=None), None)
    read = case.client.post(url(case.incident, "execute"), headers={**case.auth, **PRIVATE},
                            json={"input": "cache status"})
    assert read.status_code == 200
    prompt = case.client.post(url(case.incident, "execute"), headers={**case.auth, **PRIVATE},
                              json={"input": "cache restart"})
    assert prompt.json()["status"] == "needs_confirmation"
    confirmed = case.client.post(url(case.incident, "execute"), headers={**case.auth, **PRIVATE},
                                 json={"input": "cache restart", "confirmation": "yes",
                                       "suggestion_id": "suggestion-cache-restart"})
    assert confirmed.status_code == 200
    rows = case.app.store.console_history(case.incident.id)
    assert [row["command"] for row in rows] == ["cache.status", "cache.restart", "cache.restart"]
    assert rows[-1]["suggestion_id"] == "suggestion-cache-restart"


def test_slow_write_judge_does_not_block_a_read_on_the_same_incident(app_factory, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    case = _case(app_factory, monkeypatch, "cache restart", "cache.restart", API, "dependency_unavailable", CACHE,
                 "RB-003", "exited", {"container_id": "cache-id", "state": "exited"})
    case.app.runner.invoke = lambda *_args, **_kwargs: (SimpleNamespace(
        status="ok", model_text="cache state", values={"state": "exited", "health": "none"},
        error_category=None), None)
    service = ConsoleService(case.app, ConsoleConfig())
    judge_started, release_judge = Event(), Event()
    original_judge = case.path.judge

    def slow_judge(proposal_id):
        judge_started.set()
        if not release_judge.wait(5):
            raise TimeoutError("test judge release timed out")
        return original_judge(proposal_id)

    case.path.judge = slow_judge
    writer = SimpleNamespace(id="writer", kind="human")
    reader = SimpleNamespace(id="reader", kind="human")
    with ThreadPoolExecutor(max_workers=2) as pool:
        write_future = pool.submit(service.run, writer, case.incident, "cache restart", None, "yes",
                                   granted=frozenset({"propose_action"}),
                                   role_grants=frozenset({"propose_action"}))
        try:
            assert judge_started.wait(3), "write did not reach the slow judge"
            read_future = pool.submit(service.run, reader, case.incident, "cache status")
            result = read_future.result(timeout=2)
            assert result.status == "ok"
        finally:
            release_judge.set()
        assert write_future.result(timeout=5).status == "ok"
