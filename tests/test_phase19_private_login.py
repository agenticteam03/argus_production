"""ACR-0032 (phase 19): a private browser login whose full token works only on the private path.

`POST /api/v1/ops/auth/token` issues an `ops` token only to a human approver with two WebAuthn credentials, only when
the edge says the request came through the private path (`X-Argus-Ops: 1`); the session ends after 15 minutes without
a request, and one hour after the login at most. An `ops`
token is refused on any request without that header (the WebAuthn ceremonies included), and audited.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from argus.adapters.inbound.http import build_api
from test_core import make_app  # noqa: F401

PASSWORD = "a-long-password"
PRIVATE = {"X-Argus-Ops": "1", "X-Argus-Edge": "1", "X-Real-IP": "192.0.2.10"}
PUBLIC = {"X-Argus-Ops": "0", "X-Argus-Edge": "1", "X-Real-IP": "192.0.2.10"}
LOGIN = "/api/v1/ops/auth/token"


def _client(app, monkeypatch, *, credentials: int = 2, mounted: bool = True, edge: str = "testclient"):
    app.settings.ops_peer = edge                        # TestClient's peer plays the edge (argus-v18-ui)
    if mounted:
        app.action_rows = app.store
    password = PasswordHash.recommended().hash(PASSWORD)
    for user, role in (("alice", "approver"), ("olga", "operator")):
        app.store.upsert_principal(user, "human", role, ["lab"], password)
    app.store.upsert_principal("bot", "service", "approver", ["lab"], password)
    api = build_api(app)
    monkeypatch.setattr(api.state.second_factor, "credentials", lambda principal: [{}] * credentials)
    return api, TestClient(api)


def _login(client, user="alice", headers=PRIVATE):
    return client.post(LOGIN, data={"username": user, "password": PASSWORD}, headers=headers)


def test_the_private_login_is_unmounted_without_the_action_routes(make_app, monkeypatch):  # noqa: F811
    _, client = _client(make_app(), monkeypatch, mounted=False)
    assert _login(client).status_code == 404


def test_the_private_login_answers_404_off_the_private_path(make_app, monkeypatch):  # noqa: F811
    _, client = _client(make_app(), monkeypatch)
    assert _login(client, headers=PUBLIC).status_code == 404
    assert _login(client, headers={}).status_code == 404                     # loopback: no edge header at all


def test_the_header_counts_only_from_the_edge_itself(make_app, monkeypatch):  # noqa: F811
    """#325 review: the API's neighbours on argus-v18-core (worker, tunnel, egress) reach it without the edge; a
    header they send is not the private path."""
    app = make_app()
    _, client = _client(app, monkeypatch)
    token = _login(client).json()["access_token"]
    app.settings.ops_peer = "argus-v18-ui"              # the real edge's name; TestClient's peer is someone else now
    assert _login(client).status_code == 404
    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}", **PRIVATE}).status_code == 401


def test_an_approver_with_two_keys_gets_an_ops_token_for_one_hour_at_most(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    _, client = _client(app, monkeypatch)
    r = _login(client)
    assert r.status_code == 200, r.text
    assert r.json()["access"] == "ops"
    session = [s for s in app.store.audit_chain() if s[1]["event"] == "access.login"][-1][1]
    assert session["actor"] == "alice" and session["detail"]["via"] == "ops" and session["detail"]["access"] == "ops"
    jti = session["detail"]["session"]
    [row] = [s for s in _sessions(app) if s["jti"].startswith(jti)]
    assert row["expires_at"] - row["created_at"] == timedelta(hours=1)


def _sessions(app):
    return [app.store.get_session(r[0]) for r in app.store._q("SELECT jti FROM auth_session")]


def test_only_a_human_approver_with_two_keys_gets_one(make_app, monkeypatch):  # noqa: F811
    _, client = _client(make_app(), monkeypatch)
    assert _login(client, "olga").status_code == 401                         # an operator is not an approver
    assert _login(client, "bot").status_code == 401                          # a service is not a person
    assert client.post(LOGIN, data={"username": "alice", "password": "wrong"}, headers=PRIVATE).status_code == 401
    _, one_key = _client(make_app(), monkeypatch, credentials=1)
    assert _login(one_key).status_code == 401                                # ACR-0018 D3: two credentials


def test_a_refused_private_login_alerts_the_team(make_app, monkeypatch):  # noqa: F811
    """ACR-0032 §4: a refused or locked private login joins the security alerts (#344)."""
    from argus.infrastructure.security_alerts import ALERT_EVENTS
    app = make_app()
    _, client = _client(app, monkeypatch)
    assert client.post(LOGIN, data={"username": "alice", "password": "wrong"}, headers=PRIVATE).status_code == 401
    [refused] = [r[1] for r in app.store.audit_chain() if r[1]["event"] == "access.ops_login_failed"]
    assert refused["detail"]["via"] == "ops" and refused["detail"]["password_ok"] is False
    assert {"access.ops_login_failed", "access.login_locked"} <= set(ALERT_EVENTS)
    assert "access.login_failed" not in ALERT_EVENTS                     # a public typo does not page the team


def test_an_ops_token_is_refused_once_its_hour_is_over(make_app, monkeypatch):  # noqa: F811
    import argus.adapters.inbound.http as http
    _, client = _client(make_app(), monkeypatch)
    monkeypatch.setattr(http, "OPS_SESSION", timedelta(minutes=-1))     # issued already expired
    token = _login(client).json()["access_token"]
    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}", **PRIVATE}).status_code == 401


def test_an_ops_session_ends_after_15_minutes_without_a_request(make_app, monkeypatch):  # noqa: F811
    """Each request on the private path is activity and moves the idle deadline; 15 minutes without one end it."""
    import argus.adapters.inbound.http as http
    app = make_app()
    _, client = _client(app, monkeypatch)
    start = http.utcnow()
    token = _login(client).json()["access_token"]
    auth = {"Authorization": f"Bearer {token}", **PRIVATE}

    def me_at(minutes):
        monkeypatch.setattr(http, "utcnow", lambda: start + timedelta(minutes=minutes))
        return client.get("/api/v1/me", headers=auth).status_code

    assert me_at(10) == 200
    assert me_at(24) == 200                                              # 14 minutes after the last request
    assert me_at(40) == 401                                              # 16 minutes: ended
    assert me_at(41) == 401                                              # and it stays ended
    refused = [r[1] for r in app.store.audit_chain() if r[1]["event"] == "security.session_refused"]
    assert refused[-1]["detail"]["reason"] == "idle"


def test_the_store_refreshes_only_a_live_session(make_app):  # noqa: F811
    app = make_app()
    now = datetime.now(timezone.utc)
    idle = timedelta(minutes=15)
    app.store.add_session("c" * 32, "alice", "ops", now, now + timedelta(hours=1))
    assert app.store.touch_session("c" * 32, now + timedelta(minutes=14), idle)
    assert app.store.get_session("c" * 32)["last_seen_at"] == now + timedelta(minutes=14)
    assert not app.store.touch_session("c" * 32, now + timedelta(minutes=30), idle)
    app.store.add_session("d" * 32, "alice", "ops", now, now + timedelta(hours=1))
    app.store.revoke_session("d" * 32, "alice", "logout", now)
    assert not app.store.touch_session("d" * 32, now, idle)


def test_a_scoped_token_still_cannot_answer_an_approval(make_app, monkeypatch):  # noqa: F811
    _, client = _client(make_app(), monkeypatch)
    for scope in ("read", "investigate"):
        r = client.post("/api/v1/auth/token", headers=PRIVATE,
                        data={"username": "alice", "password": PASSWORD, "scope": scope})
        auth = {"Authorization": f"Bearer {r.json()['access_token']}", **PRIVATE}
        answer = client.post("/api/v1/ops/approvals/appr_x/answer", headers=auth,
                             json={"decision": "approved", "proposal_digest": "0" * 64, "step_up_token": "t"})
        assert answer.status_code in (401, 403), (scope, answer.text)


def test_an_ops_token_works_only_with_the_private_path_header(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    _, client = _client(app, monkeypatch)
    token = _login(client).json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}
    me = client.get("/api/v1/me", headers={**auth, **PRIVATE})
    assert me.status_code == 200 and me.json()["access"] == "ops"
    for headers in (PUBLIC, {}):
        assert client.get("/api/v1/me", headers={**auth, **headers}).status_code == 401
        assert client.post("/api/v1/auth/webauthn/step-up/options", headers={**auth, **headers},
                           json={"object": "approval:x:y"}).status_code == 401
    refused = [r[1] for r in app.store.audit_chain() if r[1]["event"] == "security.session_refused"]
    assert refused and refused[-1]["detail"]["reason"] == "off private path"


def test_an_ops_token_is_a_full_token_for_the_privileged_routes(make_app, monkeypatch):  # noqa: F811
    api, client = _client(make_app(), monkeypatch)
    monkeypatch.setattr(api.state.second_factor, "privileged_ready", lambda user, session: True)
    token = _login(client).json()["access_token"]
    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}", **PRIVATE}).json()
    assert {"approve_action", "place_hold"} <= set(me["permissions"])
    assert {"approve_action", "place_hold"} <= set(me["actions"])        # ACR-0001: the UI shows what /me lists


def test_without_the_second_factor_me_lists_no_privileged_action(make_app, monkeypatch):  # noqa: F811
    _, client = _client(make_app(), monkeypatch)                         # privileged_ready is false: no key yet
    token = _login(client).json()["access_token"]
    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}", **PRIVATE}).json()
    assert not {"approve_action", "place_hold"} & set(me["actions"])


def test_the_public_login_still_never_issues_a_full_token(make_app, monkeypatch):  # noqa: F811
    _, client = _client(make_app(), monkeypatch)
    r = client.post("/api/v1/auth/token", data={"username": "alice", "password": PASSWORD}, headers=PRIVATE)
    assert r.status_code == 400
