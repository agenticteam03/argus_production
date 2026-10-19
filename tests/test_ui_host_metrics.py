"""The public UI receives only bounded, named host metrics, never PromQL."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from argus.adapters.inbound.http import build_api
from test_core import FakeMetrics, make_app  # noqa: F401


def test_read_token_gets_live_host_metrics_and_missing_values_stay_unknown(make_app):
    metrics = FakeMetrics({
        "vm-095/host:vm-095": {"host_cpu_busy_ratio": 0.25, "host_memory_available_ratio": 0.4,
                               "host_disk_used_ratio": 0.7},
        "vm-166/host:vm-166": {"host_cpu_busy_ratio": 0.8, "host_memory_available_ratio": None,
                               "host_disk_used_ratio": 1.5},
    })
    app = make_app(metrics=metrics)
    app.store.upsert_principal("alice", "human", "viewer", ["lab"], PasswordHash.recommended().hash("long-password"))
    api = TestClient(build_api(app))
    token = api.post("/api/v1/auth/token", data={"username": "alice", "password": "long-password",
                                               "scope": "read"}).json()["access_token"]
    response = api.get("/api/v1/host-metrics", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    rows = response.json()
    assert [row["host"] for row in rows] == ["vm-095", "vm-166"]
    assert rows[0]["values"] == {"cpu_busy_ratio": 0.25, "memory_used_ratio": 0.6, "disk_used_ratio": 0.7}
    assert rows[1]["values"]["memory_used_ratio"] is None
    assert rows[1]["values"]["disk_used_ratio"] is None  # invalid ratios are never shown as percentages
    assert rows[0]["observed_at"]


def test_host_metrics_requires_auth_and_does_not_fail_all_hosts_when_one_is_stale(make_app):
    class OneHostDown(FakeMetrics):
        def snapshot(self, target, signals):
            if target.host == "vm-166":
                from argus.ports.ports import StaleMetrics
                raise StaleMetrics("private backend detail")
            return super().snapshot(target, signals)

    app = make_app(metrics=OneHostDown({"vm-095/host:vm-095": {"host_cpu_busy_ratio": 0.1}}))
    app.store.upsert_principal("alice", "human", "viewer", ["lab"], PasswordHash.recommended().hash("long-password"))
    api = TestClient(build_api(app))
    assert api.get("/api/v1/host-metrics").status_code == 401
    token = api.post("/api/v1/auth/token", data={"username": "alice", "password": "long-password",
                                               "scope": "read"}).json()["access_token"]
    rows = api.get("/api/v1/host-metrics", headers={"Authorization": f"Bearer {token}"}).json()
    assert rows[0]["available"] is True
    assert {k: v for k, v in rows[1].items() if k not in ("thresholds", "heartbeat_age_s", "heartbeat_stale")} == {
        "host": "vm-166", "target": "vm-166/host:vm-166", "available": False, "observed_at": None,
        "values": {"cpu_busy_ratio": None, "memory_used_ratio": None, "disk_used_ratio": None}}   # + ACR-0021 fields


def test_host_metrics_reuses_a_short_snapshot_for_concurrent_dashboard_clients(make_app):
    class CountingMetrics(FakeMetrics):
        calls = 0

        def snapshot(self, target, signals):
            self.calls += 1
            return super().snapshot(target, signals)

    metrics = CountingMetrics({"vm-095/host:vm-095": {"host_cpu_busy_ratio": 0.1}})
    app = make_app(metrics=metrics)
    app.store.upsert_principal("alice", "human", "viewer", ["lab"], PasswordHash.recommended().hash("long-password"))
    api = TestClient(build_api(app))
    token = api.post("/api/v1/auth/token", data={"username": "alice", "password": "long-password",
                                               "scope": "read"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert api.get("/api/v1/host-metrics", headers=headers).status_code == 200
    assert api.get("/api/v1/host-metrics", headers=headers).status_code == 200
    assert metrics.calls == 2  # once per inventory host, not once per viewer and poll


def viewer_headers(app, api):
    app.store.upsert_principal("alice", "human", "viewer", ["lab"], PasswordHash.recommended().hash("long-password"))
    token = api.post("/api/v1/auth/token", data={"username": "alice", "password": "long-password",
                                               "scope": "read"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_a_slow_host_is_answered_unavailable_within_the_budget_and_never_blocks_the_other(make_app):
    release = threading.Event()

    class SlowHost(FakeMetrics):
        def snapshot(self, target, signals):
            if target.host == "vm-166":
                release.wait(10)                          # a Prometheus query near its own timeout
            return super().snapshot(target, signals)

    metrics = SlowHost({"vm-095/host:vm-095": {"host_cpu_busy_ratio": 0.1}})
    app = make_app(metrics=metrics)
    built = build_api(app)
    built.state.host_metrics_budget_s = 0.3
    api = TestClient(built)
    headers = viewer_headers(app, api)
    try:
        started = time.monotonic()
        rows = api.get("/api/v1/host-metrics", headers=headers).json()
        assert time.monotonic() - started < 3
        assert rows[0]["available"] is True and rows[1]["available"] is False
    finally:
        release.set()


def test_a_slow_host_is_read_once_at_a_time_and_concurrent_viewers_do_not_queue_on_it(make_app):
    release = threading.Event()

    class SlowHost(FakeMetrics):
        calls = 0

        def snapshot(self, target, signals):
            if target.host == "vm-166":
                type(self).calls += 1
                release.wait(10)
            return super().snapshot(target, signals)

    app = make_app(metrics=SlowHost({}))
    built = build_api(app)
    built.state.host_metrics_budget_s = 0.2
    api = TestClient(built)
    headers = viewer_headers(app, api)
    try:
        started = time.monotonic()
        with ThreadPoolExecutor(4) as pool:              # four viewers arrive while the cache is cold
            codes = list(pool.map(lambda _: api.get("/api/v1/host-metrics", headers=headers).status_code, range(4)))
        assert codes == [200] * 4
        assert time.monotonic() - started < 3            # none waited behind another's Prometheus I/O
        assert SlowHost.calls == 1                       # they share the one read still running: nothing piles up
    finally:
        release.set()


def test_a_malformed_prometheus_answer_is_one_unavailable_host_not_a_500(make_app):
    class BadJson(FakeMetrics):
        def snapshot(self, target, signals):
            if target.host == "vm-166":
                raise ValueError("Expecting value: line 1 column 1")
            return super().snapshot(target, signals)

    app = make_app(metrics=BadJson({"vm-095/host:vm-095": {"host_cpu_busy_ratio": 0.1}}))
    api = TestClient(build_api(app))
    response = api.get("/api/v1/host-metrics", headers=viewer_headers(app, api))
    assert response.status_code == 200
    assert [row["available"] for row in response.json()] == [True, False]
