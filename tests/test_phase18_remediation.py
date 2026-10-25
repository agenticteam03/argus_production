"""Phase 18: the supervised action path is safe before a real gateway exists."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from argus.actions.remediation import (
    Alternative, FakeActionGateway, JudgeResult, Prediction, ProposalInput,
    RemediationFlow, RemediationRefused, freeze_proposal, judge_proposal,
)
from argus.actions.execution import ActionExecutor, Precheck, Verification
from argus.adapters.outbound.judge import OpenAIJudge
from argus.orchestration.action_recovery import OfflineActionRecovery
from argus.orchestration.action_path import OfflineActionPath


NOW = datetime(2026, 10, 25, tzinfo=timezone.utc)
TARGET = "vm-166/container:argus-lab-cache"
JUDGE_CONTEXT = {"evidence_extracts": {"ev_cache_exited": "state=exited"},
                 "ground_extracts": {"runbook:RB-003": "Start the stopped cache to restore the dependency."},
                 "service_card": {"safe_actions": ["container.start"]},
                 "action_card": {"name": "container.start"}}
GOOD_CHECKS = {"cause_supported": True, "action_addresses_cause": True, "grounds_support_action": True,
               "less_invasive_exists": False, "risk_understated": False}


def candidate(**changes) -> ProposalInput:
    data = dict(
        incident_id="inc_sc03", capability="container.start", target=TARGET,
        target_identity={"container_id": "cache-1"}, arguments={}, root_cause=TARGET,
        rationale="The cache exited; starting its existing container restores the dependency.",
        evidence_refs=["ev_cache_exited"], grounds=["runbook:RB-003"],
        prediction=Prediction(signal="dependency_probe_min", target="vm-166/container:argus-lab-api",
                              expected="healthy", within_seconds=120),
        alternatives=[Alternative(action="wait", why_not="The dependency remains unavailable.")],
        preview="Start existing cache container", rollback="container.stop",
        inventory_version="inventory-1", policy_version="policy-1", evidence_version="evidence-1",
    )
    data.update(changes)
    return ProposalInput(**data)


def test_freeze_binds_every_executable_field_and_refuses_missing_grounds():
    original = freeze_proposal(candidate(), at=NOW)
    assert original.digest == freeze_proposal(candidate(), at=NOW).digest
    assert original.digest != freeze_proposal(candidate(preview="Different preview"), at=NOW).digest
    assert original.digest != freeze_proposal(candidate(arguments={"force": True}), at=NOW).digest
    assert original.digest != freeze_proposal(candidate(target_identity={"container_id": "cache-2"}), at=NOW).digest
    with pytest.raises(RemediationRefused, match="grounds"):
        freeze_proposal(candidate(grounds=[]), at=NOW)
    with pytest.raises(RemediationRefused, match="vm-095"):
        freeze_proposal(candidate(target="vm-095/container:argus-lab-cache"), at=NOW)


def test_judge_is_read_only_fail_closed_and_cannot_lower_risk():
    proposal = freeze_proposal(candidate(), at=NOW)
    seen = []

    def model(packet):
        seen.append(packet)
        return {"verdict": "disagree", "checks": {**GOOD_CHECKS, "risk_understated": True},
                "reasons": ["The cache may have active clients."]}

    result = judge_proposal(proposal, model, initial_risk="green", **JUDGE_CONTEXT)
    assert result.verdict == "disagree" and result.risk == "amber"
    assert len(seen) == 1 and "conversation" not in seen[0]
    assert "dispatch" not in seen[0]
    assert judge_proposal(proposal, lambda _: {"verdict": "agree", "checks": GOOD_CHECKS, "reasons": []},
                          initial_risk="red", **JUDGE_CONTEXT).risk == "red"
    assert judge_proposal(proposal, lambda _: {"verdict": "approve"}, initial_risk="green",
                          **JUDGE_CONTEXT).verdict == "doubt"
    assert judge_proposal(proposal, lambda _: (_ for _ in ()).throw(TimeoutError()),
                          initial_risk="green", **JUDGE_CONTEXT).verdict == "doubt"
    assert judge_proposal(proposal, lambda _: {"verdict": "agree", "checks": GOOD_CHECKS, "reasons": [],
                                             "dispatch": "now"}, initial_risk="green",
                          **JUDGE_CONTEXT).verdict == "doubt"
    assert judge_proposal(proposal, lambda _: {"verdict": "agree",
                                             "checks": {**GOOD_CHECKS, "cause_supported": False}, "reasons": []},
                          initial_risk="green", **JUDGE_CONTEXT).verdict == "doubt"


def test_second_model_adapter_has_no_tools_or_decider_conversation():
    captured = []

    def reply(**payload):
        captured.append(payload)
        return SimpleNamespace(status="completed", output=[],
                               output_text='{"verdict":"agree","checks":{},"reasons":[]}',
                               usage=SimpleNamespace(input_tokens=100, output_tokens=20))

    client = SimpleNamespace(responses=SimpleNamespace(create=reply))
    judge = OpenAIJudge("", "gpt-6.1-sol", deciding_model="gpt-5.6-luna", client=client)
    assert judge({"proposal_digest": "test"})["verdict"] == "agree"
    assert judge.last_usage == {"input_tokens": 100, "output_tokens": 20}
    assert "tools" not in captured[0] and "previous_response_id" not in captured[0]
    assert set(captured[0]["input"][0]) == {"role", "content"}
    with pytest.raises(ValueError, match="different model"):
        OpenAIJudge("", "gpt-6.1-sol", deciding_model="gpt-6.1-sol", client=client)


def test_mutating_nested_proposal_after_freeze_refuses_approval():
    proposal = freeze_proposal(candidate(), at=NOW)
    proposal.input.arguments["force"] = True
    flow = RemediationFlow(gateway=FakeActionGateway(), gate_open={("container.start", TARGET)})
    with pytest.raises(RemediationRefused, match="digest"):
        flow.request_approval(proposal, JudgeResult.agree(proposal.digest), at=NOW)


def test_closed_gate_never_creates_an_approval_or_dispatches():
    gateway = FakeActionGateway()
    flow = RemediationFlow(gateway=gateway, gate_open=frozenset())
    proposal = freeze_proposal(candidate(), at=NOW)
    with pytest.raises(RemediationRefused, match="write gate"):
        flow.request_approval(proposal, JudgeResult.agree(proposal.digest), at=NOW)
    assert flow.approvals == {} and gateway.calls == []


def test_approval_is_digest_bound_human_only_single_use_and_expires():
    flow = RemediationFlow(gateway=FakeActionGateway(), gate_open={("container.start", TARGET)})
    proposal = freeze_proposal(candidate(), at=NOW)
    approval = flow.request_approval(proposal, JudgeResult.agree(proposal.digest), at=NOW)
    with pytest.raises(RemediationRefused, match="digest"):
        flow.answer(approval.id, digest="bad", principal="operator", principal_kind="human", at=NOW)
    with pytest.raises(RemediationRefused, match="human"):
        flow.answer(approval.id, digest=proposal.digest, principal="bot", principal_kind="agent", at=NOW)
    flow.answer(approval.id, digest=proposal.digest, principal="operator", principal_kind="human", at=NOW)
    with pytest.raises(RemediationRefused, match="pending"):
        flow.answer(approval.id, digest=proposal.digest, principal="operator", principal_kind="human", at=NOW)
    later = flow.request_approval(proposal, JudgeResult.agree(proposal.digest), at=NOW)
    with pytest.raises(RemediationRefused, match="expired"):
        flow.answer(later.id, digest=proposal.digest, principal="operator", principal_kind="human",
                    at=NOW + timedelta(minutes=31))


def test_precheck_rejects_changed_identity_evidence_and_holds():
    gateway = FakeActionGateway()
    flow = RemediationFlow(gateway=gateway, gate_open={("container.start", TARGET)})
    proposal = freeze_proposal(candidate(), at=NOW)
    approval = flow.request_approval(proposal, JudgeResult.agree(proposal.digest), at=NOW)
    flow.answer(approval.id, digest=proposal.digest, principal="operator", principal_kind="human", at=NOW)
    with pytest.raises(RemediationRefused, match="identity"):
        flow.execute(approval.id, at=NOW, identity={"container_id": "cache-2"},
                     inventory_version="inventory-1", policy_version="policy-1",
                     evidence_version="evidence-1", incident_open=True)
    assert gateway.calls == []
    with pytest.raises(RemediationRefused, match="evidence"):
        flow.execute(approval.id, at=NOW, identity={"container_id": "cache-1"},
                     inventory_version="inventory-1", policy_version="policy-1",
                     evidence_version="evidence-2", incident_open=True)
    flow.hold(TARGET)
    with pytest.raises(RemediationRefused, match="hold"):
        flow.execute(approval.id, at=NOW, identity={"container_id": "cache-1"},
                     inventory_version="inventory-1", policy_version="policy-1",
                     evidence_version="evidence-1", incident_open=True)
    assert gateway.calls == []


def test_fake_gateway_dispatch_once_and_ambiguous_response_does_not_retry():
    gateway = FakeActionGateway(ambiguous=True)
    flow = RemediationFlow(gateway=gateway, gate_open={("container.start", TARGET)})
    proposal = freeze_proposal(candidate(), at=NOW)
    approval = flow.request_approval(proposal, JudgeResult.agree(proposal.digest), at=NOW)
    flow.answer(approval.id, digest=proposal.digest, principal="operator", principal_kind="human", at=NOW)
    kw = dict(at=NOW, identity={"container_id": "cache-1"}, inventory_version="inventory-1",
              policy_version="policy-1", evidence_version="evidence-1", incident_open=True)
    assert flow.execute(approval.id, **kw) == "indeterminate"
    assert len(gateway.calls) == 1
    with pytest.raises(RemediationRefused, match="already attempted"):
        flow.execute(approval.id, **kw)
    assert len(gateway.calls) == 1


def test_sqlite_proposal_and_approval_survive_reopen_and_answer_once(tmp_path):
    from argus.adapters.outbound.sqlite_store import SqliteStore

    path = str(tmp_path / "phase18.db")
    proposal = freeze_proposal(candidate(), at=NOW)
    store = SqliteStore(path)
    store.add_action_proposal(proposal)
    store.add_action_approval("appr_test", proposal.id, proposal.digest, NOW, proposal.expires_at)
    store._db.close()
    reopened = SqliteStore(path)
    try:
        assert reopened.get_action_proposal(proposal.id).digest == proposal.digest
        assert reopened.answer_action_approval("appr_test", proposal.digest, "operator", "approved", NOW)
        assert not reopened.answer_action_approval("appr_test", proposal.digest, "operator", "approved", NOW)
        assert reopened.get_action_approval("appr_test")["state"] == "approved"
        assert reopened.get_resume_intent("appr_test")["decision"] == "approved"
        reopened.add_target_hold("hold_test", TARGET, "review", "operator", NOW)
        assert reopened.active_target_holds(TARGET, NOW) == ["hold_test"]
        assert reopened.release_target_hold("hold_test", "operator", NOW)
        assert not reopened.release_target_hold("hold_test", "operator", NOW)
        assert reopened.active_target_holds(TARGET, NOW) == []
        reopened.add_action("act_test", proposal.id, "appr_test")
        assert reopened.start_action("act_test", NOW)
        assert not reopened.start_action("act_test", NOW)
        assert reopened.finish_action("act_test", "confirmed", NOW, {"gateway": "confirmed"})
        assert not reopened.finish_action("act_test", "failed", NOW, {})
        assert reopened.get_action("act_test")["state"] == "confirmed"
        reopened.add_action_outcome("act_test", proposal.input.incident_id, "lab", "recovered_verified",
                                    {"prediction_met": True}, NOW)
        with pytest.raises(Exception, match="insert-only"):
            reopened._db.execute("UPDATE action_outcome SET origin='production' WHERE action_id='act_test'")
    finally:
        reopened._db.close()


def _durable_setup(tmp_path, *, gateway=None):
    from argus.adapters.outbound.sqlite_store import SqliteStore

    store = SqliteStore(str(tmp_path / "action.db"))
    proposal = freeze_proposal(candidate(), at=NOW)
    store.add_action_proposal(proposal)
    store.add_action_approval("appr_durable", proposal.id, proposal.digest, NOW, proposal.expires_at)
    assert store.answer_action_approval("appr_durable", proposal.digest, "operator", "approved", NOW)
    gateway = gateway or FakeActionGateway()
    executor = ActionExecutor(store, gateway, gate_open=frozenset({("container.start", TARGET)}), daily_host_cap=2)
    check = Precheck({"container_id": "cache-1"}, "inventory-1", "policy-1", "evidence-1", NOW,
                     True, True, True, True)
    return store, gateway, executor, check


def test_durable_executor_claims_before_dispatch_and_verifies_newer_sample(tmp_path):
    store, gateway, executor, check = _durable_setup(tmp_path)
    try:
        action = executor.execute("appr_durable", check, at=NOW)
        assert action["state"] == "confirmed" and gateway.calls == [action["id"]]
        assert executor.execute("appr_durable", check, at=NOW)["id"] == action["id"]
        assert len(gateway.calls) == 1
        old = Verification(NOW, True, "dependency_probe_min", "vm-166/container:argus-lab-api", "healthy")
        with pytest.raises(RemediationRefused, match="predates"):
            executor.verify(action["id"], old, at=NOW)
        sample = Verification(NOW + timedelta(seconds=10), True, "dependency_probe_min",
                              "vm-166/container:argus-lab-api", "healthy")
        assert executor.verify(action["id"], sample, at=sample.sampled_at) == "recovered_verified"
    finally:
        store._db.close()


def test_crash_after_claim_reconciles_without_second_dispatch(tmp_path):
    store, gateway, executor, check = _durable_setup(tmp_path)
    try:
        proposal = store.get_action_proposal(store.get_action_approval("appr_durable")["proposal_id"])
        assert store.reserve_action("act_crashed", proposal.id, "appr_durable", TARGET, NOW, daily_host_cap=2)
        result = executor.execute("appr_durable", check, at=NOW)
        assert result["state"] == "indeterminate" and gateway.calls == []
        assert not store.reserve_action("act_second", proposal.id, "appr_durable", TARGET, NOW,
                                        daily_host_cap=2)
    finally:
        store._db.close()


def test_precheck_and_global_hold_refuse_before_claim(tmp_path):
    store, gateway, executor, check = _durable_setup(tmp_path)
    try:
        with pytest.raises(RemediationRefused, match="current"):
            executor.execute("appr_durable", Precheck(**{**check.__dict__,
                                                        "observed_at": NOW - timedelta(minutes=1)}), at=NOW)
        store.add_target_hold("emergency", "*", "stop", "operator", NOW)
        with pytest.raises(RemediationRefused, match="hold"):
            executor.execute("appr_durable", check, at=NOW)
        assert gateway.calls == [] and store.get_action_for_approval("appr_durable") is None
    finally:
        store._db.close()


def test_outbox_and_resume_intent_recover_after_reopen(tmp_path):
    from argus.adapters.outbound.sqlite_store import SqliteStore

    store, _, _, _ = _durable_setup(tmp_path)
    path = store._db.execute("PRAGMA database_list").fetchone()[2]
    store._db.close()
    reopened = SqliteStore(path)
    calls = []

    class Runner:
        def run(self, incident_id):
            calls.append(incident_id)
            return SimpleNamespace(outcome="denied")

    try:
        worker = OfflineActionRecovery(reopened, Runner(), clock=lambda: NOW)
        assert worker.run_once() == {"notified": 1, "resumed": 1, "pending": 0, "failed": 0}
        assert worker.run_once() == {"notified": 0, "resumed": 0, "pending": 0, "failed": 0}
        assert calls == ["inc_sc03"]
        assert len(reopened.notifications()) == 1
        assert reopened.get_resume_intent("appr_durable")["state"] == "done"
    finally:
        reopened._db.close()


def test_offline_path_checks_candidate_judges_and_uses_persisted_answer(tmp_path):
    from argus.adapters.outbound.sqlite_store import SqliteStore

    store = SqliteStore(str(tmp_path / "path.db"))
    gateway = FakeActionGateway()
    current = [NOW]

    class Incident:
        id = "inc_sc03"
        root_cause_target = TARGET

        def model_copy(self, **kw):
            return self

    class Policy:
        cards = {"container.start": SimpleNamespace(identity_fields=["container_id"],
                                                     parameters={"timeout": {"min": 1, "max": 30}})}

        def next_actions(self, *args, **kwargs):
            return [{"action": "container.start", "target": TARGET, "grounds": ["RB-003"],
                     "evidence_refs": ["ev_cache_exited"]}]

    class Inventory:
        def target(self, target):
            return SimpleNamespace(service_card=lambda: SimpleNamespace(safe_actions=["container.start"], never=[]))

    path = OfflineActionPath(
        rows=store, action_policy=Policy(), inventory=Inventory(),
        proposer=lambda *_: candidate(), judge_model=lambda _: {"verdict": "agree", "checks": GOOD_CHECKS,
                                                                  "reasons": []},
        judge_model_id="gpt-6.1-sol", judge_context=lambda _: {**JUDGE_CONTEXT, "initial_risk": "green"},
        snapshot=lambda _, at: Precheck({"container_id": "cache-1"}, "inventory-1", "policy-1", "evidence-1",
                                        at, True, True, True, True),
        sample=lambda _, at: Verification(at, True, "dependency_probe_min", "vm-166/container:argus-lab-api",
                                          "healthy"), gateway=gateway,
        gate_open=frozenset({("container.start", TARGET)}), daily_host_cap=2, clock=lambda: current[0])
    try:
        path.proposer = lambda *_: candidate(arguments={"force": True})
        with pytest.raises(RemediationRefused, match="unreviewed"):
            path.propose(Incident(), {"passages": [{"runbook_id": "RB-003"}]})
        path.proposer = lambda *_: candidate()
        proposal_id = path.propose(Incident(), {"passages": [{"runbook_id": "RB-003"}]})
        assert path.propose(Incident(), {}) == proposal_id  # crash replay uses the frozen row
        assert path.judge(proposal_id).verdict == "agree"
        assert path.judge(proposal_id).verdict == "agree"  # no second judge call
        approval_id = path.request(proposal_id)
        assert path.request(proposal_id) == approval_id
        with pytest.raises(RemediationRefused, match="human"):
            path.answer(approval_id, digest=store.get_action_proposal(proposal_id).digest,
                        principal="agent", principal_kind="agent", decision="approved")
        assert path.answer(approval_id, digest=store.get_action_proposal(proposal_id).digest,
                           principal="operator", principal_kind="human", decision="approved")
        path.precheck(approval_id)
        action = path.execute(approval_id)
        assert action["state"] == "confirmed" and len(gateway.calls) == 1
        current[0] = NOW + timedelta(seconds=10)
        assert path.verify(action["id"]) == "recovered_verified"
        assert path.verify(action["id"]) == "recovered_verified"
    finally:
        store._db.close()
