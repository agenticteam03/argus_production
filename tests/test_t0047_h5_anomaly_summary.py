"""T-0047 H5 (ACR-0024 §3.7): `summarize_anomalies` (`analysis.anomaly_summary`, §12.2 Level 3, executor `prometheus`).

The incident class's signals (`config/ui-incident-signals.yaml`) on the target, its declared dependencies on the same
host and its host: onset (the first of two consecutive samples past the warning line of `config/signals.yaml`, or the
bad state of a 0/1 signal), the deviation from the 24 h baseline ending an hour before the window (p5 / p50 / p95,
unknown under half sampled), and which onset came first. Facts with numbers, never a cause; offered to no class.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from argus.capabilities.catalog import STATE_LINES, build_catalog, onset
from argus.detectors.classes import CLASSES
from argus.domain.model import TargetInfo, TargetRef
from argus.infrastructure.wiring import load_anomaly_inputs, read_signals

ROOT = Path(__file__).resolve().parents[1]
S = {s.name: s for s in build_catalog()}["analysis.anomaly_summary"]
API = TargetRef.parse("vm-166/container:argus-lab-api")
CACHE = TargetRef.parse("vm-166/container:argus-lab-cache")
OTHER = TargetRef.parse("vm-095/container:argus-lab-cache")
HOST = TargetRef.parse("vm-166/host:vm-166")
DEP = [("dependency_probe_min", "target"), ("container_restart_count", "target"), ("host_cpu_busy_ratio", "host")]
BASE = [(float(i), 0.2) for i in range(289)]                       # a full 24 h baseline at 300 s


def pts(*vals, start=1000.0):
    return [(start + 60 * i, float(v)) for i, v in enumerate(vals)]


class Client:
    def __init__(self, now: dict, base: dict | None = None, lines=None, class_signals=None, fail=()):
        self.now, self.base, self.asked, self.fail = now, base or {}, [], set(fail)
        self.lines = lines if lines is not None else {"host_cpu_busy_ratio": (0.75, "above")}
        self.class_signals = class_signals if class_signals is not None else {"dependency_unavailable": DEP}

    def range(self, signal, target, minutes, step_s, end_offset_s=0, **params):
        self.asked.append((signal, str(target), minutes, end_offset_s, params))
        if (signal, str(target)) in self.fail:
            from argus.capabilities.spec import ExecutorError
            raise ExecutorError("unreachable", "prometheus: down")
        return (self.base if end_offset_s else self.now).get((signal, str(target)), [])


def _call(client, target=API, info=None, **args):
    return S.impl(S.args_model(**{"incident_class": "dependency_unavailable", **args}), target, info, client)


def test_a_level_3_safe_prometheus_read_offered_to_no_class():
    assert (S.model_name, S.level, S.safety_class, S.executor, S.tags) == (
        "summarize_anomalies", 3, "READ_ONLY_SAFE", "prometheus", frozenset({"anomaly"}))
    assert [c.name for c in CLASSES if S.tags & c.tool_tags] == []
    pol = yaml.safe_load((ROOT / "config" / "policy.yaml").read_text(encoding="utf-8"))
    assert pol["capabilities"]["analysis.anomaly_summary"]["max_per_incident"] == 1


def test_the_class_argument_names_exactly_the_registered_classes():
    names = set(S.args_model.model_json_schema()["properties"]["incident_class"]["enum"])
    assert names == {c.name for c in CLASSES}


def test_the_committed_files_give_every_class_a_signal_list_and_the_lines():
    lines, by_class = load_anomaly_inputs(ROOT / "config", set(read_signals(ROOT / "config")))
    assert set(by_class) == {c.name for c in CLASSES}
    assert lines["host_cpu_busy_ratio"] == (0.75, "above") and lines["host_memory_available_ratio"] == (0.25, "below")
    assert not set(STATE_LINES) & set(lines)                      # a 0/1 state has no line in signals.yaml


def test_onset_needs_two_consecutive_samples_past_the_line():
    assert onset(pts(0.5, 0.8, 0.5, 0.8, 0.9), 0.75, "above") == 1180.0
    assert onset(pts(0.8, 0.5, 0.8), 0.75, "above") is None
    assert onset(pts(1, 0, 0), 0.5, "below") == 1060.0


def test_the_dependency_moved_first_and_the_facts_say_so():
    info = TargetInfo(ref=API, host="vm-166", depends_on=[CACHE, OTHER])
    now = {("dependency_probe_min", str(API)): pts(1, 1, 0, 0, 0),
           ("container_restart_count", str(CACHE)): pts(3, 3, 4, 5, 6),
           ("dependency_probe_min", str(CACHE)): pts(0, 0, 0, 0, 0),
           ("host_cpu_busy_ratio", str(HOST)): pts(0.2, 0.3, 0.8, 0.9, 0.9)}
    base = {("dependency_probe_min", str(API)): [(t, 1.0) for t, _ in BASE],
            ("host_cpu_busy_ratio", str(HOST)): BASE}
    c = Client(now, base)
    r = _call(c, info=info, minutes=60)
    assert r.status == "ok"
    asked = {(s, t) for s, t, *_ in c.asked}
    assert (("dependency_probe_min", str(OTHER)) not in asked and ("host_cpu_busy_ratio", str(HOST)) in asked)
    assert [(o["signal"], o["target"]) for o in r.values["onsets"]] == [
        ("dependency_probe_min", str(CACHE)), ("dependency_probe_min", str(API)), ("host_cpu_busy_ratio", str(HOST))]
    assert "First past its warning line: dependency_probe_min on argus-lab-cache" in r.model_text
    api = next(x for x in r.values["series"] if x["signal"] == "dependency_probe_min" and x["target"] == str(API))
    assert (api["peak"], api["direction"], api["baseline"]["p5"], api["beyond_baseline"]) == (0.0, "below", 1.0, 1.0)
    restarts = next(x for x in r.values["series"] if x["signal"] == "container_restart_count" and x["target"] == str(CACHE))
    assert restarts["warning"] is None and "no warning line (onset not computed)" in r.model_text
    assert "cause" not in r.model_text.replace("facts, not a cause", "")


def test_the_windows_asked():
    c = Client({}, {})
    _call(c, target=API, info=TargetInfo(ref=API, host="vm-166"), minutes=60)
    now = [a for a in c.asked if a[3] == 0]
    earlier = [a for a in c.asked if a[3]]
    assert {a[2] for a in now} == {60} and {(a[2], a[3]) for a in earlier} == {(1440, 60 * 60 + 3600)}


def test_unknown_is_never_calm():
    c = Client({("dependency_probe_min", str(API)): pts(1, 1, 1)},
               {("dependency_probe_min", str(API)): [(0.0, 1.0)] * 10},             # under half of 24 h sampled
               fail={("host_cpu_busy_ratio", str(HOST))})
    r = _call(c, info=TargetInfo(ref=API, host="vm-166"))
    rows = {x["signal"]: x for x in r.values["series"]}
    assert rows["dependency_probe_min"]["baseline"] is None and "baseline unknown" in r.model_text
    assert rows["container_restart_count"]["read"] == "no data" and "NO DATA (unknown, not zero)" in r.model_text
    assert rows["host_cpu_busy_ratio"]["read"] == "failed" and r.partial
    assert "No signal was past its warning line in the last 60 min." in r.model_text


def test_no_signal_list_or_no_series_is_an_error_not_a_calm_answer():
    assert _call(Client({}, class_signals={})).status == "error"
    r = _call(Client({}), info=TargetInfo(ref=API, host="vm-166"))
    assert (r.status, r.error_category) == ("error", "not_found")


def test_disk_signals_use_the_targets_declared_mounts_only():
    lines = {"host_disk_used_ratio_5m": (0.85, "above")}
    cls = {"disk_pressure": [("host_disk_used_ratio_5m", "target"), ("host_disk_hours_to_full", "target")]}
    c = Client({("host_disk_used_ratio_5m", str(HOST)): pts(0.9, 0.92)}, lines=lines, class_signals=cls)
    r = _call(c, target=HOST, info=TargetInfo(ref=HOST, host="vm-166", mounts=["/", "/srv/lab"]),
              incident_class="disk_pressure")
    assert {a[4]["mounts"] for a in c.asked} == {"/|/srv/lab"} and r.values["onsets"][0]["at"]
    c2 = Client({}, lines=lines, class_signals=cls)
    assert _call(c2, target=HOST, info=TargetInfo(ref=HOST, host="vm-166"), incident_class="disk_pressure").status == "error"
    assert c2.asked == []


# --- step 2: per-target range fixtures in the replay ------------------------------------------------------------------
# The replay answered every target with the same series per signal (`range.<signal>`), so for a dependency incident the
# victim and its dependency looked identical and "which onset came first" meant nothing. `range` stays the case
# target's series; `range_by_target.<target>.<signal>` gives another target its own; a target named there has no
# fallback (its missing signals are no data, never the case target's).
CASES = ROOT / "tests" / "eval" / "cases"
BACKEND = TargetRef.parse("vm-166/container:argus-lab-backend")
DEP_CASES = {"dep-backend-stopped": BACKEND, "dep-backend-wrong-network": BACKEND, "dep-cache-paused": CACHE,
             "dep-cache-restarting": CACHE, "dep-cache-stopped": CACHE, "ambiguous-dep-all-running": CACHE}


def _fixture_client(case_id: str):
    from argus.evaluation.cases import load_cases
    from argus.evaluation.replay import FixtureExecutor
    case = next(c for c in load_cases(CASES) if c.id == case_id)
    lines, class_signals = load_anomaly_inputs(ROOT / "config", set(read_signals(ROOT / "config")))
    return case, FixtureExecutor(case.fixtures.get("prometheus", {}), lines, class_signals)


def test_a_range_by_target_answers_that_target_only():
    from argus.evaluation.replay import FixtureExecutor
    ex = FixtureExecutor({"range": {"container_restart_count": [[-60, 1], [0, 1]]},
                          "range_by_target": {str(CACHE): {"container_restart_count": [[-60, 5], [0, 6]]}}})
    assert [v for _, v in ex.range("container_restart_count", API, 30, 60)] == [1.0, 1.0]
    assert [v for _, v in ex.range("container_restart_count", CACHE, 30, 60)] == [5.0, 6.0]
    assert ex.range("container_memory_bytes", CACHE, 30, 60) == []                  # named target: no fallback
    assert [v for _, v in ex.range("container_restart_count", HOST, 30, 60)] == [1.0, 1.0]   # unnamed: as before


@pytest.mark.parametrize("case_id", DEP_CASES)
def test_every_dependency_case_gives_the_victim_a_probe_and_the_dependency_its_own_series(case_id):
    case, client = _fixture_client(case_id)
    dep = DEP_CASES[case_id]
    victim = TargetRef.parse(case.target)
    r = S.impl(S.args_model(incident_class="dependency_unavailable"), victim,
               TargetInfo(ref=victim, host="vm-166", depends_on=[dep]), client)
    rows = {(x["target"], x["signal"]): x for x in r.values["series"]}
    assert rows[(str(victim), "dependency_probe_min")]["onset"], case_id         # the probe failed: an onset
    own = case.fixtures["prometheus"].get("range_by_target", {}).get(str(dep), {}).get("container_restart_count")
    assert own, f"{case_id}: no series of its own for {dep}"
    assert [v for _, v in client.range("container_restart_count", dep, 30, 60)] == [float(v) for _, v in own]


def test_a_restarting_dependency_shows_its_restarts_beside_the_victims_probe():
    case, client = _fixture_client("dep-cache-restarting")
    r = S.impl(S.args_model(incident_class="dependency_unavailable"), API,
               TargetInfo(ref=API, host="vm-166", depends_on=[CACHE]), client)
    rows = {(x["target"], x["signal"]): x for x in r.values["series"]}
    assert rows[(str(CACHE), "container_restart_count")]["peak"] > rows[(str(API), "container_restart_count")]["peak"]
    assert r.values["onsets"][0]["target"] == str(API)                            # only the probe has a line


@pytest.mark.parametrize("case_id", ["restart-crash-01", "restart-crash-02", "restart-exit0-job-01", "restart-oom-01",
                                     "restart-oom-02", "restart-sigkill-01"])
def test_every_restart_case_has_the_series_its_class_fires_on(case_id):
    """`container_restart_loop` fires on `restarts_10m`; `oom_killed` tells RB-001 from RB-008. Each series ends at
    the case's snapshot value, and the read finds the loop's onset."""
    case, client = _fixture_client(case_id)
    (target, snap), = case.metrics.items()
    ref = TargetRef.parse(target)
    for signal in ("restarts_10m", "oom_killed"):
        assert client.range(signal, ref, 30, 60)[-1][1] == snap[signal], (case_id, signal)
    r = S.impl(S.args_model(incident_class="container_restart_loop"), ref, TargetInfo(ref=ref, host=ref.host), client)
    rows = {x["signal"]: x for x in r.values["series"]}
    assert rows["restarts_10m"]["onset"] and "read" not in rows["oom_killed"], case_id
