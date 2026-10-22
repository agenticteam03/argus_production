"""ACR-0018, phase 16 step 3: the WebAuthn second factor and the step-up token (D1-D4 in the PHASE-16 task).

A software authenticator (ECDSA P-256, "none" attestation) runs the real ceremonies against py_webauthn:
- a password alone never binds a key: the first credential needs another administrator's ticket, single-use and
  expiring, for that person only; a further one needs a step-up of an enrolled key;
- a login completed with a key marks that session only; a privileged permission needs it and two keys (D3);
- a step-up token is single-use, ≤ 5 minutes, and only for the principal, session and object it was issued for;
- a challenge is single-use, short-lived and bound to its ceremony; a wrong origin or relying party, or a counter that
  goes back (a cloned key), is refused; every refusal is audited;
- another administrator's reset revokes the keys and ends the sessions; nobody resets themselves.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
from datetime import timedelta

import cbor2
import jwt
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from argus.adapters.inbound.http import ROLE_PERMISSIONS, build_api
from argus.application.second_factor import SecondFactorRefused, register_object
from argus.domain.model import utcnow
from test_core import make_app  # noqa: F401  (fixture)

PASSWORD = "a-long-password"
RP, ORIGIN = "argus.example.test", "https://argus.example.test"


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class SoftKey:
    """A software authenticator: what a passkey or a security key returns to the browser."""

    def __init__(self, rp_id: str = RP, origin: str = ORIGIN):
        self.rp_id, self.origin = rp_id, origin
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.cred_id = os.urandom(16)
        self.count = 0

    def _client(self, kind: str, challenge: str) -> bytes:
        return json.dumps({"type": kind, "challenge": challenge, "origin": self.origin, "crossOrigin": False}).encode()

    def create(self, options: dict) -> dict:
        n = self.key.public_key().public_numbers()
        cose = cbor2.dumps({1: 2, 3: -7, -1: 1, -2: n.x.to_bytes(32, "big"), -3: n.y.to_bytes(32, "big")})
        auth = (hashlib.sha256(self.rp_id.encode()).digest() + bytes([0x45]) + self.count.to_bytes(4, "big")
                + bytes(16) + len(self.cred_id).to_bytes(2, "big") + self.cred_id + cose)
        att = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth})
        return {"id": b64(self.cred_id), "rawId": b64(self.cred_id), "type": "public-key",
                "response": {"clientDataJSON": b64(self._client("webauthn.create", options["challenge"])),
                             "attestationObject": b64(att)}}

    def get(self, options: dict, count: int | None = None) -> dict:
        self.count = self.count + 1 if count is None else count
        auth = hashlib.sha256(self.rp_id.encode()).digest() + bytes([0x05]) + self.count.to_bytes(4, "big")
        client = self._client("webauthn.get", options["challenge"])
        sig = self.key.sign(auth + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256()))
        return {"id": b64(self.cred_id), "rawId": b64(self.cred_id), "type": "public-key",
                "response": {"clientDataJSON": b64(client), "authenticatorData": b64(auth), "signature": b64(sig)}}


@pytest.fixture()
def wa(make_app):
    app = make_app()
    app.settings.webauthn_rp_id, app.settings.webauthn_origin = RP, ORIGIN
    pw = PasswordHash.recommended().hash(PASSWORD)
    for user in ("alice", "bob"):
        app.store.upsert_principal(user, "human", "operator", ["lab"], pw)
    api = build_api(app)
    return app, api.state.second_factor, TestClient(api)


def login(client, user="alice", scope=None) -> tuple[dict, str]:
    r = client.post("/api/v1/auth/token", data={"username": user, "password": PASSWORD,
                                                **({"scope": scope} if scope else {})})
    assert r.status_code == 200, r.text
    t = r.json()["access_token"]
    return {"Authorization": f"Bearer {t}"}, jwt.decode(t, options={"verify_signature": False})["jti"]


def enrol(client, h, key, ticket=None, step_up=None, label="key"):
    r = client.post("/api/v1/auth/webauthn/register/options", json={"ticket": ticket, "step_up_token": step_up},
                    headers=h)
    if r.status_code != 200:
        return r
    return client.post("/api/v1/auth/webauthn/register/verify", headers=h,
                       json={"challenge_id": r.json()["challenge_id"], "credential": key.create(r.json()["options"]),
                             "label": label})


def assertion(client, h, key, kind, obj=None, count=None):
    body = {"object": obj} if kind == "step-up" else None
    r = client.post(f"/api/v1/auth/webauthn/{kind}/options", json=body, headers=h)
    assert r.status_code == 200, r.text
    return client.post(f"/api/v1/auth/webauthn/{kind}/verify", headers=h,
                       json={"challenge_id": r.json()["challenge_id"],
                             "credential": key.get(r.json()["options"], count)})


def _audit_rows(app):
    rows = app.store._q("SELECT body FROM audit ORDER BY rowid")
    return [json.loads(r[0]) for r in rows]


def enrolled(app, second, client, user="alice", keys=1):
    """`user` logged in with `keys` enrolled keys (the first by a ticket from the other administrator)."""
    h, jti = login(client, user)
    other = "bob" if user == "alice" else "alice"
    first = SoftKey()
    assert enrol(client, h, first, ticket=second.allow_enrol(user, other)).status_code == 200
    made = [first]
    for _ in range(keys - 1):
        r = assertion(client, h, first, "step-up", register_object(user))
        nxt = SoftKey()
        assert enrol(client, h, nxt, step_up=r.json()["step_up_token"]).status_code == 200
        made.append(nxt)
    return h, jti, made


# --- configuration --------------------------------------------------------------------------------------------------
def test_without_a_relying_party_the_ceremonies_answer_503(make_app):
    app = make_app()
    client = TestClient(build_api(app))
    app.store.upsert_principal("alice", "human", "operator", ["lab"], PasswordHash.recommended().hash(PASSWORD))
    h, _ = login(client)
    assert client.post("/api/v1/auth/webauthn/login/options", headers=h).status_code == 503
    assert client.get("/api/v1/me", headers=h).json()["second_factor"] is None


# --- enrolment (D4) ------------------------------------------------------------------------------------------------
def test_a_password_alone_cannot_bind_a_key(wa):
    app, second, client = wa
    h, _ = login(client)
    r = enrol(client, h, SoftKey())
    assert r.status_code == 403 and "enrolment ticket" in r.json()["detail"]
    assert [e["detail"]["reason"] for e in _audit_rows(app) if e["event"] == "security.webauthn_register_refused"]
    assert second.credentials("alice") == []


def test_the_first_key_takes_another_administrators_ticket_once(wa):
    app, second, client = wa
    with pytest.raises(SecondFactorRefused):
        second.allow_enrol("alice", "alice")                     # nobody issues their own
    code = second.allow_enrol("alice", "bob")
    assert code not in json.dumps(_audit_rows(app))              # the code is never recorded, only its hash
    h, _ = login(client)
    a, b = SoftKey(), SoftKey()
    opts = [client.post("/api/v1/auth/webauthn/register/options", json={"ticket": code}, headers=h).json()
            for _ in range(2)]                                   # two ceremonies started with the same ticket
    ok = client.post("/api/v1/auth/webauthn/register/verify", headers=h,
                     json={"challenge_id": opts[0]["challenge_id"], "credential": a.create(opts[0]["options"])})
    again = client.post("/api/v1/auth/webauthn/register/verify", headers=h,
                        json={"challenge_id": opts[1]["challenge_id"], "credential": b.create(opts[1]["options"])})
    assert ok.status_code == 200 and ok.json()["enrolled"] == 1
    assert again.status_code == 403 and "ticket" in again.json()["detail"]
    assert len(second.credentials("alice")) == 1


def test_a_ticket_is_for_its_own_person_and_expires(wa):
    app, second, client = wa
    code = second.allow_enrol("alice", "bob")
    hb, _ = login(client, "bob")
    assert enrol(client, hb, SoftKey(), ticket=code).status_code == 403          # alice's ticket, bob's session
    h, _ = login(client)
    later = utcnow() + timedelta(hours=25)
    second.now = lambda: later
    assert enrol(client, h, SoftKey(), ticket=code).status_code == 403          # past its 24 h


def test_a_further_key_needs_a_step_up_of_an_enrolled_one(wa):
    app, second, client = wa
    h, _, (first,) = enrolled(app, second, client)
    assert enrol(client, h, SoftKey()).status_code == 403                       # no step-up
    wrong = assertion(client, h, first, "step-up", "test:something-else").json()["step_up_token"]
    assert enrol(client, h, SoftKey(), step_up=wrong).status_code == 403        # a step-up for another object
    right = assertion(client, h, first, "step-up", register_object("alice")).json()["step_up_token"]
    assert enrol(client, h, SoftKey(), step_up=right).status_code == 200
    assert client.get("/api/v1/me", headers=h).json()["second_factor"]["enrolled"] == 2


# --- login and privileged permissions (D3) -------------------------------------------------------------------------
def test_a_login_with_a_key_marks_that_session_only(wa):
    app, second, client = wa
    h, jti, (key,) = enrolled(app, second, client)
    other, _ = login(client)
    assert client.get("/api/v1/me", headers=h).json()["second_factor"] == {"enrolled": 1, "verified": False}
    assert assertion(client, h, key, "login").status_code == 200
    assert client.get("/api/v1/me", headers=h).json()["second_factor"]["verified"] is True
    assert client.get("/api/v1/me", headers=other).json()["second_factor"]["verified"] is False
    assert app.store.get_session(jti)["second_factor_at"] is not None


def test_a_privileged_permission_needs_this_logins_second_factor_and_two_keys(wa, monkeypatch):
    app, second, client = wa
    monkeypatch.setitem(ROLE_PERMISSIONS, "operator", ROLE_PERMISSIONS["operator"] | {"approve_action"})
    h, _, keys = enrolled(app, second, client, keys=1)
    perms = lambda: client.get("/api/v1/me", headers=h).json()["permissions"]   # noqa: E731
    assert "approve_action" not in perms() and "view" in perms()
    assert assertion(client, h, keys[0], "login").status_code == 200
    assert "approve_action" not in perms()                                     # one key: not yet (D3)
    r = assertion(client, h, keys[0], "step-up", register_object("alice"))
    assert enrol(client, h, SoftKey(), step_up=r.json()["step_up_token"]).status_code == 200
    assert "approve_action" in perms()
    fresh, _ = login(client)                                                   # a new login starts without it
    assert "approve_action" not in client.get("/api/v1/me", headers=fresh).json()["permissions"]


# --- the step-up token -------------------------------------------------------------------------------------------------
def test_a_step_up_token_is_single_use_and_bound_to_principal_session_and_object(wa):
    app, second, client = wa
    h, jti, (key,) = enrolled(app, second, client)
    _, other_jti = login(client)
    issue = lambda obj="test:approval-1:abc": assertion(client, h, key, "step-up", obj).json()["step_up_token"]  # noqa: E731
    t = issue()
    second.consume_step_up(t, "alice", jti, "test:approval-1:abc")
    with pytest.raises(SecondFactorRefused):
        second.consume_step_up(t, "alice", jti, "test:approval-1:abc")         # replayed
    for principal, session, obj in (("alice", jti, "test:approval-2:abc"), ("alice", other_jti, "test:approval-1:abc"),
                                    ("bob", jti, "test:approval-1:abc")):
        with pytest.raises(SecondFactorRefused):
            second.consume_step_up(issue(), principal, session, obj)           # another object, session, person
    t = issue()
    later = utcnow() + timedelta(minutes=6)
    second.now = lambda: later
    with pytest.raises(SecondFactorRefused):
        second.consume_step_up(t, "alice", jti, "test:approval-1:abc")         # older than 5 minutes
    refused = [e for e in _audit_rows(app) if e["event"] == "security.step_up_refused"]
    assert len(refused) == 5 and all(t not in json.dumps(e) for e in refused)


def test_a_step_up_names_an_object(wa):
    app, second, client = wa
    h, _, _ = enrolled(app, second, client)
    for bad in ("", "no-kind", "x:" + "a" * 300, "Approval:1"):
        r = client.post("/api/v1/auth/webauthn/step-up/options", json={"object": bad}, headers=h)
        assert r.status_code in (403, 422), bad


# --- challenges, origin, relying party, counter -------------------------------------------------------------------------
def test_a_challenge_is_single_use_bound_to_its_ceremony_and_short_lived(wa):
    app, second, client = wa
    h, _, (key,) = enrolled(app, second, client)
    r = client.post("/api/v1/auth/webauthn/login/options", headers=h).json()
    body = {"challenge_id": r["challenge_id"], "credential": key.get(r["options"])}
    assert client.post("/api/v1/auth/webauthn/step-up/verify", json=body, headers=h).status_code == 403   # wrong kind
    r = client.post("/api/v1/auth/webauthn/login/options", headers=h).json()
    body = {"challenge_id": r["challenge_id"], "credential": key.get(r["options"])}
    assert client.post("/api/v1/auth/webauthn/login/verify", json=body, headers=h).status_code == 200
    body["credential"] = key.get(r["options"])
    assert client.post("/api/v1/auth/webauthn/login/verify", json=body, headers=h).status_code == 403     # replayed
    r = client.post("/api/v1/auth/webauthn/login/options", headers=h).json()
    later = utcnow() + timedelta(minutes=6)
    second.now = lambda: later
    body = {"challenge_id": r["challenge_id"], "credential": key.get(r["options"])}
    assert client.post("/api/v1/auth/webauthn/login/verify", json=body, headers=h).status_code == 403     # expired


def test_another_origin_or_relying_party_is_refused(wa):
    app, second, client = wa
    h, _ = login(client)
    for key in (SoftKey(origin="https://argus.evil.test"), SoftKey(rp_id="evil.test")):
        r = enrol(client, h, key, ticket=second.allow_enrol("alice", "bob"))
        assert r.status_code == 403 and "not verified" in r.json()["detail"]
    assert second.credentials("alice") == []


def test_a_counter_that_goes_back_is_refused_as_a_clone(wa):
    app, second, client = wa
    h, _, (key,) = enrolled(app, second, client)
    assert assertion(client, h, key, "login", count=5).status_code == 200
    r = assertion(client, h, key, "login", count=3)
    assert r.status_code == 403
    assert [e for e in _audit_rows(app) if e["event"] == "security.webauthn_login_refused"]


def test_a_key_of_another_person_is_refused(wa):
    app, second, client = wa
    _, _, (alices,) = enrolled(app, second, client, "alice")
    hb, _, _ = enrolled(app, second, client, "bob")
    assert assertion(client, hb, alices, "login").status_code == 403


# --- reset (D3), tokens, storage ------------------------------------------------------------------------------------
def test_another_administrators_reset_revokes_the_keys_and_ends_the_sessions(wa):
    app, second, client = wa
    h, jti, _ = enrolled(app, second, client)
    with pytest.raises(SecondFactorRefused):
        second.reset("alice", "alice")
    assert second.reset("alice", "bob") == (1, 1)
    assert second.credentials("alice") == [] and app.store.get_session(jti)["revoked_at"] is not None
    assert client.get("/api/v1/me", headers=h).status_code == 401
    assert [e for e in _audit_rows(app) if e["event"] == "security.webauthn_reset"]


def test_a_read_or_investigate_token_may_complete_its_own_second_factor(wa):
    app, second, client = wa
    for scope in ("read", "investigate"):
        h, _ = login(client, scope=scope)
        r = client.post("/api/v1/auth/webauthn/register/options", json={"ticket": second.allow_enrol("alice", "bob")},
                        headers=h)
        assert r.status_code == 200, (scope, r.text)


def test_the_second_factor_tables_are_never_deleted(wa):
    app, second, client = wa
    enrolled(app, second, client, keys=2)                     # a row in each table, the step-up included
    for table in ("webauthn_credential", "webauthn_challenge", "webauthn_enrol_ticket", "step_up_token"):
        with pytest.raises(sqlite3.DatabaseError):
            app.store._q(f"DELETE FROM {table}")
