"""HTTP inbound adapter (FastAPI): human API with JWT on the loopback listener, Alertmanager webhook
on the private listener (v1.8 §7.1, §17.3). The only FastAPI location.

No `from __future__ import annotations` here: FastAPI must resolve the local dependency closures."""

import hmac
import uuid
from datetime import timedelta
from typing import Annotated, Literal

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pwdlib import PasswordHash
from pydantic import BaseModel, ConfigDict

from argus.domain.model import Incident, Principal, RequestKind, TargetRef, TriggerKind, utcnow

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


def _principal_dep(app_ctx):
    def dep(token: Annotated[str, Depends(oauth2)]) -> Principal:
        try:
            claims = jwt.decode(token, app_ctx.jwt_key, algorithms=["HS256"], audience="argus-api")
        except jwt.PyJWTError:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token",
                                headers={"WWW-Authenticate": "Bearer"})
        row = app_ctx.store.get_principal(claims["sub"])
        if row is None or row["disabled"]:          # disabling takes effect before token expiry
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "principal disabled")
        return Principal(id=row["id"], kind=row["kind"], role=row["role"], scopes=frozenset(row["scopes"]))
    return dep


def build_api(app_ctx) -> FastAPI:
    api = FastAPI(title="Argus v1.8", version="0.2.0",
                  description="Read-only SRE diagnosis agent on two hosts (vm-095, vm-166). "
                              "Log in with **Authorize**. Targets and incidents: docs/INCIDENTS.md.")
    current = _principal_dep(app_ctx)

    def require(*roles: str):
        def dep(p: Annotated[Principal, Depends(current)]) -> Principal:
            if p.role not in roles:
                raise HTTPException(status.HTTP_403_FORBIDDEN, f"role {p.role} may not do this")
            return p
        return dep

    @api.post("/api/v1/auth/token", tags=["auth"])
    def token(form: Annotated[OAuth2PasswordRequestForm, Depends()]):
        row = app_ctx.store.get_principal(form.username)
        ok = row is not None and not row["disabled"] and hasher.verify(form.password, row["password_hash"])
        if not ok:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad credentials")
        now = utcnow()
        claims = {"sub": row["id"], "kind": row["kind"], "role": row["role"], "scopes": row["scopes"],
                  "iat": now, "exp": now + timedelta(minutes=app_ctx.settings.jwt_ttl_min),
                  "jti": uuid.uuid4().hex, "aud": "argus-api"}
        return {"access_token": jwt.encode(claims, app_ctx.jwt_key, algorithm="HS256"), "token_type": "bearer"}

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
                 "root_cause_target": i.root_cause_target} for i in app_ctx.store.list_incidents(limit)]

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
        created = []
        for a in payload.get("alerts", []):
            if a.get("status") != "firing":
                continue
            labels = a.get("labels", {})
            host, name = labels.get("argus_host"), labels.get("container") or labels.get("owner")
            if not host or not name:
                continue
            try:
                target = TargetRef(host=host, kind="container", name=name)
            except ValueError:
                continue
            key = f"alert:{a.get('fingerprint')}:{a.get('startsAt')}"
            inc = new_incident(target, TriggerKind.alert, RequestKind.report,
                               f"alert {labels.get('alertname')}: {a.get('annotations', {}).get('summary', '')}",
                               "alertmanager", key)
            inc, dup = app_ctx.store.create_incident(inc, key)
            created.append({"incident_id": inc.id, "duplicate": dup})
        return {"accepted": created}

    @hook.get("/healthz")
    def healthz():
        return {"ok": True}

    return hook
