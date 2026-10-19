"""T-0045 step B3 (ACR-0021): the system map with box health and problems, one state per dependency link, the roles and the
cause path of an incident. Built from the inventory, the MetricsPort and the store only: no executor call."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from argus.adapters.inbound.http import build_api
from argus.adapters.outbound.config_adapters import PrometheusMetrics, YamlInventory
from argus.application.thresholds import Thresholds
from argus.application.topology import Topology
from argus.domain.model import EvidenceRecord, TargetRef, utcnow
from argus.ports.ports import MetricsUnavailable, ProbeSample
from argus.infrastructure.wiring import read_signals
from test_core import ROOT, FakeMetrics, FakeTargetAgent, incident, make_app  # noqa: F401  (make_app is a fixture)

INVENTORY = """
hosts:
  h1: {executors: {prometheus: "http://prom.internal:9090"}}
targets:
  - ref: h1/host:h1
  - ref: h1/container:web
    depends_on: [h1/container:db, h1/container:cache]
  - ref: h1/container:db
    tcp_ports: [5432]
    networks: [appnet]
  - ref: h1/container:cache
    tcp_ports: [6379]
  - ref: h1/container:burner
    profile: scenario
  - ref: h1/container:slowlink
    depends_on: [h1/container:db]
    link_warning_ms: 400
"""
THRESHOLDS = Thresholds.from_data({
    "restarts_10m": {"warning": 2, "critical": 3, "direction": "above"},
    "container_cpu_quota_used_ratio_5m": {"warning": 0.7, "critical": 0.8, "direction": "above"}},
    {"restarts_10m", "container_cpu_quota_used_ratio_5m"})
NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)


class Metrics(FakeMetrics):
    def __init__(self, by_target=None, probes=None, down=False):
        super().__init__(by_target or {})
        self.probes, self.down, self.executor_calls = probes or {}, down, 0

    def dependency_probes(self, target):
        if self.down:
            raise MetricsUnavailable("prometheus down")
        return self.probes.get(str(target), {})


class NoStore:
    def list_evidence(self, incident_id):
        return []


def topo(metrics, thresholds=THRESHOLDS):
    return Topology(YamlInventory(INVENTORY), metrics, NoStore(), now=lambda: NOW, thresholds=thresholds)


def node(body, name):
    return next(n for n in body["nodes"] if n["id"] == f"h1/container:{name}" or n["id"] == name)


def edge(body, a, b):
    return next(e for e in body["edges"] if e["from"] == f"h1/container:{a}" and e["to"] == f"h1/container:{b}")


def sample(success, duration=0.01, age=5):
    return ProbeSample(success, duration, NOW - timedelta(seconds=age))


# --- one state per dependency (red before: an owner with two dependencies showed both `unknown`) ---------------------------
def test_an_owner_with_two_dependencies_gets_two_independent_link_states():
    body = topo(Metrics({"h1/container:web": {"restarts_10m": 0, "dependency_probe_min": 0}},
                        {"h1/container:web": {"db": sample(1), "cache": sample(0)}})).view()
    assert edge(body, "web", "db")["state"] == "ok"
    broken = edge(body, "web", "cache")
    assert broken["state"] == "broken" and broken["reason"] == "not reachable" and "not reachable" in broken["label"]


def test_a_stale_or_missing_probe_is_unknown_never_ok():
    body = topo(Metrics({}, {"h1/container:web": {"db": ProbeSample(None, None, NOW)}})).view()
    assert edge(body, "web", "db")["state"] == "unknown" and edge(body, "web", "cache")["state"] == "unknown"
    assert edge(body, "web", "db")["latency_ms"] is None


def test_a_slow_answer_is_slow_and_the_owner_may_set_its_own_limit():
    probes = {"h1/container:web": {"db": sample(1, 0.25), "cache": sample(1, 0.05)},
              "h1/container:slowlink": {"db": sample(1, 0.25)}}
    body = topo(Metrics({}, probes)).view()
    assert edge(body, "web", "db")["state"] == "slow" and edge(body, "web", "db")["latency_ms"] == 250.0   # default 100 ms
    assert edge(body, "web", "cache")["state"] == "ok"
    assert edge(body, "slowlink", "db")["state"] == "ok"                                                   # its own 400 ms


def test_a_link_says_when_it_was_checked_and_has_a_stable_id_and_kind():
    body = topo(Metrics({}, {"h1/container:web": {"db": sample(1, age=5)}})).view()
    e = edge(body, "web", "db")
    assert e["id"] == "h1/container:web->h1/container:db:5432" and e["kind"] == "dependency"
    assert e["checked_at"] == "2026-10-18T11:59:55Z"
    assert edge(body, "web", "cache")["checked_at"] is None


def test_a_monitoring_outage_leaves_the_links_unknown():
    body = topo(Metrics({}, down=True)).view()
    assert {e["state"] for e in body["edges"] if e["kind"] == "dependency"} == {"unknown"}


def test_argus_read_edges_have_their_own_kind():
    t = Topology(YamlInventory(INVENTORY.replace("h1: {executors", "h2: {executors: {}}\n  h1: {executors")), Metrics(),
                 NoStore(), home_host="h1", now=lambda: NOW)
    reads = [e for e in t.view()["edges"] if e["state"] == "read"]
    assert reads and all(e["kind"] == "argus_reads" and e["id"] for e in reads)


# --- health, idle, problems -------------------------------------------------------------------------------------------
def test_health_idle_and_unknown():
    body = topo(Metrics({"h1/container:web": {"restarts_10m": 0, "health_unhealthy": 0},
                         "h1/container:db": {"restarts_10m": 1, "health_unhealthy": 1}})).view()
    assert node(body, "web")["health"] == "healthy" and node(body, "web")["idle"] is False
    assert node(body, "db")["health"] == "degraded"                                    # unhealthy
    assert node(body, "cache")["health"] == "unknown" and node(body, "cache")["idle"] is False
    assert node(body, "burner")["health"] == "idle" and node(body, "burner")["idle"] is True   # scenario-only, no sample


def test_a_running_scenario_container_is_not_idle():
    body = topo(Metrics({"h1/container:burner": {"restarts_10m": 0, "health_unhealthy": 0}})).view()
    assert node(body, "burner")["health"] == "healthy" and node(body, "burner")["idle"] is False


def test_restart_problems_use_the_catalogue_thresholds():
    body = topo(Metrics({"h1/container:web": {"restarts_10m": 2}, "h1/container:db": {"restarts_10m": 4},
                         "h1/container:cache": {"restarts_10m": 0}})).view()
    assert node(body, "cache")["problems"] == [] and node(body, "cache")["health"] == "healthy"
    warn, = node(body, "web")["problems"]
    assert warn["severity"] == "warning" and warn["signal"] == "restarts_10m" and warn["value"] == 2
    assert warn["threshold"] == 2 and set(warn) == {"kind", "severity", "summary", "signal", "value", "threshold", "unit"}
    assert node(body, "web")["health"] == "degraded"
    crit, = node(body, "db")["problems"]
    assert crit["severity"] == "critical" and crit["threshold"] == 3 and node(body, "db")["health"] == "failed"


def test_cpu_quota_problem_is_shown_in_percent():
    body = topo(Metrics({"h1/container:web": {"restarts_10m": 0, "container_cpu_quota_used_ratio_5m": 0.85}})).view()
    p, = node(body, "web")["problems"]
    assert (p["kind"], p["severity"], p["value"], p["threshold"], p["unit"]) == ("cpu_quota", "critical", 85.0, 80.0, "%")


def test_an_unhealthy_check_is_a_warning_problem():
    body = topo(Metrics({"h1/container:web": {"restarts_10m": 0, "health_unhealthy": 1}})).view()
    p, = node(body, "web")["problems"]
    assert p["signal"] == "health_unhealthy" and p["severity"] == "warning"


def test_networks_are_the_declared_ones():
    body = topo(Metrics()).view()
    assert node(body, "db")["networks"] == ["appnet"] and node(body, "web")["networks"] == []


def test_inventory_profile_and_link_limit_are_validated():
    with pytest.raises(ValueError, match="profile"):
        YamlInventory(INVENTORY.replace("profile: scenario", "profile: sometimes"))
    with pytest.raises(ValueError, match="link_warning_ms"):
        YamlInventory(INVENTORY.replace("link_warning_ms: 400", "link_warning_ms: -5"))


# --- the Prometheus adapter -------------------------------------------------------------------------------------------
def test_the_prometheus_adapter_groups_the_probes_by_dependency(monkeypatch):
    now = datetime.now(timezone.utc).timestamp()
    answers = {
        "argus_probe_success": [{"metric": {"dependency": "db"}, "value": [now, "1"]},
                                {"metric": {"dependency": "cache"}, "value": [now - 600, "0"]}],
        "argus_probe_duration_seconds": [{"metric": {"dependency": "db"}, "value": [now, "0.042"]}]}
    queries = []

    class R:
        def __init__(self, result): self.result = result
        def raise_for_status(self): pass
        def json(self): return {"data": {"result": self.result}}

    def fake_get(url, params=None, timeout=None):
        queries.append(params["query"])
        return R(next(v for k, v in answers.items() if params["query"].startswith(k)))
    monkeypatch.setattr("argus.adapters.outbound.config_adapters.httpx.get", fake_get)
    metrics = PrometheusMetrics(YamlInventory(INVENTORY), read_signals(ROOT / "config"), 90)
    probes = metrics.dependency_probes(TargetRef.parse("h1/container:web"))
    assert probes["db"].success == 1 and probes["db"].duration_s == 0.042
    assert probes["cache"].success is None                          # older than max_staleness_s: missing, not 0
    assert all('argus_host="h1"' in q and 'owner="web"' in q for q in queries) and len(queries) == 2


# --- the incident overlay: roles and the cause path --------------------------------------------------------------------
PASSWORD = "a-long-password"
CLIENT, BACKEND = "vm-166/container:argus-lab-client", "vm-166/container:argus-lab-backend"
API, CACHE = "vm-166/container:argus-lab-api", "vm-166/container:argus-lab-cache"


def _api(app):
    app.store.upsert_principal("alice", "human", "operator", ["lab"], PasswordHash.recommended().hash(PASSWORD))
    api = TestClient(build_api(app))
    token = api.post("/api/v1/auth/token", data={"username": "alice", "password": PASSWORD, "scope": "read"}).json()["access_token"]
    return api, {"Authorization": f"Bearer {token}"}


def _status(app, inc, target, **data):
    values = {"state": "running", "health": "healthy", "restart_count": 0, "oom_killed": False, "exit_code": 0,
              "networks": ["argus-lab-app"], "memory_limit_bytes": 64 * 1048576, **data}
    app.store.append_evidence(EvidenceRecord(
        evidence_id=f"obs_{target.split(':')[-1]}", incident_id=inc.id, kind="observation", capability="container.status",
        target=target, host="vm-166", executor="docker_read", caller="strategy:baseline", source_time=utcnow(),
        collected_at=utcnow(), status="ok", values={"values": values, "units": {}}, model_text="status").with_hash())


def _overlay(app, target, root=None):
    inc = incident(app, target)
    inc.root_cause_target = root
    app.store.update_incident(inc)
    return inc


def _get(api, h, **params):
    r = api.get("/api/v1/topology", params=params, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _by_target(body):
    return {n["target"]: n for n in body["nodes"]}


def test_sc03_cause_path_and_roles(make_app):
    app = make_app()
    inc = _overlay(app, API, CACHE)
    api, h = _api(app)
    body = _get(api, h, incident_id=inc.id)
    nodes = _by_target(body)
    assert body["cause_path"] == [API, CACHE]
    assert nodes[API]["role"] == "affected" and nodes[CACHE]["role"] == "root_cause"
    assert "role" not in nodes[BACKEND] or nodes[BACKEND]["role"] is None


def test_sc07_cause_path_and_roles(make_app):
    app = make_app()
    inc = _overlay(app, CLIENT, BACKEND)
    api, h = _api(app)
    body = _get(api, h, incident_id=inc.id)
    assert body["cause_path"] == [CLIENT, BACKEND]
    assert _by_target(body)[CLIENT]["role"] == "affected" and _by_target(body)[BACKEND]["role"] == "root_cause"


def test_a_target_that_is_its_own_root_cause_and_an_incident_without_one(make_app):
    app = make_app()
    alone, none = _overlay(app, CLIENT, CLIENT), _overlay(app, CLIENT, None)
    api, h = _api(app)
    same = _get(api, h, incident_id=alone.id)
    assert same["cause_path"] == [CLIENT] and _by_target(same)[CLIENT]["role"] == "root_cause"
    assert _get(api, h, incident_id=none.id)["cause_path"] == []


def test_nodes_between_are_on_path():
    inv = YamlInventory(INVENTORY.replace("  - ref: h1/container:burner\n    profile: scenario\n",
        "  - ref: h1/container:burner\n    profile: scenario\n    depends_on: [h1/container:web]\n"))
    t = Topology(inv, Metrics(), NoStore(), now=lambda: NOW)
    inc = incident_obj("h1/container:burner", "h1/container:db")
    body = t.view_for(inc)
    roles = {n["id"]: n.get("role") for n in body["nodes"]}
    assert body["cause_path"] == ["h1/container:burner", "h1/container:web", "h1/container:db"]
    assert roles["h1/container:web"] == "on_path" and roles["h1/container:burner"] == "affected"


def incident_obj(target, root):
    from argus.domain.model import Incident, RequestKind, TriggerKind
    return Incident(id="inc_x", target=TargetRef.parse(target), trigger_kind=TriggerKind.manual, request_kind=RequestKind.report,
                    reason="t", principal="p", trigger_id="t", opened_at=NOW, root_cause_target=root)


def test_the_overlay_replaces_networks_and_checks_memory_against_the_limit(make_app):
    app = make_app(metrics=FakeMetrics({BACKEND: {"restarts_10m": 0, "health_unhealthy": 0,
                                                  "container_memory_bytes": 62.7 * 1048576}}))
    inc = _overlay(app, CLIENT, BACKEND)
    _status(app, inc, CLIENT)
    _status(app, inc, BACKEND, networks=["argus-lab-iso"])
    api, h = _api(app)
    backend = _by_target(_get(api, h, incident_id=inc.id))[BACKEND]
    assert backend["networks"] == ["argus-lab-iso"]
    mem, = [p for p in backend["problems"] if p["signal"] == "container_memory_bytes"]
    assert mem["unit"] == "MiB" and mem["value"] == 62.7 and mem["severity"] == "critical" and mem["threshold"] == 57.6
    assert backend["health"] == "failed"


def test_a_running_container_without_any_fresh_sample_is_stale_metrics(make_app):
    app = make_app()
    inc = _overlay(app, CLIENT, BACKEND)
    _status(app, inc, CLIENT)
    api, h = _api(app)
    client = _by_target(_get(api, h, incident_id=inc.id))[CLIENT]
    assert [(p["kind"], p["severity"]) for p in client["problems"]] == [("stale_metrics", "warning")]
    assert client["health"] == "degraded"


def test_an_exited_container_is_failed(make_app):
    app = make_app()
    inc = _overlay(app, "vm-166/container:argus-lab-worker", None)
    _status(app, inc, "vm-166/container:argus-lab-worker", state="exited")
    api, h = _api(app)
    assert _by_target(_get(api, h, incident_id=inc.id))["vm-166/container:argus-lab-worker"]["health"] == "failed"


# --- never ------------------------------------------------------------------------------------------------------------------
def test_no_address_url_or_secret_and_no_executor_call(make_app, monkeypatch):
    monkeypatch.setenv("ARGUS_HOME_HOST", "vm-095")
    app = make_app()
    inc = _overlay(app, CLIENT, BACKEND)
    _status(app, inc, CLIENT)
    _status(app, inc, BACKEND, networks=["argus-lab-iso"])
    api, h = _api(app)
    text = json.dumps(_get(api, h)) + json.dumps(_get(api, h, incident_id=inc.id))
    assert not re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text) and "://" not in text and "token" not in text.lower()
    assert FakeTargetAgent.calls == []                                         # only the MetricsPort and the store
