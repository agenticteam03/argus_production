"""T-0045 step B6, first half (ACR-0021): `GET /api/v1/target-metrics?target=<host/kind:name>&range=15m|1h`.

The drawer's charts for one box. The browser names an inventory target (else 404) and a range from a fixed list (else
422); the server picks the series (CPU quota used and memory for a container; CPU, memory used and disk used for a
host), reads them through `MetricsPort.range` on that target's own host only, and answers at most ~130 points per
series with the UI's warning and critical lines. A missing sample is `null` (a gap, never 0); a series that cannot be
read is all gaps and the others still answer. One shared answer per (target, range) for 30 s. Any role may read it.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from argus.application.target_metrics import TargetMetrics
from argus.application.thresholds import Thresholds
from argus.domain.model import TargetRef
from test_acr0017_incident_metrics import RangeMetrics, _api
from test_core import make_app  # noqa: F401  (fixture)

WORKER = "vm-166/container:argus-lab-worker"
HOST = "vm-166/host:vm-166"
NOW = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)


def _get(api, headers, target, rng=None):
    params = {"target": target} if rng is None else {"target": target, "range": rng}
    return api.get("/api/v1/target-metrics", params=params, headers=headers)


# --- the answer ----------------------------------------------------------------------------------------------------------
def test_a_container_answers_cpu_quota_and_memory_on_its_own_host(make_app):
    metrics = RangeMetrics()
    app = make_app(metrics=metrics)
    api, h = _api(app)
    r = _get(api, h, WORKER, "15m")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["target"] == WORKER and body["range"] == "15m"
    assert [(s["key"], s["kind"]) for s in body["series"]] == [("container_cpu_quota_used_ratio_5m", "cpu"),
                                                               ("container_memory_bytes", "memory")]
    cpu, mem = body["series"]
    assert cpu["thresholds"] == {"warning": 0.7, "critical": 0.8, "direction": "above"} and cpu["max"] == 1.0
    assert mem["thresholds"] is None and mem["unit"] == "bytes"
    assert all(len(s["points"]) <= 131 for s in body["series"])
    assert {c["target"] for c in metrics.calls} == {WORKER} and {c["minutes"] for c in metrics.calls} == {15}


def test_a_host_answers_cpu_memory_used_and_disk(make_app):
    metrics = RangeMetrics()
    app = make_app(metrics=metrics)
    api, h = _api(app)
    body = _get(api, h, HOST, "1h").json()
    assert [(s["key"], s["kind"]) for s in body["series"]] == [("host_cpu_busy_ratio", "cpu"),
                                                               ("host_memory_used_ratio", "memory"),
                                                               ("host_disk_used_ratio", "disk")]
    mem = body["series"][1]
    assert mem["thresholds"] == {"warning": 0.75, "critical": 0.9, "direction": "above"}   # available, flipped
    assert {p[1] for p in mem["points"] if p[1] is not None} == {0.0}                     # 1 - the available 1.0
    assert {c["target"] for c in metrics.calls} == {HOST} and {c["minutes"] for c in metrics.calls} == {60}
    assert {c["signal"] for c in metrics.calls} == {"host_cpu_busy_ratio", "host_memory_available_ratio",
                                                    "host_disk_used_ratio"}


def test_the_range_defaults_to_15_minutes(make_app):
    app = make_app(metrics=RangeMetrics())
    api, h = _api(app)
    assert _get(api, h, WORKER).json()["range"] == "15m"


def test_a_missing_or_unreadable_series_is_gaps_and_the_others_still_answer(make_app):
    app = make_app(metrics=RangeMetrics(missing={"container_memory_bytes"},
                                        failing={"container_cpu_quota_used_ratio_5m"}))
    api, h = _api(app)
    body = _get(api, h, WORKER, "15m").json()
    assert all(p[1] is None for s in body["series"] for p in s["points"])
    app = make_app(metrics=RangeMetrics(failing={"host_disk_used_ratio"}))
    api, h = _api(app)
    series = {s["key"]: s for s in _get(api, h, HOST, "15m").json()["series"]}
    assert all(p[1] is None for p in series["host_disk_used_ratio"]["points"])
    assert any(p[1] is not None for p in series["host_cpu_busy_ratio"]["points"])


# --- what the browser may ask --------------------------------------------------------------------------------------------
def test_a_target_outside_the_inventory_is_404(make_app):
    api, h = _api(make_app(metrics=RangeMetrics()))
    for t in ("vm-166/container:nosuch", "vm-999/host:vm-999", "vm-166/volume:argus-lab-worker"):
        assert _get(api, h, t, "15m").status_code == 404, t


def test_a_bad_range_or_a_malformed_target_is_422(make_app):
    metrics = RangeMetrics()
    api, h = _api(make_app(metrics=metrics))
    for rng in ("30m", "6h", "1h; drop", ""):
        assert _get(api, h, WORKER, rng).status_code == 422, rng
    for t in ("", "../etc/passwd", "vm-166/container:a b", "vm-166/container:x{y}", "http://example.invalid/", "x" * 200):
        assert _get(api, h, t, "15m").status_code == 422, t
    assert api.get("/api/v1/target-metrics", headers=h).status_code == 422          # the target is required
    assert metrics.calls == []


def test_any_role_reads_it_and_a_login_is_required(make_app):
    app = make_app(metrics=RangeMetrics())
    for role in ("viewer", "operator", "approver"):
        api, h = _api(app, role=role)
        assert _get(api, h, WORKER, "15m").status_code == 200, role
    assert _get(api, {}, WORKER, "15m").status_code == 401


def test_the_answer_holds_no_address_or_internal_url(make_app):
    app = make_app(metrics=RangeMetrics())
    api, h = _api(app)
    urls = {u for host in app.inventory.hosts() for u in host.executors.values()}
    for t in (WORKER, HOST):
        text = _get(api, h, t, "1h").text
        assert not re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", text) and "http" not in text
        assert not any(u in text for u in urls)


# --- the shared cache ----------------------------------------------------------------------------------------------------
def test_one_shared_answer_per_target_and_range_for_30_seconds():
    metrics, clock = RangeMetrics(), [0.0]
    tm = TargetMetrics(metrics, Thresholds(), now=lambda: NOW, clock=lambda: clock[0])
    worker = TargetRef.parse(WORKER)
    first = tm.window(worker, "15m")
    assert tm.window(worker, "15m") is first and len(metrics.calls) == 2
    tm.window(worker, "1h")
    assert len(metrics.calls) == 4                                       # another range is another answer
    clock[0] = 31
    tm.window(worker, "15m")
    assert len(metrics.calls) == 6                                       # expired: read again


def test_the_window_ends_now_with_at_most_130_points():
    tm = TargetMetrics(RangeMetrics(), Thresholds(), now=lambda: NOW)
    body = tm.window(TargetRef.parse(HOST), "1h")
    assert body["to"] == "2026-10-19T12:00:00Z" and body["from"] == "2026-10-19T11:00:00Z"
    assert body["step_s"] == 30 and all(len(s["points"]) == 121 for s in body["series"])
    assert body["series"][0]["thresholds"] is None                      # no thresholds configured: no lines
