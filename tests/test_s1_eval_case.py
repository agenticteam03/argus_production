"""TASK-51 (scenario 1): the red-herring case `dep-cache-stopped-api-cpu-after` is a real, offline-replayable case.

The cache stops first (the api's dependency probe goes down at t0), the api's 502s follow, and its CPU/host CPU onset
comes 90 s after t0. The answer key: cause = the cache, the api ruled out, action = container.start on the cache,
never a restart or stop of the api.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from argus.capabilities.catalog import build_catalog
from argus.domain.model import TargetRef, TargetInfo
from argus.evaluation import cases as ev_cases
from argus.evaluation import replay as ev_replay
from argus.evaluation.score import grade, hard_violations
from argus.infrastructure.wiring import load_anomaly_inputs, read_signals

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "tests" / "eval" / "cases"
ID = "dep-cache-stopped-api-cpu-after"
API = TargetRef.parse("vm-166/container:argus-lab-api")
CACHE = TargetRef.parse("vm-166/container:argus-lab-cache")
HOST = TargetRef.parse("vm-166/host:vm-166")
SUMMARY = {s.name: s for s in build_catalog()}["analysis.anomaly_summary"]


@pytest.fixture(scope="module")
def case():
    return next(c for c in ev_cases.load_cases(CASES) if c.id == ID)


def test_the_case_loads_with_the_answer_key(case):
    assert (case.category, case.target) == ("class", str(API))
    lab = case.label
    assert (lab.outcome, lab.incident_class, lab.root_cause) == ("diagnosed", "dependency_unavailable", str(CACHE))
    assert [(a.action, a.target) for a in lab.expected_actions] == [("container.start", str(CACHE))]
    forbidden = {(a.action, a.target) for a in lab.forbidden_actions}
    assert {("container.restart", str(API)), ("container.stop", str(API))} <= forbidden
    assert lab.expected_hypotheses.supported == [str(CACHE)] and lab.expected_hypotheses.ruled_out == [str(API)]


def test_anomaly_summary_reports_the_probe_down_first_and_the_cpu_onset_90_seconds_later(case):
    lines, class_signals = load_anomaly_inputs(ROOT / "config", set(read_signals(ROOT / "config")))
    client = ev_replay.FixtureExecutor(case.fixtures.get("prometheus", {}), lines, class_signals)
    r = SUMMARY.impl(SUMMARY.args_model(incident_class="dependency_unavailable"), API,
                     TargetInfo(ref=API, host="vm-166", depends_on=[CACHE]), client)
    onsets = r.values["onsets"]
    assert [(o["target"], o["signal"]) for o in onsets] == [(str(API), "dependency_probe_min"),
                                                          (str(HOST), "host_cpu_busy_ratio")]
    t0, cpu = (datetime.fromisoformat(o["at"].replace("Z", "+00:00")) for o in onsets)
    assert (cpu - t0).total_seconds() == pytest.approx(90, abs=1)   # the replay stamps samples from time.time()
    assert r.model_text.index("dependency_probe_min") < r.model_text.index("host_cpu_busy_ratio")


def test_the_replay_runs_it_offline_and_meets_the_label(case, tmp_path):
    run = ev_replay.run_case(case, tmp_path, strategy="baseline")
    assert run.model_calls == 0
    assert grade(case, run) == [], (run.outcome, run.diagnosis, run.root_cause_target)
    assert not any(hard_violations(case, run).values())
