"""TASK-55: a card's `verify` may list several checks that must all hold in the window (scenarios 2 and 4).

The single-check form keeps working; `verify_by_role` gives `container.restart` a worker-specific form."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
import yaml

from argus.actions.cards import load_action_cards
from argus.actions.execution import ActionExecutor, Precheck, Verification
from argus.actions.remediation import FakeActionGateway, Prediction, RemediationRefused, freeze_proposal
from test_core import ROOT as _ROOT
from test_phase18_remediation import NOW, agreed, candidate

ROOT = Path(_ROOT)
WORKER = "vm-166/container:argus-lab-jobworker"
RATE = "jobs_processed_rate"
SLOPE = "queue_depth_slope"


@pytest.fixture()
def cards():
    return load_action_cards(ROOT / "config/actions")


def _card_copy(tmp_path, verify, **extra):
    raw = yaml.safe_load((ROOT / "config/actions/container.restart.yaml").read_text(encoding="utf-8"))
    raw["verify"] = verify
    raw.pop("verify_by_role", None)
    raw.update(extra)
    (tmp_path / "container.restart.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    return tmp_path


# ---- the card ------------------------------------------------------------------------------------------------

def test_single_signal_cards_are_unchanged(cards):
    for name, card in cards.items():
        if name == "container.restart":
            continue
        assert "checks" not in card.verify and card.verify["signal"], name
        (check,) = card.verify_checks()
        assert check == {"signal": card.verify["signal"], "op": "==", "expected": card.verify["expected"]}
        assert card.verify_window() == card.verify["window_sec"]


def test_restart_has_a_worker_specific_verify(cards):
    card = cards["container.restart"]
    assert [c["signal"] for c in card.verify_checks()] == ["up"]
    assert card.verify_window() == 60
    assert card.verify_window("api") == 60
    checks = card.verify_checks("worker")
    assert [(c["signal"], c["op"], c["expected"]) for c in checks] == [(RATE, ">", 0), (SLOPE, "<", 0)]
    assert card.verify_window("worker") > 0


def test_checks_form_loads(tmp_path):
    verify = {"checks": [{"signal": "up", "expected": 1}, {"signal": "link_ok", "expected": 1}], "window_sec": 90}
    card = load_action_cards(_card_copy(tmp_path, verify))["container.restart"]
    assert [c["signal"] for c in card.verify_checks()] == ["up", "link_ok"]
    assert card.verify_window() == 90


@pytest.mark.parametrize("verify", [
    {"checks": [], "window_sec": 60},
    {"checks": [{"expected": 1}], "window_sec": 60},
    {"checks": [{"signal": "up"}], "window_sec": 60},
    {"checks": [{"signal": "up", "expected": 1, "op": "~="}], "window_sec": 60},
    {"checks": [{"signal": "up", "expected": 1, "extra": 1}], "window_sec": 60},
    {"checks": [{"signal": "up", "expected": 1}]},
    {"checks": [{"signal": "up", "expected": 1}], "window_sec": 0},
    {"checks": [{"signal": "up", "expected": 1}], "signal": "up", "expected": 1, "window_sec": 60},
    {"checks": "up", "window_sec": 60},
])
def test_bad_checks_are_refused(tmp_path, verify):
    with pytest.raises(ValueError):
        load_action_cards(_card_copy(tmp_path, verify))


def test_bad_role_verify_is_refused(tmp_path):
    base = {"signal": "up", "expected": 1, "window_sec": 60}
    with pytest.raises(ValueError):
        load_action_cards(_card_copy(tmp_path, base, verify_by_role={"worker": {"checks": [], "window_sec": 5}}))
    with pytest.raises(ValueError):
        load_action_cards(_card_copy(tmp_path, base, verify_by_role=["worker"]))


# ---- the executor --------------------------------------------------------------------------------------------

def _setup(tmp_path, cards, window=180):
    from argus.adapters.outbound.sqlite_store import SqliteStore

    store = SqliteStore(str(tmp_path / "action.db"))
    proposal = freeze_proposal(candidate(
        capability="container.restart", target=WORKER, target_identity={"container_id": "jw-1"}, root_cause=WORKER,
        prediction=Prediction(signal=RATE, target=WORKER, expected="positive", within_seconds=window),
        rollback="none"), at=NOW)
    store.add_action_proposal(proposal)
    agreed(store, proposal, NOW)
    store.add_action_approval("appr_multi", proposal.id, proposal.digest, NOW, proposal.expires_at)
    assert store.answer_action_approval("appr_multi", proposal.digest, "operator", "approved", NOW)
    executor = ActionExecutor(store, FakeActionGateway(), gate_open=frozenset({("container.restart", WORKER)}),
                              daily_host_cap=2, cards=cards)
    check = Precheck({"container_id": "jw-1"}, "inventory-1", "policy-1", "evidence-1", NOW, True, True, True, True)
    action = executor.execute("appr_multi", check, at=NOW)
    assert action["state"] == "confirmed"
    return store, executor, action


def _sample(seconds, signal, actual, cleared=True):
    return Verification(NOW + timedelta(seconds=seconds), cleared, signal, WORKER, actual)


def test_all_checks_hold_is_verified_with_one_line_per_check(tmp_path, cards):
    store, executor, action = _setup(tmp_path, cards)
    try:
        samples = [_sample(30, RATE, "2.5"), _sample(30, SLOPE, "-0.4")]
        assert executor.verify(action["id"], samples, at=NOW + timedelta(seconds=30),
                               role="worker") == "recovered_verified"
        details = store.get_action_outcome(action["id"])["body"]
        assert details["prediction_met"] is True
        assert [(c["signal"], c["actual"], c["ok"]) for c in details["checks"]] == [(RATE, "2.5", True),
                                                                                  (SLOPE, "-0.4", True)]
    finally:
        store._db.close()


def test_one_failing_check_is_not_verified_after_the_window(tmp_path, cards):
    store, executor, action = _setup(tmp_path, cards)
    try:
        at = NOW + timedelta(seconds=30)
        samples = [_sample(30, RATE, "2.5"), _sample(30, SLOPE, "0.9")]      # processing, but the queue still grows
        assert executor.verify(action["id"], samples, at=at, role="worker") is None      # keeps waiting
        late = NOW + timedelta(seconds=200)
        samples = [_sample(120, RATE, "2.5"), _sample(120, SLOPE, "0.9")]
        assert executor.verify(action["id"], samples, at=late, role="worker") == "action_failed"
        details = store.get_action_outcome(action["id"])["body"]
        assert details["prediction_met"] is False
        assert [c["ok"] for c in details["checks"]] == [True, False]
    finally:
        store._db.close()


def test_a_missing_check_is_a_failure_at_the_deadline(tmp_path, cards):
    store, executor, action = _setup(tmp_path, cards)
    try:
        late = NOW + timedelta(seconds=200)
        assert executor.verify(action["id"], [_sample(100, RATE, "3")], at=late, role="worker") == "action_failed"
        lines = store.get_action_outcome(action["id"])["body"]["checks"]
        assert lines[1]["signal"] == SLOPE and lines[1]["actual"] is None and lines[1]["ok"] is False
    finally:
        store._db.close()


def test_a_sample_outside_the_window_does_not_count(tmp_path, cards):
    store, executor, action = _setup(tmp_path, cards)
    try:
        late = NOW + timedelta(seconds=400)
        samples = [_sample(300, RATE, "2.5"), _sample(300, SLOPE, "-1")]       # good, but after the 180 s window
        assert executor.verify(action["id"], samples, at=late, role="worker") == "action_failed"
    finally:
        store._db.close()


def test_a_detector_that_has_not_cleared_fails_the_check(tmp_path, cards):
    store, executor, action = _setup(tmp_path, cards)
    try:
        at = NOW + timedelta(seconds=200)
        samples = [_sample(100, RATE, "2.5"), _sample(100, SLOPE, "-1", cleared=False)]
        assert executor.verify(action["id"], samples, at=at, role="worker") == "action_failed"
    finally:
        store._db.close()


def test_a_sample_before_the_action_completed_is_refused(tmp_path, cards):
    store, executor, action = _setup(tmp_path, cards)
    try:
        with pytest.raises(RemediationRefused, match="predates"):
            executor.verify(action["id"], [_sample(0, RATE, "2"), _sample(10, SLOPE, "-1")], at=NOW, role="worker")
    finally:
        store._db.close()


def test_the_single_check_path_is_unchanged_without_cards(tmp_path):
    store, executor, action = _setup(tmp_path, None)
    try:
        sample = _sample(30, RATE, "positive")
        assert executor.verify(action["id"], sample, at=sample.sampled_at) == "recovered_verified"
        assert "checks" not in store.get_action_outcome(action["id"])["body"]
    finally:
        store._db.close()


def test_a_list_of_samples_needs_cards_with_several_checks(tmp_path, cards):
    store, executor, action = _setup(tmp_path, cards)
    try:
        sample = _sample(30, RATE, "positive")
        # default role: container.restart's single `up` check, so the prediction decides, as before
        assert executor.verify(action["id"], [sample], at=sample.sampled_at) == "recovered_verified"
    finally:
        store._db.close()


# ---- the evaluation case -------------------------------------------------------------------------------------

def test_worker_stalled_case_loads_with_its_answer_key(monkeypatch):
    monkeypatch.setenv("ARGUS_JWT_KEY", "x" * 40)
    from argus import evaluation

    case = {c.id: c for c in evaluation.load_cases(ROOT / "tests/eval/cases")}["worker-stalled"]
    assert case.target == WORKER and case.label.incident_class == "worker_stalled"
    assert case.label.root_cause == WORKER
    hyp = case.label.expected_hypotheses
    assert WORKER in hyp.supported
    assert {"vm-166/container:argus-lab-cache", "vm-166/container:argus-lab-db"} <= set(hyp.ruled_out)
    assert [(a.action, a.target) for a in case.label.expected_actions] == [("container.restart", WORKER)]
    assert {a.action for a in case.label.forbidden_actions} >= {"container.stop"}
    assert "RB-022" in case.label.runbooks
