"""T-0045 step B1 (ACR-0021): the signal thresholds the UI draws, the host-metrics answer that carries them, and the
heartbeat age. Read-only: no write capability, no model call."""
from __future__ import annotations

import ipaddress
import json
import re
from datetime import timedelta

import pytest
import yaml
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from argus.adapters.inbound.http import build_api
from argus.application.thresholds import Thresholds
from argus.detectors import classes
from argus.domain.model import MetricSnapshot, TargetRef, utcnow
from test_core import ROOT, RUNBOOKS, FakeMetrics, make_app  # noqa: F401  (fixture)

SIGNALS = yaml.safe_load((ROOT / "config" / "signals.yaml").read_text(encoding="utf-8"))
TEMPLATES = {k: v for k, v in SIGNALS.items() if k != "thresholds"}


# --- the catalogue: validated at startup ------------------------------------------------------------------------------
def test_the_shipped_catalogue_has_thresholds_for_the_ui_signals():
    th = Thresholds.from_data(SIGNALS.get("thresholds"), set(TEMPLATES))
    assert set(th.signals()) == {
        "host_cpu_busy_ratio", "host_memory_available_ratio", "host_disk_used_ratio", "restarts_10m",
        "container_cpu_quota_used_ratio_5m", "container_cpu_throttled_ratio_5m", "db_connection_usage",
        "http_gateway_error_ratio_5m", "host_disk_used_ratio_5m"}
    assert th.get("host_memory_available_ratio").direction == "below"
    assert th.get("restarts_10m").as_dict() == {"warning": 2, "critical": 3, "direction": "above"}


def test_no_thresholds_block_is_allowed():
    assert Thresholds.from_data(None, set(TEMPLATES)).signals() == []


@pytest.mark.parametrize("bad, why", [
    ({"no_such_signal": {"warning": 1, "critical": 2, "direction": "above"}}, "unknown signal"),
    ({"restarts_10m": {"warning": "x", "critical": 3, "direction": "above"}}, "warning"),
    ({"restarts_10m": {"warning": 2, "critical": True, "direction": "above"}}, "critical"),
    ({"restarts_10m": {"warning": 2, "critical": 3, "direction": "sideways"}}, "direction"),
    ({"restarts_10m": {"warning": 2, "critical": 3}}, "direction"),
    ({"restarts_10m": {"warning": 5, "critical": 3, "direction": "above"}}, "warning"),      # warning past critical
    ({"host_memory_available_ratio": {"warning": 0.1, "critical": 0.25, "direction": "below"}}, "warning"),
    ({"restarts_10m": {"warning": 2, "critical": 3, "direction": "above", "extra": 1}}, "unknown field"),
    ({"restarts_10m": [2, 3]}, "restarts_10m"),
])
def test_a_bad_catalogue_entry_is_refused_naming_it(bad, why):
    with pytest.raises(ValueError) as e:
        Thresholds.from_data(bad, set(TEMPLATES))
    assert why in str(e.value)


def test_a_threshold_is_not_a_prometheus_template():
    """`thresholds` lives beside the templates in the file but is never served as one."""
    from argus.infrastructure.wiring import read_signals
    templates = read_signals(ROOT / "config")
    assert "thresholds" not in templates and all(isinstance(v, str) for v in templates.values())


def test_the_api_refuses_to_start_with_a_bad_threshold(make_app, tmp_path, monkeypatch):
    from argus.infrastructure.wiring import Settings, build
    cfg = tmp_path / "config"
    cfg.mkdir()
    for f in (ROOT / "config").glob("*"):
        if f.is_file():
            (cfg / f.name).write_bytes(f.read_bytes())
    data = yaml.safe_load((cfg / "signals.yaml").read_text(encoding="utf-8"))
    data["thresholds"]["restarts_10m"]["direction"] = "sideways"
    (cfg / "signals.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    monkeypatch.setenv("ARGUS_JWT_KEY", "x" * 40)
    s = Settings(config_dir=cfg, secrets_dir=tmp_path / "none", runbooks_dir=RUNBOOKS, db_path=str(tmp_path / "t.db"))
    with pytest.raises(SystemExit) as e:
        build(s, metrics=FakeMetrics(), require_credentials=False)
    assert "restarts_10m" in str(e.value) and "direction" in str(e.value)


# --- the numbers agree with the detectors (a later detector change cannot drift silently) -----------------------------
def _fires(detector, **values) -> bool:
    snap = MetricSnapshot(target=TargetRef.parse("vm-166/container:argus-lab-api"), observed_at=utcnow(), values=values)
    return detector(snap).matched


def test_critical_equals_the_detector_threshold():
    th = Thresholds.from_data(SIGNALS["thresholds"], set(TEMPLATES))
    eps = 1e-6
    c = lambda name: th.get(name).critical                                            # noqa: E731
    assert _fires(classes.container_restart_loop, restarts_10m=c("restarts_10m"))
    assert not _fires(classes.container_restart_loop, restarts_10m=c("restarts_10m") - eps)
    assert _fires(classes.postgresql_connection_exhaustion, db_up=1, db_connection_usage=c("db_connection_usage"))
    assert not _fires(classes.postgresql_connection_exhaustion, db_up=1,
                      db_connection_usage=c("db_connection_usage") - eps)
    assert _fires(classes.disk_pressure, host_disk_used_ratio_5m=c("host_disk_used_ratio_5m"))
    assert not _fires(classes.disk_pressure, host_disk_used_ratio_5m=c("host_disk_used_ratio_5m") - eps)
    assert _fires(classes.nginx_upstream_failure, http_gateway_error_ratio_5m=c("http_gateway_error_ratio_5m"))
    assert not _fires(classes.nginx_upstream_failure, http_gateway_error_ratio_5m=c("http_gateway_error_ratio_5m") - eps)
    both = dict(container_cpu_throttled_ratio_5m=c("container_cpu_throttled_ratio_5m"),
                container_cpu_quota_used_ratio_5m=c("container_cpu_quota_used_ratio_5m"))
    assert _fires(classes.cpu_saturation, **both)
    for name in both:
        assert not _fires(classes.cpu_saturation, **{**both, name: both[name] - eps})


# --- host-metrics: thresholds and heartbeat ---------------------------------------------------------------------------
def _api(make_app, metrics=None):
    app = make_app(metrics=metrics or FakeMetrics({
        "vm-095/host:vm-095": {"host_cpu_busy_ratio": 0.25, "host_memory_available_ratio": 0.4,
                               "host_disk_used_ratio": 0.7}}))
    app.store.upsert_principal("alice", "human", "viewer", ["lab"], PasswordHash.recommended().hash("long-password"))
    api = TestClient(build_api(app))
    token = api.post("/api/v1/auth/token", data={"username": "alice", "password": "long-password",
                                               "scope": "read"}).json()["access_token"]
    return app, api, {"Authorization": f"Bearer {token}"}


def test_host_metrics_rows_carry_thresholds_in_the_gauges_own_terms(make_app):
    _, api, h = _api(make_app)
    for row in api.get("/api/v1/host-metrics", headers=h).json():
        assert row["thresholds"] == {
            "cpu_busy_ratio": {"warning": 0.75, "critical": 0.9, "direction": "above"},
            "memory_used_ratio": {"warning": 0.75, "critical": 0.9, "direction": "above"},   # 1 - available (0.25 / 0.10)
            "disk_used_ratio": {"warning": 0.75, "critical": 0.9, "direction": "above"}}


def test_heartbeat_age_and_staleness_come_from_the_stored_state(make_app):
    app, api, h = _api(make_app)
    now = utcnow()
    app.store.save_monitoring_state("vm-095", {"state": "alive", "last_beat_at": (now - timedelta(seconds=40)).isoformat()})
    app.store.save_monitoring_state("vm-166", {"state": "lost", "last_beat_at": (now - timedelta(seconds=400)).isoformat()})
    rows = {r["host"]: r for r in api.get("/api/v1/host-metrics", headers=h).json()}
    assert 35 <= rows["vm-095"]["heartbeat_age_s"] <= 60 and rows["vm-095"]["heartbeat_stale"] is False
    assert rows["vm-166"]["heartbeat_age_s"] >= 395 and rows["vm-166"]["heartbeat_stale"] is True


def test_an_unknown_heartbeat_is_null_not_zero_and_not_fresh(make_app):
    _, api, h = _api(make_app)
    for row in api.get("/api/v1/host-metrics", headers=h).json():
        assert row["heartbeat_age_s"] is None and row["heartbeat_stale"] is None


def test_host_metrics_answer_holds_no_address_or_url(make_app):
    app, api, h = _api(make_app)
    app.store.save_monitoring_state("vm-095", {"state": "alive", "last_beat_at": utcnow().isoformat()})
    text = json.dumps(api.get("/api/v1/host-metrics", headers=h).json())
    assert "://" not in text
    for token in re.findall(r"\d+\.\d+\.\d+\.\d+", text):
        with pytest.raises(ValueError):
            ipaddress.ip_address(token)
