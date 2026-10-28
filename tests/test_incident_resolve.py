"""ACR-0041: a person closes an escalated incident that was fixed outside Argus, with a reason.

`POST /api/v1/incidents/{id}/resolve` needs the `resolve_incident` permission (operator, approver; never a viewer) and
works with the UI's `investigate` token, like starting an investigation (ACR-0012): closing an incident acts on nothing.
Only an `escalated` incident may be resolved; the incident keeps its diagnosis and outcome, gains a `resolution` (who,
when, why) and becomes `closed`, and the audit records `incident.resolved` on the incident.
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from argus.adapters.inbound.http import build_api
from argus.domain.model import IncidentOutcome, IncidentStatus, utcnow
from test_core import incident, make_app  # noqa: F401

PASSWORD = "a-long-password"
TARGET = "vm-166/container:argus-lab-cache"


def _client(app, role="operator", scope="investigate"):
    app.store.upsert_principal("olga", "human", role, ["lab"], PasswordHash.recommended().hash(PASSWORD))
    client = TestClient(build_api(app))
    data = {"username": "olga", "password": PASSWORD, **({"scope": scope} if scope else {})}
    token = client.post("/api/v1/auth/token", data=data).json()["access_token"]
    return client, {"Authorization": f"Bearer {token}"}


def _escalated(app):
    inc = incident(app, TARGET)
    inc.status, inc.outcome = IncidentStatus.escalated, IncidentOutcome.diagnosed
    inc.diagnosis, inc.closed_at = "the cache was stopped", utcnow()
    app.store.update_incident(inc)
    return inc


def test_an_operator_resolves_an_escalated_incident_with_a_reason(make_app):  # noqa: F811
    app = make_app()
    inc = _escalated(app)
    client, auth = _client(app)
    r = client.post(f"/api/v1/incidents/{inc.id}/resolve", headers=auth, json={"reason": "  restarted by hand  "})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "closed" and r.json()["resolution"]["by"] == "olga"
    done = app.store.get_incident(inc.id)
    assert done.status == IncidentStatus.closed and done.outcome == IncidentOutcome.diagnosed
    assert done.diagnosis == "the cache was stopped"                       # the diagnosis is kept
    assert done.resolution.by == "olga" and done.resolution.reason == "restarted by hand"
    [line] = [b for _, b, _, _ in app.store.audit_chain() if b["event"] == "incident.resolved"]
    assert line["actor"] == "olga" and line["incident_id"] == inc.id
    assert line["detail"] == {"reason": "restarted by hand", "outcome": "diagnosed"}
    page = client.get(f"/api/v1/incidents/{inc.id}", headers=auth).json()
    assert page["status"] == "closed" and page["resolution"]["reason"] == "restarted by hand"


def test_only_an_escalated_incident_can_be_resolved_and_only_once(make_app):  # noqa: F811
    app = make_app()
    queued = incident(app, TARGET)
    inc = _escalated(app)
    client, auth = _client(app)
    assert client.post(f"/api/v1/incidents/{queued.id}/resolve", headers=auth,
                       json={"reason": "x"}).status_code == 409
    assert client.post(f"/api/v1/incidents/{inc.id}/resolve", headers=auth, json={"reason": "x"}).status_code == 200
    assert client.post(f"/api/v1/incidents/{inc.id}/resolve", headers=auth, json={"reason": "y"}).status_code == 409
    assert app.store.get_incident(inc.id).resolution.reason == "x"
    assert client.post("/api/v1/incidents/inc_missing/resolve", headers=auth, json={"reason": "x"}).status_code == 404


def test_a_reason_is_required_and_bounded(make_app):  # noqa: F811
    app = make_app()
    inc = _escalated(app)
    client, auth = _client(app)
    for body in ({}, {"reason": ""}, {"reason": "   "}, {"reason": "x" * 501}, {"reason": "x", "extra": 1}):
        assert client.post(f"/api/v1/incidents/{inc.id}/resolve", headers=auth, json=body).status_code == 422, body
    assert app.store.get_incident(inc.id).status == IncidentStatus.escalated


def test_a_viewer_or_a_read_token_cannot_resolve(make_app):  # noqa: F811
    app = make_app()
    inc = _escalated(app)
    client, auth = _client(app, role="viewer", scope="read")
    assert client.post(f"/api/v1/incidents/{inc.id}/resolve", headers=auth, json={"reason": "x"}).status_code == 403
    app2 = make_app()
    inc2 = _escalated(app2)
    client2, auth2 = _client(app2, role="operator", scope="read")
    assert client2.post(f"/api/v1/incidents/{inc2.id}/resolve", headers=auth2, json={"reason": "x"}).status_code == 403
    assert app2.store.get_incident(inc2.id).status == IncidentStatus.escalated


def test_me_lists_the_resolve_action_for_an_operator_but_not_a_viewer(make_app):  # noqa: F811
    app = make_app()
    client, auth = _client(app)
    assert "resolve_incident" in client.get("/api/v1/me", headers=auth).json()["actions"]
    app2 = make_app()
    client2, auth2 = _client(app2, role="viewer", scope="read")
    assert "resolve_incident" not in client2.get("/api/v1/me", headers=auth2).json()["actions"]


def test_the_store_closes_only_an_escalated_incident(make_app):  # noqa: F811
    app = make_app()
    inc = _escalated(app)
    now = utcnow()
    done = app.store.resolve_incident(inc.id, "olga", "fixed", now)
    assert done is not None and done.status == IncidentStatus.closed and done.resolution.at == now
    assert app.store.resolve_incident(inc.id, "olga", "again", now) is None
    assert app.store.resolve_incident(incident(app, TARGET).id, "olga", "queued", now) is None
