"""OP-014 step 9: tests written from the mutation run of `argus/application/second_factor.py` (WebAuthn, phase 16 step
3; mutmut 3.3.1, 2026-10-23). The ceremonies were well tested; what survived was mostly what the audit and a refusal
say, which the existing tests read only as a status code:

- a registration or an assertion without user verification (the authenticator's UV flag) is refused: removing
  `require_user_verification=True` survived in both;
- the options sent to the browser are pinned: the relying party's name, a stable user handle per person, 5 minutes, user verification
  required, the enrolled keys excluded from a new registration and allowed for a login; an invalid ticket is refused
  when the options are asked for, not only at the end; a registration by step-up stores no ticket;
- every refusal names its reason (a library error cut to 200 characters) and is audited under its ceremony's event,
  as the person refused, with the credential or object it was about; a registration, a login completed with a key, a
  step-up issued and a step-up used are audited with their credential, session or object;
- a reset records who revoked the keys and the sessions, and why;
- the enrolment code and the step-up token keep their length (18 and 32 random bytes); a step-up expires 5 minutes
  after it is issued; a label is cut to 64 characters, and none gives an empty one.
"""
from __future__ import annotations

import base64
import hashlib
import re
from datetime import timedelta

import cbor2
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from argus.application.second_factor import STEP_UP_TTL, SecondFactorRefused, register_object
from argus.domain.model import utcnow
from test_acr0018_webauthn import SoftKey, _audit_rows, assertion, b64, enrolled, login, wa  # noqa: F401  (fixture)
from test_core import make_app  # noqa: F401  (fixture)

OBJ = "test:approval-1:abc"


class NoUserVerification(SoftKey):
    """An authenticator that proves presence but not the person (UV flag clear)."""

    def get(self, options: dict, count: int | None = None) -> dict:
        self.count = self.count + 1 if count is None else count
        auth = hashlib.sha256(self.rp_id.encode()).digest() + bytes([0x01]) + self.count.to_bytes(4, "big")
        client = self._client("webauthn.get", options["challenge"])
        sig = self.key.sign(auth + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256()))
        return {"id": b64(self.cred_id), "rawId": b64(self.cred_id), "type": "public-key",
                "response": {"clientDataJSON": b64(client), "authenticatorData": b64(auth), "signature": b64(sig)}}


class NoUserVerificationOnCreate(SoftKey):
    """An authenticator that registers with presence only (UV flag clear)."""

    def create(self, options: dict) -> dict:
        body = SoftKey.create(self, options)
        att = cbor2.loads(base64.urlsafe_b64decode(body["response"]["attestationObject"] + "=="))
        auth = bytearray(att["authData"])
        auth[32] = 0x41                                                # UP and AT, no UV
        att["authData"] = bytes(auth)
        body["response"]["attestationObject"] = b64(cbor2.dumps(att))
        return body


def _events(app, event: str) -> list[dict]:
    return [e for e in _audit_rows(app) if e["event"] == f"security.{event}"]


def _fixed_clock(second):
    now = utcnow()
    second.now = lambda: now
    return now


# --- enrolment and reset ---------------------------------------------------------------------------------------------
def test_self_issued_tickets_and_resets_say_why(wa):
    _, second, _ = wa
    with pytest.raises(SecondFactorRefused, match="^nobody issues their own enrolment ticket$"):
        second.allow_enrol("alice", "alice")
    with pytest.raises(SecondFactorRefused, match="^nobody resets their own credentials$"):
        second.reset("alice", "alice")


def test_the_enrolment_code_and_the_step_up_token_keep_their_length(wa):
    app, second, client = wa
    assert len(second.allow_enrol("alice", "bob")) == 24             # 18 random bytes, URL-safe base64
    h, _, (key,) = enrolled(app, second, client)
    token = assertion(client, h, key, "step-up", OBJ).json()["step_up_token"]
    assert len(token) == 43                                            # 32 random bytes


def test_a_reset_records_who_revoked_and_why(wa):
    app, second, client = wa
    h, jti, (key,) = enrolled(app, second, client)
    assert second.reset("alice", "bob") == (1, 1)
    assert app.store._q("SELECT revoked_by FROM webauthn_credential WHERE principal='alice'") == [("bob",)]
    session = app.store.get_session(jti)
    assert (session["revoked_by"], session["revoke_reason"]) == ("bob", "webauthn reset")
    (e,) = _events(app, "webauthn_reset")
    assert (e["actor"], e["detail"]) == ("bob", {"principal": "alice", "credentials": 1, "sessions": 1})


def test_an_enrolment_ticket_is_audited_with_its_person_and_hours(wa):
    app, second, _ = wa
    second.allow_enrol("alice", "b" * 70)
    (e,) = _events(app, "webauthn_enrol_allowed")
    assert (e["actor"], e["detail"]) == ("b" * 64, {"principal": "alice", "hours": 24})
    assert re.fullmatch(r"aud_[0-9a-f]{16}", e["audit_id"])


def test_an_invalid_ticket_is_refused_when_the_options_are_asked_for(wa):
    app, second, client = wa
    _, jti = login(client)
    for ticket in (None, "not-a-ticket"):
        with pytest.raises(SecondFactorRefused,
                           match="^the first credential needs an enrolment ticket from another administrator$"):
            second.register_options("alice", jti, ticket=ticket)
    assert len(_events(app, "webauthn_register_refused")) == 2


def test_the_registration_options_are_pinned(wa):
    app, second, client = wa
    _, jti = login(client)
    _, first = second.register_options("alice", jti, ticket=second.allow_enrol("alice", "bob"))
    assert first["user"] == {"id": b64(hashlib.sha256(b"alice").digest()[:16]), "name": "alice",
                             "displayName": "alice"}
    assert first["rp"] == {"name": "Argus", "id": "argus.example.test"}
    assert first["timeout"] == 300000 and first["excludeCredentials"] == []
    assert first["authenticatorSelection"] == {"residentKey": "preferred", "requireResidentKey": False,
                                               "userVerification": "required"}
    h, jti, (key,) = enrolled(app, second, client, "bob")
    token = assertion(client, h, key, "step-up", register_object("bob")).json()["step_up_token"]
    _, more = second.register_options("bob", jti, step_up_token=token)
    assert more["excludeCredentials"] == [{"id": b64(key.cred_id), "type": "public-key"}]
    _, login_options = second.login_options("bob", jti)
    assert (login_options["timeout"], login_options["userVerification"], login_options["rpId"]) == (
        300000, "required", "argus.example.test")
    assert login_options["allowCredentials"] == [{"id": b64(key.cred_id), "type": "public-key"}]
    tickets = app.store._q("SELECT ticket IS NULL FROM webauthn_challenge WHERE kind='register' ORDER BY created_at")
    assert [bool(t[0]) for t in tickets] == [False, False, True]            # alice's, bob's first, bob's step-up


def test_a_registration_without_user_verification_is_refused(wa):
    app, second, client = wa
    _, jti = login(client)
    cid, options = second.register_options("alice", jti, ticket=second.allow_enrol("alice", "bob"))
    with pytest.raises(SecondFactorRefused, match="^registration not verified: User verification is required"):
        second.register_verify("alice", jti, cid, NoUserVerificationOnCreate().create(options))
    assert second.credentials("alice") == []


def test_a_registration_not_verified_is_audited_as_a_register_refusal(wa):
    app, second, client = wa
    h, jti = login(client)
    cid, options = second.register_options("alice", jti, ticket=second.allow_enrol("alice", "bob"))
    with pytest.raises(SecondFactorRefused, match="^registration not verified: "):
        second.register_verify("alice", jti, cid, SoftKey(origin="https://argus.evil.test").create(options))
    (e,) = _events(app, "webauthn_register_refused")
    assert e["actor"] == "alice" and e["detail"]["reason"].startswith("registration not verified: ")


def test_a_registration_is_audited_and_answered_with_its_credential(wa):
    app, second, client = wa
    h, jti = login(client)
    cid, options = second.register_options("alice", jti, ticket=second.allow_enrol("alice", "bob"))
    key = SoftKey()
    assert second.register_verify("alice", jti, cid, key.create(options)) == {"credential": b64(key.cred_id)[:8],
                                                                               "enrolled": 1}
    assert [c["label"] for c in second.credentials("alice")] == [""]             # no label given: an empty one
    token = assertion(client, h, key, "step-up", register_object("alice")).json()["step_up_token"]
    cid, options = second.register_options("alice", jti, step_up_token=token)
    other = SoftKey()
    second.register_verify("alice", jti, cid, other.create(options), label="L" * 70)
    assert [c["label"] for c in second.credentials("alice")] == ["", "L" * 64]
    assert [(e["actor"], e["detail"]) for e in _events(app, "webauthn_registered")] == [
        ("alice", {"credential": b64(key.cred_id)[:8], "label": "", "enrolled": 1, "with_ticket": True}),
        ("alice", {"credential": b64(other.cred_id)[:8], "label": "L" * 64, "enrolled": 2, "with_ticket": False})]


def test_a_used_ticket_is_refused_at_the_end_of_the_ceremony(wa):
    app, second, client = wa
    _, jti = login(client)
    code = second.allow_enrol("alice", "bob")
    (cid1, o1), (cid2, o2) = (second.register_options("alice", jti, ticket=code) for _ in range(2))
    second.register_verify("alice", jti, cid1, SoftKey().create(o1))
    with pytest.raises(SecondFactorRefused, match="^the enrolment ticket was used or has expired$"):
        second.register_verify("alice", jti, cid2, SoftKey().create(o2))
    (e,) = _events(app, "webauthn_register_refused")
    assert (e["actor"], e["detail"]) == ("alice", {"reason": "the enrolment ticket was used or has expired"})


def test_a_long_verification_error_is_cut_to_200_characters(wa):
    app, second, client = wa
    far = "https://" + "x" * 250 + ".test"
    _, jti = login(client)
    cid, options = second.register_options("alice", jti, ticket=second.allow_enrol("alice", "bob"))
    with pytest.raises(SecondFactorRefused) as refused:
        second.register_verify("alice", jti, cid, SoftKey(origin=far).create(options))
    assert len(str(refused.value)) == 200
    h, jti, (key,) = enrolled(app, second, client)
    cid, options = second.login_options("alice", jti)
    stolen = SoftKey(origin=far)
    stolen.key, stolen.cred_id = key.key, key.cred_id
    with pytest.raises(SecondFactorRefused) as refused:
        second.login_verify("alice", jti, cid, stolen.get(options))
    assert len(str(refused.value)) == 200
    assert [len(e["detail"]["reason"]) for e in _audit_rows(app) if e["event"].endswith("_refused")] == [200, 200]


# --- assertions ------------------------------------------------------------------------------------------------------
def test_an_assertion_without_user_verification_is_refused(wa):
    app, second, client = wa
    h, jti, (key,) = enrolled(app, second, client)
    weak = NoUserVerification()
    weak.key, weak.cred_id, weak.count = key.key, key.cred_id, key.count
    cid, options = second.login_options("alice", jti)
    with pytest.raises(SecondFactorRefused, match="^assertion not verified: User verification is required"):
        second.login_verify("alice", jti, cid, weak.get(options))
    assert app.store.get_session(jti)["second_factor_at"] is None
    (e,) = _events(app, "webauthn_login_refused")
    assert e["actor"] == "alice" and e["detail"]["credential"] == b64(key.cred_id)[:8]
    assert e["detail"]["reason"].startswith("assertion not verified: ")


def test_a_login_without_a_credential_says_so(wa):
    app, second, client = wa
    _, jti = login(client)
    with pytest.raises(SecondFactorRefused, match="^no credential enrolled$"):
        second.login_options("alice", jti)
    (e,) = _events(app, "webauthn_login_refused")
    assert (e["actor"], e["detail"]) == ("alice", {"reason": "no credential enrolled"})


def test_an_unknown_challenge_and_a_foreign_key_say_why(wa):
    app, second, client = wa
    _, _, (alices,) = enrolled(app, second, client, "alice")
    _, bob_jti, _ = enrolled(app, second, client, "bob")
    with pytest.raises(SecondFactorRefused, match="^unknown, used or expired challenge$"):
        second.login_verify("bob", bob_jti, "wch_missing", {})
    cid, options = second.login_options("bob", bob_jti)
    with pytest.raises(SecondFactorRefused, match="^not a credential of this principal$"):
        second.login_verify("bob", bob_jti, cid, alices.get(options))
    assert [(e["actor"], e["detail"]) for e in _events(app, "webauthn_login_refused")] == [
        ("bob", {"reason": "unknown, used or expired challenge"}),
        ("bob", {"reason": "not a credential of this principal"})]


def test_a_login_whose_session_ended_meanwhile_is_refused(wa):
    app, second, client = wa
    h, jti, (key,) = enrolled(app, second, client)
    cid, options = second.login_options("alice", jti)
    app.store.revoke_session(jti, "alice", "logout", utcnow())
    with pytest.raises(SecondFactorRefused, match="^session ended$"):
        second.login_verify("alice", jti, cid, key.get(options))
    (e,) = _events(app, "webauthn_login_refused")
    assert (e["actor"], e["detail"]) == ("alice", {"reason": "session ended"})


def test_a_login_with_a_key_is_audited_with_its_credential_and_session(wa):
    app, second, client = wa
    h, jti, (key,) = enrolled(app, second, client)
    cid, options = second.login_options("alice", jti)
    second.login_verify("alice", jti, cid, key.get(options))
    (e,) = _events(app, "webauthn_login")
    assert (e["actor"], e["detail"]) == ("alice", {"credential": b64(key.cred_id)[:8], "session": jti[:8]})


# --- step-up ---------------------------------------------------------------------------------------------------------
def test_a_step_up_object_that_is_not_kind_reference_says_so(wa):
    app, second, client = wa
    _, jti, _ = enrolled(app, second, client)
    for bad in ("", None, "no-kind"):
        with pytest.raises(SecondFactorRefused, match="^the object must look like kind:reference$"):
            second.step_up_options("alice", jti, bad)


def test_a_step_up_is_issued_for_five_minutes_and_audited(wa):
    app, second, client = wa
    h, jti, (key,) = enrolled(app, second, client)
    now = _fixed_clock(second)
    cid, options = second.step_up_options("alice", jti, OBJ)
    token, expires = second.step_up_verify("alice", jti, cid, key.get(options))
    assert expires == now + STEP_UP_TTL == now + timedelta(minutes=5)
    (e,) = _events(app, "step_up_issued")
    assert (e["actor"], e["detail"]) == ("alice", {"object": OBJ, "credential": b64(key.cred_id)[:8]})
    second.consume_step_up(token, "alice", jti, OBJ)
    (e,) = _events(app, "step_up_used")
    assert (e["actor"], e["detail"]) == ("alice", {"object": OBJ})


def test_a_refused_step_up_says_why_and_names_its_object(wa):
    app, second, client = wa
    h, jti, (key,) = enrolled(app, second, client)
    with pytest.raises(SecondFactorRefused, match=r"^a fresh step-up is needed \(missing, used or expired\)$"):
        second.consume_step_up(None, "alice", jti, OBJ)
    token = assertion(client, h, key, "step-up", OBJ).json()["step_up_token"]
    with pytest.raises(SecondFactorRefused, match="^the step-up was issued for another object or session$"):
        second.consume_step_up(token, "alice", jti, register_object("alice"))
    assert [(e["actor"], e["detail"]) for e in _events(app, "step_up_refused")] == [
        ("alice", {"reason": "a fresh step-up is needed (missing, used or expired)", "object": OBJ}),
        ("alice", {"reason": "the step-up was issued for another object or session",
                   "object": register_object("alice")})]
