"""ACR-0017 (incident metrics): `GET /api/v1/incidents/{id}/metrics?range=15m|30m|1h`.

The UI's charts around an incident. The browser sends no PromQL and no target: the server takes a fixed list of named
signals per incident class (`config/ui-incident-signals.yaml`, validated at startup), reads them with
`MetricsPort.range` on the incident's own host only, and answers at most ~130 points per series (the step grows for a
long incident). A missing sample is `null` (a gap), never 0.
"""
from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from argus.adapters.inbound.http import build_api
from argus.domain.model import IncidentStatus, TargetRef, utcnow
from argus.ports.ports import MetricsUnavailable
from test_core import ROOT, FakeMetrics, incident, make_app  # noqa: F401  (make_app is a fixture)

PASSWORD = "a-long-password"
CLIENT = "vm-166/container:argus-lab-client"


class RangeMetrics(FakeMetrics):
    """Answers every range read with one sample per step (or none for `missing`), and records each call."""

    def __init__(self, missing: set[str] | None = None, failing: set[str] | None = None, every: int = 1):
        super().__init__({})
        self.missing, self.failing, self.every, self.calls = missing or set(), failing or set(), every, []

    def range(self, target, signal, minutes, step_s, end=None):
        self.calls.append({"target": str(target), "signal": signal, "minutes": minutes, "step_s": step_s, "end": end})
        if signal in self.failing:
            raise MetricsUnavailable("prometheus down")
        if signal in self.missing:
            return []
        stop = end.timestamp()
        start = stop - minutes * 60
        pts, t, i = [], start, 0
        while t <= stop:
            if i % self.every == 0:
                pts.append((t, 1.0))
            t += step_s
            i += 1
        return pts


def _api(app, role="viewer", scope="read"):
    app.store.upsert_principal("alice", "human", role, ["lab"], PasswordHash.recommended().hash(PASSWORD))
    api = TestClient(build_api(app))
    data = {"username": "alice", "password": PASSWORD}
    if scope:
        data["scope"] = scope
    token = api.post("/api/v1/auth/token", data=data).json()["access_token"]
    return api, {"Authorization": f"Bearer {token}"}


def _classified(app, target=CLIENT, cls="dependency_unavailable", minutes_open=4, closed=True):
    inc = incident(app, target)
    inc.incident_class = cls
    inc.opened_at = utcnow() - timedelta(minutes=minutes_open + 5)
    if closed:
        inc.closed_at = utcnow() - timedelta(minutes=5)          # closed long enough ago that its +2 min tail is past
        inc.status = IncidentStatus.closed
    app.store.update_incident(inc)
    return inc


# --- the route ------------------------------------------------------------------------------------------------------
def test_needs_a_login_and_any_role_with_a_read_token_gets_it(make_app):
    app = make_app(metrics=RangeMetrics())
    inc = _classified(app)
    assert TestClient(build_api(app)).get(f"/api/v1/incidents/{inc.id}/metrics").status_code == 401
    api, headers = _api(app, role="viewer")
    r = api.get(f"/api/v1/incidents/{inc.id}/metrics", headers=headers)
    assert r.status_code == 200
    assert r.json()["incident_id"] == inc.id


def test_range_is_one_of_three_values_and_an_unknown_incident_is_404(make_app):
    app = make_app(metrics=RangeMetrics())
    inc = _classified(app)
    api, headers = _api(app)
    for good in ("15m", "30m", "1h"):
        assert api.get(f"/api/v1/incidents/{inc.id}/metrics?range={good}", headers=headers).status_code == 200
    for bad in ("2h", "5m", "up", "30m; drop"):
        assert api.get(f"/api/v1/incidents/{inc.id}/metrics", params={"range": bad}, headers=headers).status_code == 422
    assert api.get("/api/v1/incidents/inc_nope/metrics", headers=headers).status_code == 404


def test_the_series_come_from_the_class_list_and_the_detector_signal_is_fired(make_app):
    app = make_app(metrics=RangeMetrics())
    inc = _classified(app, cls="dependency_unavailable")
    api, headers = _api(app)
    body = api.get(f"/api/v1/incidents/{inc.id}/metrics", headers=headers).json()
    keys = [s["key"] for s in body["series"]]
    assert keys[0] == "dependency_probe_min"
    fired = [s["key"] for s in body["series"] if s["fired"]]
    assert fired == ["dependency_probe_min"]
    for s in body["series"]:
        assert set(s) == {"key", "title", "unit", "max", "fired", "points",
                         "kind", "thresholds", "detector_threshold",      # + ACR-0021 (T-0045 B2)
                         "baseline"}                                      # + T-0045 B7


def test_an_incident_without_a_class_gets_the_host_series_only(make_app):
    metrics = RangeMetrics()
    app = make_app(metrics=metrics)
    inc = _classified(app, cls=None)
    api, headers = _api(app)
    body = api.get(f"/api/v1/incidents/{inc.id}/metrics", headers=headers).json()
    assert body["series"] and all(s["key"].startswith("host_") for s in body["series"])
    assert not any(s["fired"] for s in body["series"])


def test_reads_stay_on_the_incidents_host(make_app):
    metrics = RangeMetrics()
    app = make_app(metrics=metrics)
    inc = _classified(app)
    api, headers = _api(app)
    api.get(f"/api/v1/incidents/{inc.id}/metrics", headers=headers)
    assert metrics.calls
    assert {TargetRef.parse(c["target"]).host for c in metrics.calls} == {"vm-166"}
    assert {c["target"] for c in metrics.calls} <= {CLIENT, "vm-166/host:vm-166"}


def test_the_window_covers_the_incident_and_ends_after_it_closed(make_app):
    metrics = RangeMetrics()
    app = make_app(metrics=metrics)
    inc = _classified(app, minutes_open=4)
    api, headers = _api(app)
    body = api.get(f"/api/v1/incidents/{inc.id}/metrics?range=15m", headers=headers).json()
    assert body["range"] == "15m"
    stored = app.store.get_incident(inc.id)
    end = metrics.calls[0]["end"]
    assert abs((end - (stored.closed_at + timedelta(minutes=2))).total_seconds()) < 1
    assert metrics.calls[0]["minutes"] * 60 >= (end - stored.opened_at).total_seconds() + 15 * 60 - 60
    assert body["from"] < body["to"]


def test_an_open_incident_ends_now_not_in_the_future(make_app):
    metrics = RangeMetrics()
    app = make_app(metrics=metrics)
    inc = _classified(app, closed=False)
    api, headers = _api(app)
    api.get(f"/api/v1/incidents/{inc.id}/metrics", headers=headers)
    assert metrics.calls[0]["end"] <= utcnow() + timedelta(seconds=1)


def test_a_long_incident_keeps_at_most_about_130_points_per_series(make_app):
    metrics = RangeMetrics()
    app = make_app(metrics=metrics)
    inc = _classified(app, minutes_open=6 * 60)
    api, headers = _api(app)
    body = api.get(f"/api/v1/incidents/{inc.id}/metrics?range=1h", headers=headers).json()
    for s in body["series"]:
        assert len(s["points"]) <= 131
    assert all(c["step_s"] >= 30 for c in metrics.calls)


def test_a_missing_sample_is_null_and_a_failing_series_is_all_gaps(make_app):
    metrics = RangeMetrics(missing={"container_restart_count"}, failing={"host_cpu_busy_ratio"}, every=2)
    app = make_app(metrics=metrics)
    inc = _classified(app)
    api, headers = _api(app)
    series = {s["key"]: s for s in api.get(f"/api/v1/incidents/{inc.id}/metrics", headers=headers).json()["series"]}
    probe = [v for _, v in series["dependency_probe_min"]["points"]]
    assert None in probe and 1.0 in probe and 0 not in probe          # every other step: gaps, never zeros
    assert all(v is None for _, v in series["container_restart_count"]["points"])
    assert all(v is None for _, v in series["host_cpu_busy_ratio"]["points"])
    assert series["dependency_probe_min"]["points"]                    # the others still answer


def test_a_closed_incident_is_read_once_and_then_served_from_the_cache(make_app):
    metrics = RangeMetrics()
    app = make_app(metrics=metrics)
    inc = _classified(app)
    api, headers = _api(app)
    def chart():                                       # the window's reads; B7's baseline (24 h) is read once apart
        return [c for c in metrics.calls if c["minutes"] != 1440]

    def baseline():
        return [c for c in metrics.calls if c["minutes"] == 1440]
    api.get(f"/api/v1/incidents/{inc.id}/metrics", headers=headers)
    first, base = len(chart()), len(baseline())
    api.get(f"/api/v1/incidents/{inc.id}/metrics", headers=headers)
    assert len(chart()) == first
    api.get(f"/api/v1/incidents/{inc.id}/metrics?range=1h", headers=headers)     # another range: its own entry
    assert len(chart()) == 2 * first
    assert len(baseline()) == base                     # the baseline does not depend on the range


# --- the configuration ----------------------------------------------------------------------------------------------
def test_the_shipped_signal_list_is_valid():
    import yaml
    from argus.application.incident_metrics import SignalList
    from argus.detectors.classes import CLASSES
    signals = yaml.safe_load((ROOT / "config" / "signals.yaml").read_text(encoding="utf-8"))
    data = yaml.safe_load((ROOT / "config" / "ui-incident-signals.yaml").read_text(encoding="utf-8"))
    lst = SignalList.from_data(data, set(signals), {c.name for c in CLASSES})
    assert set(lst.by_class) <= {c.name for c in CLASSES}
    assert lst.default


@pytest.mark.parametrize("bad, message", [
    ({"default": [{"signal": "no_such_signal", "title": "x"}]}, "unknown signal"),
    ({"default": [], "classes": {"no_such_class": []}}, "unknown class"),
    ({"default": [{"signal": "host_cpu_busy_ratio", "title": "x", "scope": "elsewhere"}]}, "scope"),
    ({"default": [{"signal": "host_cpu_busy_ratio", "title": "x", "fired": "yes"}]}, "fired"),
    ({"nope": 1}, "unknown key"),
])
def test_an_invalid_signal_list_is_refused_at_startup(bad, message):
    from argus.application.incident_metrics import SignalList
    with pytest.raises(ValueError, match=message):
        SignalList.from_data(bad, {"host_cpu_busy_ratio"}, {"dependency_unavailable"})


# --- the Prometheus adapter (MetricsPort.range with an end time) -----------------------------------------------------
def test_prometheus_range_asks_query_range_for_the_window_that_ends_at_end(monkeypatch):
    from argus.adapters.outbound.config_adapters import PrometheusMetrics, YamlInventory
    seen = {}

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {"result": [{"values": [[100.0, "1"], [130.0, "0"]]}]}}

    def fake_get(url, params=None, timeout=None):
        seen.update(url=url, **params)
        return Resp()

    monkeypatch.setattr(httpx, "get", fake_get)
    inv = YamlInventory((ROOT / "config" / "inventory.yaml").read_text(encoding="utf-8"))
    pm = PrometheusMetrics(inv, {"dependency_probe_min": 'min(argus_probe_success{argus_host="$host",owner="$name"})'})
    end = utcnow()
    pts = pm.range(TargetRef.parse(CLIENT), "dependency_probe_min", 30, 30, end=end)
    assert seen["url"].endswith("/api/v1/query_range")
    assert seen["end"] == pytest.approx(end.timestamp())
    assert seen["start"] == pytest.approx(end.timestamp() - 30 * 60)
    assert seen["step"] == 30
    assert 'owner="argus-lab-client"' in seen["query"] and 'argus_host="vm-166"' in seen["query"]
    assert pts == [(100.0, 1.0), (130.0, 0.0)]
    with pytest.raises(ValueError):
        pm.range(TargetRef.parse(CLIENT), "not_a_signal", 30, 30)
