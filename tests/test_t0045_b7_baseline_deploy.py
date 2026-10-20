"""T-0045 step B7 (ACR-0021): the incident metrics answer gains the 6h and 24h ranges (`ranges_available`), a
`baseline` per series (p50 / p95 of the 24 h that end an hour before the incident; null when under half of it has
samples) and `deploy` events from the `deploy_event` table, recorded by `argus deploy record` (which `ops/deploy.sh`
calls after `DEPLOY OK`). Read-only for the answer; no model call."""
from __future__ import annotations

import json
from argparse import Namespace
from datetime import datetime, timedelta, timezone

import pytest

from argus.domain.model import utcnow
from test_core import incident, make_app  # noqa: F401  (make_app is a fixture)
from test_t0045_b2_incident_metrics import WORKER, ScriptMetrics, _get, _incident

SHA = "dfa73326026b4bcf5fed2e1d490f450e2818a6a1"


class BaselineMetrics(ScriptMetrics):
    """The chart's own window as in B2 (by fraction); a window that ends 1 h or more before now is the baseline: its
    value is `base(i)` for the i-th 5-minute sample (None = no sample)."""

    def __init__(self, base, script=None):
        super().__init__(script or {"container_memory_bytes": lambda f: 30 * 1048576})
        self.base, self.baseline_calls = base, []

    def range(self, target, signal, minutes, step_s, end=None):
        if end is not None and end < utcnow() - timedelta(minutes=50):
            self.baseline_calls.append((str(target), signal, minutes, step_s, end))
            start = end.timestamp() - minutes * 60
            out = []
            for i in range(minutes * 60 // step_s + 1):
                v = self.base(i)
                if v is not None:
                    out.append((start + i * step_s, v))
            return out
        return super().range(target, signal, minutes, step_s, end=end)


def _series(body, key):
    return next(s for s in body["series"] if s["key"] == key)


# --- ranges ----------------------------------------------------------------------------------------------------------
def test_the_long_ranges_keep_at_most_130_points_and_the_answer_lists_them(make_app):
    app = make_app(metrics=BaselineMetrics(lambda i: None))
    inc = _incident(app)
    for rng in ("6h", "24h"):
        body = _get(app, inc, rng)
        assert body["range"] == rng
        assert body["ranges_available"] == ["15m", "30m", "1h", "6h", "24h"]
        assert all(len(s["points"]) <= 131 for s in body["series"])
        first = datetime.fromisoformat(body["from"].replace("Z", "+00:00"))
        assert first <= inc.opened_at - timedelta(hours=6 if rng == "6h" else 24)


def test_an_unknown_range_is_still_refused(make_app):
    from test_t0045_b2_incident_metrics import _api
    app = make_app(metrics=BaselineMetrics(lambda i: None))
    api, h = _api(app)
    inc = _incident(app)
    assert api.get(f"/api/v1/incidents/{inc.id}/metrics", params={"range": "2h"}, headers=h).status_code == 422


# --- baseline ----------------------------------------------------------------------------------------------------------
def test_the_baseline_is_p50_and_p95_of_the_24_hours_ending_an_hour_before_the_incident(make_app):
    metrics = BaselineMetrics(lambda i: float(i) * 1048576)                 # 0, 1, ..., 288 MiB (289 samples)
    app = make_app(metrics=metrics)
    inc = _incident(app)
    s = _series(_get(app, inc), "container_memory_bytes")
    calls = [c for c in metrics.baseline_calls if c[1] == "container_memory_bytes"]
    assert len(calls) == 1
    _, _, minutes, step, end = calls[0]
    assert (minutes, step) == (1440, 300)
    assert abs((inc.opened_at - timedelta(hours=1) - end).total_seconds()) < 1
    base = s["baseline"]
    assert base["p50"] == 144.0                                              # scaled to MiB like the series (B2)
    assert base["p95"] == pytest.approx(273.6)                               # 0.95 × 288, linear between ranks
    assert base["from"] < base["to"] and base["to"].endswith("Z")


def test_the_baseline_is_null_when_under_half_of_its_window_has_samples(make_app):
    app = make_app(metrics=BaselineMetrics(lambda i: 5.0 if i % 3 == 0 else None))   # a third of the samples
    inc = _incident(app)
    assert _series(_get(app, inc), "container_memory_bytes")["baseline"] is None


def test_the_baseline_is_null_when_its_read_fails_and_the_chart_still_answers(make_app):
    from argus.ports.ports import MetricsUnavailable

    def broken(i):
        raise MetricsUnavailable("prometheus down")
    app = make_app(metrics=BaselineMetrics(broken))
    inc = _incident(app)
    s = _series(_get(app, inc), "container_memory_bytes")
    assert s["baseline"] is None and any(v is not None for _, v in s["points"])


def test_a_failed_baseline_read_is_not_kept_and_the_next_answer_reads_it_again(make_app):
    from argus.ports.ports import MetricsUnavailable
    down = [True]

    def flaky(i):
        if down[0]:
            raise MetricsUnavailable("prometheus down")
        return 7.0
    app = make_app(metrics=BaselineMetrics(flaky))
    inc = _incident(app)
    assert _series(_get(app, inc, "15m"), "container_memory_bytes")["baseline"] is None
    down[0] = False
    assert _series(_get(app, inc, "1h"), "container_memory_bytes")["baseline"] is not None


def test_the_baseline_is_read_once_per_incident_whatever_the_range(make_app):
    metrics = BaselineMetrics(lambda i: 7.0)
    app = make_app(metrics=metrics)
    inc = _incident(app)
    for rng in ("15m", "1h", "24h"):
        _get(app, inc, rng)
    assert len([c for c in metrics.baseline_calls if c[1] == "container_memory_bytes"]) == 1


# --- deploy events -------------------------------------------------------------------------------------------------------
def test_a_deploy_of_the_incidents_host_inside_the_window_is_an_event(make_app):
    app = make_app(metrics=BaselineMetrics(lambda i: None))
    inc = _incident(app)
    inside = inc.opened_at - timedelta(minutes=5)
    app.store.add_deploy_event("vm-166", SHA, "main", "alice", inside)
    app.store.add_deploy_event("vm-095", SHA, "main", "alice", inside)                     # another host
    app.store.add_deploy_event("vm-166", SHA, "old", "alice", inc.opened_at - timedelta(hours=3))   # before 15m
    body = _get(app, inc, "15m")
    deploys = [e for e in body["events"] if e["kind"] == "deploy"]
    assert len(deploys) == 1
    assert deploys[0]["label"] == "Deployed main (dfa7332)" and "alice" not in deploys[0]["label"]
    assert deploys[0]["at"] == inside.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    assert len([e for e in _get(app, inc, "6h")["events"] if e["kind"] == "deploy"]) == 2


def test_the_store_keeps_deploy_events_by_host_and_time(make_app):
    app = make_app()
    now = utcnow()
    app.store.add_deploy_event("vm-095", SHA, "main", "alice", now - timedelta(hours=2))
    app.store.add_deploy_event("vm-095", SHA[:12], "task/x", "bob", now - timedelta(minutes=1))
    got = app.store.deploy_events("vm-095", now - timedelta(hours=1), now)
    assert [(e["ref"], e["actor"]) for e in got] == [("task/x", "bob")]
    assert app.store.deploy_events("vm-166", now - timedelta(days=1), now) == []


# --- argus deploy record ---------------------------------------------------------------------------------------------------
@pytest.fixture()
def cli_env(tmp_path, monkeypatch):
    from test_core import ROOT
    monkeypatch.setenv("ARGUS_DB_BACKEND", "sqlite")
    monkeypatch.setenv("ARGUS_DB", str(tmp_path / "cli.db"))
    monkeypatch.setenv("ARGUS_CONFIG_DIR", str(ROOT / "config"))
    monkeypatch.setenv("ARGUS_HOME_HOST", "vm-095")
    return tmp_path


def _record(**kw):
    from argus.__main__ import deploy
    args = dict(action="record", host=None, commit=SHA, ref="main", who="alice")
    deploy(Namespace(**{**args, **kw}))


def test_deploy_record_stores_the_event_on_the_home_host_and_audits_it(cli_env, capsys):
    from argus.adapters.outbound.sqlite_store import SqliteStore
    _record()
    store = SqliteStore(str(cli_env / "cli.db"))
    got = store.deploy_events("vm-095", utcnow() - timedelta(minutes=1), utcnow() + timedelta(minutes=1))
    assert [(e["commit"], e["ref"], e["actor"]) for e in got] == [(SHA, "main", "alice")]
    audits = [json.loads(r[0]) for r in store._q("SELECT body FROM audit WHERE incident_id IS NULL")]
    assert any(a["event"] == "deploy.recorded" and a["actor"] == "alice" and a["detail"]["host"] == "vm-095"
               for a in audits)
    assert "deploy recorded" in capsys.readouterr().out
    _record(host="vm-166", ref="task/T-0045-B7")
    assert len(store.deploy_events("vm-166", utcnow() - timedelta(minutes=1), utcnow() + timedelta(minutes=1))) == 1


@pytest.mark.parametrize("bad", [dict(host="vm-999"), dict(commit="not-a-sha"), dict(commit="abc"),
                                 dict(ref="main; rm -rf /"), dict(ref=""), dict(who="bad user")])
def test_deploy_record_refuses_what_is_not_a_host_commit_ref_or_handle(cli_env, bad):
    with pytest.raises(SystemExit):
        _record(**bad)
