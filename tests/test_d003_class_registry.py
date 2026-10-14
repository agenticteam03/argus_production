"""D-003 (ARCHITECTURE §21.2, decided 2026-10-13): a class keeps a model strategy only if it matches or beats the
deterministic baseline on all its evaluation cases (ambiguous ones included); otherwise it is switched to `baseline`
in the class registry (a data change). Counted that way (baseline on `main` f51c2b4, model from EVAL-main re-graded by
EVAL-6): `dependency_unavailable` 0.90 vs 1.00 and `nginx_upstream_failure` 0.92 vs 1.00 run `baseline`;
`health_check_failed` keeps the model (0.97 vs 0.83: the baseline diagnoses `ambiguous-health-no-cause`, where the
right answer is to escalate). OP-013 revisits the decision with held-out cases the baseline was not written from.
"""
from __future__ import annotations

import pytest

from test_core import ROOT

CASES = ROOT / "tests" / "eval" / "cases"
TO_BASELINE = {"dependency_unavailable", "nginx_upstream_failure"}
KEPT = {"container_restart_loop": "model_loop", "health_check_failed": "model_loop",
        "postgresql_connection_exhaustion": "model_loop", "cpu_saturation": "model_loop",
        "disk_pressure": "confirm_then_reason", "monitoring_blind_spot": "evidence_pack"}


def _registry() -> dict[str, str]:
    from argus.detectors.classes import CLASSES
    return {c.name: c.strategy for c in CLASSES}


def test_the_two_classes_under_the_baseline_run_the_baseline():
    reg = _registry()
    assert {name: reg[name] for name in TO_BASELINE} == dict.fromkeys(TO_BASELINE, "baseline")


def test_the_classes_that_match_or_beat_the_baseline_keep_their_strategy():
    reg = _registry()
    assert {name: reg[name] for name in KEPT} == KEPT
    assert set(reg) == TO_BASELINE | set(KEPT)              # a new class must be decided here too


@pytest.fixture()
def ev(monkeypatch):
    monkeypatch.setenv("ARGUS_JWT_KEY", "x" * 40)
    from argus import evaluation
    return evaluation


def test_their_evaluation_cases_pass_as_registered_without_a_model(ev, tmp_path):
    """The registry as shipped (no strategy override, no model): every case of the two classes passes, with no
    model call and no hard violation."""
    cases = [c for c in ev.load_cases(CASES) if c.label.incident_class in TO_BASELINE]
    assert len(cases) >= 11
    failed = {}
    for c in cases:
        run = ev.run_case(c, workdir=tmp_path, llm=None)
        problems = ev.grade(c, run) + [f"{k}={v}" for k, v in ev.hard_violations(c, run).items() if v]
        if run.model_calls:
            problems.append(f"model calls {run.model_calls}")
        if problems:
            failed[c.id] = problems
    assert failed == {}


def test_the_baseline_would_diagnose_the_ambiguous_health_case(ev, tmp_path):
    """Why `health_check_failed` keeps the model: run with the baseline, the ambiguous case gets a diagnosis."""
    c = next(c for c in ev.load_cases(CASES) if c.id == "ambiguous-health-no-cause")
    run = ev.run_case(c, workdir=tmp_path, llm=None, strategy="baseline")
    assert run.outcome == "diagnosed" and ev.grade(c, run)
