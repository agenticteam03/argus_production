"""Alert identity precision (ARCHITECTURE §6.6; review of PR #45).

The webhook's `startsAt` comes from Go's `time.Time` (up to nanoseconds; Python keeps microseconds) and the API v2's
from `strfmt.DateTime` (milliseconds). The identity truncates `startsAt` to milliseconds, so a pushed and a pulled copy
of one alert are one identity. The string format of the identities already stored (millisecond or whole-second
times) does not change, so a deploy cannot make a firing alert look new.
"""
from __future__ import annotations

from datetime import datetime, timezone

from argus.domain.model import AlertNotification
from test_core import make_app  # noqa: F401  (make_app = fixture)


def _alert(starts: datetime) -> AlertNotification:
    return AlertNotification(fingerprint="fp1", status="firing", starts_at=starts,
                             labels={"alertname": "ContainerUnhealthy", "argus_host": "vm-166",
                                     "container": "argus-lab-api"})


def test_a_pushed_and_a_pulled_copy_have_one_identity():
    from argus.application.alerts import alert_identity
    pushed = datetime(2026, 10, 9, 13, 21, 41, 123456, tzinfo=timezone.utc)      # Go nanoseconds, kept to µs
    pulled = datetime(2026, 10, 9, 13, 21, 41, 123000, tzinfo=timezone.utc)      # API v2 milliseconds
    assert alert_identity(_alert(pushed)) == alert_identity(_alert(pulled))


def test_the_stored_identity_format_does_not_change():
    from argus.application.alerts import alert_identity
    ms = datetime(2026, 10, 9, 13, 21, 41, 123000, tzinfo=timezone.utc)
    whole = datetime(2026, 10, 9, 13, 21, 41, tzinfo=timezone.utc)
    assert alert_identity(_alert(ms)) == f"alert:fp1:{ms.isoformat()}" == "alert:fp1:2026-10-09T13:21:41.123000+00:00"
    assert alert_identity(_alert(whole)) == "alert:fp1:2026-10-09T13:21:41+00:00"


def test_a_pushed_and_a_pulled_copy_open_one_incident(make_app):
    """The same alert with a nanosecond `startsAt` (push, Go) and a millisecond one (API v2 format) is one incident."""
    from fastapi.testclient import TestClient
    from argus.adapters.inbound.http import build_webhook
    from test_core import FakeMetrics
    app = make_app(metrics=FakeMetrics())
    app.alertmanager_token = "am-token-123"
    hook = TestClient(build_webhook(app))
    labels = _alert(datetime.now(timezone.utc)).labels

    def post(starts: str):
        body = {"alerts": [{"status": "firing", "fingerprint": "fp1", "startsAt": starts, "labels": labels,
                            "annotations": {}}]}
        return hook.post("/api/v1/alerts", json=body, headers={"Authorization": "Bearer am-token-123"}).json()

    first = post("2026-10-09T13:21:41.123456789Z")["accepted"][0]
    second = post("2026-10-09T13:21:41.123Z")["accepted"][0]
    assert second["duplicate"] and second["incident_id"] == first["incident_id"]
    assert len(app.store.list_incidents()) == 1
