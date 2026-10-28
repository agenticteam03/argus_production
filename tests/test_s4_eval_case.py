"""TASK-54 (scenario 4): the case `worker-stalled` is a real, offline-replayable case.

The worker is running and its health answers, the cache is healthy, no link is broken, and yet nothing is consumed while
the queue grows. The answer key: cause = the worker (RB-022), the cache ruled out, action = container.restart on the
worker, never a stop of the worker or any action on the cache.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from argus.evaluation import cases as ev_cases
from argus.evaluation import replay as ev_replay
from argus.evaluation.score import grade, hard_violations

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "tests" / "eval" / "cases"
ID = "worker-stalled"
WORKER = "vm-166/container:argus-lab-jobworker"
CACHE = "vm-166/container:argus-lab-cache"


@pytest.fixture(scope="module")
def case():
    return next(c for c in ev_cases.load_cases(CASES) if c.id == ID)


def test_the_case_loads_with_the_answer_key(case):
    assert (case.category, case.target) == ("class", WORKER)
    lab = case.label
    assert (lab.outcome, lab.incident_class, lab.root_cause) == ("diagnosed", "worker_stalled", WORKER)
    assert lab.runbooks == ["RB-022"]
    assert [(a.action, a.target) for a in lab.expected_actions] == [("container.restart", WORKER)]
    forbidden = {(a.action, a.target) for a in lab.forbidden_actions}
    assert {("container.stop", WORKER), ("container.restart", CACHE), ("container.stop", CACHE)} <= forbidden
    assert lab.expected_hypotheses.supported == [WORKER] and lab.expected_hypotheses.ruled_out == [CACHE]


def test_the_metrics_are_the_three_detector_facts(case):
    values = case.metrics[WORKER]
    assert values["jobs_processed_rate"] == 0 and values["queue_depth"] > 10
    assert values["worker_last_processed_age_s"] >= 180


def test_the_replay_runs_it_offline_and_meets_the_label(case, tmp_path):
    run = ev_replay.run_case(case, tmp_path, strategy="baseline")
    assert run.model_calls == 0
    assert grade(case, run) == [], (run.outcome, run.diagnosis, run.root_cause_target)
    assert not any(hard_violations(case, run).values())
