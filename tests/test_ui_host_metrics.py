"""The public UI receives only bounded, named host metrics, never PromQL."""

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
    assert rows[1] == {"host": "vm-166", "target": "vm-166/host:vm-166", "available": False,
                       "observed_at": None, "values": {"cpu_busy_ratio": None,
                                                     "memory_used_ratio": None, "disk_used_ratio": None}}


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
