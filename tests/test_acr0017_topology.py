"""ACR-0017 (system map): `GET /api/v1/topology[?incident_id=<id>]`.

The UI's Map tab, "Where it broke" card and Dashboard live map. Built from the inventory (targets, declared
dependencies with their ports, declared networks), the latest named signals per container (restarts, health) and
the dependency probe (`dependency_probe_min`): no new read on the hosts. With `incident_id` (operator/approver), the
incident's target and root cause get their state and **real** networks from the incident's stored `container.status`
evidence. Shown on purpose: container names, Docker networks, dependency ports. Never: VM addresses, Argus's
internal endpoints (executor and Alertmanager URLs), tokens or secrets.
"""
from __future__ import annotations

import json
import re

from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from argus.adapters.inbound.http import build_api
from argus.domain.model import EvidenceRecord, utcnow
from argus.ports.ports import MetricsUnavailable, ProbeSample, StaleMetrics
from test_core import ROOT, FakeMetrics, incident, make_app  # noqa: F401  (make_app is a fixture)

PASSWORD = "a-long-password"
CLIENT = "vm-166/container:argus-lab-client"
BACKEND = "vm-166/container:argus-lab-backend"
API = "vm-166/container:argus-lab-api"
CACHE = "vm-166/container:argus-lab-cache"


def _api(app, role="viewer"):
    app.store.upsert_principal("alice", "human", role, ["lab"], PasswordHash.recommended().hash(PASSWORD))
    api = TestClient(build_api(app))
    token = api.post("/api/v1/auth/token", data={"username": "alice", "password": PASSWORD,
                                               "scope": "read"}).json()["access_token"]
    return api, {"Authorization": f"Bearer {token}"}


def _get(api, headers, **params):
    r = api.get("/api/v1/topology", params=params, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _node(body, target):
    return next(n for n in body["nodes"] if n["target"] == target)


def _edge(body, a, b):
    return next(e for e in body["edges"] if e["from"] == a and e["to"] == b)


# --- access ---------------------------------------------------------------------------------------------------------
def test_needs_a_login_and_any_role_gets_the_map(make_app):
    app = make_app()
    assert TestClient(build_api(app)).get("/api/v1/topology").status_code == 401
    api, headers = _api(app, role="viewer")
    body = _get(api, headers)
    assert {"observed_at", "hosts", "nodes", "edges"} <= set(body)


def test_the_incident_overlay_is_for_operators_and_approvers_only(make_app):
    app = make_app()
    inc = incident(app, CLIENT)
    api, headers = _api(app, role="viewer")
    assert api.get("/api/v1/topology", params={"incident_id": inc.id}, headers=headers).status_code == 403


def test_a_bad_or_unknown_incident_id_is_refused(make_app):
    app = make_app()
    api, headers = _api(app, role="operator")
    assert api.get("/api/v1/topology", params={"incident_id": "../etc"}, headers=headers).status_code == 422
    assert api.get("/api/v1/topology", params={"incident_id": "inc_nope"}, headers=headers).status_code == 404


# --- what is shown --------------------------------------------------------------------------------------------------
def test_one_node_per_inventory_target_and_one_edge_per_declared_dependency_with_its_port(make_app):
    app = make_app()
    api, headers = _api(app)
    body = _get(api, headers)
    assert {n["target"] for n in body["nodes"]} == {str(t.ref) for t in app.inventory.targets()}
    edge = _edge(body, CLIENT, BACKEND)
    assert edge["port"] == 8080
    assert _edge(body, API, CACHE)["port"] == 6379
    client = _node(body, CLIENT)
    assert client["host"] == "vm-166" and client["label"] == "argus-lab-client" and client["kind"] == "container"
    assert {"label": "Declared networks", "value": "argus-lab-app"} in client["info"]


def test_the_dependency_probe_drives_the_edge_and_unknown_is_never_ok(make_app):
    class PerLinkMetrics(FakeMetrics):
        def dependency_probes(self, target):
            if str(target) == CLIENT:
                return {"argus-lab-backend": ProbeSample(0, 0.01, utcnow(), "refused"),
                        "argus-lab-api": ProbeSample(1, 0.01, utcnow())}
            return {}

    metrics = PerLinkMetrics({CLIENT: {"dependency_probe_min": 0, "restarts_10m": 0, "health_unhealthy": 0},
                              API: {"dependency_probe_min": 1, "restarts_10m": 0, "health_unhealthy": 0}})
    app = make_app(metrics=metrics)
    api, headers = _api(app)
    body = _get(api, headers)
    assert _edge(body, CLIENT, BACKEND)["state"] == "broken"
    assert "8080" in _edge(body, CLIENT, BACKEND)["label"]
    assert _edge(body, CLIENT, API)["state"] == "ok"
    assert _edge(body, API, CACHE)["state"] == "ok"
    leaker_db = _edge(body, "vm-166/container:argus-lab-leaker", "vm-166/container:argus-lab-db")
    assert leaker_db["state"] == "unknown"                          # no sample: unknown, never ok


def test_status_comes_from_the_signals(make_app):
    metrics = FakeMetrics({"vm-166/container:argus-lab-worker": {"restarts_10m": 4, "health_unhealthy": 0},
                           API: {"restarts_10m": 0, "health_unhealthy": 1},
                           CACHE: {"restarts_10m": 0, "health_unhealthy": 0}})
    app = make_app(metrics=metrics)
    api, headers = _api(app)
    body = _get(api, headers)
    assert _node(body, "vm-166/container:argus-lab-worker")["status"] == "restarting"
    assert _node(body, API)["status"] == "unhealthy"
    assert _node(body, CACHE)["status"] == "running"
    assert _node(body, BACKEND)["status"] == "unknown"              # no sample at all
    assert {n["status"] for n in body["nodes"]} <= {"running", "restarting", "unhealthy", "stopped", "unknown"}


def test_a_host_whose_monitoring_is_down_is_unknown_not_ok(make_app):
    class Down(FakeMetrics):
        def snapshot(self, target, signals):
            if target.host == "vm-166":
                raise MetricsUnavailable("prometheus down")
            raise StaleMetrics("no fresh samples")
    app = make_app(metrics=Down())
    api, headers = _api(app)
    body = _get(api, headers)
    assert {n["status"] for n in body["nodes"]} == {"unknown"}
    assert {e["state"] for e in body["edges"] if e["state"] != "read"} == {"unknown"}


def test_the_argus_host_is_marked_and_reads_the_monitored_hosts(make_app, monkeypatch):
    monkeypatch.setenv("ARGUS_HOME_HOST", "vm-095")
    app = make_app()
    api, headers = _api(app)
    body = _get(api, headers)
    roles = {h["id"]: h["role"] for h in body["hosts"]}
    assert roles == {"vm-095": "argus", "vm-166": "monitored"}
    assert _edge(body, "vm-095/host:vm-095", "vm-166/host:vm-166")["state"] == "read"


def test_without_a_home_host_every_host_is_monitored_and_there_is_no_read_edge(make_app, monkeypatch):
    monkeypatch.delenv("ARGUS_HOME_HOST", raising=False)
    app = make_app()
    api, headers = _api(app)
    body = _get(api, headers)
    assert {h["role"] for h in body["hosts"]} == {"monitored"}
    assert not [e for e in body["edges"] if e["state"] == "read"]


# --- never --------------------------------------------------------------------------------------------------------
def test_no_vm_address_internal_endpoint_or_secret_in_the_answer(make_app, monkeypatch):
    monkeypatch.setenv("ARGUS_HOME_HOST", "vm-095")
    app = make_app()
    inc = incident(app, CLIENT)
    api, headers = _api(app, role="operator")
    text = json.dumps(_get(api, headers)) + json.dumps(_get(api, headers, incident_id=inc.id))
    for h in app.inventory.hosts():
        for url in [*h.executors.values(), h.alertmanager or ""]:
            if url:
                assert url not in text
                assert re.sub(r"^https?://", "", url).split("/")[0] not in text      # nor its host:port
    assert not re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text)                      # no IP address
    assert "http://" not in text and "https://" not in text
    assert "token" not in text.lower()


# --- the incident overlay -------------------------------------------------------------------------------------------
def _status_evidence(app, inc, target, networks, state="running", restarts=0):
    app.store.append_evidence(EvidenceRecord(
        evidence_id=f"obs_{target.split(':')[-1]}", incident_id=inc.id, kind="observation",
        capability="container.status", target=target, host="vm-166", executor="docker_read", caller="strategy:baseline",
        source_time=utcnow(), collected_at=utcnow(), status="ok",
        values={"values": {"state": state, "health": "healthy", "restart_count": restarts, "oom_killed": False,
                           "exit_code": 0, "networks": networks, "memory_limit_bytes": 536870912},
                "units": {"memory_limit_bytes": "bytes"}},
        model_text="status").with_hash())


def test_the_overlay_shows_the_real_networks_and_names_the_broken_link(make_app):
    app = make_app()
    inc = incident(app, CLIENT)
    inc.root_cause_target = BACKEND
    app.store.update_incident(inc)
    _status_evidence(app, inc, CLIENT, ["argus-lab-app"])
    _status_evidence(app, inc, BACKEND, ["argus-lab-iso"])
    api, headers = _api(app, role="operator")
    body = _get(api, headers, incident_id=inc.id)
    assert body["incident_id"] == inc.id
    backend = _node(body, BACKEND)
    assert {"label": "Networks (at the incident)", "value": "argus-lab-iso"} in backend["info"]
    assert {"label": "Memory limit", "value": "512 MiB"} in backend["info"]
    assert backend["status"] == "running"
    edge = _edge(body, CLIENT, BACKEND)
    assert edge["state"] == "broken" and "no shared network" in edge["label"]


def test_the_overlay_maps_an_exited_container_to_stopped(make_app):
    app = make_app()
    inc = incident(app, "vm-166/container:argus-lab-worker")
    _status_evidence(app, inc, "vm-166/container:argus-lab-worker", ["argus-lab-app"], state="exited", restarts=5)
    api, headers = _api(app, role="operator")
    body = _get(api, headers, incident_id=inc.id)
    assert _node(body, "vm-166/container:argus-lab-worker")["status"] == "stopped"


# --- cost -----------------------------------------------------------------------------------------------------------
def test_the_global_map_is_shared_for_a_short_time(make_app):
    class Counting(FakeMetrics):
        calls = 0

        def snapshot(self, target, signals):
            Counting.calls += 1
            return super().snapshot(target, signals)
    app = make_app(metrics=Counting())
    api, headers = _api(app)
    _get(api, headers)
    first = Counting.calls
    assert first > 0
    _get(api, headers)
    assert Counting.calls == first                                   # served from the 20 s snapshot
