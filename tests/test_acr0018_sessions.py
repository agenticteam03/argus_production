"""ACR-0018, phase 16 step 1: server-side sessions, revocation, the persisted login limiter, explicit permissions.

- Every token has a session row (its `jti`); every request checks it, so logout, a password change, a disable or an
  administrator's revocation ends a session at the next request, not at the token's expiry.
- A forged or foreign `jti`, or a token from before sessions existed, is refused.
- Failed logins are kept in the store: a restart of the API (a new limiter on the same store) keeps a lockout.
- Permissions are explicit per route; `/me` lists them; a role is a bundle.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from argus.adapters.inbound.http import ROLE_PERMISSIONS, LoginLimiter, build_api
from argus.domain.model import utcnow
from test_core import make_app  # noqa: F401  (fixture)

PASSWORD = "a-long-password"


@pytest.fixture()
def ui(make_app):
    app = make_app()
    pw = PasswordHash.recommended().hash(PASSWORD)
    app.store.upsert_principal("alice", "human", "operator", ["lab"], pw)
    app.store.upsert_principal("bob", "human", "viewer", ["lab"], pw)
    api = build_api(app)
    return app, api, TestClient(api)


def token(client, user="alice", scope=None) -> str:
    data = {"username": user, "password": PASSWORD, **({"scope": scope} if scope else {})}
    r = client.post("/api/v1/auth/token", data=data)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


def me(client, t: str):
    return client.get("/api/v1/me", headers=auth(t))


# --- sessions ----------------------------------------------------------------------------------------------------------
def test_a_login_creates_a_session_for_its_jti(ui):
    app, _, client = ui
    t = token(client)
    jti = jwt.decode(t, options={"verify_signature": False})["jti"]
    s = app.store.get_session(jti)
    assert s["principal"] == "alice" and s["access"] == "full" and s["revoked_at"] is None
    assert me(client, t).status_code == 200


def test_logout_ends_the_session_at_the_next_request(ui):
    app, _, client = ui
    t = token(client)
    assert client.post("/api/v1/auth/logout", headers=auth(t)).json() == {"ended": True}
    r = me(client, t)
    assert r.status_code == 401 and "session ended" in r.json()["detail"]
    assert '"access.logout"' in "".join(b for (b,) in sqlite3.connect(app.settings.db_path).execute(
        "SELECT body FROM audit WHERE incident_id IS NULL"))


@pytest.mark.parametrize("scope", ["read", "investigate"])
def test_a_narrowed_token_may_still_log_out(ui, scope):
    _, _, client = ui
    t = token(client, scope=scope)
    assert client.post("/api/v1/auth/logout", headers=auth(t)).status_code == 200
    assert me(client, t).status_code == 401


def test_revoking_a_principal_ends_all_its_sessions_and_only_its(ui):
    app, _, client = ui
    a1, a2, b = token(client), token(client, scope="read"), token(client, user="bob")
    assert app.store.revoke_principal_sessions("alice", "admin", "test", utcnow()) == 2
    assert me(client, a1).status_code == 401 and me(client, a2).status_code == 401
    assert me(client, b).status_code == 200


def test_a_revoked_session_stays_revoked(ui):
    app, _, client = ui
    jti = jwt.decode(token(client), options={"verify_signature": False})["jti"]
    assert app.store.revoke_session(jti, "alice", "logout", utcnow()) is True
    assert app.store.revoke_session(jti, "alice", "again", utcnow()) is False       # the first revocation is kept
    assert app.store.get_session(jti)["revoke_reason"] == "logout"


def _forge(app, sub: str, jti: str) -> str:
    now = utcnow()
    claims = {"sub": sub, "kind": "human", "role": "operator", "scopes": ["lab"], "access": "full", "iat": now,
              "exp": now + timedelta(minutes=5), "jti": jti, "aud": "argus-api"}
    return jwt.encode(claims, app.jwt_key, algorithm="HS256")


def test_a_token_without_a_session_is_refused(ui):
    """Signed with the right key (a token from before sessions existed, or one minted outside the login): refused."""
    app, _, client = ui
    assert me(client, _forge(app, "alice", uuid.uuid4().hex)).status_code == 401


def test_a_token_naming_another_principals_session_is_refused(ui):
    app, _, client = ui
    bobs = jwt.decode(token(client, user="bob"), options={"verify_signature": False})["jti"]
    assert me(client, _forge(app, "alice", bobs)).status_code == 401


def test_a_session_row_is_never_deleted(ui):
    app, _, client = ui
    token(client)
    with pytest.raises(sqlite3.IntegrityError, match="never deleted"):
        with sqlite3.connect(app.settings.db_path) as c:
            c.execute("DELETE FROM auth_session")


# --- the login limiter survives a restart ------------------------------------------------------------------------------
def test_a_lockout_survives_a_restart_of_the_api(ui):
    app, api, client = ui
    lim = api.state.login_limiter
    assert lim.store is app.store
    for _ in range(lim.max_per_user):
        client.post("/api/v1/auth/token", data={"username": "alice", "password": "wrong"})
    restarted = LoginLimiter(lim.max_per_user, lim.max_per_address, lim.window_s, app.store)
    assert restarted.retry_after("alice", "198.51.100.9") > 0                   # same user, any address: still locked
    restarted.succeeded("alice")
    assert restarted.retry_after("alice", "198.51.100.9") == 0


def test_without_a_store_the_limiter_counts_in_memory():
    lim = LoginLimiter(2, 10, 60, store=object())
    lim.failed("u", "a")
    lim.failed("u", "a")
    assert lim.store is None and lim.retry_after("u", "a") > 0


# --- permissions -------------------------------------------------------------------------------------------------------
def test_me_lists_the_permissions_of_the_role(ui):
    _, _, client = ui
    assert me(client, token(client)).json()["permissions"] == sorted(ROLE_PERMISSIONS["operator"])
    assert me(client, token(client, user="bob")).json()["permissions"] == ["view"]


@pytest.mark.parametrize("user, evidence, investigate", [("alice", 404, 202), ("bob", 403, 403)])
def test_each_route_checks_its_permission(ui, user, evidence, investigate):
    """The authorization matrix of the built routes: a viewer has `view` only."""
    _, _, client = ui
    t = token(client, user=user)
    assert client.get("/api/v1/evidence/ev_none", headers=auth(t)).status_code == evidence
    r = client.post("/api/v1/investigations", headers=auth(t), json={"target": "vm-166/container:argus-lab-worker"})
    assert r.status_code == investigate, r.text


def test_every_role_has_a_bundle_and_view_is_in_each():
    assert set(ROLE_PERMISSIONS) == {"viewer", "operator", "approver"}
    assert all("view" in perms for perms in ROLE_PERMISSIONS.values())


# --- EdDSA token signing (ACR-0018 §17.2) -------------------------------------------------------------------------------
@pytest.fixture()
def ed_ui(make_app):  # noqa: F811
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    app = make_app()
    app.jwt_signing = Ed25519PrivateKey.generate()
    app.store.upsert_principal("alice", "human", "operator", ["lab"], PasswordHash.recommended().hash(PASSWORD))
    return app, TestClient(build_api(app))


def test_with_an_ed25519_key_tokens_are_eddsa(ed_ui):
    _, client = ed_ui
    t = token(client)
    assert jwt.get_unverified_header(t)["alg"] == "EdDSA" and me(client, t).status_code == 200


def test_with_an_ed25519_key_an_hs256_token_is_refused_even_with_a_session(ed_ui):
    """No algorithm confusion: the old shared key, a real session row, still 401."""
    app, client = ed_ui
    jti = uuid.uuid4().hex
    app.store.add_session(jti, "alice", "full", utcnow(), utcnow() + timedelta(minutes=5))
    assert me(client, _forge(app, "alice", jti)).status_code == 401


def test_a_token_signed_by_another_ed25519_key_is_refused(ed_ui):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    app, client = ed_ui
    claims = jwt.decode(token(client), app.jwt_signing.public_key(), algorithms=["EdDSA"], audience="argus-api")
    assert me(client, jwt.encode(claims, Ed25519PrivateKey.generate(), algorithm="EdDSA")).status_code == 401


def test_the_signing_key_must_be_an_ed25519_pem():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from argus.infrastructure.wiring import ed25519_signing_key

    def pem(k):
        return k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                               serialization.NoEncryption()).decode()
    assert ed25519_signing_key(None) is None
    assert isinstance(ed25519_signing_key(pem(Ed25519PrivateKey.generate())), Ed25519PrivateKey)
    with pytest.raises(SystemExit, match="Ed25519"):
        ed25519_signing_key(pem(ec.generate_private_key(ec.SECP256R1())))
    with pytest.raises(SystemExit, match="not a PEM"):
        ed25519_signing_key("not a key")


# --- a refused session is a security event ----------------------------------------------------------------------------
def _security_events(app) -> list[dict]:
    import json
    with sqlite3.connect(app.settings.db_path) as c:
        bodies = [json.loads(b) for (b,) in c.execute("SELECT body FROM audit WHERE incident_id IS NULL")]
    return [b for b in bodies if b["category"] == "security"]


@pytest.mark.parametrize("case, reason", [("after_logout", "revoked"), ("no_session", "no session"),
                                          ("foreign", "another principal's session")])
def test_a_signed_token_without_its_session_is_audited(ui, case, reason):
    app, _, client = ui
    if case == "after_logout":
        t = token(client)
        client.post("/api/v1/auth/logout", headers=auth(t))
    elif case == "no_session":
        t = _forge(app, "alice", uuid.uuid4().hex)
    else:
        t = _forge(app, "alice", jwt.decode(token(client, user="bob"), options={"verify_signature": False})["jti"])
    assert me(client, t).status_code == 401
    events = _security_events(app)
    assert [(e["event"], e["actor"], e["detail"]["reason"]) for e in events] == [("security.session_refused", "alice", reason)]


def test_a_badly_signed_token_writes_nothing(ui):
    app, _, client = ui
    assert me(client, "not.a.jwt").status_code == 401
    assert _security_events(app) == []


def test_failures_out_of_the_window_are_pruned(ui):
    """Address-keyed failures are never cleared by a success; a new failure drops every row past the window."""
    app, api, _ = ui
    lim = api.state.login_limiter
    t = [1_000_000.0]
    lim.now = lambda: t[0]
    lim.failed("alice", "198.51.100.1")
    t[0] += lim.window_s + 5
    lim.failed("bob", "198.51.100.2")
    with sqlite3.connect(app.settings.db_path) as c:
        keys = sorted(k for (k,) in c.execute("SELECT key FROM login_failure"))
    assert keys == ["a:198.51.100.2", "u:bob"]


def test_a_successful_login_is_audited_without_the_token(ui):
    import json
    app, _, client = ui
    t = token(client, scope="read")
    jti = jwt.decode(t, options={"verify_signature": False})["jti"]
    with sqlite3.connect(app.settings.db_path) as c:
        rows = [json.loads(b) for (b,) in c.execute("SELECT body FROM audit WHERE incident_id IS NULL")]
    login = [r for r in rows if r["event"] == "access.login"]
    assert len(login) == 1 and login[0]["actor"] == "alice"
    assert login[0]["detail"]["access"] == "read" and login[0]["detail"]["session"] == jti[:8]
    assert t not in json.dumps(login[0]) and jti not in json.dumps(login[0])
