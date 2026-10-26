"""Phase 18: tests for guards that no earlier test would miss if they were removed (TASK-23 review of #323)."""
from __future__ import annotations

import sqlite3
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from argus.actions.execution import ActionExecutor, Precheck
from argus.actions.remediation import FakeActionGateway, RemediationRefused, freeze_proposal
from argus.actions.risk import RiskColor, RiskTable
from argus.adapters.outbound.sqlite_store import SqliteStore
from argus.orchestration.action_path import OfflineActionPath
from test_phase18_remediation import GOOD_CHECKS, JUDGE_CONTEXT, NOW, TARGET, agreed, candidate

ROOT = Path(__file__).resolve().parents[1]
CHECK = Precheck({"container_id": "cache-1"}, "inventory-1", "policy-1", "evidence-1", NOW, True, True, True, True)


class _Incident:
    id = "inc_sc03"
    root_cause_target = TARGET

    def model_copy(self, **kw):
        return self


def _path(tmp_path, *, base=RiskColor.green, criticality="low", gate=True, gateway=None, verdict="agree",
          db="guards.db"):
    store = SqliteStore(str(tmp_path / db))

    class Policy:
        cards = {"container.start": SimpleNamespace(identity_fields=["container_id"], parameters={})}
        risk_table = SimpleNamespace(lookup=lambda action, kind: base)

        def next_actions(self, *args, **kwargs):
            return [{"action": "container.start", "target": TARGET, "grounds": ["RB-003"],
                     "evidence_refs": ["ev_cache_exited"]}]

    class Inventory:
        def target(self, target):
            return SimpleNamespace(service_card=lambda: SimpleNamespace(
                safe_actions=["container.start"], never=[], kind="stateless", criticality=criticality))

    checks = GOOD_CHECKS if verdict == "agree" else {**GOOD_CHECKS, "risk_understated": True}
    reasons = [] if verdict == "agree" else ["The judge is not convinced."]
    path = OfflineActionPath(
        rows=store, action_policy=Policy(), inventory=Inventory(), proposer=lambda *_: candidate(),
        judge_model=lambda _: {"verdict": verdict, "checks": checks, "reasons": reasons},
        judge_model_id="gpt-6.1-sol", judge_context=lambda _: JUDGE_CONTEXT, snapshot=lambda _, at: CHECK,
        sample=lambda _, at: None, gateway=gateway or FakeActionGateway(),
        gate_open=frozenset({("container.start", TARGET)}) if gate else frozenset(), daily_host_cap=2,
        clock=lambda: NOW)
    return store, path


def _judged(path):
    proposal_id = path.propose(_Incident(), {"passages": [{"runbook_id": "RB-003"}]})
    return proposal_id, path.judge(proposal_id)


def _stored_verdict(store, proposal_id, **changes):
    """Write a judge row directly, as a bug or a second writer could."""
    proposal = store.get_action_proposal(proposal_id)
    body = {"verdict": "agree", "checks": GOOD_CHECKS, "reasons": [], "risk": "green",
            "proposal_digest": proposal.digest, **changes}
    store.add_judge_verdict(proposal_id, "gpt-6.1-sol", body, NOW)


# --- risk colours and the typed name (M1, M2, M3) ---------------------------------------------------------------------

def test_the_reviewed_risk_table_has_red_and_forbidden_cells():
    table = RiskTable.from_yaml(ROOT / "config" / "risk.yaml")
    assert table.lookup("container.stop", "stateful") == RiskColor.red
    assert table.lookup("container.restart", "database") == RiskColor.forbidden


def test_a_red_proposal_needs_the_typed_target_name_to_be_approved(tmp_path):
    store, path = _path(tmp_path, base=RiskColor.red)
    try:
        proposal_id, judged = _judged(path)
        assert judged.verdict == "agree" and judged.risk == "red"
        approval_id = path.request(proposal_id)
        digest = store.get_action_proposal(proposal_id).digest
        who = dict(digest=digest, principal="operator", principal_kind="human")
        for typed in (None, "", "argus-lab-worker", "ARGUS-LAB-CACHE"):
            with pytest.raises(RemediationRefused, match="typing the target name"):
                path.answer(approval_id, decision="approved", confirmation_target=typed, **who)
        assert store.get_action_approval(approval_id)["state"] == "pending"
        assert path.answer(approval_id, decision="approved", confirmation_target="argus-lab-cache", **who)
        assert store.get_action_approval(approval_id)["state"] == "approved"
    finally:
        store._db.close()


def test_denying_a_red_proposal_needs_no_typed_name_and_green_needs_none_to_approve(tmp_path):
    store, path = _path(tmp_path, base=RiskColor.red)
    store2, path2 = _path(tmp_path, base=RiskColor.green, db="green.db")
    try:
        proposal_id, _ = _judged(path)
        approval_id = path.request(proposal_id)
        digest = store.get_action_proposal(proposal_id).digest
        assert path.answer(approval_id, digest=digest, principal="operator", principal_kind="human",
                           decision="denied")
        green_id, _ = _judged(path2)
        green_approval = path2.request(green_id)
        assert path2.answer(green_approval, digest=store2.get_action_proposal(green_id).digest,
                            principal="operator", principal_kind="human", decision="approved")
    finally:
        store._db.close()
        store2._db.close()


@pytest.mark.parametrize("base, expected", [(RiskColor.green, "amber"), (RiskColor.amber, "red"),
                                            (RiskColor.red, "forbidden")])
def test_a_high_criticality_service_raises_the_colour_one_level(tmp_path, base, expected):
    store, path = _path(tmp_path, base=base, criticality="high")
    try:
        proposal_id, judged = _judged(path)
        assert judged.risk == expected
        assert store.get_judge_verdict(proposal_id)["risk"] == expected
    finally:
        store._db.close()


def test_a_low_criticality_service_keeps_the_table_colour(tmp_path):
    store, path = _path(tmp_path, base=RiskColor.amber, criticality="low")
    try:
        assert _judged(path)[1].risk == "amber"
    finally:
        store._db.close()


def test_a_forbidden_cell_is_never_judged_and_leaves_no_verdict(tmp_path):
    store, path = _path(tmp_path, base=RiskColor.forbidden)
    try:
        proposal_id = path.propose(_Incident(), {"passages": [{"runbook_id": "RB-003"}]})
        with pytest.raises(RemediationRefused, match="forbids"):
            path.judge(proposal_id)
        assert store.get_judge_verdict(proposal_id) is None
        assert path.request(proposal_id) is None
    finally:
        store._db.close()


# --- request() is the approval boundary (M4, M5, M19, M20) ---------------------------------------------------------------

def test_request_creates_an_approval_for_an_agreeing_green_verdict_on_an_open_gate(tmp_path):
    store, path = _path(tmp_path)
    try:
        proposal_id, _ = _judged(path)
        assert path.request(proposal_id) is not None
        assert store.get_action_approval_for_proposal(proposal_id) is not None
    finally:
        store._db.close()


@pytest.mark.parametrize("change", [
    {"verdict": "doubt"},
    {"verdict": "disagree"},
    {"proposal_digest": "0" * 64},
    {"risk": "forbidden"},
], ids=["doubt", "disagree", "other-digest", "forbidden-colour"])
def test_request_refuses_a_verdict_that_is_not_an_agreement_for_this_proposal(tmp_path, change):
    store, path = _path(tmp_path)
    try:
        proposal_id = path.propose(_Incident(), {"passages": [{"runbook_id": "RB-003"}]})
        _stored_verdict(store, proposal_id, **change)
        assert path.request(proposal_id) is None
        assert store.get_action_approval_for_proposal(proposal_id) is None
    finally:
        store._db.close()


def test_request_refuses_a_proposal_that_has_no_verdict(tmp_path):
    store, path = _path(tmp_path)
    try:
        proposal_id = path.propose(_Incident(), {"passages": [{"runbook_id": "RB-003"}]})
        assert path.request(proposal_id) is None
    finally:
        store._db.close()


def test_request_refuses_while_the_write_gate_is_closed(tmp_path):
    store, path = _path(tmp_path, gate=False)
    try:
        proposal_id, judged = _judged(path)
        assert judged.verdict == "agree"
        assert path.request(proposal_id) is None
        assert store.get_action_approval_for_proposal(proposal_id) is None
    finally:
        store._db.close()


# --- freeze_proposal scope (M9) -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("target", [
    "vm-166/container:worker",
    "vm-166/container:argus-v18-worker",
    "vm-166/host:vm-166",
], ids=["not-a-lab-name", "argus-itself", "not-a-container"])
def test_freeze_refuses_anything_but_a_named_lab_container(target):
    with pytest.raises(RemediationRefused, match="lab containers"):
        freeze_proposal(candidate(target=target), at=NOW)


# --- the executor's own checks, on rows written outside the application path (M10, M12) -------------------

def _approved(tmp_path, *, gate=True):
    store = SqliteStore(str(tmp_path / "executor.db"))
    proposal = freeze_proposal(candidate(), at=NOW)
    store.add_action_proposal(proposal)
    agreed(store, proposal, NOW)  # the executor refuses an approval without the judge's stored agree
    store.add_action_approval("appr_guard", proposal.id, proposal.digest, NOW, proposal.expires_at)
    assert store.answer_action_approval("appr_guard", proposal.digest, "operator", "approved", NOW)
    gateway = FakeActionGateway()
    executor = ActionExecutor(store, gateway, daily_host_cap=2,
                              gate_open=frozenset({("container.start", TARGET)}) if gate else frozenset())
    return store, proposal, gateway, executor


def test_the_executor_refuses_while_the_gate_is_closed_and_claims_nothing(tmp_path):
    store, _, gateway, executor = _approved(tmp_path, gate=False)
    try:
        with pytest.raises(RemediationRefused, match="write gate"):
            executor.execute("appr_guard", CHECK, at=NOW)
        assert gateway.calls == [] and store.get_action_for_approval("appr_guard") is None
    finally:
        store._db.close()


class _Rows:
    """The real store, with one read replaced, to stand for a row that a second writer changed."""

    def __init__(self, store, **overrides):
        self._store, self._overrides = store, overrides

    def __getattr__(self, name):
        return self._overrides.get(name, getattr(self._store, name))


def test_the_executor_refuses_an_approved_row_that_names_no_human(tmp_path):
    store, _, gateway, _ = _approved(tmp_path)
    try:
        approval = store.get_action_approval("appr_guard")
        rows = _Rows(store, get_action_approval=lambda _id: {**approval, "actor": None})
        executor = ActionExecutor(rows, gateway, daily_host_cap=2, gate_open=frozenset({("container.start", TARGET)}))
        with pytest.raises(RemediationRefused, match="no human-approved"):
            executor.execute("appr_guard", CHECK, at=NOW)
        assert gateway.calls == [] and store.get_action_for_approval("appr_guard") is None
    finally:
        store._db.close()


def test_the_store_itself_refuses_to_approve_without_an_actor(tmp_path):
    store = SqliteStore(str(tmp_path / "actor.db"))
    try:
        proposal = freeze_proposal(candidate(), at=NOW)
        store.add_action_proposal(proposal)
        store.add_action_approval("appr_none", proposal.id, proposal.digest, NOW, proposal.expires_at)
        with pytest.raises(ValueError, match="actor"):
            store.answer_action_approval("appr_none", proposal.digest, "", "approved", NOW)
        assert store.get_action_approval("appr_none")["state"] == "pending"
    finally:
        store._db.close()


def test_the_executor_refuses_a_frozen_body_changed_after_the_digest_was_taken(tmp_path):
    store, proposal, gateway, _ = _approved(tmp_path)
    try:
        tampered = store.get_action_proposal(proposal.id)
        tampered.input.arguments["force"] = True  # the nested dict is mutable; the digest is stale
        rows = _Rows(store, get_action_proposal=lambda _id: tampered)
        executor = ActionExecutor(rows, gateway, daily_host_cap=2, gate_open=frozenset({("container.start", TARGET)}))
        with pytest.raises(RemediationRefused, match="digest"):
            executor.execute("appr_guard", CHECK, at=NOW)
        assert gateway.calls == [] and store.get_action_for_approval("appr_guard") is None
    finally:
        store._db.close()


def test_one_approval_can_be_reserved_only_once_even_after_the_cooldown(tmp_path):
    store, proposal, gateway, executor = _approved(tmp_path)
    try:
        action = executor.execute("appr_guard", CHECK, at=NOW)
        assert action["state"] == "confirmed"
        later = NOW + timedelta(minutes=11)  # past the cooldown and not at the daily cap
        assert store.reserve_action("act_again", proposal.id, "appr_guard", TARGET, later,
                                    daily_host_cap=5) is False
        assert store.get_action("act_again") is None and gateway.calls == [action["id"]]
    finally:
        store._db.close()


def test_the_unique_index_is_a_second_barrier_for_one_approval_one_action(tmp_path):
    store, proposal, _, executor = _approved(tmp_path)
    try:
        executor.execute("appr_guard", CHECK, at=NOW)
        with pytest.raises(sqlite3.IntegrityError):
            store._db.execute("INSERT INTO action (action_id, proposal_id, approval_id, state, attempted_at) "
                              "VALUES ('act_dup', ?, 'appr_guard', 'attempting', ?)", (proposal.id, NOW.isoformat()))
    finally:
        store._db.close()
