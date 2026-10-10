"""T-0026: resolved alerts (ARCHITECTURE §6.4 "Resolution", §7.3; ACR-0005).

Each alert occurrence has its own status: a `resolved` notification (push), or the alert's absence from a successful
read of its host's active alerts (pull; silenced and inhibited alerts are still active), marks only that occurrence
resolved. When every occurrence of an incident is resolved: a queued incident closes `resolved_externally` without a
run; a running one finishes its diagnosis; a concluded one is not changed. A host that cannot be read resolves nothing.
"""
from __future__ import annotations

import sqlite3
from datetime import timedelta

import httpx

from argus.domain.model import AlertNotification, IncidentOutcome, IncidentStatus, utcnow
from test_core import FakeMetrics, make_app  # noqa: F401  (make_app = fixture)
from test_op011_correlation import SC03, T0, _probe, _unhealthy

SRC = "alertmanager@vm-166"


def _handle(app):
    from argus.application.alerts import HandleAlertNotification
    return HandleAlertNotification(app.store, app.inventory, FakeMetrics(SC03))


def _resolved(a: AlertNotification, ends=None) -> AlertNotification:
    return a.model_copy(update={"status": "resolved", "ends_at": ends or T0 + timedelta(minutes=3)})


def _audited(app) -> list:
    seen, real = [], app.store.append
    app.store.append = lambda rec: seen.append(rec) or real(rec)
    return seen


def _status(app, incident_id) -> dict[str, str]:
    return {o["alertname"]: o["status"] for o in app.store.alert_occurrences(incident_id)}


# --- push: a resolved notification ----------------------------------------------------------------------------------
def test_a_resolved_notification_marks_only_its_occurrence(make_app):
    app = make_app()
    handle = _handle(app)
    first = handle(_probe(), source=SRC)
    handle(_unhealthy(), source=SRC)
    r = handle(_resolved(_probe()), source=SRC)
    assert r.disposition == "resolved" and r.incident_id == first.incident_id
    assert _status(app, first.incident_id) == {"DependencyProbeFailed": "resolved", "ContainerUnhealthy": "firing"}
    occ = {o["alertname"]: o for o in app.store.alert_occurrences(first.incident_id)}
    assert occ["DependencyProbeFailed"]["resolved_at"] == T0 + timedelta(minutes=3)      # the alert's endsAt
    assert occ["ContainerUnhealthy"]["resolved_at"] is None
    inc = app.store.get_incident(first.incident_id)
    assert inc.status == IncidentStatus.queued and inc.outcome is None                    # one of two: stays open


def test_the_resolution_is_audited(make_app):
    app = make_app()
    audited = _audited(app)
    handle = _handle(app)
    first = handle(_probe(), source=SRC)
    handle(_unhealthy(), source=SRC)
    handle(_resolved(_probe()), source=SRC)
    ev = [a for a in audited if a.event == "incident.alert_resolved"]
    assert len(ev) == 1 and ev[0].incident_id == first.incident_id
    assert ev[0].detail["alertname"] == "DependencyProbeFailed" and ev[0].detail["via"] == "notification"
    assert ev[0].detail["still_firing"] == 1
    assert not [a for a in audited if a.event == "incident.alerts_all_resolved"]


def test_an_unknown_or_repeated_resolution_is_ignored(make_app):
    app = make_app()
    audited = _audited(app)
    handle = _handle(app)
    assert handle(_resolved(_probe()), source=SRC).disposition == "ignored"              # never fired here
    handle(_probe(), source=SRC)
    assert handle(_resolved(_probe()), source=SRC).disposition == "resolved"
    assert handle(_resolved(_probe()), source=SRC).disposition == "ignored"              # already resolved
    assert len([a for a in audited if a.event == "incident.alert_resolved"]) == 1


# --- when every occurrence is resolved ------------------------------------------------------------------------------
def test_a_queued_incident_whose_alerts_all_resolve_closes_resolved_externally(make_app):
    app = make_app()
    audited = _audited(app)
    handle = _handle(app)
    first = handle(_probe(), source=SRC)
    handle(_unhealthy(), source=SRC)
    handle(_resolved(_probe()), source=SRC)
    handle(_resolved(_unhealthy()), source=SRC)
    inc = app.store.get_incident(first.incident_id)
    assert inc.status == IncidentStatus.closed and inc.outcome == IncidentOutcome.resolved_externally
    assert inc.closed_at is not None and "resolved" in (inc.diagnosis or "")
    assert app.store.claim_next_queued("w1") is None                                     # no run starts
    done = [a for a in audited if a.event == "incident.alerts_all_resolved"]
    assert len(done) == 1 and done[0].detail["closed"] is True
    assert done[0].detail["incident_status"] == "queued"


def test_a_running_incident_whose_alerts_all_resolve_keeps_running(make_app):
    app = make_app()
    audited = _audited(app)
    handle = _handle(app)
    first = handle(_probe(), source=SRC)
    assert app.store.claim_next_queued("w1").id == first.incident_id                     # a worker took it
    handle(_resolved(_probe()), source=SRC)
    inc = app.store.get_incident(first.incident_id)
    assert inc.status == IncidentStatus.running and inc.outcome is None                  # the diagnosis goes on
    done = [a for a in audited if a.event == "incident.alerts_all_resolved"]
    assert len(done) == 1 and done[0].detail["closed"] is False
    assert done[0].detail["incident_status"] == "running"


def test_a_concluded_incident_is_not_changed_by_a_resolution(make_app):
    app = make_app()
    handle = _handle(app)
    first = handle(_probe(), source=SRC)
    inc = app.store.get_incident(first.incident_id)
    inc.status, inc.outcome, inc.closed_at = IncidentStatus.closed, IncidentOutcome.diagnosed, utcnow()
    inc.diagnosis = "the cache is stopped"
    app.store.update_incident(inc)
    assert handle(_resolved(_probe()), source=SRC).disposition == "resolved"
    after = app.store.get_incident(first.incident_id)
    assert after.outcome == IncidentOutcome.diagnosed and after.diagnosis == "the cache is stopped"
    assert after.closed_at == inc.closed_at
    assert _status(app, first.incident_id) == {"DependencyProbeFailed": "resolved"}


def test_a_new_firing_after_a_resolved_externally_close_opens_a_new_incident(make_app):
    app = make_app()
    handle = _handle(app)
    first = handle(_probe(), source=SRC)
    handle(_resolved(_probe()), source=SRC)
    again = handle(_probe(starts=utcnow()), source=SRC)                                  # it fails again later
    assert again.disposition == "started" and again.incident_id != first.incident_id


# --- pull: absence from a successful read of the host's active alerts -----------------------------------------------
class Source:
    """`firing` = what the reconciliation submits; `active` = every active alert (silenced and inhibited too)."""

    def __init__(self, firing, active=None, active_error=False):
        self.firing, self.active, self.active_error = firing, active, active_error

    def firing_alerts(self, host):
        from argus.ports.ports import AlertsUnavailable
        if isinstance(self.firing, Exception):
            raise AlertsUnavailable(str(self.firing))
        return list(self.firing)

    def active_alerts(self, host):
        from argus.ports.ports import AlertsUnavailable
        if self.active_error:
            raise AlertsUnavailable("down")
        return list(self.firing if self.active is None else self.active)


def _reconcile(app, src):
    from argus.application.alerts import ReconcileFiringAlerts
    return ReconcileFiringAlerts(src, _handle(app), ["vm-166"])


def test_a_pull_pass_resolves_the_alerts_that_are_no_longer_active(make_app):
    app = make_app()
    src = Source([_probe(), _unhealthy()])
    rec = _reconcile(app, src)
    first = rec.run_once()
    assert first == {"vm-166": {"started": 1, "attached": 1}}
    src.firing = [_unhealthy()]
    assert rec.run_once() == {"vm-166": {"duplicate": 1, "resolved": 1}}
    (inc,) = app.store.list_incidents()
    assert _status(app, inc.id) == {"DependencyProbeFailed": "resolved", "ContainerUnhealthy": "firing"}
    src.firing = []
    assert rec.run_once() == {"vm-166": {"resolved": 1}}
    inc = app.store.get_incident(inc.id)
    assert inc.status == IncidentStatus.closed and inc.outcome == IncidentOutcome.resolved_externally
    assert rec.run_once() == {"vm-166": {}}


def test_a_silenced_alert_is_not_resolved(make_app):
    app = make_app()
    src = Source([_probe()])
    rec = _reconcile(app, src)
    rec.run_once()
    src.firing, src.active = [], [_probe()]                       # silenced: not submitted, but still active
    assert rec.run_once() == {"vm-166": {}}
    (inc,) = app.store.list_incidents()
    assert _status(app, inc.id) == {"DependencyProbeFailed": "firing"}


def test_a_host_that_cannot_be_read_resolves_nothing(make_app):
    app = make_app()
    src = Source([_probe()])
    rec = _reconcile(app, src)
    rec.run_once()
    src.firing = RuntimeError("tunnel down")
    assert rec.run_once() == {"vm-166": "unavailable"}
    src.firing, src.active_error = [], True                       # the firing read works, the active read fails
    assert rec.run_once() == {"vm-166": {"resolve": "unavailable"}}
    (inc,) = app.store.list_incidents()
    assert _status(app, inc.id) == {"DependencyProbeFailed": "firing"}


def test_a_refiring_alert_resolves_its_previous_occurrence(make_app):
    app = make_app()
    src = Source([_probe(starts=T0)])
    rec = _reconcile(app, src)
    rec.run_once()
    (inc,) = app.store.list_incidents()
    src.firing = [_probe(starts=T0 + timedelta(minutes=5))]       # same fingerprint, a new firing period
    out = rec.run_once()["vm-166"]
    assert out.get("resolved") == 1
    assert [o["status"] for o in app.store.alert_occurrences(inc.id)
            if o["starts_at"] == T0] == ["resolved"]


def test_only_occurrences_received_before_the_active_read_are_resolved(make_app):
    """An alert recorded (for example by the webhook) after the active read was taken is not judged by that read."""
    app = make_app()
    handle = _handle(app)
    before = utcnow() - timedelta(seconds=1)           # the Windows clock may give the same instant twice
    handle(_probe(), source=SRC)
    assert handle.resolve_absent("vm-166", [], source=SRC, read_at=before) == 0
    assert handle.resolve_absent("vm-166", [], source=SRC, read_at=utcnow()) == 1


# --- the webhook and the Alertmanager adapter -----------------------------------------------------------------------
def test_the_webhook_records_a_resolved_alert(make_app):
    from fastapi.testclient import TestClient
    from argus.adapters.inbound.http import build_webhook
    app = make_app(metrics=FakeMetrics(SC03))
    app.alertmanager_token = "am-token-123"
    hook = TestClient(build_webhook(app))

    def post(status, ends=None):
        a = _probe()
        body = {"alerts": [{"status": status, "fingerprint": a.fingerprint, "startsAt": T0.isoformat(),
                            "endsAt": ends or "0001-01-01T00:00:00Z", "labels": a.labels, "annotations": {}}]}
        return hook.post("/api/v1/alerts", json=body, headers={"Authorization": "Bearer am-token-123"}).json()

    started = post("firing")["accepted"][0]
    out = post("resolved", (T0 + timedelta(minutes=2)).isoformat())["accepted"]
    assert out == [{"incident_id": started["incident_id"], "disposition": "resolved", "duplicate": False}]
    (occ,) = app.store.alert_occurrences(started["incident_id"])
    assert occ["status"] == "resolved" and occ["resolved_at"] == T0 + timedelta(minutes=2)


def test_the_alertmanager_source_reads_every_active_alert_of_its_host():
    from argus.adapters.outbound.alerts_alertmanager import AlertmanagerSource
    from test_t0022_alerting import _am_payload
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=_am_payload(("f1", "vm-166"), ("f2", "vm-095")))

    src = AlertmanagerSource({"vm-166": "http://argus-v18-tunnel:18091"},
                             client=httpx.Client(transport=httpx.MockTransport(handler)))
    alerts = src.active_alerts("vm-166")
    assert seen["params"] == {"active": "true", "silenced": "true", "inhibited": "true", "unprocessed": "true"}
    assert [a.fingerprint for a in alerts] == ["f1"]                     # f2 says vm-095: dropped


# --- storage --------------------------------------------------------------------------------------------------------
def test_a_sqlite_file_from_before_t0026_gets_resolved_at(tmp_path):
    from argus.adapters.outbound.sqlite_store import SqliteStore
    path = str(tmp_path / "old.db")
    with sqlite3.connect(path) as db:                                    # migration-004 shape, no resolved_at
        db.execute("CREATE TABLE alert_occurrence (identity TEXT PRIMARY KEY, incident_id TEXT NOT NULL, "
                   "fingerprint TEXT NOT NULL, starts_at TEXT NOT NULL, alertname TEXT NOT NULL DEFAULT '', "
                   "labels TEXT NOT NULL, disposition TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'firing', "
                   "received_at TEXT NOT NULL)")
    SqliteStore(path)
    with sqlite3.connect(path) as db:
        assert "resolved_at" in {r[1] for r in db.execute("PRAGMA table_info(alert_occurrence)")}
