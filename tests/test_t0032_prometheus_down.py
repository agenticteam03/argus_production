"""T-0032, phase 13: Prometheus down on one host is a partition of that host only.

The implementation plan's phase 13: "partition ⇒ escalation for one host only". With vm-095's Prometheus down, a check
of a vm-095 target ends `undiagnosable` before any model call (unknown is never healthy, G-007), and a check of a
vm-166 target, read through vm-166's own Prometheus, still answers.
"""
from __future__ import annotations

import httpx
import pytest
import yaml

from argus.adapters.outbound.config_adapters import PrometheusMetrics, YamlInventory
from argus.adapters.outbound.llm import ScriptedLLM
from argus.domain.model import IncidentOutcome, RequestKind, TargetRef
from argus.ports.ports import MetricsUnavailable
from test_core import ROOT, FakeMetrics, incident, make_app  # noqa: F401  (make_app = fixture)

WORKER_095 = "vm-095/container:argus-lab-worker"
WORKER_166 = "vm-166/container:argus-lab-worker"


class OneHostDown(FakeMetrics):
    """vm-095's Prometheus refuses connections; vm-166's answers."""

    def snapshot(self, target, signals):
        if target.host == "vm-095":
            raise MetricsUnavailable("prometheus at http://argus-v18-prometheus:9090: ConnectError")
        return super().snapshot(target, signals)


@pytest.mark.parametrize("runner", ["plain", "langgraph"])
def test_prometheus_down_on_one_host_escalates_that_host_only(make_app, monkeypatch, runner):
    monkeypatch.setenv("ARGUS_RUNNER", runner)
    metrics = OneHostDown({WORKER_095: {"restarts_10m": 0}, WORKER_166: {"restarts_10m": 0}})
    app = make_app(llm=ScriptedLLM([]), metrics=metrics)          # any model call would fail the run

    down = app.runner.run(incident(app, WORKER_095, RequestKind.check).id)
    assert down.outcome == IncidentOutcome.undiagnosable
    assert any("ConnectError" in f for f in down.findings)
    assert "incident.undiagnosable" in [a.event for a in app.store.list_for(down.id)]

    up = app.runner.run(incident(app, WORKER_166, RequestKind.check).id)
    assert up.outcome == IncidentOutcome.no_incident                  # the CLI shows HEALTHY


def test_the_real_adapter_turns_a_refused_connection_into_metrics_unavailable(monkeypatch):
    inventory = YamlInventory((ROOT / "config/inventory.yaml").read_text(encoding="utf-8"))
    signals = yaml.safe_load((ROOT / "config/signals.yaml").read_text(encoding="utf-8"))
    now = __import__("time").time()

    def fake_get(url, params=None, timeout=None):
        if url.startswith("http://argus-v18-prometheus:9090"):            # vm-095's Prometheus: stopped
            raise httpx.ConnectError("connection refused")
        body = {"data": {"result": [{"value": [now, "1" if "up{" in params["query"] else "0"]}]}}
        return httpx.Response(200, json=body, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    metrics = PrometheusMetrics(inventory, signals)
    with pytest.raises(MetricsUnavailable, match="argus-v18-prometheus:9090: ConnectError"):
        metrics.snapshot(TargetRef.parse(WORKER_095), {"restarts_10m"})
    snap = metrics.snapshot(TargetRef.parse(WORKER_166), {"restarts_10m"})   # vm-166 through the tunnel
    assert snap.values == {"restarts_10m": 0.0}
