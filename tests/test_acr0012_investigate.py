"""ACR-0012 (T-0016 "Level 1 Investigate"), the API side: the UI may start an investigation.

- A third kind of token, `scope=investigate`: every GET and exactly one POST, `/api/v1/investigations`. Any other
  non-GET is refused (403, audited `access.investigate_scope_refused`); it only narrows the role (a viewer cannot).
- A login through the public edge may ask `read` or `investigate`, never a full token.
- `/me` lists `start_investigation` for an operator/approver holding a full or an investigate token.
- Quotas for investigate tokens (the UI): per principal per hour, per principal queued, and all queued manual
  incidents; over one, 429 with Retry-After, audited `investigation.quota_refused`. Alerts and full tokens (the CLI,
  the E2E runner, over loopback) are never counted against them.
- `GET /api/v1/targets`: the inventory's target refs (host, kind, name) for the UI's target list, any role.
- Every accepted request is audited `investigation.requested` (who, how, from where).
"""
from __future__ import annotations

import sqlite3
import time

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from starlette.requests import Request

from argus.domain.model import RequestKind, TargetRef, TriggerKind, utcnow
from test_core import make_app  # noqa: F401  (fixture)

PASSWORD = "a-long-password"
EDGE = {"X-Argus-Edge": "public", "X-Real-IP": "203.0.113.9"}
TARGET = "vm-166/container:argus-lab-api"


@pytest.fixture()
def ui(make_app):
    from argus.adapters.inbound.http import build_api
    app = make_app()
    pw = PasswordHash.recommended().hash(PASSWORD)
    app.store.upsert_principal("alice", "human", "operator", ["lab"], pw)
    app.store.upsert_principal("vera", "human", "viewer", ["lab"], pw)
    app.store.upsert_principal("bob", "human", "operator", ["lab"], pw)

    def client():
        return TestClient(build_api(app))
    return app, client


def token(c, user="alice", scope=None, headers=None):
    data = {"username": user, "password": PASSWORD}
    if scope is not None:
        data["scope"] = scope
    r = c.post("/api/v1/auth/token", data=data, headers=headers or {})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def bearer(t, extra=None):
    return {"Authorization": f"Bearer {t}", **(extra or {})}


def access(t):
    return jwt.decode(t, options={"verify_signature": False})["access"]


def start(c, t, target=TARGET, headers=None, **body):
    return c.post("/api/v1/investigations", json={"target": target, "reason": "ui test", **body},
                  headers=bearer(t, headers))


def audit_bodies(app):
    with sqlite3.connect(app.settings.db_path) as conn:
        return [r[0] for r in conn.execute("SELECT body FROM audit WHERE incident_id IS NULL")]


# --- the token ---------------------------------------------------------------------------------------------------------
def test_scope_investigate_gives_an_investigate_token_on_loopback_and_through_the_edge(ui):
    _, client = ui
    c = client()
    assert access(token(c, scope="investigate")) == "investigate"
    assert access(token(c, scope="investigate", headers=EDGE)) == "investigate"
    assert access(token(c, scope="read", headers=EDGE)) == "read"


def test_the_edge_never_issues_a_full_token(ui):
    _, client = ui
    c = client()
    r = c.post("/api/v1/auth/token", data={"username": "alice", "password": PASSWORD}, headers=EDGE)
    assert r.status_code == 400
    assert c.post("/api/v1/auth/token", data={"username": "alice", "password": PASSWORD, "scope": "admin"}
                  ).status_code == 400


def test_an_investigate_token_reads_and_starts_an_investigation(ui):
    _, client = ui
    c = client()
    t = token(c, scope="investigate", headers=EDGE)
    assert c.get("/api/v1/incidents", headers=bearer(t)).status_code == 200
    r = start(c, t, headers=EDGE)
    assert r.status_code == 202 and r.json()["incident_id"].startswith("inc_")


def test_an_investigate_token_refuses_any_other_non_get_and_audits_it(ui):
    from argus.adapters.inbound.http import _principal_dep
    app, client = ui
    t = token(client(), scope="investigate")
    dep = _principal_dep(app)
    for method, path in (("POST", "/api/v1/approvals"), ("DELETE", "/api/v1/investigations"),
                         ("PUT", "/api/v1/investigations"), ("POST", "/api/v1/investigations/x")):
        req = Request({"type": "http", "method": method, "path": path, "headers": [], "query_string": b""})
        with pytest.raises(HTTPException) as e:
            dep(req, t)
        assert e.value.status_code == 403
    assert any('"access.investigate_scope_refused"' in b and '"alice"' in b for b in audit_bodies(app))


def test_a_viewer_cannot_start_an_investigation_whatever_the_token(ui):
    _, client = ui
    c = client()
    assert start(c, token(c, user="vera", scope="investigate")).status_code == 403


def test_a_read_token_still_cannot_start_an_investigation(ui):
    _, client = ui
    c = client()
    assert start(c, token(c, scope="read")).status_code == 403


# --- /me ---------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("user, scope, listed", [
    ("alice", "investigate", True), ("alice", None, True), ("alice", "read", False), ("vera", "investigate", False),
])
def test_me_lists_start_investigation_only_where_it_works(ui, user, scope, listed):
    _, client = ui
    c = client()
    me = c.get("/api/v1/me", headers=bearer(token(c, user=user, scope=scope))).json()
    assert ("start_investigation" in me["actions"]) is listed


# --- quotas ------------------------------------------------------------------------------------------------------------
def test_queued_per_principal_is_limited_with_retry_after_and_audited(ui):
    app, client = ui
    app.settings.investigations_queued_per_principal = 2
    c = client()
    t = token(c, scope="investigate", headers=EDGE)
    assert [start(c, t, headers=EDGE).status_code for _ in range(2)] == [202, 202]
    r = start(c, t, headers=EDGE)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
    assert any('"investigation.quota_refused"' in b and '"queued_per_principal"' in b for b in audit_bodies(app))
    assert start(c, token(c, user="bob", scope="investigate", headers=EDGE), headers=EDGE).status_code == 202


def test_per_hour_counts_closed_ones_too(ui):
    app, client = ui
    app.settings.investigations_per_hour = 3
    c = client()
    t = token(c, scope="investigate", headers=EDGE)
    for _ in range(3):                                   # each one closed, so only the hourly count can refuse
        inc_id = start(c, t, headers=EDGE).json()["incident_id"]
        assert app.store.close_queued_incident(inc_id, "resolved_externally", "test", utcnow())
    r = start(c, t, headers=EDGE)
    assert r.status_code == 429
    assert any('"per_hour"' in b for b in audit_bodies(app))


def test_an_idempotent_retry_at_the_quota_gets_its_incident_not_429(ui):
    app, client = ui
    app.settings.investigations_queued_per_principal = 1
    c = client()
    t = token(c, scope="investigate", headers=EDGE)
    first = start(c, t, headers=EDGE, idempotency_key="ui:retry-1")
    again = start(c, t, headers=EDGE, idempotency_key="ui:retry-1")
    assert first.status_code == 202 and again.status_code == 202
    assert again.json() == {**first.json(), "duplicate": True}
    assert start(c, t, headers=EDGE, idempotency_key="ui:retry-2").status_code == 429


def test_concurrent_requests_cannot_pass_the_same_last_slot(ui):
    from concurrent.futures import ThreadPoolExecutor
    app, client = ui
    app.settings.investigations_queued_per_principal = 1
    c = client()
    t = token(c, scope="investigate", headers=EDGE)
    real = app.store.list_incidents

    def slow_list(limit):                                # widen the check-then-create window
        rows = real(limit)
        time.sleep(0.2)
        return rows
    app.store.list_incidents = slow_list
    with ThreadPoolExecutor(4) as pool:
        codes = sorted(pool.map(lambda _: start(c, t, headers=EDGE).status_code, range(4)))
    assert codes == [202, 429, 429, 429]


def test_all_queued_manual_incidents_are_capped(ui):
    app, client = ui
    app.settings.investigations_queued_max = 2
    c = client()
    a, b = (token(c, user=u, scope="investigate", headers=EDGE) for u in ("alice", "bob"))
    assert start(c, a, headers=EDGE).status_code == 202 and start(c, b, headers=EDGE).status_code == 202
    assert start(c, a, headers=EDGE).status_code == 429


def test_alerts_and_full_tokens_are_never_counted_or_blocked(ui):
    from argus.adapters.inbound.http import new_incident
    app, client = ui
    app.settings.investigations_queued_per_principal = 1
    app.settings.investigations_queued_max = 1
    for i in range(3):                                   # queued alert incidents: not manual, not counted
        app.store.create_incident(new_incident(TargetRef.parse(TARGET), TriggerKind.alert, RequestKind.report,
                                               "alert", None, f"alert:{i}"), f"alert:{i}")
    c = client()
    assert start(c, token(c, scope="investigate", headers=EDGE), headers=EDGE).status_code == 202
    full = token(c)                                      # loopback, full: the CLI and the E2E runner
    assert [start(c, full).status_code for _ in range(3)] == [202, 202, 202]


# --- the target list and the audit -------------------------------------------------------------------------------------
def test_targets_lists_the_inventory_refs_for_any_role(ui):
    app, client = ui
    c = client()
    rows = c.get("/api/v1/targets", headers=bearer(token(c, user="vera", scope="read"))).json()
    refs = {r["target"] for r in rows}
    assert TARGET in refs and all(set(r) == {"target", "host", "kind", "name", "state"} for r in rows)
    assert refs == {str(t.ref) for t in app.inventory.targets()}


def test_an_accepted_request_is_audited_with_how_and_from_where(ui):
    app, client = ui
    c = client()
    inc_id = start(c, token(c, scope="investigate", headers=EDGE), headers=EDGE).json()["incident_id"]
    rows = [b for b in audit_bodies(app) if '"investigation.requested"' in b]
    assert len(rows) == 1 and inc_id in rows[0] and '"edge"' in rows[0] and "203.0.113.9" in rows[0]
    assert '"investigate"' in rows[0]
