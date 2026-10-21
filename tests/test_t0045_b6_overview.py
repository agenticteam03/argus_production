"""T-0045 step B6, second half (ACR-0021): `GET /api/v1/overview`, the dashboard in one answer.

Built only from what Argus already has: the stored incidents, the shared topology snapshot (B3) and the shared
host-metrics snapshot (B1). No new host read and no executor call. One shared answer for 15 s. Any role may read it.
`status` is the worst severity among the open incidents (`ok` when none is open); an open incident whose class is not
known yet counts as `info`.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from argus.adapters.inbound.http import build_api
from argus.application.overview import Overview
from argus.domain.model import IncidentStatus, utcnow
from test_acr0017_incident_metrics import _api
from test_core import FakeMetrics, FakeTargetAgent, incident, make_app  # noqa: F401  (make_app is a fixture)

WORKER = "vm-166/container:argus-lab-worker"
API = "vm-166/container:argus-lab-api"
HOST = "vm-166/host:vm-166"
HOSTS = {"vm-095/host:vm-095": {"host_cpu_busy_ratio": 0.25, "host_memory_available_ratio": 0.4,
                                "host_disk_used_ratio": 0.7},
         HOST: {"host_cpu_busy_ratio": 0.8, "host_memory_available_ratio": 0.4, "host_disk_used_ratio": 0.9}}


def _inc(app, target, cls=None, status=None, minutes_ago=10, closed_minutes_ago=None):
    # opened_at is given at creation: the stores sort by the opened_at column, which an update does not change
    inc = incident(app, target, opened_at=utcnow() - timedelta(minutes=minutes_ago))
    inc.incident_class = cls
    if status:
        inc.status = status
    if closed_minutes_ago is not None:
        inc.closed_at = utcnow() - timedelta(minutes=closed_minutes_ago)
    app.store.update_incident(inc)
    return inc


def _overview(app, role="viewer"):
    api, h = _api(app, role=role)
    r = api.get("/api/v1/overview", headers=h)
    assert r.status_code == 200, r.text
    return r.json(), api, h


# --- the answer ----------------------------------------------------------------------------------------------------------
def test_open_incidents_are_counted_by_severity_and_the_worst_one_is_the_status(make_app):
    app = make_app(metrics=FakeMetrics(HOSTS))
    loop = _inc(app, WORKER, "container_restart_loop", minutes_ago=30)            # critical
    blind = _inc(app, HOST, "monitoring_blind_spot", minutes_ago=20)              # warning
    fresh = _inc(app, API, minutes_ago=5)                                         # no class yet: info
    _inc(app, API, "dependency_unavailable", IncidentStatus.closed, 60, closed_minutes_ago=40)
    _inc(app, WORKER, "container_restart_loop", IncidentStatus.escalated, 50, closed_minutes_ago=45)
    body, _, _ = _overview(app)
    assert body["status"] == "critical"
    assert body["open_incidents"] == {"critical": 1, "warning": 1, "info": 1}
    assert [i["id"] for i in body["latest_open"]] == [fresh.id, blind.id, loop.id]   # newest first
    first = body["latest_open"][2]
    assert first["target"] == WORKER and first["host"] == "vm-166" and first["severity"] == "critical"
    assert first["kind"] == "restart_loop" and first["summary"] and first["next_action"] is None
    assert body["latest_open"][0]["severity"] == "info" and body["latest_open"][0]["kind"] is None


def test_with_nothing_open_the_status_is_ok_and_the_last_close_is_given(make_app):
    app = make_app(metrics=FakeMetrics(HOSTS))
    _inc(app, API, "dependency_unavailable", IncidentStatus.closed, 60, closed_minutes_ago=40)
    late = _inc(app, WORKER, "container_restart_loop", IncidentStatus.escalated, 30, closed_minutes_ago=20)
    body, _, _ = _overview(app)
    assert body["status"] == "ok" and body["open_incidents"] == {"critical": 0, "warning": 0, "info": 0}
    assert body["latest_open"] == []
    assert body["last_closed_at"] == app.store.get_incident(late.id).closed_at.isoformat()


def test_an_empty_store_answers_too(make_app):
    body, _, _ = _overview(make_app(metrics=FakeMetrics(HOSTS)))
    assert body["status"] == "ok" and body["last_closed_at"] is None and body["latest_open"] == []


def test_the_hosts_are_the_host_metrics_answer(make_app):
    app = make_app(metrics=FakeMetrics(HOSTS))
    body, api, h = _overview(app)
    assert body["hosts"] == api.get("/api/v1/host-metrics", headers=h).json()
    assert {r["host"] for r in body["hosts"]} == {"vm-095", "vm-166"}
    assert all({"thresholds", "heartbeat_age_s", "heartbeat_stale"} <= set(r) for r in body["hosts"])


def test_fleet_and_links_are_counted_from_the_topology_snapshot(make_app):
    app = make_app(metrics=FakeMetrics(HOSTS))
    body, api, h = _overview(app)
    topo = api.get("/api/v1/topology", headers=h).json()
    assert set(body["fleet"]) == {"healthy", "degraded", "failed", "unknown", "idle"}
    assert sum(body["fleet"].values()) == len(topo["nodes"])
    for health, n in body["fleet"].items():
        assert n == sum(1 for x in topo["nodes"] if x["health"] == health), health
    deps = [e for e in topo["edges"] if e["kind"] == "dependency"]
    assert body["links"] == {"ok": sum(1 for e in deps if e["state"] == "ok"), "total": len(deps)}


def test_no_executor_is_called(make_app):
    app = make_app(metrics=FakeMetrics(HOSTS))
    _inc(app, WORKER, "container_restart_loop")
    FakeTargetAgent.calls = []
    _overview(app)
    assert FakeTargetAgent.calls == []


# --- who may read it -----------------------------------------------------------------------------------------------------
def test_any_role_reads_it_and_a_login_is_required(make_app):
    app = make_app(metrics=FakeMetrics(HOSTS))
    for role in ("viewer", "operator", "approver"):
        _overview(app, role=role)
    assert TestClient(build_api(app)).get("/api/v1/overview").status_code == 401


def test_the_answer_holds_no_address_or_internal_url(make_app):
    app = make_app(metrics=FakeMetrics(HOSTS))
    _inc(app, WORKER, "container_restart_loop")
    body, api, h = _overview(app)
    text = api.get("/api/v1/overview", headers=h).text
    urls = {u for host in app.inventory.hosts() for u in host.executors.values()}
    assert not re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", text) and "http" not in text
    assert not any(u in text for u in urls)


# --- the shared cache ----------------------------------------------------------------------------------------------------
class _Store:
    def __init__(self):
        self.calls, self.rows = 0, []

    def list_incidents(self, limit):
        self.calls += 1
        return self.rows


class _Topology:
    def view(self):
        return {"nodes": [], "edges": []}


def test_one_shared_answer_for_15_seconds():
    store, clock = _Store(), [0.0]
    ov = Overview(store, _Topology(), lambda: [], now=lambda: datetime(2026, 10, 19, tzinfo=timezone.utc),
                  clock=lambda: clock[0])
    first = ov.view()
    assert ov.view() is first and store.calls == 1
    clock[0] = 16
    ov.view()
    assert store.calls == 2
