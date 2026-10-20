"""T-0045 step B8 (ACR-0021, optional): finer link reasons. The exporter says why a dependency probe failed
(`argus_probe_error{owner,dependency,kind}`), and the map's broken link says it in plain words instead of the generic
"not reachable"."""
from __future__ import annotations

import socket
from datetime import datetime, timezone

import pytest

from argus.adapters.outbound.config_adapters import PrometheusMetrics, YamlInventory
from argus.domain.model import TargetRef
from argus.infrastructure.wiring import read_signals
from argus.ports.ports import ProbeSample
from test_core import ROOT
from test_sc07_network import _target_service
from test_t0045_b3_topology import INVENTORY, NOW, Metrics, edge, topo


# --- the exporter: the exception type gives the kind -------------------------------------------------------------------
@pytest.mark.parametrize("exc, kind", [
    (ConnectionRefusedError(111, "Connection refused"), "refused"),
    (socket.timeout("timed out"), "timeout"),
    (TimeoutError("timed out"), "timeout"),
    (socket.gaierror(-2, "Name or service not known"), "dns"),
    (OSError(113, "No route to host"), "other"),
])
def test_the_exception_type_gives_the_failure_kind(tmp_path, monkeypatch, exc, kind):
    svc = _target_service(tmp_path, monkeypatch)

    def fail(*a, **k):
        raise exc
    monkeypatch.setattr(svc.socket, "create_connection", fail)
    r = svc.tcp("argus-lab-cache", 6379)
    assert r["ok"] is False and r["kind"] == kind


def test_a_failed_probe_exports_its_kind_and_a_good_one_none(tmp_path, monkeypatch):
    svc = _target_service(tmp_path, monkeypatch)
    probes = [{"owner": "argus-lab-api", "dependency": "argus-lab-cache", "host": "argus-lab-cache", "port": 6379},
              {"owner": "argus-lab-api", "dependency": "argus-lab-db", "host": "argus-lab-db", "port": 5432}]
    monkeypatch.setattr(svc, "tcp", lambda host, port: {"ok": True, "duration_ms": 1.0} if host == "argus-lab-db"
                        else {"ok": False, "kind": "refused", "duration_ms": 1.0})
    lines = svc.probe_lines(probes, active={"argus-lab-api"})
    assert 'argus_probe_error{owner="argus-lab-api",dependency="argus-lab-cache",kind="refused"} 1' in lines
    assert not any(ln.startswith("argus_probe_error") and "argus-lab-db" in ln for ln in lines)


# --- the adapter reads the kind with the probe -------------------------------------------------------------------------
def test_the_prometheus_adapter_reads_the_failure_kind(monkeypatch):
    now = datetime.now(timezone.utc).timestamp()
    answers = {
        "argus_probe_success": [{"metric": {"dependency": "db"}, "value": [now, "1"]},
                                {"metric": {"dependency": "cache"}, "value": [now, "0"]}],
        "argus_probe_duration_seconds": [{"metric": {"dependency": "cache"}, "value": [now, "3.0"]}],
        "argus_probe_error": [{"metric": {"dependency": "cache", "kind": "timeout"}, "value": [now, "1"]},
                              {"metric": {"dependency": "db", "kind": "refused"}, "value": [now - 600, "1"]}]}

    class R:
        def __init__(self, result): self.result = result
        def raise_for_status(self): pass
        def json(self): return {"data": {"result": self.result}}

    monkeypatch.setattr("argus.adapters.outbound.config_adapters.httpx.get",
                        lambda url, params=None, timeout=None: R(next(v for k, v in answers.items()
                                                                      if params["query"].startswith(k))))
    probes = PrometheusMetrics(YamlInventory(INVENTORY), read_signals(ROOT / "config"), 90).dependency_probes(
        TargetRef.parse("h1/container:web"))
    assert probes["cache"].error_kind == "timeout"
    assert probes["db"].error_kind is None                          # stale: no reason, never an old one


# --- the map: a broken link says why ---------------------------------------------------------------------------------
@pytest.mark.parametrize("kind, reason", [("refused", "connection refused"), ("timeout", "timeout"),
                                          ("dns", "name not resolved"), ("other", "not reachable"),
                                          (None, "not reachable")])
def test_a_broken_link_says_why(kind, reason):
    body = topo(Metrics({}, {"h1/container:web": {"db": ProbeSample(1, 0.01, NOW),
                                                  "cache": ProbeSample(0, 3.0, NOW, kind)}})).view()
    broken = edge(body, "web", "cache")
    assert broken["state"] == "broken" and broken["reason"] == reason and broken["label"] == f"tcp 6379 · {reason}"
    assert edge(body, "web", "db")["reason"] is None


def test_a_good_link_ignores_a_leftover_kind():
    body = topo(Metrics({}, {"h1/container:web": {"db": ProbeSample(1, 0.01, NOW, "refused")}})).view()
    assert edge(body, "web", "db")["state"] == "ok" and edge(body, "web", "db")["reason"] is None
