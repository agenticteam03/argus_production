"""ACR-0018, phase 16 step 3: the WebAuthn second factor and the step-up token (py_webauthn, D1).

- **Enrolment.** The first credential needs a ticket from another administrator (D4: `argus webauthn allow-enrol`), a
  one-time code shown once and stored as its SHA-256; a password alone never binds a key. Every later credential
  needs a step-up of an enrolled one. Two credentials per privileged person (D3).
- **Login.** A verified assertion marks the session (`second_factor_at`). A privileged permission needs that and two
  credentials (`privileged_ready`).
- **Step-up.** A fresh assertion bound to one object (`approval:<id>:<digest>`, a terminal ticket, a hold; phase 17
  on) gives a token that is single-use, valid at most 5 minutes, for that principal, session and object only. A
  used, expired or foreign token is refused and audited.
- Every challenge is server-side, single-use and expires in 5 minutes; the relying party id and the origin are the
  UI's DNS name (D2), from the VM's environment; the sign counter refuses a cloned authenticator (py_webauthn raises
  when a non-zero counter does not grow).
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable

from webauthn import (generate_authentication_options, generate_registration_options, options_to_json,
                      verify_authentication_response, verify_registration_response)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (AuthenticatorSelectionCriteria, PublicKeyCredentialDescriptor,
                                      ResidentKeyRequirement, UserVerificationRequirement)

from argus.domain.model import AuditRecord, utcnow

CHALLENGE_TTL = timedelta(minutes=5)
STEP_UP_TTL = timedelta(minutes=5)                 # the migration refuses a longer one
CREDENTIALS_FOR_PRIVILEGE = 2                      # D3
OBJECT = re.compile(r"^[a-z][a-z0-9_.-]{0,31}:[A-Za-z0-9_.:-]{1,190}$")   # kind:reference, e.g. approval:<id>:<digest>


def register_object(principal: str) -> str:
    """The object a step-up must name to enrol a further credential."""
    return f"webauthn.register:{principal}"


def _sha256(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


class SecondFactorRefused(Exception):
    """A ceremony or token refused; the reason is safe to show (it never names a secret)."""


class SecondFactor:
    def __init__(self, store, rp_id: str, origin: str, ticket_hours: int = 24,
                 now: Callable[[], datetime] = utcnow, rp_name: str = "Argus"):
        self.store, self.rp_id, self.origin, self.rp_name = store, rp_id, origin, rp_name
        self.ticket_hours, self.now = ticket_hours, now

    @property
    def configured(self) -> bool:
        return bool(self.rp_id and self.origin)

    def _audit(self, event: str, actor: str, detail: dict[str, Any]) -> None:
        self.store.append(AuditRecord(audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=None, at=self.now(),
                                      category="security", event=f"security.{event}", actor=actor[:64], detail=detail))

    def _refuse(self, event: str, principal: str, reason: str, **detail) -> SecondFactorRefused:
        self._audit(event, principal, {"reason": reason, **detail})
        return SecondFactorRefused(reason)

    def credentials(self, principal: str) -> list[dict[str, Any]]:
        return self.store.webauthn_credentials(principal)

    def status(self, principal: str, session: dict | None) -> dict[str, Any]:
        return {"enrolled": len(self.credentials(principal)),
                "verified": bool(session and session.get("second_factor_at"))}

    def privileged_ready(self, principal: str, session: dict | None) -> bool:
        """A privileged permission counts only for a session completed with a credential, held by a person with two."""
        return bool(session and session.get("second_factor_at")) and \
            len(self.credentials(principal)) >= CREDENTIALS_FOR_PRIVILEGE

    # --- administration (the CLI on vm-095, run by the lease holder) --------------------------------------------------
    def allow_enrol(self, principal: str, by: str) -> str:
        """D4: a one-time code for the principal's first credential; returned once, stored as its SHA-256."""
        if by == principal:
            raise SecondFactorRefused("nobody issues their own enrolment ticket")
        code = secrets.token_urlsafe(18)
        now = self.now()
        self.store.add_enrol_ticket(_sha256(code), principal, by, now, now + timedelta(hours=self.ticket_hours))
        self._audit("webauthn_enrol_allowed", by, {"principal": principal, "hours": self.ticket_hours})
        return code

    def reset(self, principal: str, by: str) -> tuple[int, int]:
        """D3: another administrator revokes every credential of the principal and ends their sessions."""
        if by == principal:
            raise SecondFactorRefused("nobody resets their own credentials")
        now = self.now()
        creds = self.store.revoke_webauthn_credentials(principal, by, now)
        sessions = self.store.revoke_principal_sessions(principal, by, "webauthn reset", now)
        self._audit("webauthn_reset", by, {"principal": principal, "credentials": creds, "sessions": sessions})
        return creds, sessions

    # --- ceremonies ----------------------------------------------------------------------------------------------------
    def _challenge(self, principal: str, session: str, kind: str, challenge: bytes, obj: str | None = None,
                   ticket: str | None = None) -> str:
        cid = f"wch_{uuid.uuid4().hex}"
        now = self.now()
        self.store.add_webauthn_challenge(cid, principal, session, kind, challenge, obj, ticket, now, now + CHALLENGE_TTL)
        return cid

    def _take(self, principal: str, session: str, kind: str, challenge_id: str) -> dict[str, Any]:
        ch = self.store.take_webauthn_challenge(challenge_id, principal, session, kind, self.now())
        if ch is None:
            raise self._refuse(f"webauthn_{kind}_refused", principal, "unknown, used or expired challenge")
        return ch

    def register_options(self, principal: str, session: str, ticket: str | None = None,
                         step_up_token: str | None = None) -> tuple[str, dict]:
        creds = self.credentials(principal)
        ticket_id = None
        if not creds:
            ticket_id = _sha256(ticket) if ticket else None
            if ticket_id is None or not self.store.enrol_ticket_valid(ticket_id, principal, self.now()):
                raise self._refuse("webauthn_register_refused", principal,
                                   "the first credential needs an enrolment ticket from another administrator")
        else:
            self.consume_step_up(step_up_token, principal, session, register_object(principal))
        opts = generate_registration_options(
            rp_id=self.rp_id, rp_name=self.rp_name, user_name=principal,
            user_id=hashlib.sha256(principal.encode()).digest()[:16], timeout=int(CHALLENGE_TTL.total_seconds() * 1000),
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.PREFERRED, user_verification=UserVerificationRequirement.REQUIRED),
            exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(c["id"])) for c in creds])
        return self._challenge(principal, session, "register", opts.challenge, ticket=ticket_id), \
            json.loads(options_to_json(opts))

    def register_verify(self, principal: str, session: str, challenge_id: str, credential: dict,
                        label: str = "") -> dict[str, Any]:
        ch = self._take(principal, session, "register", challenge_id)
        try:
            v = verify_registration_response(credential=credential, expected_challenge=ch["challenge"],
                                             expected_rp_id=self.rp_id, expected_origin=self.origin,
                                             require_user_verification=True)
        except Exception as e:                       # py_webauthn raises its own InvalidRegistrationResponse and others
            raise self._refuse("webauthn_register_refused", principal, f"registration not verified: {e}"[:200])
        if ch["ticket"] and not self.store.use_enrol_ticket(ch["ticket"], principal, self.now()):
            raise self._refuse("webauthn_register_refused", principal, "the enrolment ticket was used or has expired")
        cred_id = bytes_to_base64url(v.credential_id)
        self.store.add_webauthn_credential(cred_id, principal, v.credential_public_key, v.sign_count, label[:64],
                                           self.now())
        count = len(self.credentials(principal))
        self._audit("webauthn_registered", principal, {"credential": cred_id[:8], "label": label[:64],
                                                       "enrolled": count, "with_ticket": bool(ch["ticket"])})
        return {"credential": cred_id[:8], "enrolled": count}

    def _assertion_options(self, principal: str, session: str, kind: str, obj: str | None = None) -> tuple[str, dict]:
        creds = self.credentials(principal)
        if not creds:
            raise self._refuse(f"webauthn_{kind}_refused", principal, "no credential enrolled")
        opts = generate_authentication_options(
            rp_id=self.rp_id, timeout=int(CHALLENGE_TTL.total_seconds() * 1000),
            user_verification=UserVerificationRequirement.REQUIRED,
            allow_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(c["id"])) for c in creds])
        return self._challenge(principal, session, kind, opts.challenge, obj=obj), json.loads(options_to_json(opts))

    def _assertion_verify(self, principal: str, session: str, kind: str, challenge_id: str,
                          credential: dict) -> dict[str, Any]:
        ch = self._take(principal, session, kind, challenge_id)
        cred = next((c for c in self.credentials(principal) if c["id"] == credential.get("id")), None)
        if cred is None:
            raise self._refuse(f"webauthn_{kind}_refused", principal, "not a credential of this principal")
        try:
            v = verify_authentication_response(credential=credential, expected_challenge=ch["challenge"],
                                               expected_rp_id=self.rp_id, expected_origin=self.origin,
                                               credential_public_key=cred["public_key"],
                                               credential_current_sign_count=cred["sign_count"],
                                               require_user_verification=True)
        except Exception as e:                       # a bad signature, origin or counter (a possible clone)
            raise self._refuse(f"webauthn_{kind}_refused", principal, f"assertion not verified: {e}"[:200],
                               credential=cred["id"][:8])
        self.store.update_webauthn_sign_count(cred["id"], v.new_sign_count, self.now())
        return {**ch, "credential": cred["id"][:8]}

    def login_options(self, principal: str, session: str) -> tuple[str, dict]:
        return self._assertion_options(principal, session, "login")

    def login_verify(self, principal: str, session: str, challenge_id: str, credential: dict) -> None:
        done = self._assertion_verify(principal, session, "login", challenge_id, credential)
        if not self.store.set_session_second_factor(session, self.now()):
            raise self._refuse("webauthn_login_refused", principal, "session ended")
        self._audit("webauthn_login", principal, {"credential": done["credential"], "session": session[:8]})

    def step_up_options(self, principal: str, session: str, obj: str) -> tuple[str, dict]:
        if not OBJECT.fullmatch(obj or ""):
            raise SecondFactorRefused("the object must look like kind:reference")
        return self._assertion_options(principal, session, "step_up", obj)

    def step_up_verify(self, principal: str, session: str, challenge_id: str, credential: dict) -> tuple[str, datetime]:
        done = self._assertion_verify(principal, session, "step_up", challenge_id, credential)
        token, now = secrets.token_urlsafe(32), self.now()
        self.store.add_step_up(_sha256(token), principal, session, done["object"], now, now + STEP_UP_TTL)
        self._audit("step_up_issued", principal, {"object": done["object"], "credential": done["credential"]})
        return token, now + STEP_UP_TTL

    def consume_step_up(self, token: str | None, principal: str, session: str, obj: str) -> None:
        """For the route that does the privileged thing: the token is used up whatever the answer, so it is tried
        once; refused unless it is unexpired and was issued to this principal, in this session, for this object."""
        row = self.store.take_step_up(_sha256(token), self.now()) if token else None
        if row is None:
            raise self._refuse("step_up_refused", principal, "a fresh step-up is needed (missing, used or expired)",
                               object=obj)
        if (row["principal"], row["session"], row["object"]) != (principal, session, obj):
            raise self._refuse("step_up_refused", principal, "the step-up was issued for another object or session",
                               object=obj)
        self._audit("step_up_used", principal, {"object": obj})
