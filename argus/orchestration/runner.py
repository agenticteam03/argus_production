"""The fixed safety skeleton (v1.8 §10.1), lab variant without LangGraph (v1.8-lab §4).

detect → (evidence_pack | recall → investigate loop) → record. Implements InvestigationRunner.
Every read goes through InvokeCapability; strategies only return decisions.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import uuid
from contextvars import ContextVar
from typing import Any

from argus.application.invoke_capability import InvocationContext, InvokeCapability, refs_of
from argus.detectors.classes import classes_for
from argus.domain.model import (AuditRecord, Conclude, EvidenceRecord, EvidenceRef, Escalate, Incident,
                                IncidentOutcome, IncidentStatus, InvalidDecision, RequestKind, TargetRef,
                                UseReadTools, utcnow)
from argus.orchestration.strategies import EvidencePackStrategy
from argus.orchestration.view import InvestigationView
from argus.ports.ports import (AuditSinkPort, IncidentMemoryPort, InventoryPort, KnowledgePort,
                               MetricsPort, MetricsUnavailable, NotificationPort, StaleMetrics)

log = logging.getLogger("argus.runner")

# OP-009: set by the worker when its claim on the running incident is lost. Per run (a context variable), so one
# runner object can serve several runs; LangGraph copies the context into the threads that run its nodes.
_CANCEL: ContextVar[threading.Event | None] = ContextVar("argus_run_cancel", default=None)


def allowed_values(inventory, scope) -> dict[str, dict[str, list]]:
    """The URLs and TCP ports the inventory allows for each target in scope (the probes' `url` and `port`)."""
    out = {}
    for t in scope:
        info = inventory.target(t)
        out[str(t)] = {"url": list(info.http_endpoints) if info else [], "port": list(info.tcp_ports) if info else []}
    return out


class ClaimLost(Exception):
    """The worker no longer owns this incident: stop at once and write nothing more (another worker resumes it)."""


class SkeletonRunner:
    def __init__(self, *, memory: IncidentMemoryPort, audit: AuditSinkPort, inventory: InventoryPort,
                 metrics: MetricsPort, knowledge: KnowledgePort, notifier: NotificationPort,
                 invoke: InvokeCapability, strategies: dict[str, Any], offered_specs: list[Any],
                 redactor: Any, policy_version: str, max_tool_level: int, max_reads_per_step: int = 1,
                 max_steps_cap: int = 10, events: Any = None):
        self.memory, self.audit, self.inventory = memory, audit, inventory
        self.metrics, self.knowledge, self.notifier = metrics, knowledge, notifier
        self.invoke, self.strategies = invoke, strategies
        self.all_specs = offered_specs
        self.redactor, self.policy_version = redactor, policy_version
        self.max_tool_level = max_tool_level
        self.max_reads_per_step, self.max_steps_cap = max_reads_per_step, max_steps_cap
        self.events = events                     # RunEventSink (telemetry); None = disabled
        self._spec_names = {s.name: s.model_name for s in offered_specs}

    def _ev(self, inc: Incident, node: str, phase: str, **data) -> None:
        if self.events is None:
            return
        try:
            self.events.append_run_event(inc.id, node, phase, json.loads(json.dumps(data, default=str)))
        except Exception:                        # telemetry may be dropped; audit may not (v1.8 §18.1)
            log.warning("run event dropped for %s/%s", inc.id, node)

    # ---------------------------------------------------------------------------------------------
    def _audit(self, inc: Incident, category: str, event: str, **kw) -> None:
        self.audit.append(AuditRecord(audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=inc.id, at=utcnow(),
                                      category=category, event=event, policy_version=self.policy_version, **kw))

    def _store(self, inc: Incident, kind: str, values: dict, text: str, target: str | None,
               source_time=None, caller: str = "system") -> EvidenceRef:
        red_values, n1 = self.redactor.value(values)
        red_text, n2 = self.redactor.text(text)
        rec = EvidenceRecord(evidence_id=f"ev_{uuid.uuid4().hex[:16]}", incident_id=inc.id, kind=kind,
                             capability=None, target=target, host=inc.target.host, executor=None, caller=caller,
                             source_time=source_time, collected_at=utcnow(), status="ok", values=red_values,
                             model_text=red_text, redactions=n1 + n2).with_hash()
        self.memory.append_evidence(rec)
        return EvidenceRef(evidence_id=rec.evidence_id, sha256=rec.sha256, capability=None, status="ok",
                           model_text=rec.model_text)

    def scope(self, target: TargetRef) -> set[TargetRef]:
        """Incident scope: the target, its inventory neighbours, and the hosts they run on."""
        members = {target, *self.inventory.neighbours(target)}
        hosts = {TargetRef(host=t.host, kind="host", name=t.host) for t in members}
        return {t for t in members | hosts if self.inventory.target(t) is not None}

    # ---------------------------------------------------------------------------------------------
    def run(self, incident_id: str, cancel: threading.Event | None = None) -> Incident:
        token = _CANCEL.set(cancel)
        try:
            return self._execute(incident_id)
        finally:
            _CANCEL.reset(token)

    def _guard(self) -> None:
        """OP-009: called between nodes and before every read; raises when the worker's claim was lost."""
        cancel = _CANCEL.get()
        if cancel is not None and cancel.is_set():
            raise ClaimLost()

    def _claim_lost(self, incident_id: str) -> Incident:
        inc = self.memory.get_incident(incident_id)
        log.warning("claim lost on %s: stopped, nothing more written", incident_id)
        self._audit(inc, "incident", "incident.claim_lost", detail={"status_left": str(inc.status)})
        return inc

    def _execute(self, incident_id: str) -> Incident:
        inc = self.memory.get_incident(incident_id)
        if inc is None:
            raise KeyError(incident_id)
        inc.status = IncidentStatus.running
        self.memory.update_incident(inc)
        self._audit(inc, "incident", "incident.started", actor=inc.principal,
                    detail={"target": str(inc.target), "trigger": inc.trigger_kind, "request": inc.request_kind})
        try:
            return self._run(inc)
        except ClaimLost:
            return self._claim_lost(inc.id)
        except Exception as e:  # a crash is recorded, never silent
            log.exception("run failed %s", inc.id)
            inc.diagnosis = f"internal error: {type(e).__name__}: {e}"
            return self._record_crash(inc)

    def _record_crash(self, inc: Incident) -> Incident:
        try:
            return self._record(inc, IncidentOutcome.no_action_escalated, IncidentStatus.escalated)
        except ClaimLost:                    # the claim went while crashing: the new owner records the outcome
            return self._claim_lost(inc.id)

    def _run(self, inc: Incident) -> Incident:
        target = inc.target
        if self.inventory.target(target) is None:
            self._audit(inc, "access", "access.target_not_in_inventory", detail={"target": str(target)})
            inc.diagnosis = f"{target} is not in the inventory; nothing was read"
            return self._record(inc, IncidentOutcome.refused, IncidentStatus.escalated)
        scope = self.scope(target)
        ctx = InvocationContext(incident=inc, caller="strategy", scope=scope)
        evidence: list[EvidenceRef] = []
        if inc.reason:
            evidence.append(self._store(inc, "reported_symptom", {"reason": inc.reason},
                                        f"reported by {inc.principal or inc.trigger_kind}: {inc.reason}",
                                        str(target), caller=inc.principal or "system"))

        # --- detect -------------------------------------------------------------------------------
        self._ev(inc, "detect", "enter", target=str(target), host=target.host, trigger=inc.trigger_kind,
                 request=inc.request_kind, scope=sorted(str(t) for t in scope))
        classes = classes_for(target.kind)
        snap = None
        if classes:
            signals = set().union(*(c.required_signals for c in classes))
            try:
                snap = self.metrics.snapshot(target, signals)
            except (StaleMetrics, MetricsUnavailable) as e:
                self._audit(inc, "incident", "incident.undiagnosable", detail={"error": str(e)})
                inc.findings = [f"metrics stale or unavailable: {e}", "see RB-014 (monitoring blind spot)"]
                self._ev(inc, "detect", "exit", result="undiagnosable", findings=inc.findings, next="evidence_pack")
                return self._evidence_pack(inc, ctx, evidence, IncidentOutcome.undiagnosable)
            evidence.append(self._store(inc, "metric_snapshot", {"values": snap.values},
                                        "metric snapshot: " + json.dumps(snap.values), str(target),
                                        source_time=snap.observed_at))
        matched = [(c, r) for c in classes for r in [c.detector(snap)] if r.matched] if snap else []
        inc.findings = [f for c in classes for f in (c.detector(snap).findings if snap else [])]
        if not matched:
            self._ev(inc, "detect", "exit", classes_considered=[c.name for c in classes],
                     signals=snap.values if snap else {}, result="no class matched", findings=inc.findings,
                     next="record" if inc.request_kind == RequestKind.check else "evidence_pack")
            if inc.request_kind == RequestKind.check:
                inc.diagnosis = "healthy: no registered incident class matches the current metrics"
                return self._record(inc, IncidentOutcome.no_incident, IncidentStatus.closed)
            self._audit(inc, "incident", "incident.unsupported", detail={"findings": inc.findings})
            return self._evidence_pack(inc, ctx, evidence, IncidentOutcome.unsupported_escalated)

        cls, res = matched[0]
        inc.incident_class, inc.strategy = cls.name, cls.strategy
        inc.findings = [f"{cls.name}: {f}" for f in res.findings] + [f"also matched: {c.name}" for c, _ in matched[1:]]
        self.memory.update_incident(inc)
        self._audit(inc, "decision", "decision.strategy_selected", detail={"class": cls.name, "strategy": cls.strategy})
        self._ev(inc, "detect", "exit", classes_considered=[c.name for c in classes], signals=snap.values,
                 result=cls.name, family=cls.family, findings=inc.findings, strategy=cls.strategy, next="recall")

        # --- recall ---------------------------------------------------------------------------------
        query = f"{cls.name} {' '.join(res.findings)} {inc.reason}"
        self._ev(inc, "recall", "enter", runbooks=cls.runbook_ids + cls.branch_runbook_ids)
        passages = self.knowledge.search(query, 3, cls.runbook_ids + cls.branch_runbook_ids)
        recalled = [{"runbook_id": p.runbook_id, "version": p.runbook_version, "status": p.runbook_status,
                     "section": p.section, "score": p.score,
                     "sha256": hashlib.sha256(p.text.encode()).hexdigest()} for p in passages]
        self._audit(inc, "incident", "recall.passages",
                    detail={"passages": recalled, "library": getattr(self.knowledge, "library_version", None)})
        self._ev(inc, "recall", "exit", passages=recalled,
                 library=getattr(self.knowledge, "library_version", None))

        # --- investigate ------------------------------------------------------------------------------
        offered = [s for s in self.all_specs if s.level <= self.max_tool_level and
                   (s.tags & cls.tool_tags or s.level == 1)]
        strategy = self.strategies[cls.strategy]
        return self._loop(inc, ctx, strategy, cls, passages, evidence, offered, min(cls.max_steps, self.max_steps_cap))

    def _loop(self, inc, ctx, strategy, cls, passages, evidence, offered, max_steps) -> Incident:
        decisions: list[Any] = []
        notes: list[str] = []
        down: dict[str, str] = {}
        ctx.caller = f"strategy:{strategy.name}" if strategy.name != "model_loop" else "model"
        pack = strategy.name == "evidence_pack"
        if pack:
            self._ev(inc, "evidence_pack", "enter", reason=inc.outcome)
        for step in range(max_steps):
            self._guard()
            view = InvestigationView(incident=inc, incident_class=cls, findings=inc.findings, passages=passages,
                                     evidence=evidence, decisions_so_far=decisions, offered_specs=offered,
                                     scope=sorted(ctx.scope, key=str), steps_left=max_steps - step,
                                     max_reads_per_step=self.max_reads_per_step, notes=notes,
                                     down_executors=down, allowed_values=allowed_values(self.inventory, ctx.scope))
            view.context_text = self.context(view)
            if not pack:
                self._ev(inc, "investigate", "enter", step=step + 1, strategy=strategy.name,
                         steps_left=max_steps - step)
            d = strategy.next_step(view)
            decisions.append(d)
            source = getattr(strategy, "last_source", "rule")
            if not pack:
                self._ev(inc, "investigate", "exit", step=step + 1, decided_by=source,
                         decision=self._summary(d))
            self._audit(inc, "decision", "decision." + getattr(d, "kind", "unknown"),
                        actor=ctx.caller, detail=json.loads(d.model_dump_json()) if hasattr(d, "model_dump_json") else {})
            if isinstance(d, InvalidDecision):
                if d.reason == "fabricated_tool":
                    self._audit(inc, "security", "security.fabricated_tool", actor=ctx.caller, detail={"detail": d.detail})
                if d.reason == "provider_error":     # the adapter already retried: escalate now, keep the budget honest
                    inc.diagnosis = f"model provider failed at step {step + 1} ({d.detail}); escalating with evidence"
                    return self._record(inc, inc.outcome or IncidentOutcome.no_action_escalated, IncidentStatus.escalated)
                notes.append(f"step {step + 1} was invalid ({d.reason}): {d.detail}. Correct it.")
                continue
            if isinstance(d, UseReadTools):
                node = "evidence_pack" if pack else "act"
                if not pack:
                    self._ev(inc, "act", "enter", calls=len(d.calls))
                for call in d.calls:
                    self._guard()
                    obs, ref = self.invoke(ctx, call.name, call.arguments)
                    evidence.extend(refs_of(obs, ref))          # §12.7: a combined call's sub-reads too
                    if obs.error_category in ("unreachable", "timeout"):
                        down[f"{obs.executor}@{obs.host}"] = obs.error_category
                    self._ev(inc, node, "step", capability=obs.capability,
                             tool=self._spec_names.get(obs.capability, obs.capability), target=str(obs.target),
                             host=obs.host, executor=obs.executor, status=obs.status,
                             error_category=obs.error_category, evidence_id=ref.evidence_id if ref else None,
                             sha256=ref.sha256 if ref else None, result=obs.model_text)
                if not pack:
                    self._ev(inc, "act", "exit", evidence_total=len(evidence))
                continue
            if isinstance(d, Conclude):
                inc.diagnosis, inc.confidence = d.diagnosis, d.confidence
                inc.root_cause_target = d.root_cause_target
                return self._record(inc, IncidentOutcome.diagnosed, IncidentStatus.closed, cited=d.evidence_ids)
            if isinstance(d, Escalate):
                if pack:
                    self._ev(inc, "evidence_pack", "exit", evidence_total=len(evidence))
                inc.diagnosis = d.reason
                outcome = inc.outcome or IncidentOutcome.no_action_escalated
                return self._record(inc, outcome, IncidentStatus.escalated, cited=d.evidence_ids)
        self._audit(inc, "access", "access.budget_exhausted", detail={"steps": max_steps})
        inc.diagnosis = (inc.diagnosis or "") + f" step budget of {max_steps} exhausted; escalating with evidence"
        return self._record(inc, inc.outcome or IncidentOutcome.no_action_escalated, IncidentStatus.escalated)

    def _evidence_pack(self, inc, ctx, evidence, outcome: IncidentOutcome) -> Incident:
        inc.strategy = "evidence_pack"
        inc.outcome = outcome                      # carried through the loop's Escalate
        self.memory.update_incident(inc)
        return self._loop(inc, ctx, EvidencePackStrategy(), None, [], evidence, [], 2)

    # ---------------------------------------------------------------------------------------------
    def context(self, view: InvestigationView) -> str:
        inc = view.incident
        parts = [f"INCIDENT {inc.id}", f"target: {inc.target} (host {inc.target.host})",
                 f"trigger: {inc.trigger_kind} / {inc.request_kind}"]
        if view.incident_class:
            parts.append(f"incident class: {view.incident_class.name} ({view.incident_class.family}); "
                         f"runbooks {', '.join(view.incident_class.runbook_ids)}")
            if view.incident_class.branch_runbook_ids:
                titles = getattr(self.knowledge, "titles", {})
                parts.append("branch runbooks (read one with query_runbook when the evidence points to its cause): "
                             + "; ".join(f"{r} {titles.get(r, '')}".strip()
                                         for r in view.incident_class.branch_runbook_ids))
        parts.append("findings: " + ("; ".join(view.findings) or "none"))
        parts.append("targets in scope: " + ", ".join(str(t) for t in view.scope))
        pinned = getattr(self.knowledge, "pinned_text", "")
        if pinned and view.incident_class:
            parts.append(f'<passage runbook="RUNBOOK-CONVENTIONS" pinned="true">\n{pinned}\n</passage>')
        for p in view.passages:
            parts.append(f'<passage runbook="{p.runbook_id}" version="{p.runbook_version}" status="{p.runbook_status}" '
                         f'section="{p.section}">\n{p.text}\n</passage>')
        bodies = {r.evidence_id: r for r in self.memory.get_evidence([e.evidence_id for e in view.evidence[-4:]])}
        for e in view.evidence:
            rec = bodies.get(e.evidence_id)
            if rec is None:
                parts.append(f'<evidence id="{e.evidence_id}" status="{e.status}">{e.model_text}</evidence>')
                continue
            body = json.dumps(rec.values, default=str)[:1800]
            parts.append(f'<evidence id="{rec.evidence_id}" kind="{rec.kind}" capability="{rec.capability}" '
                         f'source="{rec.executor}@{rec.host}" collected_at="{rec.collected_at.isoformat()}" '
                         f'source_time="{rec.source_time.isoformat() if rec.source_time else "unknown"}" '
                         f'status="{rec.status}" partial="{rec.partial}">\n{rec.model_text}\n{body}\n</evidence>')
        for ex, cat in sorted(view.down_executors.items()):
            parts.append(f"UNAVAILABLE: executor {ex} is {cat} in this incident; its tools will fail again. "
                         "Do not call them; use other evidence or escalate.")
        for n in view.notes[-3:]:
            parts.append("NOTE: " + n)
        parts.append(f"steps left: {view.steps_left}. Decide now.")
        return "\n\n".join(parts)

    def _record(self, inc: Incident, outcome: IncidentOutcome, status: IncidentStatus,
                cited: list[str] | None = None) -> Incident:
        self._guard()
        inc.outcome, inc.status, inc.closed_at = outcome, status, utcnow()
        self.memory.update_incident(inc)
        self._ev(inc, "record", "exit", outcome=outcome, status=status, incident_class=inc.incident_class,
                 root_cause_target=inc.root_cause_target, confidence=inc.confidence,
                 diagnosis=inc.diagnosis, cited=cited or [])
        self._audit(inc, "incident", "incident.recorded",
                    detail={"outcome": outcome, "status": status, "cited": cited or [],
                            "root_cause_target": inc.root_cause_target})
        if status == IncidentStatus.escalated:
            self.notifier.notify(f"{inc.id}:escalation", {"incident_id": inc.id, "target": str(inc.target),
                                                           "outcome": outcome, "diagnosis": inc.diagnosis})
        return inc


def _decision_summary(d) -> dict:
    kind = getattr(d, "kind", "unknown")
    if kind == "use_read_tools":
        return {"kind": kind, "calls": [{"capability": c.name, "arguments": c.arguments} for c in d.calls]}
    if kind == "conclude":
        return {"kind": kind, "confidence": d.confidence, "root_cause_target": d.root_cause_target,
                "evidence_ids": d.evidence_ids}
    if kind == "escalate":
        return {"kind": kind, "reason": d.reason}
    if kind == "invalid":
        return {"kind": kind, "reason": d.reason, "detail": d.detail}
    return {"kind": kind}


SkeletonRunner._summary = staticmethod(_decision_summary)
