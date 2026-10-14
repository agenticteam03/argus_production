"""HTTP inbound adapter (FastAPI): human API with JWT on the loopback listener, Alertmanager webhook
on the private listener (v1.8 §7.1, §17.3). The only FastAPI location.

No `from __future__ import annotations` here: FastAPI must resolve the local dependency closures."""

from urllib.parse import quote
import hmac
import uuid
from datetime import timedelta
from typing import Annotated, Literal

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pwdlib import PasswordHash
from pydantic import BaseModel, ConfigDict

from argus.application.alerts import HandleAlertNotification
from argus.domain.model import (AlertNotification, AuditRecord, Incident, Principal, RequestKind, TargetRef, TriggerKind,
                                utcnow)

READ_METHODS = ("GET", "HEAD")          # a read-only token (ACR-0001) may use only these

hasher = PasswordHash.recommended()
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


class InvestigationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str
    reason: str = ""
    request_kind: Literal["check", "report"] = "report"
    idempotency_key: str | None = None


def new_incident(target: TargetRef, trigger: TriggerKind, request: RequestKind, reason: str,
                 principal: str | None, trigger_id: str) -> Incident:
    return Incident(id=f"inc_{uuid.uuid4().hex[:12]}", target=target, trigger_kind=trigger, request_kind=request,
                    reason=reason[:2000], principal=principal, trigger_id=trigger_id, opened_at=utcnow())


class LoginLimiter:
    """§17.3 / ACR-0011: failed logins per username and per client address in a sliding window; once either reaches
    its maximum, logins for it are refused (429) until the window has passed. In memory: the API is one process
    (a restart forgets the counts, which only shortens a lockout)."""

    def __init__(self, max_per_user: int, max_per_address: int, window_s: int):
        import time
        self.max_per_user, self.max_per_address, self.window_s = max_per_user, max_per_address, window_s
        self.now = time.monotonic
        self._fails: dict[str, list[float]] = {}

    def _recent(self, key: str) -> list[float]:
        cutoff = self.now() - self.window_s
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
        for key in (f"u:{user}", f"a:{address}"):
            self._recent(key).append(self.now())

    def succeeded(self, user: str) -> None:
        self._fails.pop(f"u:{user}", None)


def _principal_dep(app_ctx):
    def dep(request: Request, token: Annotated[str, Depends(oauth2)]) -> Principal:
        try:
            claims = jwt.decode(token, app_ctx.jwt_key, algorithms=["HS256"], audience="argus-api")
        except jwt.PyJWTError:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token",
                                headers={"WWW-Authenticate": "Bearer"})
        row = app_ctx.store.get_principal(claims["sub"])
        if row is None or row["disabled"]:          # disabling takes effect before token expiry
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "principal disabled")
        # ACR-0001: a read-only token only narrows what the role allows; tokens without the claim are full
        access = claims.get("access", "full")
        request.state.access = access
        if access == "read" and request.method not in READ_METHODS:
            app_ctx.store.append(AuditRecord(
                audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=None, at=utcnow(), category="access",
                event="access.read_only_refused", actor=row["id"],
                detail={"method": request.method, "path": request.url.path}))
            raise HTTPException(status.HTTP_403_FORBIDDEN, "this token is read-only")
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

    def require(*roles: str):
        def dep(p: Annotated[Principal, Depends(current)]) -> Principal:
            if p.role not in roles:
                raise HTTPException(status.HTTP_403_FORBIDDEN, f"role {p.role} may not do this")
            return p
        return dep

    s = app_ctx.settings
    limiter = LoginLimiter(s.login_max_per_user, s.login_max_per_address, s.login_window_s)
    api.state.login_limiter = limiter

    def audit_access(event: str, user: str, detail: dict) -> None:
        app_ctx.store.append(AuditRecord(audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=None, at=utcnow(),
                                         category="access", event=event, actor=user[:64], detail=detail))

    @api.post("/api/v1/auth/token", tags=["auth"])
    def token(request: Request, form: Annotated[OAuth2PasswordRequestForm, Depends()]):
        # ACR-0011: the public edge always sets its header (and drops any copy from the browser); only then is its
        # X-Real-IP the client. Without it the peer is the client, so a header cannot pick a fresh address per try.
        edge = bool(request.headers.get(s.edge_header))
        peer = request.client.host if request.client else "unknown"
        address = (request.headers.get("X-Real-IP") or peer) if edge else peer
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
        if form.scopes and form.scopes != ["read"]:        # ACR-0001: the only scope a login may ask for is "read"
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown scope (only 'read' is accepted)")
        if edge and form.scopes != ["read"]:               # ACR-0011: a login through the public edge is read-only
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "a login through the public edge must ask for scope=read")
        access = "read" if form.scopes == ["read"] else "full"
        now = utcnow()
        claims = {"sub": row["id"], "kind": row["kind"], "role": row["role"], "scopes": row["scopes"],
                  "access": access, "iat": now, "exp": now + timedelta(minutes=app_ctx.settings.jwt_ttl_min),
                  "jti": uuid.uuid4().hex, "aud": "argus-api"}
        return {"access_token": jwt.encode(claims, app_ctx.jwt_key, algorithm="HS256"), "token_type": "bearer",
                "access": access}

    @api.get("/api/v1/me", tags=["auth"])
    def me(request: Request, p: Annotated[Principal, Depends(current)]):
        """Who is logged in, and the actions this token may use (ACR-0001). A UI shows a control only when its
        action is listed: new features add actions here, never permission logic in the UI."""
        access = request.state.access
        actions = ["view_incidents", "view_timeline"]
        if p.role in ("operator", "approver") and s.langfuse_ui_url.startswith(("http://", "https://")):
            actions.append("view_traces")                   # ACR-0013 C: only when the Langfuse UI link is configured
        if p.role in ("operator", "approver"):
            actions.append("view_evidence")
            if access == "full":
                actions.append("start_investigation")
        return {"user": p.id, "role": p.role, "access": access, "actions": actions}

    @api.post("/api/v1/investigations", status_code=202, tags=["incidents"])
    def investigate(body: InvestigationIn, p: Annotated[Principal, Depends(require("operator", "approver"))]):
        try:
            target = TargetRef.parse(body.target)
        except ValueError as e:
            raise HTTPException(422, str(e))
        inc = new_incident(target, TriggerKind.manual, RequestKind(body.request_kind), body.reason, p.id,
                           body.idempotency_key or f"manual:{uuid.uuid4().hex}")
        inc, duplicate = app_ctx.store.create_incident(inc, body.idempotency_key)
        return {"incident_id": inc.id, "status": inc.status, "duplicate": duplicate}

    @api.get("/api/v1/incidents", tags=["incidents"])
    def incidents(p: Annotated[Principal, Depends(current)], limit: int = 30):
        return [{"id": i.id, "target": str(i.target), "status": i.status, "outcome": i.outcome,
                 "class": i.incident_class, "strategy": i.strategy, "opened_at": i.opened_at,
                 "root_cause_target": i.root_cause_target}
                for i in app_ctx.store.list_incidents(min(limit, s.incidents_limit_cap))]   # ACR-0011: capped

    @api.get("/api/v1/incidents/{incident_id}", tags=["incidents"])
    def incident(incident_id: str, p: Annotated[Principal, Depends(current)]):
        inc = app_ctx.store.get_incident(incident_id)
        if inc is None:
            raise HTTPException(404, "not found")
        view = inc.model_dump(mode="json")
        view["target"] = str(inc.target)
        if p.role in ("operator", "approver"):
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
        return view

    @api.get("/api/v1/incidents/{incident_id}/events", tags=["incidents"])
    def run_events(incident_id: str, p: Annotated[Principal, Depends(current)], after: int = 0):
        if app_ctx.store.get_incident(incident_id) is None:
            raise HTTPException(404, "not found")
        return app_ctx.store.list_run_events(incident_id, after)

    @api.get("/api/v1/evidence/{evidence_id}", tags=["incidents"])
    def evidence(evidence_id: str, p: Annotated[Principal, Depends(require("operator", "approver"))]):
        rec = app_ctx.store.get_evidence([evidence_id])
        if not rec:
            raise HTTPException(404, "not found")
        return rec[0]

    @api.get("/api/v1/escalations", tags=["incidents"])
    def escalations(p: Annotated[Principal, Depends(current)]):
        return app_ctx.store.notifications()

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
