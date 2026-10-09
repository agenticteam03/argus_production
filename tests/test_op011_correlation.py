"""OP-011: alert correlation (ARCHITECTURE §6.4, `application/correlation.py`).

Two alerts on one target and class are one incident: the second is attached to the open incident as an alert
occurrence (`attached`, evidence version + 1) after the compatibility test (a fresh detector run gives the same class
for the same target, and the labels name no other container or dependency). Anything else opens a new incident;
a failed or impossible test never merges.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from argus.domain.model import AlertNotification, IncidentStatus, utcnow
from test_core import FakeMetrics, make_app  # noqa: F401  (make_app = fixture)

T0 = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
API = "vm-166/container:argus-lab-api"
SC03 = {API: {"dependency_probe_min": 0, "health_unhealthy": 1, "restarts_10m": 0}}   # cache stopped


def _probe(fp="fp-probe", dependency="argus-lab-cache", owner="argus-lab-api", starts=T0) -> AlertNotification:
    return AlertNotification(fingerprint=fp, status="firing", starts_at=starts, ends_at=None,
                             labels={"alertname": "DependencyProbeFailed", "argus_host": "vm-166", "owner": owner,
                                     "dependency": dependency},
                             annotations={"summary": "a declared dependency is not reachable"})


def _unhealthy(fp="fp-health", container="argus-lab-api", starts=T0) -> AlertNotification:
    return AlertNotification(fingerprint=fp, status="firing", starts_at=starts, ends_at=None,
                             labels={"alertname": "ContainerUnhealthy", "argus_host": "vm-166", "container": container},
                             annotations={"summary": "the Docker health check reports unhealthy"})


def _handle(app, metrics, **kw):
    from argus.application.alerts import HandleAlertNotification
    return HandleAlertNotification(app.store, app.inventory, metrics, **kw)


def test_two_alerts_on_one_target_and_class_are_one_incident(make_app):
    app = make_app()
    handle = _handle(app, FakeMetrics(SC03))
    first = handle(_probe(), source="alertmanager@vm-166")
    second = handle(_unhealthy(), source="alertmanager@vm-166")
    assert first.disposition == "started" and second.disposition == "attached"
    assert second.incident_id == first.incident_id
    occ = app.store.alert_occurrences(first.incident_id)
    assert [(o["alertname"], o["disposition"]) for o in occ] == [("DependencyProbeFailed", "started"),
                                                                 ("ContainerUnhealthy", "attached")]
    version, last = app.store.evidence_state(first.incident_id)
    assert version == 2 and last is not None
    assert len(app.store.list_incidents()) == 1


def test_an_attached_alert_stays_attached_after_the_incident_closes(make_app):
    app = make_app()
    handle = _handle(app, FakeMetrics(SC03))
    first = handle(_probe(), source="alertmanager@vm-166")
    handle(_unhealthy(), source="alertmanager@vm-166")
    inc = app.store.get_incident(first.incident_id)
    inc.status, inc.closed_at = IncidentStatus.closed, utcnow()
    app.store.update_incident(inc)
    again = [handle(a, source="alertmanager@vm-166") for a in (_probe(), _unhealthy())]   # still firing: next pass
    assert [r.disposition for r in again] == ["duplicate", "duplicate"]
    assert {r.incident_id for r in again} == {first.incident_id}
    assert len(app.store.list_incidents()) == 1


def test_the_attach_is_audited_on_the_incident(make_app):
    app = make_app()
    audited, real = [], app.store.append
    app.store.append = lambda rec: audited.append(rec) or real(rec)
    handle = _handle(app, FakeMetrics(SC03))
    first = handle(_probe(), source="alertmanager@vm-166")
    handle(_unhealthy(), source="alertmanager@vm-166")
    ev = [a for a in audited if a.event == "incident.alert_attached"]
    assert len(ev) == 1 and ev[0].incident_id == first.incident_id
    assert ev[0].detail["alertname"] == "ContainerUnhealthy" and ev[0].detail["evidence_version"] == 2
    assert ev[0].detail["incident_class"] == "dependency_unavailable"


def test_a_different_class_opens_a_new_incident(make_app):
    app = make_app()
    handle = _handle(app, FakeMetrics(SC03))
    first = handle(_probe(), source="alertmanager@vm-166")
    inc = app.store.get_incident(first.incident_id)
    inc.status, inc.incident_class = IncidentStatus.running, "container_restart_loop"    # detected another class
    app.store.update_incident(inc)
    second = handle(_unhealthy(), source="alertmanager@vm-166")
    assert second.disposition == "started" and second.incident_id != first.incident_id


def test_no_compatibility_test_means_no_merge(make_app):
    app = make_app()
    first = _handle(app, FakeMetrics(SC03))(_probe(), source="alertmanager@vm-166")
    stale = _handle(app, FakeMetrics(SC03, stale=True))(_unhealthy(), source="alertmanager@vm-166")
    assert stale.disposition == "started" and stale.incident_id != first.incident_id
    healthy = _handle(app, FakeMetrics({API: {"dependency_probe_min": 1, "health_unhealthy": 0, "restarts_10m": 0}}))
    third = healthy(_unhealthy(fp="fp-3"), source="alertmanager@vm-166")         # fresh detection: no class at all
    assert third.disposition == "started" and third.incident_id not in (first.incident_id, stale.incident_id)


def test_a_different_dependency_is_an_independent_failure(make_app):
    app = make_app()
    handle = _handle(app, FakeMetrics(SC03))
    first = handle(_probe(), source="alertmanager@vm-166")
    other = handle(_probe(fp="fp-db", dependency="argus-lab-db"), source="alertmanager@vm-166")
    assert other.disposition == "started" and other.incident_id != first.incident_id


def test_only_an_open_incident_within_the_window_takes_an_alert(make_app):
    app = make_app()
    handle = _handle(app, FakeMetrics(SC03), window=timedelta(minutes=30))
    first = handle(_probe(), source="alertmanager@vm-166")
    inc = app.store.get_incident(first.incident_id)
    inc.status, inc.closed_at = IncidentStatus.closed, utcnow()
    app.store.update_incident(inc)
    after_close = handle(_unhealthy(), source="alertmanager@vm-166")
    assert after_close.disposition == "started" and after_close.incident_id != first.incident_id
    old = _handle(app, FakeMetrics(SC03), window=timedelta(seconds=0), now=lambda: utcnow() + timedelta(seconds=5))
    late = old(_unhealthy(fp="fp-late"), source="alertmanager@vm-166")
    assert late.disposition == "started" and late.incident_id != after_close.incident_id


def test_one_pull_pass_of_sc03_gives_one_incident(make_app):
    from argus.application.alerts import ReconcileFiringAlerts
    from test_t0022_alerting import FakeSource
    app = make_app()
    rec = ReconcileFiringAlerts(FakeSource({"vm-166": [_probe(), _unhealthy()]}), _handle(app, FakeMetrics(SC03)),
                                ["vm-166"])
    assert rec.run_once() == {"vm-166": {"started": 1, "attached": 1}}
    assert rec.run_once() == {"vm-166": {"duplicate": 2}}
    assert len(app.store.list_incidents()) == 1


def test_the_webhook_and_the_pull_correlate_with_the_detector_metrics(make_app):
    from fastapi.testclient import TestClient
    from argus.adapters.inbound.http import build_webhook
    app = make_app(metrics=FakeMetrics(SC03))
    assert isinstance(app.metrics, FakeMetrics)          # the metrics port the detectors use, exposed to intake
    app.alertmanager_token = "am-token-123"
    hook = TestClient(build_webhook(app))
    body = {"alerts": [{"status": "firing", "fingerprint": a.fingerprint, "startsAt": T0.isoformat(),
                        "labels": a.labels, "annotations": {}} for a in (_probe(), _unhealthy())]}
    out = hook.post("/api/v1/alerts", json=body, headers={"Authorization": "Bearer am-token-123"}).json()["accepted"]
    assert [o["disposition"] for o in out] == ["started", "attached"]
    assert out[0]["incident_id"] == out[1]["incident_id"] and not any(o["duplicate"] for o in out)
