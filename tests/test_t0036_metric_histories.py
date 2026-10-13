"""T-0036: the Level 2 metric histories of ARCHITECTURE §12 that were still missing: `get_cpu_history`,
`get_disk_history`, `get_network_history` (`metrics.cpu_history` / `.disk_history` / `.network_history`, executor
`prometheus`). Like `get_memory_history`: named signal templates of `config/signals.yaml` only (never free-form
PromQL), a bounded window, NO DATA = unknown. CPU: a container's cores in use (cAdvisor) or a host's busy share
(node-exporter); disk: the fullest of the host's DECLARED mounts (the inventory's `mounts`, as detection reads them);
network: a container's received + sent bytes per second. Offered to no class until an evaluation batch measures
them (as the snapshot, T-0034).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from argus.capabilities.catalog import build_catalog
from argus.detectors.classes import CLASSES
from argus.domain.model import TargetInfo, TargetRef

ROOT = Path(__file__).resolve().parents[1]
SPECS = {s.name: s for s in build_catalog()}
SIGNALS = yaml.safe_load((ROOT / "config" / "signals.yaml").read_text(encoding="utf-8"))
NEW = {"metrics.cpu_history": ("get_cpu_history", {"container", "host"}),
       "metrics.disk_history": ("get_disk_history", {"host"}),
       "metrics.network_history": ("get_network_history", {"container"})}
API = TargetRef.parse("vm-166/container:argus-lab-api")
HOST = TargetRef.parse("vm-166/host:vm-166")


class Client:
    """The prometheus executor as the impl sees it; records what was asked."""

    def __init__(self, series=None):
        self.asked, self.series = [], series if series is not None else [(1000.0 + 60 * i, 0.1 * i) for i in range(5)]

    def range(self, signal, target, minutes, step_s, **params):
        self.asked.append((signal, str(target), minutes, params))
        return self.series


def _call(name, target, client, minutes=30, info=None):
    s = SPECS[name]
    return s.impl(s.args_model(minutes=minutes), target, info, client)


@pytest.mark.parametrize("name", sorted(NEW))
def test_the_three_histories_are_level_2_safe_prometheus_reads(name):
    s = SPECS[name]
    model, kinds = NEW[name]
    assert (s.model_name, s.level, s.safety_class, s.executor) == (model, 2, "READ_ONLY_SAFE", "prometheus")
    assert set(s.target_kinds) == kinds
    assert s.args_model.model_fields["minutes"].metadata                  # bounded like memory_history (2..240)
    pol = yaml.safe_load((ROOT / "config" / "policy.yaml").read_text(encoding="utf-8"))
    assert pol["capabilities"][name]["max_per_incident"] == 4


@pytest.mark.parametrize("name", sorted(NEW))
def test_offered_to_no_class_until_measured(name):
    assert [c.name for c in CLASSES if SPECS[name].tags & c.tool_tags] == []


def test_every_signal_they_read_is_a_named_template_filtered_on_the_host():
    for sig in ("container_cpu_cores", "host_cpu_busy_ratio", "host_disk_used_ratio_mounts",
                "container_network_bytes_per_s"):
        assert sig in SIGNALS, sig
        assert 'argus_host="$host"' in SIGNALS[sig], sig
    assert "$mounts" in SIGNALS["host_disk_used_ratio_mounts"]


def test_cpu_history_reads_cores_of_a_container_and_the_busy_share_of_a_host():
    c = Client()
    r = _call("metrics.cpu_history", API, c)
    assert c.asked[0][0] == "container_cpu_cores" and "CPU cores in use" in r.model_text
    c = Client()
    r = _call("metrics.cpu_history", HOST, c)
    assert c.asked[0][0] == "host_cpu_busy_ratio" and "CPU busy share" in r.model_text
    assert "first=0" in r.model_text and "max=0.4" in r.model_text and r.status == "ok"


def test_disk_history_reads_the_declared_mounts_of_the_host():
    c = Client()
    info = TargetInfo(ref=HOST, mounts=["/", "/srv/argus-lab-fill"])
    r = _call("metrics.disk_history", HOST, c, info=info)
    assert c.asked[0][0] == "host_disk_used_ratio_mounts"
    assert c.asked[0][3] == {"mounts": "/|/srv/argus-lab-fill"}
    assert "fullest declared filesystem used share" in r.model_text


def test_disk_history_without_declared_mounts_is_unknown_not_zero():
    c = Client()
    r = _call("metrics.disk_history", HOST, c, info=TargetInfo(ref=HOST))
    assert c.asked == [] and r.status == "error" and "NO DATA" in r.model_text and "unknown" in r.model_text


def test_network_history_reads_bytes_per_second_of_a_container():
    c = Client()
    r = _call("metrics.network_history", API, c, minutes=60)
    assert c.asked[0][:3] == ("container_network_bytes_per_s", str(API), 60)
    assert "network bytes/s (received + sent)" in r.model_text


def test_no_samples_is_unknown_not_zero():
    r = _call("metrics.network_history", API, Client(series=[]))
    assert r.status == "error" and "NO DATA" in r.model_text and "unknown, not zero" in r.model_text


def test_the_prometheus_client_fills_mounts_only_from_the_inventory():
    from argus.tooling.executors import PrometheusClient
    c = PrometheusClient("http://p", None, SIGNALS)
    expr = c.expr("host_disk_used_ratio_mounts", HOST, mounts="/|/srv/argus-lab-fill")
    assert 'argus_host="vm-166"' in expr and 'mountpoint=~"/|/srv/argus-lab-fill"' in expr
    assert c.expr("container_cpu_cores", API) == SIGNALS["container_cpu_cores"].replace("$host", "vm-166").replace(
        "$name", "argus-lab-api")
    with pytest.raises(Exception):
        c.expr("host_disk_used_ratio_mounts", HOST, mounts='/"} or vector(1) #')   # not a plain path list


def test_the_replay_answers_the_new_histories_from_the_case_fixtures():
    from argus.evaluation.replay import FixtureExecutor
    import inspect
    assert "**" in str(inspect.signature(FixtureExecutor.range))            # accepts the mounts parameter
