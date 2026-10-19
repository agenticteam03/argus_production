"""HTTP inbound adapter (FastAPI): human API with JWT on the loopback listener, Alertmanager webhook
on the private listener (v1.8 §7.1, §17.3). The only FastAPI location.

No `from __future__ import annotations` here: FastAPI must resolve the local dependency closures."""

from urllib.parse import quote
import hmac
import logging
import math
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta
from threading import Lock, RLock
from typing import Annotated, Literal

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pwdlib import PasswordHash
from pydantic import BaseModel, ConfigDict, Field

from argus.application.alerts import HandleAlertNotification
from argus.application.incident_view import build_verdict
from argus.detectors.classes import CLASSES
from argus.domain.model import (AlertNotification, AuditRecord, Incident, IncidentStatus, Principal, RequestKind,
                                TargetRef, TriggerKind, utcnow)
from argus.ports.ports import MetricsUnavailable, StaleMetrics

READ_METHODS = ("GET", "HEAD")          # a read-only token (ACR-0001) may use only these
INVESTIGATE_WRITES = {("POST", "/api/v1/investigations")}   # the one non-GET of an `investigate` token (ACR-0012)
SCOPES = {"read", "investigate"}        # what a login may ask for; none = a full token (loopback only)

log = logging.getLogger("argus.api")

# A host's heartbeat renews every 60-75 s (T-0035, measured on Alertmanager): older than twice that is stale. It sits
# between two reconcile ticks and the scheduler's loss (`stale_after_s`, deploy/scheduler/schedules.yaml); a test pins it.
HEARTBEAT_STALE_S = 150
hasher = PasswordHash.recommended()
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


INCIDENT_ID = r"^inc_[A-Za-z0-9_-]+$"   # an incident id in a request (never a path or free text)


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
        if (access == "investigate" and request.method not in READ_METHODS
                and (request.method, request.url.path) not in INVESTIGATE_WRITES):
            app_ctx.store.append(AuditRecord(
                audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=None, at=utcnow(), category="access",
                event="access.investigate_scope_refused", actor=row["id"],
                detail={"method": request.method, "path": request.url.path}))
            raise HTTPException(status.HTTP_403_FORBIDDEN, "this token may only read and start investigations")
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
    host_metrics_lock = RLock()          # re-entrant: a read's done-callback may run in the thread that submitted it
    host_metrics_cache: dict = {"at": 0.0, "rows": None}
    host_metrics_reads: dict = {}        # host target → its in-flight read
    host_metrics_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="host-metrics")
    api.state.host_metrics_budget_s = 20.0
    from argus.application.target_metrics import TargetMetrics
    target_metrics = TargetMetrics(app_ctx.metrics, app_ctx.thresholds)   # ACR-0021: one shared answer per API
    quota_lock = Lock()                  # ACR-0012: quota check and incident creation are one step (one API process)
    limiter = LoginLimiter(s.login_max_per_user, s.login_max_per_address, s.login_window_s)
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
            if access in ("full", "investigate"):          # ACR-0012: an investigate token may start one
                actions.append("start_investigation")
        return {"user": p.id, "role": p.role, "access": access, "actions": actions}

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
                    p: Annotated[Principal, Depends(require("operator", "approver"))]):
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

    @api.get("/api/v1/targets", tags=["incidents"])
    def targets(p: Annotated[Principal, Depends(current)]):
        """ACR-0012: the inventory's targets for a UI's target list (refs only: no address, port or credential)."""
        return sorted(({"target": str(t.ref), "host": t.ref.host, "kind": t.ref.kind, "name": t.ref.name}
                       for t in app_ctx.inventory.targets()), key=lambda r: r["target"])

    @api.get("/api/v1/host-metrics", tags=["metrics"])
    def host_metrics(p: Annotated[Principal, Depends(current)]):
        """Only named host signals already in the catalogue; no browser-supplied target or PromQL."""
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
        operator = p.role in ("operator", "approver")
        # ACR-0021 (T-0045 B4): the verdict card's fields, derived from the store alone; a viewer's carry no evidence text
        view.update(build_verdict(
            inc, next((c for c in CLASSES if c.name == inc.incident_class), None), app_ctx.store.list_evidence(incident_id),
            [e for a in app_ctx.store.list_for(incident_id) if a.event == "incident.recorded"
             for e in (a.detail or {}).get("cited") or []],
            {str(t.ref): [str(d) for d in t.depends_on] for t in app_ctx.inventory.targets()}, operator))
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
        if p.role not in ("operator", "approver"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "the incident overlay uses evidence: operator or approver")
        inc = app_ctx.store.get_incident(incident_id)
        if inc is None:
            raise HTTPException(404, "not found")
        return app_ctx.topology.view_for(inc)

    @api.get("/api/v1/incidents/{incident_id}/metrics", tags=["incidents"])
    def incident_metrics(incident_id: str, p: Annotated[Principal, Depends(current)],
                         rng: Annotated[Literal["15m", "30m", "1h"], Query(alias="range")] = "30m"):
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
