"""T-0038: `compare_incident_baseline` (`metrics.compare_baseline`, ARCHITECTURE §12 Level 3, executor `prometheus`):
the same named signal over the current window and over the same window earlier (1 h, 24 h or 7 days ago), "no
stored baseline". The model names a METRIC (memory, cpu, restarts, disk, network), never a signal or PromQL; which
signal is read depends on the target kind. A window without samples is unknown, never zero, and is said so.
Offered to no class until measured.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from argus.capabilities.catalog import build_catalog
from argus.detectors.classes import CLASSES
from argus.domain.model import TargetInfo, TargetRef

ROOT = Path(__file__).resolve().parents[1]
SPECS = {s.name: s for s in build_catalog()}
S = SPECS["metrics.compare_baseline"]
API = TargetRef.parse("vm-166/container:argus-lab-api")
HOST = TargetRef.parse("vm-166/host:vm-166")


class Client:
    def __init__(self, now_series, earlier_series):
        self.now_series, self.earlier_series, self.asked = now_series, earlier_series, []

    def range(self, signal, target, minutes, step_s, end_offset_s=0, **params):
        self.asked.append((signal, minutes, end_offset_s, params))
        return self.earlier_series if end_offset_s else self.now_series


def pts(*vals):
    return [(1000.0 + 60 * i, float(v)) for i, v in enumerate(vals)]


def _call(target, client, info=None, **args):
    return S.impl(S.args_model(**args), target, info, client)


def test_a_level_3_safe_prometheus_read_offered_to_no_class():
    assert (S.model_name, S.level, S.safety_class, S.executor) == (
        "compare_incident_baseline", 3, "READ_ONLY_SAFE", "prometheus")
    assert set(S.target_kinds) == {"container", "host"}
    assert [c.name for c in CLASSES if S.tags & c.tool_tags] == []
    pol = yaml.safe_load((ROOT / "config" / "policy.yaml").read_text(encoding="utf-8"))
    assert pol["capabilities"]["metrics.compare_baseline"]["max_per_incident"] == 2


def test_the_current_window_against_the_same_window_a_day_ago():
    c = Client(pts(100, 200, 300), pts(100, 100, 100))
    r = _call(API, c, metric="memory", minutes=30, earlier="24h")
    assert c.asked == [("container_memory_bytes", 30, 0, {}), ("container_memory_bytes", 30, 86400, {})]
    assert r.status == "ok"
    assert "last 30 min mean=200 max=300" in r.model_text and "24h earlier mean=100 max=100" in r.model_text
    assert "mean x2" in r.model_text
    assert r.values["now"]["mean"] == 200 and r.values["earlier"]["max"] == 100


@pytest.mark.parametrize("target,metric,signal", [
    (API, "cpu", "container_cpu_cores"), (API, "restarts", "container_restart_count"),
    (HOST, "cpu", "host_cpu_busy_ratio"), (HOST, "memory", "host_memory_available_ratio"),
    (HOST, "network", "host_network_bytes_per_s")])
def test_the_signal_depends_on_the_metric_and_the_target_kind(target, metric, signal):
    c = Client(pts(1, 2), pts(1, 1))
    _call(target, c, metric=metric, earlier="1h")
    assert {a[0] for a in c.asked} == {signal} and c.asked[1][2] == 3600


def test_disk_compares_the_declared_mounts():
    c = Client(pts(0.5, 0.6), pts(0.3, 0.3))
    info = TargetInfo(ref=HOST, mounts=["/", "/srv/argus-lab-fill"])
    _call(HOST, c, info=info, metric="disk", earlier="7d")
    assert c.asked[0] == ("host_disk_used_ratio_mounts", 30, 0, {"mounts": "/|/srv/argus-lab-fill"})
    assert c.asked[1][2] == 7 * 86400


@pytest.mark.parametrize("target,metric", [(API, "disk"), (API, "network"), (HOST, "restarts")])
def test_a_metric_the_target_kind_has_not_is_refused_not_guessed(target, metric):
    c = Client(pts(1), pts(1))
    r = _call(target, c, metric=metric)
    assert c.asked == [] and r.status == "error" and r.error_category == "invalid_args"


def test_a_window_without_samples_is_unknown_not_zero():
    r = _call(API, Client(pts(5, 6), []), metric="memory")
    assert r.status == "ok" and r.partial and "24h earlier: NO DATA (unknown, not zero)" in r.model_text
    r = _call(API, Client([], []), metric="memory")
    assert r.status == "error" and "NO DATA" in r.model_text


def test_the_model_names_a_metric_never_a_signal():
    with pytest.raises(Exception):
        S.args_model(metric="container_memory_bytes")
    with pytest.raises(Exception):
        S.args_model(metric="memory", earlier="3h")
    with pytest.raises(Exception):
        S.args_model(metric="memory", minutes=500)


def test_the_client_reads_an_earlier_window():
    import inspect
    from argus.evaluation.replay import FixtureExecutor
    from argus.tooling.executors import PrometheusClient
    assert "end_offset_s" in inspect.signature(PrometheusClient.range).parameters
    assert "**" in str(inspect.signature(FixtureExecutor.range))
