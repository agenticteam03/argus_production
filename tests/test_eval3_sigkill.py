"""EVAL-3: an exit 137 without an OOM kill is an unexplained kill; Argus escalates it (RB-008).

RB-008, written before the evaluation: "Absence of retained OOM evidence does not prove a non-OOM cause; preserve
uncertainty for unexplained kills"; workflow step 1 "Unknown kill -> retain OOM/external alternatives"; decision tree
"unexplained -> multiple_hypotheses / insufficient_evidence". `restart-sigkill-01` was labelled `diagnosed` with the
worker itself as root cause, i.e. the victim of a kill sent from outside named as its cause. In EVAL-2 the model
escalated it 5/5, as the runbook says. The label and the baseline now follow RB-008. The label changed after seeing the
model's answers; RB-008's text predates them (recorded in the task and the journal).
"""
from __future__ import annotations

from pathlib import Path

import yaml

from argus.evaluation.cases import load_cases
from argus.evaluation.replay import run_case
from argus.evaluation.score import grade

CASES = Path(__file__).resolve().parent / "eval" / "cases"


def _case():
    return next(c for c in load_cases(CASES) if c.id == "restart-sigkill-01")


def test_the_sigkill_case_is_labelled_as_an_unexplained_kill():
    raw = yaml.safe_load((CASES / "restart-sigkill-01.yaml").read_text(encoding="utf-8"))
    label = raw["label"]
    assert label["outcome"] == "no_action_escalated" and label.get("abstain") is True
    assert "root_cause" not in label and label["runbooks"] == ["RB-008"]
    status = raw["fixtures"]["docker_read"]["/containers/argus-lab-worker/status"]
    assert status["exit_code"] == 137 and status["oom_killed"] is False       # the story itself is unchanged


def test_the_baseline_escalates_an_exit_137_without_oom(tmp_path):
    c = _case()
    run = run_case(c, tmp_path, strategy="baseline")
    assert run.outcome == "no_action_escalated" and run.root_cause_target is None
    assert grade(c, run) == []


def test_the_baseline_still_names_an_oom_kill_and_an_application_crash(tmp_path):
    for cid in ("restart-oom-01", "restart-crash-01"):
        c = next(x for x in load_cases(CASES) if x.id == cid)
        run = run_case(c, tmp_path, strategy="baseline")
        assert run.outcome == "diagnosed" and grade(c, run) == [], cid
