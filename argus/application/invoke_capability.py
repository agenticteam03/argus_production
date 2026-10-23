"""InvokeCapability — the single guarded entry point to every capability (v1.8 §12.4).

resolve → validate → budget → audit requested → policy → execute → redact → store evidence →
audit result → return. Nothing else calls the catalogue (enforced by tests/test_boundaries.py).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import ValidationError

from argus.domain.minimize import minimize
from argus.domain.model import (AuditRecord, EvidenceRecord, EvidenceRef, Incident, Observation,
                                TargetRef, utcnow)
from argus.policy.engine import PolicyEngine
from argus.ports.ports import AuditSinkPort, IncidentMemoryPort, InventoryPort


class ToolCatalogue(Protocol):
    def list(self) -> list[Any]: ...
    def spec(self, name: str) -> Any: ...
    def call(self, spec: Any, args: Any, target: TargetRef) -> Observation: ...


@dataclass
class InvocationContext:
    incident: Incident
    caller: str                                   # "model", "strategy:<name>", principal id
    scope: set[TargetRef]
    counters: dict[str, int] = field(default_factory=dict)


class InvokeCapability:
    def __init__(self, catalogue: ToolCatalogue, policy: PolicyEngine, inventory: InventoryPort,
                 memory: IncidentMemoryPort, audit: AuditSinkPort, redactor: Any):
        # redactor is injected by wiring (duck-typed: .text(str), .value(obj)); application never imports capabilities
        self.catalogue, self.policy, self.inventory = catalogue, policy, inventory
        self.memory, self.audit, self.redactor = memory, audit, redactor

    def _audit(self, ctx: InvocationContext, category: str, event: str, **kw) -> None:
        self.audit.append(AuditRecord(audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=ctx.incident.id,
                                      at=utcnow(), category=category, event=event, actor=ctx.caller,
                                      policy_version=self.policy.version, **kw))

    def _refused(self, ctx, name: str, target: TargetRef | None, category: str, text: str) -> Observation:
        tgt = target or ctx.incident.target
        return Observation(observation_id=f"obs_{uuid.uuid4().hex[:16]}", status="refused", capability=name,
                           target=tgt, host=tgt.host, executor="none", collected_at=utcnow(),
                           error_category=category, model_text=f"REFUSED {name}: {text}")

    def _store(self, ctx: InvocationContext, obs: Observation) -> EvidenceRef:
        rec = EvidenceRecord(evidence_id=obs.observation_id, incident_id=ctx.incident.id, kind="observation",
                             capability=obs.capability, target=str(obs.target), host=obs.host,
                             executor=obs.executor, caller=ctx.caller, source_time=obs.source_time,
                             collected_at=obs.collected_at, status=obs.status,
                             values={"values": obs.values, "units": obs.units, "identities": obs.identities,
                                     "coverage": obs.coverage, "error_category": obs.error_category,
                                     "duration_ms": obs.duration_ms},
                             model_text=obs.model_text, partial=obs.partial, truncated=obs.truncated,
                             redactions=obs.redactions).with_hash()
        self.memory.append_evidence(rec)
        return EvidenceRef(evidence_id=rec.evidence_id, sha256=rec.sha256, capability=rec.capability,
                           status=rec.status, model_text=rec.model_text, target=rec.target, kind=rec.kind)

    def __call__(self, ctx: InvocationContext, name: str, arguments: dict[str, Any]) -> tuple[Observation, EvidenceRef | None]:
        arguments = dict(arguments or {})
        # 1. resolve
        spec = self.catalogue.spec(name)
        if spec is None or getattr(spec, "permission", "read") != "read":
            self._audit(ctx, "security", "security.unknown_or_write_capability", capability=name, arguments=arguments)
            return self._finish(ctx, self._refused(ctx, name, None, "forbidden", "unknown or non-read capability"))
        # 2. validate target and arguments
        raw_target = arguments.pop("target", None)
        try:
            target = TargetRef.parse(str(raw_target))
        except ValueError as e:
            self._audit(ctx, "tool", "tool.refused", capability=spec.name, policy_rule="validation", detail={"error": str(e)})
            return self._finish(ctx, self._refused(ctx, spec.name, None, "invalid_args", f"bad target: {e}"))
        if target.kind not in spec.target_kinds or self.inventory.target(target) is None:
            self._audit(ctx, "tool", "tool.refused", capability=spec.name, policy_rule="inventory",
                        detail={"target": str(target)})
            return self._finish(ctx, self._refused(ctx, spec.name, target, "out_of_scope",
                                                   f"{target} is not an inventory target of kind {sorted(spec.target_kinds)}"))
        try:
            args = spec.args_model.model_validate(arguments)
        except ValidationError as e:
            self._audit(ctx, "tool", "tool.refused", capability=spec.name, policy_rule="validation",
                        detail={"error": e.errors(include_url=False)[:3]})
            return self._finish(ctx, self._refused(ctx, spec.name, target, "invalid_args", str(e.errors()[0]["msg"])))
        # 3–5. audit requested, then policy (after a concrete capability + arguments, before execution)
        red_args, _ = self.redactor.value(arguments)
        self._audit(ctx, "tool", "tool.requested", capability=spec.name,
                    arguments={"target": str(target), **red_args})
        decision = self.policy.check(capability=spec.name, level=spec.level, safety_class=spec.safety_class,
                                     target=target, incident_scope=ctx.scope,
                                     used_in_incident=ctx.counters.get(spec.name, 0), arguments=args.model_dump())
        if not decision.allowed:
            self._audit(ctx, "tool", "tool.refused", capability=spec.name, policy_rule=decision.rule,
                        detail={"reason": decision.reason, "target": str(target)})
            return self._finish(ctx, self._refused(ctx, spec.name, target, "out_of_scope"
                                                   if decision.rule == "incident_scope" else "forbidden", decision.reason))
        ctx.counters[spec.name] = ctx.counters.get(spec.name, 0) + 1
        if getattr(spec, "max_subcalls", 0):
            # §12.7: a combined capability runs here, its sub-reads back through this entry point (never an executor)
            return self._finish(ctx, self._combined(ctx, spec, args, target), completed=True)
        # 6–7. execute through the catalogue (redaction happens in the dispatcher and again here)
        obs = self.catalogue.call(spec, args, target)
        text, n = self.redactor.text(obs.model_text)
        obs = obs.model_copy(update={"model_text": text, "redactions": obs.redactions + n})
        return self._finish(ctx, obs, completed=True)

    def _combined(self, ctx: InvocationContext, spec: Any, args: Any, target: TargetRef) -> Observation:
        sub = _SubInvoker(self, ctx, spec)
        base = dict(observation_id=f"obs_{uuid.uuid4().hex[:16]}", capability=spec.name, target=target,
                    host=target.host, executor=spec.executor, collected_at=utcnow())
        try:
            res = spec.impl(args, target, self.inventory.target(target), sub)
        except Exception as e:                    # a combined capability's own fault: an error, never a crash
            return Observation(**base, status="error", error_category="internal", values=sub._values(),
                               model_text=f"{spec.name} on {target}: error ({type(e).__name__})")
        text, n = self.redactor.text(res.model_text)
        values, dropped = {**(res.values or {}), **sub._values()}, []
        if getattr(spec, "allowed_fields", None) is not None:      # ACR-0028
            values, dropped = minimize(values, spec.allowed_fields)
        return Observation(**base, status=res.status, error_category=res.error_category,
                           values=values, units=res.units,
                           source_time=res.source_time, partial=res.partial, coverage=res.coverage,
                           model_text=text, redactions=n, dropped_fields=dropped)

    def _finish(self, ctx: InvocationContext, obs: Observation, completed: bool = False):
        # 8. evidence first, 9. then the audit record that references it
        ref = self._store(ctx, obs)
        event = "tool.completed" if obs.status == "ok" else ("tool.failed" if completed else "tool.refused_recorded")
        try:
            detail = {"status": obs.status, "error_category": obs.error_category}
            if obs.dropped_fields:                 # ACR-0028: a gateway that grows a field is visible here
                detail["dropped_fields"] = obs.dropped_fields
            self._audit(ctx, "tool", event, capability=obs.capability, evidence_id=ref.evidence_id, detail=detail)
        except Exception:
            # Audit failure: the observation is discarded (never used without its audit record).
            return self._refused(ctx, obs.capability, obs.target, "internal", "audit unavailable"), None
        return obs, ref


class _SubInvoker:
    """§12.7: what a combined capability's impl gets instead of an executor client: `read` only, bound to this incident,
    with the caller `capability:<name>`; the incident's counters are shared (max_per_incident still holds)."""

    def __init__(self, invoke: InvokeCapability, ctx: InvocationContext, spec: Any):
        self._invoke, self._spec, self._n, self._refs = invoke, spec, 0, []
        self._ctx = InvocationContext(incident=ctx.incident, caller=f"capability:{spec.name}", scope=ctx.scope,
                                      counters=ctx.counters)

    def _refuse(self, name: str, target: TargetRef, rule: str, text: str):
        inv = self._invoke
        inv._audit(self._ctx, "tool", "tool.refused", capability=name, policy_rule=rule,
                   detail={"reason": text, "target": str(target), "combined": self._spec.name})
        obs, ref = inv._finish(self._ctx, inv._refused(self._ctx, name, target, "forbidden", text))
        if ref:
            self._refs.append(ref)
        return obs, ref

    def read(self, name: str, target: TargetRef, arguments: dict[str, Any] | None = None):
        self._n += 1
        if self._n > self._spec.max_subcalls:
            return self._refuse(name, target, "max_subcalls",
                                f"{self._spec.name} may read {self._spec.max_subcalls} times")
        sub = self._invoke.catalogue.spec(name)
        if sub is not None and getattr(sub, "max_subcalls", 0):
            return self._refuse(name, target, "nested_combined", "a combined capability cannot call another one")
        obs, ref = self._invoke(self._ctx, name, {"target": str(target), **(arguments or {})})
        if ref:
            self._refs.append(ref)
        return obs, ref

    def _values(self) -> dict[str, Any]:
        return {"subcalls": [r.evidence_id for r in self._refs],
                "subcall_refs": [r.model_dump(mode="json") for r in self._refs]}


def refs_of(obs: Observation, ref: EvidenceRef | None) -> list[EvidenceRef]:
    """The evidence a runner keeps for one call: a combined capability's sub-reads first (the model can cite them; the
    graph runner's counters count them, OP-012), then the call's own record."""
    if ref is None:
        return []
    subs = obs.values.get("subcall_refs") if isinstance(obs.values, dict) else None
    return [EvidenceRef.model_validate(r) for r in subs or []] + [ref]
