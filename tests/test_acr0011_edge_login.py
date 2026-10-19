"""ACR-0011 (T-0016 step 4a): the API side of the public UI edge.

- A login that arrives through the edge (Nginx always sets `X-Argus-Edge`) issues only read tokens: without
  `scope=read` it is refused (400). The loopback login (CLI, Swagger) is unchanged.
- Failed logins are audited (`access.login_failed`: the username and the client, never the password) and limited per
  username and per client address, with a lockout (429 + Retry-After), as §17.3 already promised.
- `GET /api/v1/incidents` caps `limit` server-side (200), whatever the client asks.
"""
from __future__ import annotations

import sqlite3

import jwt
import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from test_core import make_app  # noqa: F401  (fixture)

PASSWORD = "a-long-password"
EDGE = {"X-Argus-Edge": "public", "X-Real-IP": "203.0.113.7"}


@pytest.fixture()
def ui(make_app):
    from argus.adapters.inbound.http import build_api
    app = make_app()
    pw = PasswordHash.recommended().hash(PASSWORD)
    app.store.upsert_principal("alice", "human", "operator", ["lab"], pw)
    app.store.upsert_principal("bob", "human", "viewer", ["lab"], pw)
    api = build_api(app)
    return app, api, TestClient(api)


def login(client, user="alice", password=PASSWORD, scope=None, headers=None):
    data = {"username": user, "password": password}
    if scope is not None:
        data["scope"] = scope
    return client.post("/api/v1/auth/token", data=data, headers=headers or {})


def access_events(app):
    with sqlite3.connect(app.settings.db_path) as c:
        return [row[0] for row in c.execute("SELECT body FROM audit WHERE incident_id IS NULL")]


# --- the edge login is read-only -----------------------------------------------------------------------------------
def test_a_login_through_the_edge_without_scope_read_is_refused(ui):
    _, _, client = ui
    r = login(client, headers=EDGE)
    assert r.status_code == 400 and "read" in r.json()["detail"]


def test_a_login_through_the_edge_with_scope_read_gets_a_read_token(ui):
    _, _, client = ui
    r = login(client, scope="read", headers=EDGE)
    assert r.status_code == 200
    assert jwt.decode(r.json()["access_token"], options={"verify_signature": False})["access"] == "read"


def test_the_loopback_login_is_unchanged(ui):
    _, _, client = ui
    r = login(client)                                   # CLI / Swagger: no edge header
    assert r.status_code == 200
    assert jwt.decode(r.json()["access_token"], options={"verify_signature": False})["access"] == "full"


# --- failed logins: audited and limited ----------------------------------------------------------------------------
def test_a_failed_login_is_audited_without_the_password(ui):
    app, _, client = ui
    guess = "-".join(["wrong", "guess", "123"])        # built at run time: no secret-like literal (gitleaks)
    assert login(client, password=guess, scope="read", headers=EDGE).status_code == 401
    events = [e for e in access_events(app) if '"access.login_failed"' in e]
    assert len(events) == 1
    assert '"alice"' in events[0] and "203.0.113.7" in events[0] and guess not in events[0]


def test_an_unknown_user_is_audited_and_answered_like_a_wrong_password(ui):
    app, _, client = ui
    r = login(client, user="nobody", password="x", scope="read", headers=EDGE)
    assert r.status_code == 401 and r.json()["detail"] == "bad credentials"
    assert any('"access.login_failed"' in e and '"nobody"' in e for e in access_events(app))


def test_too_many_failures_lock_the_username_even_with_the_right_password(ui):
    app, api, client = ui
    limit = api.state.login_limiter.max_per_user
    for _ in range(limit):
        assert login(client, password="wrong", scope="read", headers=EDGE).status_code == 401
    r = login(client, scope="read", headers=EDGE)                    # the right password, too late
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
    assert any('"access.login_locked"' in e for e in access_events(app))
    assert login(client, user="bob", scope="read", headers={**EDGE, "X-Real-IP": "198.51.100.1"}).status_code == 200


def test_too_many_failures_from_one_address_lock_that_address(ui):
    _, api, client = ui
    limit = api.state.login_limiter.max_per_address
    for i in range(limit):
        login(client, user=f"guess{i}", password="x", scope="read", headers=EDGE)
    assert login(client, user="bob", scope="read", headers=EDGE).status_code == 429
    assert login(client, user="bob", scope="read", headers={**EDGE, "X-Real-IP": "198.51.100.1"}).status_code == 200


def test_the_lock_ends_after_the_window_and_a_success_clears_the_count(ui):
    _, api, client = ui
    lim = api.state.login_limiter
    t = [1_000.0]
    lim.now = lambda: t[0]
    for _ in range(lim.max_per_user):
        login(client, password="wrong", scope="read", headers=EDGE)
    assert login(client, scope="read", headers=EDGE).status_code == 429
    t[0] += lim.window_s + 1
    assert login(client, scope="read", headers=EDGE).status_code == 200
    for _ in range(lim.max_per_user - 1):                            # a success cleared the user's count
        login(client, password="wrong", scope="read", headers=EDGE)
    assert login(client, scope="read", headers=EDGE).status_code == 200


def test_without_the_edge_the_client_address_is_the_peer_not_a_header(ui):
    """X-Real-IP counts only when the edge sent the request; otherwise anyone could pick a fresh address per try."""
    _, api, client = ui
    lim = api.state.login_limiter
    for i in range(lim.max_per_address):
        login(client, user=f"guess{i}", password="x", headers={"X-Real-IP": f"192.0.2.{i}"})
    assert login(client, user="bob", headers={"X-Real-IP": "192.0.2.250"}).status_code == 429


# --- the incident list is capped -----------------------------------------------------------------------------------
def test_the_incident_list_limit_is_capped_server_side(ui, monkeypatch):
    app, _, client = ui
    token = login(client, scope="read").json()["access_token"]
    asked = []
    monkeypatch.setattr(app.store, "list_incidents", lambda limit, parent_id=None: asked.append(limit) or [])
    client.get("/api/v1/incidents?limit=1000", headers={"Authorization": f"Bearer {token}"})
    client.get("/api/v1/incidents?limit=30", headers={"Authorization": f"Bearer {token}"})
    assert asked == [200, 30]
