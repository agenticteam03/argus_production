"""HTTP inbound adapter (FastAPI): human API with JWT on the loopback listener, Alertmanager webhook
on the private listener (v1.8 §7.1, §17.3). The only FastAPI location.

No `from __future__ import annotations` here: FastAPI must resolve the local dependency closures."""

from urllib.parse import quote
import hmac
import logging
import math
import re
import socket
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock, RLock
from typing import Annotated, Literal

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pwdlib import PasswordHash
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from argus.application.alerts import HandleAlertNotification
from argus.application.incident_view import build_verdict
from argus.detectors.classes import CLASSES
from argus.domain.model import (AlertNotification, AuditRecord, Incident, IncidentStatus, Principal, RequestKind,
                                TargetRef, TriggerKind, utcnow)
from argus.ports.ports import MetricsUnavailable, StaleMetrics

READ_METHODS = ("GET", "HEAD")          # a read-only token (ACR-0001) may use only these
INVESTIGATE_WRITES = {("POST", "/api/v1/investigations")}   # the one non-GET of an `investigate` token (ACR-0012)
# ACR-0041: ...and closing an escalated incident, which acts on nothing
RESOLVE_PATH = re.compile(r"^/api/v1/incidents/[A-Za-z0-9_-]{1,64}/resolve$")
SCOPES = {"read", "investigate"}        # what a login may ask for; none = a full token (loopback only)
ANY_TOKEN_WRITES = {("POST", "/api/v1/auth/logout")}   # ACR-0018: every token may end its own session
# ACR-0018 step 3: every token may complete its own second factor (the UI's tokens are read or investigate ones): a
# ceremony binds a key or marks a session only with the principal's credential, a ticket or a step-up
SECOND_FACTOR_WRITES = {("POST", f"/api/v1/auth/webauthn/{c}/{s}") for c in ("register", "login", "step-up")
                        for s in ("options", "verify")}
# ACR-0018 §17.3: permissions are explicit and checked per route; a role is a bundle of them. Only the permissions of
# what is built are listed; remaining privileged permissions come with their routes. ACR-0018: a privileged
# permission counts only for a session completed with a WebAuthn credential, held by a person with two (D3).
PRIVILEGED_PERMISSIONS = frozenset({"propose_action", "approve_action", "place_hold", "open_terminal", "admin",
                                    "manage_corpus"})
# ACR-0018 step 4: every route that needs a privileged permission lives under this prefix, the only one the public
# edge passes on the private path (a client certificate of the team's CA and an allowlisted address; else 404).
OPS_PREFIX = "/api/v1/ops/"
# ACR-0032: the private browser login, the one route under the prefix that needs no privileged permission (the edge's
# certificate and allowlist protect it); its `ops` token is full but works only on the private path, until 15 minutes
# without a request or one hour after the login.
OPS_LOGIN = "/api/v1/ops/auth/token"
OPS_SESSION = timedelta(hours=1)                 # ACR-0032: an ops session's absolute end
OPS_IDLE = timedelta(minutes=15)                 # ...and its end after this long without a request
PENDING_LIST_LIMIT, PENDING_SCAN_PAGE = 50, 100  # the pending list's length; approvals read per store page
FULL_ACCESS = frozenset({"full", "ops"})
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "viewer": frozenset({"view"}),
    "operator": frozenset({"view", "view_evidence", "investigate", "resolve_incident"}),    # ACR-0041: close an
    "approver": frozenset({"view", "view_evidence", "investigate", "resolve_incident"}),    # escalated incident
}
# Phase 19: granted only while the action routes are mounted (`action_rows`); production wiring mounts none yet.
# ACR-0042: `count_waiting_approvals` is not privileged: it gives an approver only how many approvals wait (the bell),
# with any token; seeing and deciding them stays privileged and private.
ACTION_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "approver": frozenset({"approve_action", "place_hold", "count_waiting_approvals"})}
# ACR-0034 local tier: installing a staged reference source is a privileged act (step-up each time); ACR-0040: an
# approver may do it as well as an administrator
CORPUS_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {"admin": frozenset({"manage_corpus"}),
                                                      "approver": frozenset({"manage_corpus"})}


def permissions_of(p: Principal) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(p.role, frozenset())


def granted_permissions(p: Principal, second_factor_ready: bool) -> frozenset[str]:
    """What this request may use: the role's permissions, without the privileged ones until the second factor holds."""
    perms = permissions_of(p)
    return perms if second_factor_ready else perms - PRIVILEGED_PERMISSIONS

log = logging.getLogger("argus.api")

# A host's heartbeat renews every 60-75 s (T-0035, measured on Alertmanager): older than twice that is stale. It sits
# between two reconcile ticks and the scheduler's loss (`stale_after_s`, deploy/scheduler/schedules.yaml); a test pins it.
HEARTBEAT_STALE_S = 150
hasher = PasswordHash.recommended()
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


INCIDENT_ID = r"^inc_[A-Za-z0-9_-]+$"   # an incident id in a request (never a path or free text)


class EnrolIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket: str | None = Field(None, max_length=64)            # D4: the first credential
    step_up_token: str | None = Field(None, max_length=64)     # a further one


class CeremonyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    challenge_id: str = Field(pattern=r"^wch_[0-9a-f]{32}$")
    credential: dict                                           # the browser's PublicKeyCredential as JSON
    label: str = Field("", max_length=64)


class StepUpIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    object: str = Field(max_length=224)


class ApprovalAnswerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approved", "denied"]
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    step_up_token: str = Field(min_length=1, max_length=64)
    confirmation_target: str | None = Field(None, max_length=128)
    reason: str | None = Field(None, max_length=500)

    @model_validator(mode="after")
    def _denial_has_a_reason(self):
        if self.decision == "denied" and not (self.reason or "").strip():
            raise ValueError("a denial needs a reason (ACR-0019 §3.12)")
        return self


class CorpusApproveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_up_token: str = Field(min_length=1, max_length=64)


class CorpusRejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=500)
    step_up_token: str = Field(min_length=1, max_length=64)


class HoldReleaseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=500)
    step_up_token: str = Field(min_length=1, max_length=64)


class HoldIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=500)
    step_up_token: str = Field(min_length=1, max_length=64)


class ResolveIn(BaseModel):
    """ACR-0041: why the escalated incident is closed (what fixed it, outside Argus)."""
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("a reason is required")
        return value.strip()


class ConsoleExecuteIn(BaseModel):
    """ACR-0043: one line typed in the operator console, for one incident."""
    model_config = ConfigDict(extra="forbid")
    input: str = Field(max_length=200)                         # the incident comes from the path
    suggestion_id: str | None = Field(None, max_length=64)
    confirmation: str | None = Field(None, max_length=64)      # CON-6: the write's confirmation; unused by reads


class InvestigationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str
    reason: str = ""
    request_kind: Literal["check", "report"] = "report"
    idempotency_key: str | None = None
    parent_id: str | None = Field(None, pattern=INCIDENT_ID, max_length=64)   # ACR-0021 B5: the incident re-checked


def new_incident(target: TargetRef, trigger: TriggerKind, request: RequestKind, reason: str,
                 principal: str | None, trigger_id: str, parent_id: str | None = None) -> Incident:
    return Incident(id=f"inc_{uuid.uuid4().hex[:12]}", target=target, trigger_kind=trigger, request_kind=request,
                    reason=reason[:2000], principal=principal, trigger_id=trigger_id, opened_at=utcnow(),
                    parent_id=parent_id)


class LoginLimiter:
    """§17.3 / ACR-0011: failed logins per username and per client address in a sliding window; once either reaches
    its maximum, logins for it are refused (429) until the window has passed. ACR-0018: with a store, the failures
    are kept in it (`login_failure`, migration 010), so a restart no longer forgets a lockout; without one (a test
    double), in memory. `now` is wall-clock seconds."""

    def __init__(self, max_per_user: int, max_per_address: int, window_s: int, store=None):
        import time
        self.max_per_user, self.max_per_address, self.window_s = max_per_user, max_per_address, window_s
        self.now = time.time
        self.store = store if hasattr(store, "add_login_failure") else None
        self._fails: dict[str, list[float]] = {}

    def _at(self, seconds: float) -> datetime:
        return datetime.fromtimestamp(seconds, timezone.utc)

    def _recent(self, key: str) -> list[float]:
        cutoff = self.now() - self.window_s
        if self.store is not None:
            return [x.timestamp() for x in self.store.login_failures(key, self._at(cutoff))]
        times = [t for t in self._fails.get(key, []) if t > cutoff]
        self._fails[key] = times
        return times

    def retry_after(self, user: str, address: str) -> int:
        """Seconds until a login may be tried again; 0 = not locked."""
        waits = [int(times[0] + self.window_s - self.now()) + 1
                 for key, cap in ((f"u:{user}", self.max_per_user), (f"a:{address}", self.max_per_address))
                 if len(times := self._recent(key)) >= cap]
        return max(waits, default=0)

    def failed(self, user: str, address: str) -> None:
        if self.store is not None:                  # failures out of the window count for nothing: drop them
            self.store.prune_login_failures(self._at(self.now() - self.window_s))
        for key in (f"u:{user}", f"a:{address}"):
            if self.store is not None:
                self.store.add_login_failure(key, self._at(self.now()))
            else:
                self._recent(key).append(self.now())

    def succeeded(self, user: str) -> None:
        if self.store is not None:
            self.store.clear_login_failures(f"u:{user}")
        else:
            self._fails.pop(f"u:{user}", None)



def sign_token(app_ctx, claims: dict) -> str:
    """ACR-0018 §17.2: EdDSA with the API's Ed25519 key when it has one, else the lab's HS256 key."""
    key = getattr(app_ctx, "jwt_signing", None)
    if key is not None:
        return jwt.encode(claims, key, algorithm="EdDSA")
    return jwt.encode(claims, app_ctx.jwt_key, algorithm="HS256")


def verify_token(app_ctx, token: str) -> dict:
    """Only the configured algorithm is accepted: with an Ed25519 key, an HS256 token is refused even when it is signed
    with the old shared key (no algorithm confusion)."""
    key = getattr(app_ctx, "jwt_signing", None)
    if key is not None:
        return jwt.decode(token, key.public_key(), algorithms=["EdDSA"], audience="argus-api")
    return jwt.decode(token, app_ctx.jwt_key, algorithms=["HS256"], audience="argus-api")

def private_path(request: Request, settings) -> bool:
    """ACR-0032: the edge says private path, and the request really comes from the edge. The name is resolved on
    every call (Docker's DNS; the UI container's address changes when it is recreated); unresolvable: never."""
    if request.headers.get(settings.ops_header) != "1" or request.client is None:
        return False
    peer = request.client.host
    if peer == settings.ops_peer:
        return True
    try:
        return peer in {a[4][0] for a in socket.getaddrinfo(settings.ops_peer, None)}
    except OSError:
        return False


def client_cert(request: Request, settings) -> str:
    """ACR-0038: "verified" when the edge verified a team certificate on this private request, else "none" (the
    passkey-only mode, or no certificate). Off the private path the header is not believed."""
    if private_path(request, settings) and request.headers.get(settings.ops_cert_header) == "SUCCESS":
        return "verified"
    return "none"


def _principal_dep(app_ctx):
    def dep(request: Request, token: Annotated[str, Depends(oauth2)]) -> Principal:
        try:
            claims = verify_token(app_ctx, token)
        except jwt.PyJWTError:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token",
                                headers={"WWW-Authenticate": "Bearer"})
        row = app_ctx.store.get_principal(claims["sub"])
        if row is None or row["disabled"]:          # disabling takes effect before token expiry
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "principal disabled")
        # ACR-0018: the token's session must exist, belong to it and not be revoked (logout, a password change or an
        # administrator ends it at once); a token issued before sessions existed has none and must log in again
        session = app_ctx.store.get_session(str(claims.get("jti", "")))
        if session is None or session["principal"] != row["id"] or session["revoked_at"] is not None:
            # a correctly signed token without a live session of its own: a token used after logout or revocation,
            # or one minted outside the login. Audited as a security event (only signed tokens get here: no flood)
            why = "no session" if session is None else ("another principal's session"
                                                        if session["principal"] != row["id"] else "revoked")
            app_ctx.store.append(AuditRecord(
                audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=None, at=utcnow(), category="security",
                event="security.session_refused", actor=row["id"],
                detail={"reason": why, "session": str(claims.get("jti", ""))[:8], "path": request.url.path}))
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session ended; log in again",
                                headers={"WWW-Authenticate": "Bearer"})
        request.state.jti = session["jti"]
        request.state.session = session
        # ACR-0001: a read-only token only narrows what the role allows; tokens without the claim are full
        access = claims.get("access", "full")
        request.state.access = access
        if access == "ops" and not private_path(request, app_ctx.settings):
            # ACR-0032: a private-login token is used off the private path (stolen, or a public tab): refused, audited
            app_ctx.store.append(AuditRecord(
                audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=None, at=utcnow(), category="security",
                event="security.session_refused", actor=row["id"],
                detail={"reason": "off private path", "session": session["jti"][:8], "path": request.url.path}))
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "this token works only on the private path",
                                headers={"WWW-Authenticate": "Bearer"})
        if access == "ops" and not app_ctx.store.touch_session(session["jti"], utcnow(), OPS_IDLE):
            # ACR-0032: 15 minutes without a request end an ops session (the hour is the token's own expiry)
            app_ctx.store.append(AuditRecord(
                audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=None, at=utcnow(), category="security",
                event="security.session_refused", actor=row["id"],
                detail={"reason": "idle", "session": session["jti"][:8], "path": request.url.path}))
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session ended after 15 minutes without use; log in again",
                                headers={"WWW-Authenticate": "Bearer"})
        if (request.method, request.url.path) in ANY_TOKEN_WRITES | SECOND_FACTOR_WRITES:
            pass                                    # ACR-0018: ending one's own session, one's second factor
        elif access == "read" and request.method not in READ_METHODS:
            app_ctx.store.append(AuditRecord(
                audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=None, at=utcnow(), category="access",
                event="access.read_only_refused", actor=row["id"],
                detail={"method": request.method, "path": request.url.path}))
            raise HTTPException(status.HTTP_403_FORBIDDEN, "this token is read-only")
        elif (access == "investigate" and request.method not in READ_METHODS
                and (request.method, request.url.path) not in INVESTIGATE_WRITES
                and not (request.method == "POST" and RESOLVE_PATH.match(request.url.path))):
            app_ctx.store.append(AuditRecord(
                audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=None, at=utcnow(), category="access",
                event="access.investigate_scope_refused", actor=row["id"],
                detail={"method": request.method, "path": request.url.path}))
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "this token may only read, start investigations and resolve escalated incidents")
        return Principal(id=row["id"], kind=row["kind"], role=row["role"], scopes=frozenset(row["scopes"]))
    return dep


def build_api(app_ctx) -> FastAPI:
    api = FastAPI(title="Argus v1.8", version="0.2.0",
                  description="Read-only SRE diagnosis agent on two hosts (vm-095, vm-166). "
                              "Log in with **Authorize**. Targets and incidents: docs/INCIDENTS.md.")
    current = _principal_dep(app_ctx)
    if app_ctx.settings.ui_origins:          # ACR-0001: only the listed browser origins; none by default
        from fastapi.middleware.cors import CORSMiddleware
        api.add_middleware(CORSMiddleware, allow_origins=app_ctx.settings.ui_origins, allow_methods=["GET", "POST"],
                           allow_headers=["Authorization", "Content-Type"], allow_credentials=False)

    from argus.application.second_factor import SecondFactor, SecondFactorRefused
    second = SecondFactor(app_ctx.store, app_ctx.settings.webauthn_rp_id, app_ctx.settings.webauthn_origin,
                          ticket_hours=app_ctx.settings.webauthn_enrol_ticket_hours)
    api.state.second_factor = second
    action_rows = getattr(app_ctx, "action_rows", None)

    def role_permissions(p: Principal) -> frozenset[str]:
        """ACR-0018 §5: `approve_action` and `place_hold` belong to the approver role only, assigned per person with
        `argus user add --role approver`; an operator investigates but never approves."""
        perms = permissions_of(p) | CORPUS_ROLE_PERMISSIONS.get(p.role, frozenset())
        if action_rows is not None:
            return perms | ACTION_ROLE_PERMISSIONS.get(p.role, frozenset())
        return perms

    def granted(request: Request, p: Principal) -> frozenset[str]:
        perms = role_permissions(p)
        if getattr(request.state, "access", "full") not in FULL_ACCESS:
            perms = perms - PRIVILEGED_PERMISSIONS
        if not perms & PRIVILEGED_PERMISSIONS:
            return perms
        return perms if second.privileged_ready(p.id, getattr(request.state, "session", None)) else perms - PRIVILEGED_PERMISSIONS

    def require(permission: str):
        """ACR-0018: a route names the permission it needs; the principal's role must grant it, and a privileged one
        needs the session's second factor and two credentials (step 3)."""
        def dep(request: Request, p: Annotated[Principal, Depends(current)]) -> Principal:
            if permission not in role_permissions(p):
                raise HTTPException(status.HTTP_403_FORBIDDEN, f"role {p.role} lacks the permission {permission}")
            if permission not in granted(request, p):
                raise HTTPException(status.HTTP_403_FORBIDDEN,
                                    f"the permission {permission} needs a second factor (two credentials, this login)")
            return p
        return dep

    s = app_ctx.settings
    host_metrics_lock = RLock()          # re-entrant: a read's done-callback may run in the thread that submitted it
    host_metrics_cache: dict = {"at": 0.0, "rows": None}
    host_metrics_reads: dict = {}        # host target → its in-flight read
    host_metrics_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="host-metrics")
    api.state.host_metrics_budget_s = 20.0
    from argus.application.target_metrics import TargetMetrics
    target_metrics = TargetMetrics(app_ctx.metrics, app_ctx.thresholds)   # ACR-0021: one shared answer per API
    from argus.application.overview import Overview
    overview = Overview(app_ctx.store, app_ctx.topology, lambda: host_metrics_rows(), limit=s.incidents_limit_cap)
    quota_lock = Lock()                  # ACR-0012: quota check and incident creation are one step (one API process)
    limiter = LoginLimiter(s.login_max_per_user, s.login_max_per_address, s.login_window_s, app_ctx.store)
    api.state.login_limiter = limiter

    def audit_access(event: str, user: str, detail: dict) -> None:
        app_ctx.store.append(AuditRecord(audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=None, at=utcnow(),
                                         category="access", event=event, actor=user[:64], detail=detail))

    def origin(request: Request) -> tuple[bool, str]:
        """(through the public edge?, the client address). ACR-0011: the edge always sets its header (and drops any
        copy from the browser); only then is its X-Real-IP the client. Without it the peer is the client, so a header
        cannot pick a fresh address per try."""
        edge = bool(request.headers.get(s.edge_header))
        peer = request.client.host if request.client else "unknown"
        return edge, (request.headers.get("X-Real-IP") or peer) if edge else peer

    @api.post("/api/v1/auth/token", tags=["auth"])
    def token(request: Request, form: Annotated[OAuth2PasswordRequestForm, Depends()]):
        edge, address = origin(request)
        where = {"client": address, "via": "edge" if edge else "loopback"}
        wait = limiter.retry_after(form.username, address)
        if wait:
            audit_access("access.login_locked", form.username, where)
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many failed logins; try again later",
                                headers={"Retry-After": str(wait)})
        row = app_ctx.store.get_principal(form.username)
        ok = row is not None and not row["disabled"] and hasher.verify(form.password, row["password_hash"])
        if not ok:
            limiter.failed(form.username, address)
            audit_access("access.login_failed", form.username, where)     # never the password
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad credentials")
        limiter.succeeded(form.username)
        # ACR-0001 / ACR-0012: a login asks for at most one scope, `read` or `investigate`; none = a full token
        if len(form.scopes) > 1 or (form.scopes and form.scopes[0] not in SCOPES):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown scope (only 'read' or 'investigate')")
        if edge and not form.scopes:                       # ACR-0011 / ACR-0012: the public edge never issues a full token
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "a login through the public edge must ask for scope=read or scope=investigate")
        access = form.scopes[0] if form.scopes else "full"
        now = utcnow()
        expires = now + timedelta(minutes=app_ctx.settings.jwt_ttl_min)
        jti = uuid.uuid4().hex
        app_ctx.store.add_session(jti, row["id"], access, now, expires)     # ACR-0018: the server-side session
        audit_access("access.login", row["id"], {**where, "access": access, "session": jti[:8]})   # never the token
        claims = {"sub": row["id"], "kind": row["kind"], "role": row["role"], "scopes": row["scopes"],
                  "access": access, "iat": now, "exp": expires, "jti": jti, "aud": "argus-api"}
        return {"access_token": sign_token(app_ctx, claims), "token_type": "bearer",
                "access": access}

    @api.post("/api/v1/auth/logout", tags=["auth"])
    def logout(request: Request, p: Annotated[Principal, Depends(current)]):
        """ACR-0018: end this token's session now; the next request with it is refused."""
        app_ctx.store.revoke_session(request.state.jti, p.id, "logout", utcnow())
        audit_access("access.logout", p.id, {"session": request.state.jti[:8]})
        return {"ended": True}

    @api.get("/api/v1/me", tags=["auth"])
    def me(request: Request, p: Annotated[Principal, Depends(current)]):
        """Who is logged in, and the actions this token may use (ACR-0001). A UI shows a control only when its
        action is listed: new features add actions here, never permission logic in the UI."""
        access, granted_now = request.state.access, granted(request, p)
        actions = ["view_incidents", "view_timeline"]
        if "view_evidence" in granted_now and s.langfuse_ui_url.startswith(("http://", "https://")):
            actions.append("view_traces")                   # ACR-0013 C: only when the Langfuse UI link is configured
        if "view_evidence" in granted_now:
            actions.append("view_evidence")
            if "investigate" in granted_now and access in ("full", "ops", "investigate"):   # ACR-0012: an investigate token
                actions.append("start_investigation")                                  # may start one
        if "resolve_incident" in granted_now and access in ("full", "ops", "investigate"):   # ACR-0041
            actions.append("resolve_incident")
        if second.configured:
            actions.append("manage_second_factor")          # ACR-0018 step 3: enrol a key, complete the login
        # Phase 19: a granted privileged permission is also an action, so the UI shows its control (ACR-0001)
        actions += sorted(granted_now & {"approve_action", "place_hold", "manage_corpus"})   # ACR-0040: the corpus too
        if "count_waiting_approvals" in granted_now:        # ACR-0042: the bell's count, with any token
            actions.append("count_waiting_approvals")
        # ACR-0018: what the role grants; the token's access may narrow it (a read token starts nothing); a privileged
        # permission is listed only once the second factor holds
        return {"user": p.id, "role": p.role, "access": access, "actions": actions, "permissions": sorted(granted_now),
                "second_factor": second.status(p.id, request.state.session) if second.configured else None}

    # --- ACR-0018 step 3: WebAuthn (D1-D4) ------------------------------------------------------------------------------
    def ceremony(request: Request, p: Principal, fn, *args):
        if not second.configured:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "the second factor is not configured here")
        try:
            return fn(p.id, request.state.jti, *args)
        except SecondFactorRefused as e:
            raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))

    @api.post("/api/v1/auth/webauthn/register/options", tags=["auth"])
    def webauthn_register_options(request: Request, body: EnrolIn, p: Annotated[Principal, Depends(current)]):
        """D4: the first credential with another administrator's ticket; a further one with a step-up
        (object `webauthn.register:<user>`)."""
        cid, options = ceremony(request, p, second.register_options, body.ticket, body.step_up_token)
        return {"challenge_id": cid, "options": options}

    @api.post("/api/v1/auth/webauthn/register/verify", tags=["auth"])
    def webauthn_register_verify(request: Request, body: CeremonyIn, p: Annotated[Principal, Depends(current)]):
        return ceremony(request, p, second.register_verify, body.challenge_id, body.credential, body.label)

    @api.post("/api/v1/auth/webauthn/login/options", tags=["auth"])
    def webauthn_login_options(request: Request, p: Annotated[Principal, Depends(current)]):
        cid, options = ceremony(request, p, second.login_options)
        return {"challenge_id": cid, "options": options}

    @api.post("/api/v1/auth/webauthn/login/verify", tags=["auth"])
    def webauthn_login_verify(request: Request, body: CeremonyIn, p: Annotated[Principal, Depends(current)]):
        """Completes this session's login with a credential: its privileged permissions count from now on."""
        ceremony(request, p, second.login_verify, body.challenge_id, body.credential)
        return {"verified": True}

    @api.post("/api/v1/auth/webauthn/step-up/options", tags=["auth"])
    def webauthn_step_up_options(request: Request, body: StepUpIn, p: Annotated[Principal, Depends(current)]):
        cid, options = ceremony(request, p, second.step_up_options, body.object)
        return {"challenge_id": cid, "options": options}

    @api.post("/api/v1/auth/webauthn/step-up/verify", tags=["auth"])
    def webauthn_step_up_verify(request: Request, body: CeremonyIn, p: Annotated[Principal, Depends(current)]):
        """A single-use token for the object named in its options, valid 5 minutes, in this session only; the route
        that does the privileged thing consumes it (never shown in the audit)."""
        token_value, expires = ceremony(request, p, second.step_up_verify, body.challenge_id, body.credential)
        return {"step_up_token": token_value, "expires_at": expires}

    @api.get("/api/v1/auth/webauthn/credentials", tags=["auth"])
    def webauthn_credentials(p: Annotated[Principal, Depends(current)]):
        """The caller's enrolled credentials: a short id, the label and dates (never the key)."""
        return [{"credential": c["id"][:8], "label": c["label"], "created_at": c["created_at"],
                 "last_used_at": c["last_used_at"]} for c in second.credentials(p.id)]

    def over_quota(principal: str, idempotency_key: str | None) -> tuple[str, int] | None:
        """ACR-0012: (which quota, seconds to wait) when an investigate token may not start one more; None = allowed.
        Only manual incidents count: alerts, schedules and the system are never limited here. A retry with the key of
        an incident already created starts nothing, so it is allowed and answered as a duplicate."""
        now = utcnow()
        manual = [i for i in app_ctx.store.list_incidents(1000) if i.trigger_kind == TriggerKind.manual]
        if idempotency_key and any(i.trigger_id == idempotency_key for i in manual):
            return None
        queued = [i for i in manual if i.status == IncidentStatus.queued]
        if len(queued) >= s.investigations_queued_max:
            return "queued_max", 60
        if sum(i.principal == principal for i in queued) >= s.investigations_queued_per_principal:
            return "queued_per_principal", 60
        hour = sorted(i.opened_at for i in manual if i.principal == principal and i.opened_at > now - timedelta(hours=1))
        if len(hour) >= s.investigations_per_hour:
            return "per_hour", max(1, int((hour[0] + timedelta(hours=1) - now).total_seconds()) + 1)
        return None

    @api.post("/api/v1/investigations", status_code=202, tags=["incidents"])
    def investigate(request: Request, body: InvestigationIn,
                    p: Annotated[Principal, Depends(require("investigate"))]):
        try:
            target = TargetRef.parse(body.target)
        except ValueError as e:
            raise HTTPException(422, str(e))
        # ACR-0021 B5: a re-check names an existing incident (every role reads every incident, so it is readable)
        if body.parent_id is not None and app_ctx.store.get_incident(body.parent_id) is None:
            raise HTTPException(422, "parent_id: no such incident")
        access = request.state.access
        edge, address = origin(request)
        how = {"access": access, "via": "edge" if edge else "loopback", "client": address,
               "target": str(target), "request_kind": body.request_kind, "parent_id": body.parent_id}
        with quota_lock:                                    # concurrent POSTs cannot all pass the same last free slot
            if access == "investigate":                     # ACR-0012: the UI's token is limited; a full one is not
                refused = over_quota(p.id, body.idempotency_key)
                if refused:
                    audit_access("investigation.quota_refused", p.id, {**how, "quota": refused[0]})
                    raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                        f"investigation quota reached ({refused[0]}); try again later",
                                        headers={"Retry-After": str(refused[1])})
            inc = new_incident(target, TriggerKind.manual, RequestKind(body.request_kind), body.reason, p.id,
                               body.idempotency_key or f"manual:{uuid.uuid4().hex}", body.parent_id)
            inc, duplicate = app_ctx.store.create_incident(inc, body.idempotency_key)
        audit_access("investigation.requested", p.id, {**how, "incident_id": inc.id, "duplicate": duplicate})
        return {"incident_id": inc.id, "status": inc.status, "duplicate": duplicate}

    @api.post("/api/v1/incidents/{incident_id}/resolve", tags=["incidents"])
    def resolve_incident(incident_id: str, body: ResolveIn,
                         request: Request, p: Annotated[Principal, Depends(require("resolve_incident"))]):
        """ACR-0041: close an escalated incident that was fixed outside Argus, with a reason. It keeps its diagnosis and
        outcome; only an escalated incident, once."""
        if p.kind != "human":
            raise HTTPException(403, "a human principal is required")
        inc = app_ctx.store.get_incident(incident_id)
        if inc is None:
            raise HTTPException(404, "no such incident")
        done = app_ctx.store.resolve_incident(incident_id, p.id, body.reason, utcnow())
        if done is None:
            raise HTTPException(409, "only an escalated incident can be resolved")
        app_ctx.store.append(AuditRecord(audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=incident_id,
                                         at=done.resolution.at, category="decision", event="incident.resolved",
                                         actor=p.id[:64], detail={"reason": body.reason,
                                                                  "outcome": done.outcome.value if done.outcome else None}))
        return done.model_dump(mode="json")

    @api.get("/api/v1/targets", tags=["incidents"])
    def targets(p: Annotated[Principal, Depends(current)]):
        """ACR-0012: the inventory's targets for a UI's target list (refs only: no address, port or credential)."""
        return sorted(({"target": str(t.ref), "host": t.ref.host, "kind": t.ref.kind, "name": t.ref.name}
                       for t in app_ctx.inventory.targets()), key=lambda r: r["target"])

    @api.get("/api/v1/host-metrics", tags=["metrics"])
    def host_metrics(p: Annotated[Principal, Depends(current)]):
        """Only named host signals already in the catalogue; no browser-supplied target or PromQL."""
        return host_metrics_rows()

    def host_metrics_rows() -> list[dict]:
        """The host-metrics answer, shared with `/api/v1/overview` (ACR-0021): one 20 s snapshot for both."""
        # The lock guards only the cache and the in-flight reads, never Prometheus I/O. Hosts are read in parallel, at
        # most one read per host at a time, and the answer waits at most `host_metrics_budget_s` (under the edge's 30 s
        # proxy timeout): a host still reading is `available: false`, so one slow host never hides the other.
        with host_metrics_lock:
            if host_metrics_cache["rows"] is not None and time.monotonic() - host_metrics_cache["at"] < 20:
                return [with_context(r) for r in host_metrics_cache["rows"]]
            reads = {}
            for target in sorted((t.ref for t in app_ctx.inventory.targets() if t.ref.kind == "host"), key=str):
                read = host_metrics_reads.get(target)
                if read is None:
                    read = host_metrics_reads[target] = host_metrics_pool.submit(read_host_row, target)
                    read.add_done_callback(lambda f, t=target: forget_read(t, f))
                reads[target] = read
        wait(reads.values(), timeout=api.state.host_metrics_budget_s)
        rows = [f.result() if f.done() else host_row(t, {}, None) for t, f in reads.items()]
        with host_metrics_lock:
            host_metrics_cache.update(at=time.monotonic(), rows=rows)
        return [with_context(r) for r in rows]

    def with_context(row: dict) -> dict:
        """ACR-0021: the gauges' warning and critical lines, and the monitoring heartbeat's age, computed per answer
        (the 20 s cache holds only the readings). A heartbeat nobody has recorded is null, never fresh."""
        out = {**row, "thresholds": host_thresholds(), "heartbeat_age_s": None, "heartbeat_stale": None}
        try:
            beat = (app_ctx.store.monitoring_state(row["host"]) or {}).get("last_beat_at")
            if beat:
                age = max(0, round((utcnow() - datetime.fromisoformat(beat)).total_seconds()))
                out.update(heartbeat_age_s=age, heartbeat_stale=age > HEARTBEAT_STALE_S)
        except Exception:                                  # a store hiccup leaves the heartbeat unknown, not the answer
            log.exception("heartbeat read failed for %s", row.get("host"))
        return out

    def host_thresholds() -> dict:
        """The three gauge fields' lines (memory is shown as used, so its `available` lines are flipped)."""
        th, out = app_ctx.thresholds, {}
        for field, signal, flip in (("cpu_busy_ratio", "host_cpu_busy_ratio", False),
                                    ("memory_used_ratio", "host_memory_available_ratio", True),
                                    ("disk_used_ratio", "host_disk_used_ratio", False)):
            t = th.get(signal) if th else None
            out[field] = (t.complement() if flip else t).as_dict() if t else None
        return out

    def forget_read(target, future) -> None:
        with host_metrics_lock:
            if host_metrics_reads.get(target) is future:
                del host_metrics_reads[target]

    def host_row(target, values: dict, observed_at) -> dict:
        values = {"cpu_busy_ratio": None, "memory_used_ratio": None, "disk_used_ratio": None, **values}
        return {"host": target.host, "target": str(target), "available": any(v is not None for v in values.values()),
                "observed_at": observed_at, "values": values}

    def read_host_row(target) -> dict:
        signals = {"host_cpu_busy_ratio", "host_memory_available_ratio", "host_disk_used_ratio"}
        try:
            snapshot = app_ctx.metrics.snapshot(target, signals)
        except (StaleMetrics, MetricsUnavailable):
            return host_row(target, {}, None)
        except Exception:                                  # a bad answer from Prometheus: this host only, never a 500
            log.exception("host metrics read failed for %s", target)
            return host_row(target, {}, None)
        raw, values = snapshot.values, {}
        for field, signal in (("cpu_busy_ratio", "host_cpu_busy_ratio"), ("disk_used_ratio", "host_disk_used_ratio")):
            value = raw.get(signal)
            if value is not None and math.isfinite(value) and 0 <= value <= 1:
                values[field] = value
        available = raw.get("host_memory_available_ratio")
        if available is not None and math.isfinite(available) and 0 <= available <= 1:
            values["memory_used_ratio"] = round(1 - available, 10)
        return host_row(target, values, snapshot.observed_at.isoformat() if snapshot.observed_at else None)

    @api.get("/api/v1/incidents", tags=["incidents"])
    def incidents(p: Annotated[Principal, Depends(current)], limit: int = 30,
                  parent_id: Annotated[str | None, Query(pattern=INCIDENT_ID, max_length=64)] = None):
        """`parent_id` (ACR-0021 B5): only the re-checks of that incident, newest first."""
        return [{"id": i.id, "target": str(i.target), "status": i.status, "outcome": i.outcome,
                 "class": i.incident_class, "strategy": i.strategy, "opened_at": i.opened_at,
                 "root_cause_target": i.root_cause_target, "parent_id": i.parent_id}
                for i in app_ctx.store.list_incidents(min(limit, s.incidents_limit_cap),   # ACR-0011: capped
                                                      parent_id=parent_id)]

    @api.get("/api/v1/incidents/{incident_id}", tags=["incidents"])
    def incident(incident_id: str, p: Annotated[Principal, Depends(current)]):
        inc = app_ctx.store.get_incident(incident_id)
        if inc is None:
            raise HTTPException(404, "not found")
        view = inc.model_dump(mode="json")
        view["target"] = str(inc.target)
        operator = "view_evidence" in permissions_of(p)
        evidence = app_ctx.store.list_evidence(incident_id)
        audit = app_ctx.store.list_for(incident_id)
        recalled = {p["runbook_id"] for a in audit if a.event == "recall.passages"
                    for p in (a.detail or {}).get("passages", []) if "runbook_id" in p}
        next_actions = (app_ctx.action_policy.next_actions(inc, evidence, recalled, app_ctx.inventory)
                        if operator and app_ctx.action_policy else [])
        # ACR-0021 (T-0045 B4): the verdict card's fields, derived from the store alone; a viewer's carry no evidence text
        view.update(build_verdict(
            inc, next((c for c in CLASSES if c.name == inc.incident_class), None), evidence,
            [e for a in audit if a.event == "incident.recorded"
             for e in (a.detail or {}).get("cited") or []],
            {str(t.ref): [str(d) for d in t.depends_on] for t in app_ctx.inventory.targets()}, operator,
            app_ctx.store.hypotheses(incident_id) if hasattr(app_ctx.store, "hypotheses") else [],
            next_actions))   # ACR-0024 §3.6; Phase 17 candidates are read-only
        if operator:
            view["evidence"] = [{"evidence_id": e.evidence_id, "kind": e.kind, "capability": e.capability,
                                 "target": e.target, "executor": e.executor, "status": e.status,
                                 "caller": e.caller, "collected_at": e.collected_at, "source_time": e.source_time,
                                 "sha256": e.sha256, "model_text": e.model_text}
                                for e in app_ctx.store.list_evidence(incident_id)]
            if s.langfuse_ui_url.startswith(("http://", "https://")):      # ACR-0013 C: a link, never Langfuse data
                proj = f"/project/{quote(s.langfuse_project_id, safe='')}" if s.langfuse_project_id else ""
                view["trace_url"] = f"{s.langfuse_ui_url}{proj}/traces?search={quote(incident_id, safe='')}"
            view["audit"] = [{"at": a.at, "event": a.event, "capability": a.capability, "actor": a.actor,
                              "policy_rule": a.policy_rule, "evidence_id": a.evidence_id, "detail": a.detail}
                             for a in app_ctx.store.list_for(incident_id)]
            if action_rows is not None:          # the supervised action's trail, while the action routes are mounted
                from argus.application.incident_action import incident_action
                found = incident_action(action_rows, incident_id)
                if found is not None:
                    view["action"] = found
        return view

    @api.get("/api/v1/incidents/{incident_id}/events", tags=["incidents"])
    def run_events(incident_id: str, p: Annotated[Principal, Depends(current)], after: int = 0):
        if app_ctx.store.get_incident(incident_id) is None:
            raise HTTPException(404, "not found")
        return app_ctx.store.list_run_events(incident_id, after)

    @api.get("/api/v1/topology", tags=["incidents"])
    def topology(p: Annotated[Principal, Depends(current)],
                 incident_id: Annotated[str | None, Query(pattern=r"^inc_[A-Za-z0-9_-]+$", max_length=64)] = None):
        """ACR-0017: the system map: inventory targets, declared dependencies with their ports and networks, live state
        from named signals and the dependency probe; with `incident_id` (operator/approver), the incident's target and
        root cause from its stored evidence. Never VM addresses, Argus's internal endpoints or secrets."""
        if incident_id is None:
            return app_ctx.topology.view()
        if "view_evidence" not in permissions_of(p):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "the incident overlay uses evidence: operator or approver")
        inc = app_ctx.store.get_incident(incident_id)
        if inc is None:
            raise HTTPException(404, "not found")
        return app_ctx.topology.view_for(inc)

    @api.get("/api/v1/incidents/{incident_id}/metrics", tags=["incidents"])
    def incident_metrics(incident_id: str, p: Annotated[Principal, Depends(current)],
                         rng: Annotated[Literal["15m", "30m", "1h", "6h", "24h"], Query(alias="range")] = "30m"):
        """ACR-0017: the incident's metric window, a fixed signal list per class on the incident's own host; no
        PromQL or target from the browser; at most ~130 points per series; a missing sample is null."""
        inc = app_ctx.store.get_incident(incident_id)
        if inc is None:
            raise HTTPException(404, "not found")
        return app_ctx.incident_metrics.window(inc, rng)

    @api.get("/api/v1/target-metrics", tags=["metrics"])
    def target_metrics_route(p: Annotated[Principal, Depends(current)],
                             target: Annotated[str, Query(pattern=r"^[A-Za-z0-9_.-]+/[a-z_]+:[A-Za-z0-9_.-]+$",
                                                          max_length=128)],
                             rng: Annotated[Literal["15m", "1h"], Query(alias="range")] = "15m"):
        """ACR-0021 (T-0045 B6): one inventory target's recent signals for the UI's drawer, a fixed series list per
        kind on that target's own host; no PromQL from the browser; at most ~130 points per series; missing is null."""
        try:
            ref = TargetRef.parse(target)
        except ValueError:
            raise HTTPException(404, "not found") from None
        if app_ctx.inventory.target(ref) is None:
            raise HTTPException(404, "not found")
        return target_metrics.window(ref, rng)

    @api.get("/api/v1/overview", tags=["metrics"])
    def overview_route(p: Annotated[Principal, Depends(current)]):
        """ACR-0021 (T-0045 B6): the dashboard in one answer, from the stored incidents and the shared topology and
        host-metrics snapshots; no new host read, no executor call; one shared answer for 15 s."""
        return overview.view()

    @api.get("/api/v1/evidence/{evidence_id}", tags=["incidents"])
    def evidence(evidence_id: str, p: Annotated[Principal, Depends(require("view_evidence"))]):
        rec = app_ctx.store.get_evidence([evidence_id])
        if not rec:
            raise HTTPException(404, "not found")
        return rec[0]

    @api.get("/api/v1/escalations", tags=["incidents"])
    def escalations(p: Annotated[Principal, Depends(current)]):
        return app_ctx.store.notifications()

    # Phase 19 draft: mounted only by explicit composition. Production does not supply action_rows.
    if action_rows is not None:
        from argus.application.second_factor import CREDENTIALS_FOR_PRIVILEGE

        @api.post(OPS_LOGIN, tags=["ops"])
        def ops_token(request: Request, form: Annotated[OAuth2PasswordRequestForm, Depends()]):
            """ACR-0032: the private browser login. Only through the private path (else 404, as if absent); a full
            `ops` token for a human approver with two WebAuthn credentials; the limiter, lockout and audit of the
            public login; 15 minutes idle, one hour at most."""
            if not private_path(request, s):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
            _, address = origin(request)
            where = {"client": address, "via": "ops", "client_cert": client_cert(request, s)}
            wait = limiter.retry_after(form.username, address)
            if wait:
                audit_access("access.login_locked", form.username, where)
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many failed logins; try again later",
                                    headers={"Retry-After": str(wait)})
            row = app_ctx.store.get_principal(form.username)
            ok = row is not None and not row["disabled"] and hasher.verify(form.password, row["password_hash"])
            eligible = (ok and row["kind"] == "human"
                        and bool(ACTION_ROLE_PERMISSIONS.get(row["role"]) or CORPUS_ROLE_PERMISSIONS.get(row["role"]))
                        and len(second.credentials(row["id"])) >= CREDENTIALS_FOR_PRIVILEGE)
            if not eligible:                                # one answer for a wrong password and a non-approver
                limiter.failed(form.username, address)
                audit_access("access.ops_login_failed", form.username, {**where, "password_ok": ok})
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad credentials")
            limiter.succeeded(form.username)
            now = utcnow()
            expires, jti = now + OPS_SESSION, uuid.uuid4().hex
            app_ctx.store.add_session(jti, row["id"], "ops", now, expires)
            audit_access("access.login", row["id"], {**where, "access": "ops", "session": jti[:8]})
            claims = {"sub": row["id"], "kind": row["kind"], "role": row["role"], "scopes": row["scopes"],
                      "access": "ops", "iat": now, "exp": expires, "jti": jti, "aud": "argus-api"}
            return {"access_token": sign_token(app_ctx, claims), "token_type": "bearer", "access": "ops"}

        from argus.application.approval_view import ApprovalViewRefused, approval_view, answerable_approval
        from argus.application.holds import (hold_audit, hold_release_step_up_object, hold_step_up_object,
                                             validate_hold_target)

        def require_action_scope(p: Principal, target: str) -> None:
            info = app_ctx.inventory.target(TargetRef.parse(target))
            if info is None or info.scope not in p.scopes:
                raise HTTPException(403, "target is outside this principal's scope")

        def waiting_approvals(p: Principal) -> list[dict]:
            """The approvals waiting for a person, in this principal's scope; one that no longer verifies is left out
            (opening it by id shows why). At most PENDING_LIST_LIMIT."""
            if p.kind != "human":
                raise HTTPException(403, "a human principal is required")
            out, now, after = [], utcnow(), None
            while len(out) < PENDING_LIST_LIMIT:            # filter first, then fill the page (#347 review)
                page = action_rows.list_pending_approvals(now, limit=PENDING_SCAN_PAGE, after=after)
                for approval_id in page:
                    try:
                        view = approval_view(action_rows, approval_id)
                    except ApprovalViewRefused:
                        continue
                    info = app_ctx.inventory.target(TargetRef.parse(view["proposal"]["input"]["target"]))
                    if view["state"] != "pending" or info is None or info.scope not in p.scopes:
                        continue
                    data = view["proposal"]["input"]
                    out.append({"id": view["id"], "incident_id": data["incident_id"],
                                "capability": data["capability"], "target": data["target"],
                                "risk": view["judge"]["risk"], "verdict": view["judge"]["verdict"],
                                "expires_at": view["expires_at"]})
                    if len(out) == PENDING_LIST_LIMIT:
                        break
                if len(page) < PENDING_SCAN_PAGE:
                    break
                after = page[-1]
            return out

        @api.get("/api/v1/ops/approvals", tags=["ops"])
        def pending_approvals(p: Annotated[Principal, Depends(require("approve_action"))]):
            """The approvals waiting for a person, in this principal's scope; one that no longer verifies is left out
            (opening it by id shows why)."""
            return waiting_approvals(p)

        @api.get("/api/v1/approvals/waiting", tags=["actions"])
        def approvals_waiting(p: Annotated[Principal, Depends(require("count_waiting_approvals"))]):
            """ACR-0042: how many approvals wait for this approver (the same filter as the private list, at most 50),
            with any token and no second factor: a count only, never an id, an incident, an action or a target."""
            return {"waiting": len(waiting_approvals(p))}

        @api.get("/api/v1/ops/approvals/{approval_id}", tags=["ops"])
        def inspect_approval(approval_id: str, p: Annotated[Principal, Depends(require("approve_action"))]):
            if p.kind != "human":
                raise HTTPException(403, "a human principal is required")
            try:
                view = approval_view(action_rows, approval_id)
            except ApprovalViewRefused as exc:
                raise HTTPException(409, str(exc)) from exc
            require_action_scope(p, view["proposal"]["input"]["target"])
            return view

        @api.post("/api/v1/ops/approvals/{approval_id}/answer", tags=["ops"])
        def answer_approval(approval_id: str, body: ApprovalAnswerIn, request: Request,
                            p: Annotated[Principal, Depends(require("approve_action"))]):
            if p.kind != "human":
                raise HTTPException(403, "a human principal is required")
            try:
                view = answerable_approval(action_rows, approval_id, body.proposal_digest,
                                           body.decision, body.confirmation_target)
            except ApprovalViewRefused as exc:
                raise HTTPException(409, str(exc)) from exc
            require_action_scope(p, view["proposal"]["input"]["target"])
            try:
                second.consume_step_up(body.step_up_token, p.id, request.state.jti,
                                       f"approval:{approval_id}:{body.proposal_digest}")
            except SecondFactorRefused as exc:
                raise HTTPException(403, str(exc)) from exc
            now = utcnow()
            # on the incident's own audit too, so its page shows which operator answered
            audit = hold_audit("action.approval_answered", p.id, now,
                               incident_id=view["proposal"]["input"]["incident_id"], approval_id=approval_id,
                               proposal_digest=body.proposal_digest, decision=body.decision,
                               reason=body.reason.strip() if body.reason else None,
                               client_cert=client_cert(request, s),
                               judge_verdict=view["judge"]["verdict"], risk=view["judge"]["risk"])   # ACR-0039
            if not action_rows.answer_action_approval(approval_id, body.proposal_digest, p.id,
                                                      body.decision, now, audit=audit):
                raise HTTPException(409, "approval is no longer pending")
            return {"state": body.decision}

        @api.get("/api/v1/ops/holds", tags=["ops"])
        def inspect_holds(target: Annotated[str, Query(max_length=128)],
                          p: Annotated[Principal, Depends(require("place_hold"))]):
            if p.kind != "human":
                raise HTTPException(403, "a human principal is required")
            try:
                validate_hold_target(target, app_ctx.inventory)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            if target != "*" and "/" in target:
                require_action_scope(p, target)
            return action_rows.list_active_target_holds(target, utcnow())

        @api.post("/api/v1/ops/holds", status_code=201, tags=["ops"])
        def place_hold(body: HoldIn, request: Request,
                       p: Annotated[Principal, Depends(require("place_hold"))]):
            if p.kind != "human":
                raise HTTPException(403, "a human principal is required")
            try:
                validate_hold_target(body.target, app_ctx.inventory)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            if body.target != "*" and "/" in body.target:
                require_action_scope(p, body.target)
            try:
                second.consume_step_up(body.step_up_token, p.id, request.state.jti,
                                       hold_step_up_object(body.target))
            except SecondFactorRefused as exc:
                raise HTTPException(403, str(exc)) from exc
            now, hold_id = utcnow(), f"hold_{uuid.uuid4().hex}"
            audit = hold_audit("action.hold_placed", p.id, now, hold_id=hold_id, target=body.target)
            action_rows.place_target_hold(hold_id, body.target, body.reason, p.id, now, audit)
            return {"id": hold_id, "target": body.target, "placed_at": now}

        @api.post("/api/v1/ops/holds/{hold_id}/release", tags=["ops"])
        def release_hold(hold_id: str, body: HoldReleaseIn, request: Request,
                         p: Annotated[Principal, Depends(require("place_hold"))]):
            """Releasing raises power: its own step-up, bound to this hold. The emergency stop is released only from
            the CLI on vm-095 (`argus hold release`), by the lease holder."""
            if p.kind != "human":
                raise HTTPException(403, "a human principal is required")
            hold = action_rows.get_target_hold(hold_id)
            if hold is None or hold["released_at"] is not None:
                raise HTTPException(409, "hold is not active")
            if hold["target"] == "*":
                raise HTTPException(409, "the emergency stop is released only from the CLI on vm-095")
            if "/" in hold["target"]:
                require_action_scope(p, hold["target"])
            try:
                second.consume_step_up(body.step_up_token, p.id, request.state.jti,
                                       hold_release_step_up_object(hold_id))
            except SecondFactorRefused as exc:
                raise HTTPException(403, str(exc)) from exc
            now = utcnow()
            audit = hold_audit("action.hold_released", p.id, now, hold_id=hold_id, target=hold["target"],
                               reason=body.reason.strip())
            if not action_rows.release_target_hold(hold_id, p.id, now, audit=audit):
                raise HTTPException(409, "hold is not active")
            return {"id": hold_id, "released_at": now}

    # ACR-0034 local tier: mounted only when a staging folder is configured (ARGUS_CORPUS_STAGING_DIR), like the
    # phase 19 action routes; then staged reference sources are installed only by an approver's or an administrator's
    # approval (ACR-0040)
    if s.corpus_staging_dir:
        from argus.corpus import staging as corpus_staging

        def corpus_dirs() -> tuple[Path | None, Path | None]:
            return (Path(s.corpus_staging_dir) if s.corpus_staging_dir else None,
                    Path(s.corpus_dir) if s.corpus_dir else None)

        def corpus_audit(event: str, actor: str, **detail) -> None:
            app_ctx.store.append(AuditRecord(audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=None, at=utcnow(),
                                             category="decision", event=event, actor=actor[:64], detail=detail))

        @api.get("/api/v1/ops/corpus/sources", tags=["ops"])
        def corpus_sources(p: Annotated[Principal, Depends(require("manage_corpus"))]):
            """The installed reference sources and the staged ones waiting for an administrator."""
            return corpus_staging.list_sources(*corpus_dirs())

        def corpus_decision(name: str, body, request: Request, p: Principal, approve: bool):
            if p.kind != "human":
                raise HTTPException(403, "a human principal is required")
            staging_dir, corpus_dir = corpus_dirs()
            if staging_dir is None or (approve and corpus_dir is None):
                raise HTTPException(409, "no corpus staging folder configured")
            try:
                digest = corpus_staging.staged_sha256(staging_dir, name)
            except corpus_staging.StagingRefused as exc:
                raise HTTPException(409, str(exc)) from exc
            try:
                second.consume_step_up(body.step_up_token, p.id, request.state.jti, f"corpus:{name}:{digest}")
            except SecondFactorRefused as exc:
                raise HTTPException(403, str(exc)) from exc
            try:
                if approve:
                    m = corpus_staging.approve(name, staging_dir, corpus_dir, digest)
                    corpus_audit("corpus.source_approved", p.id, source=name, sha256=digest[:16])
                    return {"name": name, "status": "installed", "sources": [x["name"] for x in m["sources"]]}
                corpus_staging.reject(name, staging_dir)
            except corpus_staging.StagingRefused as exc:
                raise HTTPException(409, str(exc)) from exc
            corpus_audit("corpus.source_rejected", p.id, source=name, sha256=digest[:16], reason=body.reason.strip())
            return {"name": name, "status": "rejected"}

        @api.post("/api/v1/ops/corpus/sources/{name}/approve", tags=["ops"])
        def corpus_approve(name: str, body: CorpusApproveIn, request: Request,
                           p: Annotated[Principal, Depends(require("manage_corpus"))]):
            """Install a staged source: its hashes verified, its step-up bound to `corpus:<name>:<passages sha256>`."""
            return corpus_decision(name, body, request, p, approve=True)

        @api.post("/api/v1/ops/corpus/sources/{name}/reject", tags=["ops"])
        def corpus_reject(name: str, body: CorpusRejectIn, request: Request,
                          p: Annotated[Principal, Depends(require("manage_corpus"))]):
            """Delete a staged source, with a reason; its own step-up."""
            return corpus_decision(name, body, request, p, approve=False)

    # ACR-0043 (CON-2): the operator console. Mounted only with ARGUS_OPERATOR_CONSOLE=1 (else 404, as if absent), on
    # the private prefix only, for a person's own full session with `investigate`: never a service, an agent or a
    # scoped (read / investigate) token.
    from argus.console.config import ConsoleConfig
    console_config = ConsoleConfig()
    if console_config.enabled:
        from argus.console import registry as console_registry
        from argus.console.service import ConsoleService, NotRetryable, QuotaRefused, UnknownCommand, lines_of
        console = ConsoleService(app_ctx, console_config)
        api.state.console = console

        def console_private(request: Request) -> None:
            if not private_path(request, s):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")

        def console_person(request: Request, p: Annotated[Principal, Depends(require("investigate"))]) -> Principal:
            if p.kind != "human" or getattr(request.state, "access", "full") not in FULL_ACCESS:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "the console is for a person's own session")
            return p

        def console_incident(incident_id: str):
            inc = app_ctx.store.get_incident(incident_id) if re.match(INCIDENT_ID, incident_id) else None
            if inc is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "no such incident")
            return inc

        @api.get("/api/v1/ops/console/incidents/{incident_id}/commands", tags=["ops"],
                 dependencies=[Depends(console_private)])
        def console_commands(incident_id: str, p: Annotated[Principal, Depends(console_person)]):
            console_incident(incident_id)
            return {"commands": console_registry.catalog()}

        @api.get("/api/v1/ops/console/incidents/{incident_id}/history", tags=["ops"],
                 dependencies=[Depends(console_private)])
        def console_history(incident_id: str, p: Annotated[Principal, Depends(console_person)]):
            """The incident's stored commands, oldest first, `output` as lines like `execute` answers it (the stores
            keep one text). A refused input is an entry with `command` and `class` null. `analysis` (CON-4b) is added
            to an entry whose command was analysed, built from what is stored and the clock; others have none."""
            console_incident(incident_id)
            analyses = app_ctx.store.console_analyses(incident_id)
            entries = []
            for r in app_ctx.store.console_history(incident_id, console_config.history_limit):
                entry = {"command_id": r["command_id"], "input": r["input"], "command": r["command"],
                         "class": r["cls"], "status": r["status"], "output": lines_of(r["output"]),
                         "by": r["person"], "started_at": r["started_at"], "finished_at": r["finished_at"]}
                if r["command_id"] in analyses:      # CON-4b: Argus's comment, built from what is stored
                    entry["analysis"] = console.analysis.view(r, analyses[r["command_id"]])
                entries.append(entry)
            return {"entries": entries}

        @api.post("/api/v1/ops/console/incidents/{incident_id}/commands/{command_id}/recheck", status_code=202,
                  tags=["ops"], dependencies=[Depends(console_private)])
        def console_recheck(incident_id: str, command_id: str, p: Annotated[Principal, Depends(console_person)]):
            """CON-4b: look again at a command's result (an analysis that is retryable; else 409). The answer is
            immediate: the new state, `analyzing`; the history carries the result."""
            inc = console_incident(incident_id)
            try:
                view = console.recheck(p, inc, command_id) if re.match(r"^cmd_[0-9a-f]+$", command_id) else None
            except QuotaRefused as refused:
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                    f"console read quota reached ({refused.which}); try again later",
                                    headers={"Retry-After": str(refused.retry_after)})
            except UnknownCommand:
                view = None
            except NotRetryable:
                raise HTTPException(status.HTTP_409_CONFLICT, "this analysis is not retryable")
            if view is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "no such command")
            return {"command_id": command_id, "analysis": view}

        @api.post("/api/v1/ops/console/incidents/{incident_id}/execute", tags=["ops"],
                  dependencies=[Depends(console_private)])
        def console_execute(incident_id: str, body: ConsoleExecuteIn,
                            p: Annotated[Principal, Depends(console_person)]):
            inc = console_incident(incident_id)
            try:
                done = console.run(p, inc, body.input, body.suggestion_id)
            except QuotaRefused as refused:
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                    f"console read quota reached ({refused.which}); try again later",
                                    headers={"Retry-After": str(refused.retry_after)})
            return {"command_id": done.command_id, "input": done.input, "command": done.command,
                    "class": done.cls, "status": done.status, "output": done.output,
                    "started_at": done.started_at, "finished_at": done.finished_at}

    @api.get("/healthz", tags=["ops"])
    def healthz():
        return {"ok": True, "policy_version": app_ctx.policy.version[:12],
                "inventory_version": app_ctx.inventory.version()[:12], "llm_configured": app_ctx.llm_configured}

    return api


def build_webhook(app_ctx) -> FastAPI:
    """Private listener: Alertmanager only. No docs, no human routes."""
    hook = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @hook.post("/api/v1/alerts")
    def alerts(payload: dict, authorization: Annotated[str | None, Header()] = None):
        expected = app_ctx.alertmanager_token
        given = (authorization or "").removeprefix("Bearer ").strip()
        if not expected or not hmac.compare_digest(given, expected):
            raise HTTPException(401, "unauthorized")
        # ACR-0003: the same use case as the pull reconciliation, so a pushed and a pulled alert are one incident.
        handle = HandleAlertNotification(app_ctx.store, app_ctx.inventory, app_ctx.metrics)
        created = []
        for a in payload.get("alerts", []):
            ends = a.get("endsAt") if a.get("status") == "resolved" else None   # T-0026: when it stopped
            if isinstance(ends, str) and ends.startswith("0001-"):           # Alertmanager's zero time = unset
                ends = None
            try:
                note = AlertNotification(fingerprint=str(a.get("fingerprint", "")), status=a.get("status"),
                                         starts_at=a.get("startsAt"), ends_at=ends,
                                         labels=a.get("labels") or {}, annotations=a.get("annotations") or {})
            except ValueError:
                continue
            host = note.labels.get("argus_host", "?")
            r = handle(note, source=f"alertmanager@{host}")
            if r.incident_id:
                created.append({"incident_id": r.incident_id, "disposition": r.disposition,
                                "duplicate": r.disposition == "duplicate"})
        return {"accepted": created}

    @hook.get("/healthz")
    def healthz():
        return {"ok": True}

    return hook
