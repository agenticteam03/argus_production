"""T-0015: read access for user interfaces (ACR-0001). A login with scope=read gives a token that can only read:
it is refused on every route that is not a GET, whatever the user's role, and the refusal is audited."""
from __future__ import annotations

import sqlite3

import jwt
import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from test_core import make_app  # noqa: F401  (fixture)

PASSWORD = "a-long-password"
TARGET = "vm-166/container:argus-lab-worker"


@pytest.fixture()
def ui(make_app):
    from argus.adapters.inbound.http import build_api
    app = make_app()
    pw = PasswordHash.recommended().hash(PASSWORD)
    app.store.upsert_principal("alice", "human", "operator", ["lab"], pw)
    app.store.upsert_principal("vera", "human", "viewer", ["lab"], pw)
    return app, TestClient(build_api(app))


def login(api, user, scope=None):
    data = {"username": user, "password": PASSWORD}
    if scope is not None:
        data["scope"] = scope
    return api.post("/api/v1/auth/token", data=data)


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def claims(token):
    return jwt.decode(token, options={"verify_signature": False})


# --- step 2: read-only tokens --------------------------------------------------------------------------------------
def test_scope_read_gives_a_read_token_and_the_default_stays_full(ui):
    app, api = ui
    assert claims(login(api, "alice", "read").json()["access_token"])["access"] == "read"
    assert claims(login(api, "alice").json()["access_token"])["access"] == "full"


def test_unknown_scope_is_refused(ui):
    app, api = ui
    assert login(api, "alice", "admin").status_code == 400


def test_read_token_is_refused_on_every_non_get_route_and_audited(ui):
    app, api = ui
    read = bearer(login(api, "alice", "read").json()["access_token"])
    full = bearer(login(api, "alice").json()["access_token"])
    body = {"target": TARGET, "reason": "ui test"}
    r = api.post("/api/v1/investigations", headers=read, json=body)
    assert r.status_code == 403 and "read-only" in r.json()["detail"]
    assert api.post("/api/v1/investigations", headers=full, json=body).status_code == 202   # same user, full token
    # every non-GET route (except the login itself, and ending one's own session: ACR-0018) refuses a read token,
    # including routes added in the future
    from argus.adapters.inbound.http import ANY_TOKEN_WRITES
    writes = [(m, rt.path) for rt in api.app.routes for m in getattr(rt, "methods", set())
              if m not in ("GET", "HEAD") and rt.path != "/api/v1/auth/token" and (m, rt.path) not in ANY_TOKEN_WRITES]
    assert writes
    for method, path in writes:
        res = api.request(method, path.replace("{incident_id}", "inc_x"), headers=read, json={})
        assert res.status_code == 403, (method, path, res.status_code)
    with sqlite3.connect(app.settings.db_path) as c:
        events = [row[0] for row in c.execute("SELECT body FROM audit WHERE incident_id IS NULL")]
    assert any('"access.read_only_refused"' in e and '"alice"' in e for e in events)


def test_read_token_can_use_every_get_route(ui):
    app, api = ui
    full = bearer(login(api, "alice").json()["access_token"])
    inc = api.post("/api/v1/investigations", headers=full, json={"target": TARGET, "reason": "x"}).json()["incident_id"]
    read = bearer(login(api, "alice", "read").json()["access_token"])
    gets = [rt.path for rt in api.app.routes if "GET" in getattr(rt, "methods", set()) and rt.path.startswith("/api/")]
    assert "/api/v1/incidents" in gets
    params = {"/api/v1/target-metrics": {"target": TARGET}}                 # its one required parameter (ACR-0021)
    for path in gets:
        res = api.get(path.replace("{incident_id}", inc).replace("{evidence_id}", "ev_missing"), headers=read,
                      params=params.get(path))
        assert res.status_code in (200, 404), (path, res.status_code)          # never 401/403 for a read token


def test_a_token_from_before_this_change_counts_as_full(ui):
    """Tokens issued before the `access` claim existed (still valid up to 30 minutes after a redeploy)."""
    app, api = ui
    old = claims(login(api, "alice").json()["access_token"])
    old.pop("access")
    token = jwt.encode(old, app.jwt_key, algorithm="HS256")
    assert api.post("/api/v1/investigations", headers=bearer(token), json={"target": TARGET}).status_code == 202


def test_the_role_still_decides_what_a_full_token_may_do(ui):
    app, api = ui
    viewer = bearer(login(api, "vera").json()["access_token"])
    assert api.post("/api/v1/investigations", headers=viewer, json={"target": TARGET}).status_code == 403


# --- step 3: GET /api/v1/me -----------------------------------------------------------------------------------------
def me(api, user, scope=None):
    return api.get("/api/v1/me", headers=bearer(login(api, user, scope).json()["access_token"]))


def test_me_tells_a_ui_who_is_logged_in_and_what_the_token_may_do(ui):
    app, api = ui
    r = me(api, "alice", "read")
    assert r.status_code == 200
    assert r.json() == {"user": "alice", "role": "operator", "access": "read",
                        "actions": ["view_incidents", "view_timeline", "view_evidence"],
                        "permissions": ["investigate", "view", "view_evidence"]}    # ACR-0018: what the role grants
    full = me(api, "alice").json()
    assert full["access"] == "full" and full["actions"] == ["view_incidents", "view_timeline", "view_evidence",
                                                            "start_investigation"]
    viewer = me(api, "vera").json()                      # a viewer's full token still cannot read evidence or start
    assert viewer["role"] == "viewer" and viewer["actions"] == ["view_incidents", "view_timeline"]


def test_me_needs_a_valid_token(ui):
    app, api = ui
    assert api.get("/api/v1/me").status_code == 401
    assert api.get("/api/v1/me", headers=bearer("not-a-token")).status_code == 401


# --- step 4: browser access for development (ARGUS_UI_ORIGINS) -----------------------------------------------------
DEV = "http://localhost:5173"


def preflight(api, origin):
    return api.options("/api/v1/incidents", headers={"Origin": origin, "Access-Control-Request-Method": "GET",
                                                      "Access-Control-Request-Headers": "authorization"})


def test_no_cors_headers_by_default(ui):
    app, api = ui
    assert app.settings.ui_origins == []
    r = api.get("/healthz", headers={"Origin": DEV})
    assert "access-control-allow-origin" not in r.headers
    assert "access-control-allow-origin" not in preflight(api, DEV).headers


def test_listed_origins_only(make_app, monkeypatch):
    from argus.adapters.inbound.http import build_api
    monkeypatch.setenv("ARGUS_UI_ORIGINS", f"{DEV}, http://127.0.0.1:5173")
    app = make_app()
    assert app.settings.ui_origins == [DEV, "http://127.0.0.1:5173"]
    api = TestClient(build_api(app))
    ok = preflight(api, DEV)
    assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == DEV
    assert "access-control-allow-origin" not in preflight(api, "http://evil.example").headers
    assert api.get("/healthz", headers={"Origin": DEV}).headers["access-control-allow-origin"] == DEV
