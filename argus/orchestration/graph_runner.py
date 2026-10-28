"""The fixed safety skeleton (v1.8 §10.1) as a LangGraph graph with a checkpointer (T-0013, Phase 9 first slice).

detect → (record | evidence_pack → record | recall → investigate ⇄ act → record). Same nodes, run events, audit
and outcomes as SkeletonRunner (the plain runner, kept as the rollback: ARGUS_RUNNER=plain). The graph state is
plain JSON, checkpointed after every node per incident (thread_id = incident id), so an interrupted investigation
resumes after the last completed graph step. act and evidence_pack make ONE read per graph step, so a crash never
repeats a completed read (only the read that was interrupted runs again).
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from argus.application.invoke_capability import InvocationContext, refs_of
from argus.detectors.classes import CLASSES, classes_for
from argus.domain.model import (Conclude, EvidenceRef, Escalate, Incident, IncidentOutcome, IncidentStatus, TargetRef,
                                InvalidDecision, Passage, RequestKind, UseReadTools)
from argus.orchestration.runner import ClaimLost, SkeletonRunner, allowed_values
from argus.orchestration.strategies import EvidencePackStrategy, evidence_pack_plan
from argus.orchestration.view import InvestigationView
from argus.ports.ports import MetricsUnavailable, StaleMetrics

log = logging.getLogger("argus.graph")

_DECISIONS = {"use_read_tools": UseReadTools, "conclude": Conclude, "escalate": Escalate, "invalid": InvalidDecision}
_PACK_STEPS = 2


class RunState(TypedDict, total=False):
    incident_id: str
    route: str                    # the next node, chosen by the node that just ran
    evidence: list[dict]          # EvidenceRef, JSON
    decisions: list[dict]         # decisions so far, JSON (discriminated by "kind")
    notes: list[str]
    down: dict[str, str]          # "executor@host" -> error category
    passages: list[dict]          # Passage, JSON
    class_name: str | None
    detector_findings: list[str]  # the matched detector's findings (recall query)
    step: int
    max_steps: int
    pending: list[dict]           # the read calls the last decision asked for
    pack_outcome: str             # outcome carried through evidence_pack
    pack_started: bool            # evidence_pack already entered (its enter event was emitted)
    pack_step: int                # evidence-pack decisions taken so far
    act_open: bool                # an act batch is in progress (its enter event was emitted)
    final: dict                   # {"outcome", "status", "cited"} for record
    proposal_id: str              # phase 18: only durable row IDs cross an action checkpoint
    approval_id: str
    action_id: str


class GraphRunner(SkeletonRunner):
    """InvestigationRunner on LangGraph. Reuses SkeletonRunner's audit, evidence, scope, context and record."""

    def __init__(self, *, checkpointer: Any = None, action_path: Any = None, **kw):
        super().__init__(**kw)
        self.action_path = action_path  # no production wiring while write_gate.open is empty
        self.checkpointer = checkpointer if checkpointer is not None else InMemorySaver()
        g = StateGraph(RunState)
        for name in ("detect", "recall", "investigate", "act", "evidence_pack", "propose_action",
                     "judge_proposal", "request_approval", "await_approval", "precheck_action",
                     "execute_write", "verify", "record"):
            g.add_node(name, self._guarded(getattr(self, f"_n_{name}")))
        g.add_edge(START, "detect")
        g.add_conditional_edges("detect", _route, ["recall", "evidence_pack", "record"])
        g.add_edge("recall", "investigate")
        g.add_conditional_edges("investigate", _route, ["act", "investigate", "propose_action", "record"])
        g.add_conditional_edges("act", _route, ["act", "investigate"])           # one read per step
        g.add_conditional_edges("evidence_pack", _route, ["evidence_pack", "record"])
        g.add_conditional_edges("propose_action", _route, ["judge_proposal", "record"])
        g.add_conditional_edges("judge_proposal", _route, ["request_approval", "record"])
        g.add_conditional_edges("request_approval", _route, ["await_approval", "record"])
        g.add_conditional_edges("await_approval", _route, ["precheck_action", "record"])
        g.add_conditional_edges("precheck_action", _route, ["execute_write", "record"])
        g.add_conditional_edges("execute_write", _route, ["verify", "record"])
        g.add_edge("verify", "record")
        g.add_edge("record", END)
        self.graph = g.compile(checkpointer=self.checkpointer)

    # Graph steps outside the investigation rounds, run once per investigation:
    # detect + recall + the final investigate (it concludes or finds the budget exhausted) + record.
    # The model path is detect → recall → [investigate → act × reads] × N → investigate → record = N × (1 + reads) + 4.
    FIXED_NODES = 4
    # Slack so that a small graph change (one more node) does not hit LangGraph's ceiling before Argus's own budget.
    # Not derived from the graph: a deliberate margin, agreed in the T-0013 review (OP-006).
    SAFETY_MARGIN = 10

    @property
    def recursion_limit(self) -> int:
        """LangGraph's step ceiling, derived from Argus's own budgets (OP-006): a round costs 1 investigate step plus
        one act step per read; the largest deterministic plan (the evidence pack, 6 reads) is not capped by the read
        limit. Never below 100, the value used before OP-006."""
        largest_plan = len(evidence_pack_plan(TargetRef.parse("h/container:c")))
        per_round = 1 + max(self.max_reads_per_step, largest_plan)
        return max(100, self.max_steps_cap * per_round + self.FIXED_NODES + self.SAFETY_MARGIN)

    def _guarded(self, node):
        """OP-009: every node starts by checking the worker still owns the incident. A lost claim stops the graph
        before the node runs, so its checkpoint stays at the last completed node for the new owner."""
        def step(s: RunState) -> dict:
            self._guard()
            return node(s)
        return step

    # ------------------------------------------------------------------------------------------- entry point
    def _execute(self, incident_id: str) -> Incident:      # run() (SkeletonRunner) sets the cancel signal
        config = {"configurable": {"thread_id": incident_id}, "recursion_limit": self.recursion_limit}
        inc = self.memory.get_incident(incident_id)
        if inc is None:
            raise KeyError(incident_id)
        pending = self.graph.get_state(config).next
        if pending:                                   # interrupted earlier: continue after the last checkpoint
            self._audit(inc, "incident", "incident.resumed", actor=inc.principal, detail={"next": list(pending)})
            payload = Command(resume={}) if any(task.interrupts for task in self.graph.get_state(config).tasks) else None
        else:
            inc.status = IncidentStatus.running
            self.memory.update_incident(inc)
            self._audit(inc, "incident", "incident.started", actor=inc.principal,
                        detail={"target": str(inc.target), "trigger": inc.trigger_kind, "request": inc.request_kind})
            payload = {"incident_id": incident_id, "route": "", "evidence": [], "decisions": [], "notes": [],
                       "down": {}, "passages": [], "class_name": None, "step": 0, "max_steps": 0, "pending": []}
        try:
            self.graph.invoke(payload, config)
        except ClaimLost:
            return self._claim_lost(incident_id)
        except Exception as e:                        # a crash is recorded, never silent
            log.exception("run failed %s", incident_id)
            inc = self.memory.get_incident(incident_id)
            inc.diagnosis = f"internal error: {type(e).__name__}: {e}"
            return self._record_crash(inc)
        return self.memory.get_incident(incident_id)

    # ------------------------------------------------------------------------------------------------ helpers
    def _inc(self, s: RunState) -> Incident:
        return self.memory.get_incident(s["incident_id"])

    @staticmethod
    def _final(outcome: IncidentOutcome, status: IncidentStatus, cited: list[str] | None = None) -> dict:
        return {"route": "record", "final": {"outcome": str(outcome), "status": str(status), "cited": cited or []}}

    @staticmethod
    def _cls(name: str | None):
        return next((c for c in CLASSES if c.name == name), None)

    def _ctx(self, inc: Incident, caller: str, evidence: list[dict]) -> InvocationContext:
        """One context per graph step, so the per-capability counters (`max_per_incident`) are rebuilt from the
        incident's evidence in the run state: every executed read, not the refused ones (OP-012). They survive a resume
        because the evidence is checkpointed."""
        counters: dict[str, int] = {}
        for e in evidence:
            if e.get("capability") and e.get("status") != "refused":
                counters[e["capability"]] = counters.get(e["capability"], 0) + 1
        return InvocationContext(incident=inc, caller=caller, scope=self.scope(inc.target), counters=counters)

    def _offered(self, cls) -> list[Any]:
        return [sp for sp in self.all_specs if sp.level <= self.max_tool_level and
                (sp.tags & cls.tool_tags or sp.level == 1)]

    def _view(self, inc, cls, s: RunState, offered, steps_left) -> InvestigationView:
        view = InvestigationView(
            incident=inc, incident_class=cls, findings=inc.findings,
            passages=[Passage.model_validate(p) for p in s.get("passages", [])],
            evidence=[EvidenceRef.model_validate(e) for e in s.get("evidence", [])],
            decisions_so_far=[_DECISIONS[d["kind"]].model_validate(d) for d in s.get("decisions", [])],
            offered_specs=offered, scope=sorted(self.scope(inc.target), key=str), steps_left=steps_left,
            max_reads_per_step=self.max_reads_per_step, notes=list(s.get("notes", [])),
            down_executors=dict(s.get("down", {})),
            allowed_values=allowed_values(self.inventory, self.scope(inc.target)))
        view.context_text = self.context(view)
        return view

    def _read(self, inc, ctx, calls: list[dict], node: str, evidence: list[dict], down: dict) -> None:
        for call in calls:
            obs, ref = self.invoke(ctx, call["name"], call["arguments"])
            evidence.extend(r.model_dump(mode="json") for r in refs_of(obs, ref))   # §12.7: sub-reads too
            if obs.error_category in ("unreachable", "timeout"):
                down[f"{obs.executor}@{obs.host}"] = obs.error_category
            self._ev(inc, node, "step", capability=obs.capability,
                     tool=self._spec_names.get(obs.capability, obs.capability), target=str(obs.target),
                     host=obs.host, executor=obs.executor, status=obs.status, error_category=obs.error_category,
                     evidence_id=ref.evidence_id if ref else None, sha256=ref.sha256 if ref else None,
                     result=obs.model_text)

    # -------------------------------------------------------------------------------------------------- nodes
    def _n_detect(self, s: RunState) -> dict:
        inc = self._inc(s)
        target = inc.target
        if self.inventory.target(target) is None:
            self._audit(inc, "access", "access.target_not_in_inventory", detail={"target": str(target)})
            inc.diagnosis = f"{target} is not in the inventory; nothing was read"
            self.memory.update_incident(inc)
            return self._final(IncidentOutcome.refused, IncidentStatus.escalated)
        scope = self.scope(target)
        evidence: list[dict] = []
        if inc.reason:
            evidence.append(self._store(inc, "reported_symptom", {"reason": inc.reason},
                                        f"reported by {inc.principal or inc.trigger_kind}: {inc.reason}",
                                        str(target), caller=inc.principal or "system").model_dump(mode="json"))
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
                self.memory.update_incident(inc)
                self._ev(inc, "detect", "exit", result="undiagnosable", findings=inc.findings, next="evidence_pack")
                return {"route": "evidence_pack", "evidence": evidence,
                        "pack_outcome": str(IncidentOutcome.undiagnosable)}
            evidence.append(self._store(inc, "metric_snapshot", {"values": snap.values},
                                        "metric snapshot: " + json.dumps(snap.values), str(target),
                                        source_time=snap.observed_at).model_dump(mode="json"))
        matched = [(c, r) for c in classes for r in [c.detector(snap)] if r.matched] if snap else []
        inc.findings = [f for c in classes for f in (c.detector(snap).findings if snap else [])]
        if not matched:
            check = inc.request_kind == RequestKind.check
            self._ev(inc, "detect", "exit", classes_considered=[c.name for c in classes],
                     signals=snap.values if snap else {}, result="no class matched", findings=inc.findings,
                     next="record" if check else "evidence_pack")
            if check:
                inc.diagnosis = "healthy: no registered incident class matches the current metrics"
                self.memory.update_incident(inc)
                return {**self._final(IncidentOutcome.no_incident, IncidentStatus.closed), "evidence": evidence}
            self._audit(inc, "incident", "incident.unsupported", detail={"findings": inc.findings})
            self.memory.update_incident(inc)
            return {"route": "evidence_pack", "evidence": evidence,
                    "pack_outcome": str(IncidentOutcome.unsupported_escalated)}
        cls, res = matched[0]
        inc.incident_class, inc.strategy = cls.name, cls.strategy
        inc.findings = [f"{cls.name}: {f}" for f in res.findings] + [f"also matched: {c.name}" for c, _ in matched[1:]]
        self.memory.update_incident(inc)
        self._audit(inc, "decision", "decision.strategy_selected", detail={"class": cls.name, "strategy": cls.strategy})
        self._ev(inc, "detect", "exit", classes_considered=[c.name for c in classes], signals=snap.values,
                 result=cls.name, family=cls.family, findings=inc.findings, strategy=cls.strategy, next="recall")
        return {"route": "recall", "evidence": evidence, "class_name": cls.name,
                "detector_findings": list(res.findings)}

    def _n_recall(self, s: RunState) -> dict:
        inc, cls = self._inc(s), self._cls(s["class_name"])
        query = f"{cls.name} {' '.join(s.get('detector_findings', []))} {inc.reason}"
        self._ev(inc, "recall", "enter", runbooks=cls.runbook_ids + cls.branch_runbook_ids)
        passages = self.knowledge.search(query, 3, cls.runbook_ids + cls.branch_runbook_ids)
        recalled = [{"runbook_id": p.runbook_id, "version": p.runbook_version, "status": p.runbook_status,
                     "section": p.section, "score": p.score,
                     "sha256": hashlib.sha256(p.text.encode()).hexdigest()} for p in passages]
        library = getattr(self.knowledge, "library_version", None)
        self._audit(inc, "incident", "recall.passages", detail={"passages": recalled, "library": library})
        self._ev(inc, "recall", "exit", passages=recalled, library=library)
        return {"route": "investigate", "passages": [p.model_dump(mode="json") for p in passages],
                "step": 0, "max_steps": min(cls.max_steps, self.max_steps_cap)}

    def _n_investigate(self, s: RunState) -> dict:
        inc, cls = self._inc(s), self._cls(s["class_name"])
        step, max_steps = s["step"], s["max_steps"]
        if step >= max_steps:
            self._audit(inc, "access", "access.budget_exhausted", detail={"steps": max_steps})
            inc.diagnosis = (inc.diagnosis or "") + f" step budget of {max_steps} exhausted; escalating with evidence"
            self.memory.update_incident(inc)
            return self._final(inc.outcome or IncidentOutcome.no_action_escalated, IncidentStatus.escalated)
        strategy = self.strategies[cls.strategy]
        caller = "model" if strategy.name == "model_loop" else f"strategy:{strategy.name}"
        view = self._view(inc, cls, s, self._offered(cls), max_steps - step)
        self._ev(inc, "investigate", "enter", step=step + 1, strategy=strategy.name, steps_left=max_steps - step)
        d = strategy.next_step(view)
        self._ev(inc, "investigate", "exit", step=step + 1, decided_by=getattr(strategy, "last_source", "rule"),
                 decision=self._summary(d))
        self._audit(inc, "decision", "decision." + getattr(d, "kind", "unknown"), actor=caller,
                    detail=json.loads(d.model_dump_json()) if hasattr(d, "model_dump_json") else {})
        if getattr(d, "hypothesis_problems", None):   # ACR-0024 §3.2, log-only until T-0047 H4: the decision stands
            self._audit(inc, "decision", "hypothesis.invalid", actor=caller,
                        detail={"step": step + 1, "decision": d.kind, "problems": d.hypothesis_problems[:10]})
        self._hypotheses(inc, step + 1, d, view.evidence)
        upd = {"step": step + 1, "decisions": [*s.get("decisions", []), d.model_dump(mode="json")]}
        if isinstance(d, InvalidDecision):
            if d.reason == "fabricated_tool":
                self._audit(inc, "security", "security.fabricated_tool", actor=caller, detail={"detail": d.detail})
            if d.reason == "provider_error":          # the adapter already retried: escalate now
                inc.diagnosis = f"model provider failed at step {step + 1} ({d.detail}); escalating with evidence"
                self.memory.update_incident(inc)
                return {**upd, **self._final(inc.outcome or IncidentOutcome.no_action_escalated,
                                             IncidentStatus.escalated)}
            return {**upd, "route": "investigate",
                    "notes": [*s.get("notes", []), f"step {step + 1} was invalid ({d.reason}): {d.detail}. Correct it."]}
        if isinstance(d, UseReadTools):
            return {**upd, "route": "act", "pending": [c.model_dump(mode="json") for c in d.calls]}
        if isinstance(d, Conclude):
            inc.diagnosis, inc.confidence, inc.root_cause_target = d.diagnosis, d.confidence, d.root_cause_target
            self.memory.update_incident(inc)
            if self.action_path is not None:
                return {**upd, "route": "propose_action",
                        "final": {"outcome": str(IncidentOutcome.diagnosed),
                                  "status": str(IncidentStatus.closed), "cited": d.evidence_ids}}
            return {**upd, **self._final(IncidentOutcome.diagnosed, IncidentStatus.closed, d.evidence_ids)}
        inc.diagnosis = d.reason                      # Escalate
        self.memory.update_incident(inc)
        return {**upd, **self._final(inc.outcome or IncidentOutcome.no_action_escalated, IncidentStatus.escalated,
                                     d.evidence_ids)}

    def _n_act(self, s: RunState) -> dict:
        """ONE read per graph step: the checkpoint after each read means a crash never repeats a completed read
        (review finding, conantkd). The node routes back to itself until the batch is done."""
        inc, cls = self._inc(s), self._cls(s["class_name"])
        strategy = self.strategies[cls.strategy]
        evidence, down, pending = list(s.get("evidence", [])), dict(s.get("down", {})), list(s.get("pending", []))
        ctx = self._ctx(inc, "model" if strategy.name == "model_loop" else f"strategy:{strategy.name}", evidence)
        if not s.get("act_open"):
            self._ev(inc, "act", "enter", calls=len(pending))
        if pending:
            self._read(inc, ctx, pending[:1], "act", evidence, down)
            pending = pending[1:]
        if pending:
            return {"route": "act", "evidence": evidence, "down": down, "pending": pending, "act_open": True}
        self._ev(inc, "act", "exit", evidence_total=len(evidence))
        return {"route": "investigate", "evidence": evidence, "down": down, "pending": [], "act_open": False}

    def _n_evidence_pack(self, s: RunState) -> dict:
        """The evidence pack, one decision or ONE read per graph step (same reason as act)."""
        inc = self._inc(s)
        if not s.get("pack_started"):
            inc.strategy, inc.outcome = "evidence_pack", IncidentOutcome(s["pack_outcome"])
            self.memory.update_incident(inc)
            self._ev(inc, "evidence_pack", "enter", reason=inc.outcome)
        evidence, down, pending = list(s.get("evidence", [])), dict(s.get("down", {})), list(s.get("pending", []))
        ctx = self._ctx(inc, "strategy:evidence_pack", evidence)
        base = {"pack_started": True, "evidence": evidence, "down": down}
        if pending:
            self._read(inc, ctx, pending[:1], "evidence_pack", evidence, down)
            return {**base, "route": "evidence_pack", "pending": pending[1:]}
        step, decisions, notes = s.get("pack_step", 0), list(s.get("decisions", [])), list(s.get("notes", []))
        if step >= _PACK_STEPS:
            self._audit(inc, "access", "access.budget_exhausted", detail={"steps": _PACK_STEPS})
            inc.diagnosis = (inc.diagnosis or "") + f" step budget of {_PACK_STEPS} exhausted; escalating with evidence"
            self.memory.update_incident(inc)
            return {**base, **self._final(inc.outcome, IncidentStatus.escalated)}
        view = self._view(inc, None, {"evidence": evidence, "decisions": decisions, "notes": notes, "down": down,
                                      "passages": []}, [], _PACK_STEPS - step)
        d = EvidencePackStrategy().next_step(view)
        decisions.append(d.model_dump(mode="json"))
        self._audit(inc, "decision", "decision." + getattr(d, "kind", "unknown"), actor=ctx.caller,
                    detail=json.loads(d.model_dump_json()) if hasattr(d, "model_dump_json") else {})
        upd = {**base, "pack_step": step + 1, "decisions": decisions}
        if isinstance(d, UseReadTools):
            return {**upd, "route": "evidence_pack", "pending": [c.model_dump(mode="json") for c in d.calls]}
        if isinstance(d, Escalate):
            self._ev(inc, "evidence_pack", "exit", evidence_total=len(evidence))
            inc.diagnosis = d.reason
            self.memory.update_incident(inc)
            return {**upd, **self._final(inc.outcome, IncidentStatus.escalated, d.evidence_ids)}
        notes.append(f"step {step + 1} was invalid ({getattr(d, 'reason', '?')}): {getattr(d, 'detail', '')}. Correct it.")
        return {**upd, "route": "evidence_pack", "notes": notes}

    # Phase 18: the same incident graph carries an offline, opt-in action branch.
    # Production never supplies action_path while policy.write_gate.open is empty.
    def _n_propose_action(self, s: RunState) -> dict:
        try:
            proposal_id = self.action_path.propose(self._inc(s), s)
        except Exception as exc:
            self._audit(self._inc(s), "decision", "decision.downgraded_to_suggestion",
                        detail={"reason": str(exc)[:200]})
            return {"route": "record"}
        return {"route": "judge_proposal", "proposal_id": proposal_id} if proposal_id else {"route": "record"}

    def _n_judge_proposal(self, s: RunState) -> dict:
        try:
            verdict = self.action_path.judge(s["proposal_id"])
        except Exception as exc:
            self._audit(self._inc(s), "decision", "judge.doubt",
                        detail={"proposal_id": s["proposal_id"], "reason": str(exc)[:200]})
            return self._held_back(s, "the judge's review failed")
        self._audit(self._inc(s), "decision", "judge.verdict",
                    detail={"proposal_id": s["proposal_id"], "verdict": verdict.verdict,
                            "reasons": list(verdict.reasons), "risk": verdict.risk})
        if verdict.verdict != "agree":
            return self._held_back(s, f"the judge answered {verdict.verdict}")   # no approval or dispatch
        return {"route": "request_approval"}

    def _n_request_approval(self, s: RunState) -> dict:
        try:
            approval_id = self.action_path.request(s["proposal_id"])
        except Exception as exc:
            self._audit(self._inc(s), "access", "action.approval_refused",
                        detail={"proposal_id": s["proposal_id"], "reason": str(exc)[:200]})
            return self._held_back(s, "the approval request was refused")
        if not approval_id:
            return self._held_back(s, "the approval request was refused")
        return {"route": "await_approval", "approval_id": approval_id}

    def _held_back(self, s: RunState, why: str) -> dict:
        """The cause is found but its proposed action stopped before an approval: the problem is still there, so the
        incident goes to a person instead of closing. It keeps its diagnosis, which now says why nothing was sent."""
        inc = self._inc(s)
        inc.diagnosis = f"{inc.diagnosis or ''} The proposed action was not sent for approval: {why}.".strip()
        self.memory.update_incident(inc)
        notify = getattr(self.action_path, "held_back", None)
        if notify is not None:
            notify(inc.id)
        return self._final(IncidentOutcome.diagnosed, IncidentStatus.escalated, s["final"]["cited"])

    def _n_await_approval(self, s: RunState) -> dict:
        approval_id = s["approval_id"]
        state = self.action_path.approval_state(approval_id)
        if state == "pending":
            interrupt({"approval_id": approval_id, "proposal_id": s["proposal_id"]})
            state = self.action_path.approval_state(approval_id)  # a resume payload is never an answer
        if state == "approved":
            return {"route": "precheck_action"}
        if state in ("denied", "expired", "cancelled"):
            outcome = IncidentOutcome.expired if state == "expired" else IncidentOutcome.denied
            return {**self._final(outcome, IncidentStatus.escalated, s["final"]["cited"])}
        # A wakeup with no durable human answer pauses again.
        interrupt({"approval_id": approval_id, "proposal_id": s["proposal_id"]})
        return {"route": "await_approval"}

    def _n_precheck_action(self, s: RunState) -> dict:
        try:
            self.action_path.precheck(s["approval_id"])
        except Exception as exc:
            self._audit(self._inc(s), "access", "action.precheck_refused",
                        detail={"approval_id": s["approval_id"], "reason": str(exc)[:200]})
            return {**self._final(IncidentOutcome.no_action_escalated, IncidentStatus.escalated,
                                  s["final"]["cited"])}
        return {"route": "execute_write"}

    def _n_execute_write(self, s: RunState) -> dict:
        # This service reads frozen database rows again and makes its own fresh precheck.
        try:
            action = self.action_path.execute(s["approval_id"])
        except Exception as exc:
            self._audit(self._inc(s), "access", "action.execution_refused",
                        detail={"approval_id": s["approval_id"], "reason": str(exc)[:200]})
            return self._final(IncidentOutcome.no_action_escalated, IncidentStatus.escalated, s["final"]["cited"])
        # the operator's approved action, on the incident's own audit (the approval row says who answered)
        self._audit(self._inc(s), "decision", "action.executed",
                    detail={**self._approved(s["approval_id"]), "action_id": action["id"], "state": action["state"]})
        if action["state"] == "confirmed":
            return {"route": "verify", "action_id": action["id"]}
        outcome = (IncidentOutcome.action_failed if action["state"] == "failed"
                   else IncidentOutcome.indeterminate_escalated)
        return {**self._final(outcome, IncidentStatus.escalated, s["final"]["cited"]),
                "action_id": action["id"]}

    def _n_verify(self, s: RunState) -> dict:
        try:
            outcome = self.action_path.verify(s["action_id"])
        except Exception as exc:
            self._audit(self._inc(s), "incident", "action.verification_failed",
                        detail={"action_id": s["action_id"], "reason": str(exc)[:200]})
            outcome = "indeterminate_escalated"
        if outcome is None:
            interrupt({"action_id": s["action_id"], "waiting_for": "fresh_verification_sample"})
            try:
                outcome = self.action_path.verify(s["action_id"])
            except Exception:
                outcome = "indeterminate_escalated"
        if outcome not in ("recovered_verified", "action_failed"):
            outcome = "indeterminate_escalated"
        status = IncidentStatus.closed if outcome == "recovered_verified" else IncidentStatus.escalated
        self._audit(self._inc(s), "decision", "action.verified", detail={"action_id": s["action_id"], "outcome": outcome})
        return self._final(IncidentOutcome(outcome), status, s["final"]["cited"])

    def _approved(self, approval_id: str) -> dict:
        try:
            return self.action_path.approved_action(approval_id)
        except Exception:                                  # the audit line never stops the action branch
            return {"approval_id": approval_id}

    def _n_record(self, s: RunState) -> dict:
        f = s["final"]
        self._record(self._inc(s), IncidentOutcome(f["outcome"]), IncidentStatus(f["status"]), cited=f["cited"])
        return {"route": "end"}


def _route(s: RunState) -> str:
    return s["route"]
