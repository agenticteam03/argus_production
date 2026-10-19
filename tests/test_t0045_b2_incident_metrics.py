"""T-0045 step B2 (ACR-0021): the incident metrics answer gains `kind`, `thresholds`, `detector_threshold` per series and,
at the top, `incident_from`, `incident_to`, `events` and a template `summary`. Read-only; no model call."""
from __future__ import annotations

import json
import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from argus.adapters.inbound.http import build_api
from argus.application.incident_metrics import KINDS, SignalList
from argus.domain.model import IncidentStatus, utcnow
from argus.ports.ports import MetricsUnavailable
from test_core import FakeMetrics, incident, make_app  # noqa: F401  (make_app is a fixture)

PASSWORD = "a-long-password"
WORKER = "vm-166/container:argus-lab-worker"
CLIENT = "vm-166/container:argus-lab-client"
HOST = "vm-166/host:vm-166"


class ScriptMetrics(FakeMetrics):
    """`script[signal]` is a function of the fraction of the window (0..1) -> value or None. Unlisted signals: no data."""

    def __init__(self, script=None, failing=()):
        super().__init__({})
        self.script, self.failing, self.calls = script or {}, set(failing), []

    def range(self, target, signal, minutes, step_s, end=None):
        self.calls.append((str(target), signal))
        if signal in self.failing:
            raise MetricsUnavailable("prometheus down")
        fn = self.script.get(signal)
        if fn is None:
            return []
        stop = end.timestamp()
        start = stop - minutes * 60
        out, t = [], start
        while t <= stop:
            v = fn((t - start) / (stop - start))
            if v is not None:
                out.append((t, v))
            t += step_s
        return out


def _api(app):
    app.store.upsert_principal("alice", "human", "viewer", ["lab"], PasswordHash.recommended().hash(PASSWORD))
    api = TestClient(build_api(app))
    token = api.post("/api/v1/auth/token", data={"username": "alice", "password": PASSWORD, "scope": "read"}).json()["access_token"]
    return api, {"Authorization": f"Bearer {token}"}


def _incident(app, target=WORKER, cls="container_restart_loop", closed=True):
    inc = incident(app, target)
    inc.incident_class = cls
    inc.opened_at = utcnow() - timedelta(minutes=14)
    if closed:
        inc.closed_at = utcnow() - timedelta(minutes=5)
        inc.status = IncidentStatus.closed
    app.store.update_incident(inc)
    return inc


def _get(app, inc, rng="15m"):
    api, h = _api(app)
    r = api.get(f"/api/v1/incidents/{inc.id}/metrics", params={"range": rng}, headers=h)
    assert r.status_code == 200
    return r.json()


def _at(body, fraction):
    from datetime import datetime
    f, t = (datetime.fromisoformat(body[k].replace("Z", "+00:00")) for k in ("from", "to"))
    return f + (t - f) * fraction


def _time(s):
    from datetime import datetime
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# --- kind: in the file, validated -------------------------------------------------------------------------------------
def test_every_shipped_series_has_a_known_kind_and_the_answer_carries_it(make_app):
    import yaml
    from test_core import ROOT
    data = yaml.safe_load((ROOT / "config" / "ui-incident-signals.yaml").read_text(encoding="utf-8"))
    entries = data["default"] + [e for es in data["classes"].values() for e in es]
    assert all(e.get("kind") in KINDS and e["kind"] != "other" for e in entries)
    app = make_app(metrics=ScriptMetrics())
    body = _get(app, _incident(app))
    assert all(s["kind"] in KINDS for s in body["series"])
    assert {s["key"]: s["kind"] for s in body["series"]}["container_memory_bytes"] == "memory"


@pytest.mark.parametrize("kind", ["sideways", 3, ""])
def test_a_bad_kind_is_refused(kind):
    with pytest.raises(ValueError, match="kind"):
        SignalList.from_data({"default": [{"signal": "restarts_10m", "title": "R", "kind": kind}]}, {"restarts_10m"}, set())


# --- thresholds, scaled like the values; the detector's own line ----------------------------------------------------------
def test_thresholds_are_scaled_like_the_values_and_the_fired_series_has_the_detectors_line(make_app):
    app = make_app(metrics=ScriptMetrics())
    inc = _incident(app, CLIENT, "cpu_saturation")
    by = {s["key"]: s for s in _get(app, inc)["series"]}
    throttled, quota = by["container_cpu_throttled_ratio_5m"], by["container_cpu_quota_used_ratio_5m"]
    assert throttled["thresholds"] == {"warning": 25.0, "critical": 50.0, "direction": "above"}        # scale 100
    assert throttled["detector_threshold"] == 50.0
    assert quota["thresholds"]["critical"] == 80.0 and quota["detector_threshold"] is None             # not the fired one


def test_a_series_without_a_threshold_has_null_not_zero(make_app):
    app = make_app(metrics=ScriptMetrics())
    inc = _incident(app, CLIENT, "postgresql_connection_exhaustion")
    by = {s["key"]: s for s in _get(app, inc)["series"]}
    assert by["db_up"]["thresholds"] is None and by["db_up"]["detector_threshold"] is None
    assert by["db_connection_usage"]["detector_threshold"] == 90.0


# --- the incident band -------------------------------------------------------------------------------------------------
def test_the_incident_band_is_opened_at_to_closed_at_and_open_is_null(make_app):
    app = make_app(metrics=ScriptMetrics())
    closed, opened = _incident(app), _incident(app, closed=False)
    body = _get(app, closed)
    stored = app.store.get_incident(closed.id)
    assert abs((_time(body["incident_from"]) - stored.opened_at).total_seconds()) < 1
    assert abs((_time(body["incident_to"]) - stored.closed_at).total_seconds()) < 1
    body = _get(app, opened)
    assert body["incident_from"] and body["incident_to"] is None


# --- events --------------------------------------------------------------------------------------------------------------
def test_restart_and_oom_events_are_where_the_counters_step(make_app):
    app = make_app(metrics=ScriptMetrics({"container_restart_count": lambda f: 4 if f < 0.5 else 5,
                                          "oom_killed": lambda f: 0 if f < 0.6 else 1}))
    inc = _incident(app)
    body = _get(app, inc)
    events = {e["kind"]: e for e in body["events"]}
    assert set(events) == {"restart", "oom_kill"} and len(body["events"]) == 2
    step = body["step_s"]
    for kind, fraction in (("restart", 0.5), ("oom_kill", 0.6)):
        at = events[kind]["at"]
        assert _at(body, fraction) <= _time(at) <= _at(body, fraction) + timedelta(seconds=2 * step), kind
        assert events[kind]["label"]
    assert [e["at"] for e in body["events"]] == sorted(e["at"] for e in body["events"])


def test_no_step_means_no_event_and_a_first_sample_of_one_is_not_a_new_oom(make_app):
    app = make_app(metrics=ScriptMetrics({"container_restart_count": lambda f: 4, "oom_killed": lambda f: 1}))
    assert _get(app, _incident(app))["events"] == []


def test_a_host_incident_reads_no_container_counters(make_app):
    metrics = ScriptMetrics({"container_restart_count": lambda f: 0 if f < 0.5 else 3})
    app = make_app(metrics=metrics)
    body = _get(app, _incident(app, HOST, "disk_pressure"))
    assert body["events"] == [] and not any(sig in ("container_restart_count", "oom_killed") for _, sig in metrics.calls)


def test_a_failing_counter_read_leaves_the_answer_without_events_not_broken(make_app):
    app = make_app(metrics=ScriptMetrics({"container_restart_count": lambda f: 0 if f < 0.5 else 1},
                                         failing={"container_restart_count", "oom_killed"}))
    body = _get(app, _incident(app))
    assert body["events"] == [] and body["series"]


def test_alert_events_come_from_the_store(make_app):
    app = make_app(metrics=ScriptMetrics())
    inc = _incident(app)
    stored = app.store.get_incident(inc.id)
    fired = stored.opened_at + timedelta(minutes=2)
    app.store.add_alert_occurrence("id-1", inc.id, "fp-1", fired, {"alertname": "ArgusContainerRestartLoop"}, "started",
                                   received_at=fired)
    app.store.resolve_alert_occurrence("id-1", stored.opened_at + timedelta(minutes=6))
    body = _get(app, inc)
    kinds = [(e["kind"], e["label"]) for e in body["events"] if e["kind"].startswith("alert_")]
    assert [k for k, _ in kinds] == ["alert_fired", "alert_resolved"]
    assert all("ArgusContainerRestartLoop" in label for _, label in kinds)
    assert abs((_time(body["events"][0]["at"]) - fired).total_seconds()) < 1


def test_an_alert_outside_the_window_is_not_an_event(make_app):
    app = make_app(metrics=ScriptMetrics())
    inc = _incident(app)
    old = utcnow() - timedelta(days=2)
    app.store.add_alert_occurrence("id-old", inc.id, "fp", old, {"alertname": "Old"}, "started", received_at=old)
    assert _get(app, inc)["events"] == []


# --- summary ---------------------------------------------------------------------------------------------------------------
def test_the_summary_is_a_template_filled_from_the_series_and_differs_by_fired_state(make_app):
    hot = ScriptMetrics({"restarts_10m": lambda f: 4, "container_memory_bytes": lambda f: 60 * 1048576})
    cold = ScriptMetrics({"restarts_10m": lambda f: 0, "container_memory_bytes": lambda f: 60 * 1048576})
    app = make_app(metrics=hot)
    a = _get(app, _incident(app))["summary"]
    app2 = make_app(metrics=cold)
    b = _get(app2, _incident(app2))["summary"]
    assert "4 restarts" in a and "60" in a and a != b and "4 restarts" not in b and "60" in b


def test_every_class_has_a_summary_and_it_holds_no_address_or_url(make_app):
    from argus.detectors.classes import CLASSES
    app = make_app(metrics=ScriptMetrics({"host_cpu_busy_ratio": lambda f: 0.5}))
    for spec in CLASSES:
        target = HOST if spec.name in ("disk_pressure", "monitoring_blind_spot") else WORKER
        body = _get(app, _incident(app, target, spec.name))
        assert isinstance(body["summary"], str) and body["summary"], spec.name
        assert "://" not in json.dumps(body) and not re.search(r"\d+\.\d+\.\d+\.\d+", json.dumps(body)), spec.name
