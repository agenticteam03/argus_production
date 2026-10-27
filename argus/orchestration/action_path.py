"""The opt-in LangGraph action branch: the fake gateway (phase 18) or the reviewed HTTP client (phase 20)."""
from __future__ import annotations

import re
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from argus.actions.execution import REVIEWED_GATEWAYS, ActionExecutor, Precheck, Verification
from argus.actions.risk import RiskColor
from argus.actions.remediation import (FrozenProposal, JudgeResult, ProposalInput, RemediationRefused,
                                       agreed_verdict, freeze_proposal, judge_proposal, verify_frozen_proposal)
from argus.domain.model import EvidenceRecord, IncidentOutcome, TargetRef


class OfflineActionPath:
    """The graph keeps only row IDs; every continuation re-reads durable rows.

    All callbacks are injected (phase 20: `argus.actions.live` for the precheck and
    the verification). No production wiring constructs it while the write gate is empty.
    """

    def __init__(self, *, rows, action_policy, inventory, proposer: Callable,
                 judge_model: Callable[[dict], dict], judge_model_id: str,
                 judge_context: Callable[[FrozenProposal], dict], snapshot: Callable[[FrozenProposal, datetime], Precheck],
                 sample: Callable[[str, datetime], Verification | None], gateway,
                 gate_open: frozenset[tuple[str, str]], daily_host_cap: int,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        if not isinstance(gateway, REVIEWED_GATEWAYS):
            raise ValueError("the action path accepts only the fake gateway or the reviewed HTTP client")
        called = getattr(judge_model, "model", None)       # an adapter knows the model it calls; the stored id is it
        if called is not None and called != judge_model_id:
            raise ValueError("judge_model_id must name the model the judge calls")
        self.rows, self.action_policy, self.inventory = rows, action_policy, inventory
        self.proposer, self.judge_model, self.judge_model_id = proposer, judge_model, judge_model_id
        self.judge_context, self.snapshot, self.sample, self.clock = judge_context, snapshot, sample, clock
        self.executor = ActionExecutor(rows, gateway, gate_open=gate_open, daily_host_cap=daily_host_cap)

    def propose(self, incident, state: dict) -> str | None:
        existing = self.rows.latest_action_proposal_for_incident(incident.id)
        if existing:
            verify_frozen_proposal(existing)
            return existing.id if self.clock() < existing.expires_at else None
        evidence = self.rows.list_evidence(incident.id)
        recalled = {p["runbook_id"] for p in state.get("passages", []) if p.get("runbook_id")}
        diagnosed = incident.model_copy(update={"outcome": IncidentOutcome.diagnosed})
        candidates = self.action_policy.next_actions(diagnosed, evidence, recalled, self.inventory, now=self.clock())
        if not candidates:
            return None
        raw = self.proposer(incident, candidates, state)
        if raw is None:
            return None
        proposal_input = ProposalInput.model_validate(raw)
        offered = next((c for c in candidates if c["action"] == proposal_input.capability
                        and c["target"] == proposal_input.target), None)
        if not offered:
            raise RemediationRefused("action was not offered by reviewed cards and current evidence")
        if (proposal_input.root_cause != incident.root_cause_target
                or not set(proposal_input.evidence_refs).issubset(offered["evidence_refs"])
                or not set(proposal_input.grounds).issubset({"runbook:" + x for x in offered["grounds"]})):
            raise RemediationRefused("proposal cites a different cause, evidence or ground")
        card = self.action_policy.cards.get(proposal_input.capability)
        info = self.inventory.target(TargetRef.parse(proposal_input.target))
        service = info.service_card() if info is not None else None
        if (card is None or service is None or proposal_input.capability not in service.safe_actions
                or proposal_input.capability in service.never):
            raise RemediationRefused("service and action cards do not permit this action")
        if set(proposal_input.target_identity) != set(card.identity_fields):
            raise RemediationRefused("target identity fields differ from the action card")
        if set(proposal_input.arguments) - set(card.parameters):
            raise RemediationRefused("action arguments include unreviewed names")
        for name, value in proposal_input.arguments.items():
            bounds = card.parameters[name]
            if bounds.get("type") == "str":
                declared = list(getattr(info, "networks", None) or [])
                if (not isinstance(value, str) or not value
                        or ("pattern" in bounds and not re.fullmatch(bounds["pattern"], value))
                        or (bounds.get("enum_from") == "declared_networks" and value not in declared)):
                    raise RemediationRefused("action argument is outside the reviewed bounds")
            elif not isinstance(value, int) or isinstance(value, bool) or not bounds["min"] <= value <= bounds["max"]:
                raise RemediationRefused("action argument is outside the reviewed bounds")
        proposal = freeze_proposal(proposal_input, at=self.clock())
        self.rows.add_action_proposal(proposal)
        return proposal.id

    def judge(self, proposal_id: str) -> JudgeResult:
        existing = self.rows.get_judge_verdict(proposal_id)
        if existing:
            self._ensure_judge_evidence(proposal_id, existing)
            return JudgeResult(**{key: existing[key] for key in (
                "verdict", "checks", "reasons", "risk", "proposal_digest")})
        proposal = self.rows.get_action_proposal(proposal_id)
        verify_frozen_proposal(proposal)
        try:
            context = self.judge_context(proposal)
            info = self.inventory.target(TargetRef.parse(proposal.input.target))
            service = info.service_card() if info is not None else None
            if service is None:
                raise RemediationRefused("reviewed service card is unavailable")
            base = self.action_policy.risk_table.lookup(proposal.input.capability, service.kind)
            if base == RiskColor.forbidden:
                raise RemediationRefused("reviewed risk table forbids the action")
            initial_risk = base.elevate(1 if service.criticality == "high" else 0).value
        except Exception as exc:
            # A review that cannot start is still a stored `doubt` (fail closed), never a missing verdict row. A
            # forbidden cell is the exception: it is never judged and leaves no verdict (the risk table decides).
            if isinstance(exc, RemediationRefused) and "forbids" in str(exc):
                raise
            why = str(exc) if isinstance(exc, RemediationRefused) else type(exc).__name__
            body = {"verdict": "doubt", "checks": {}, "reasons": [f"the review could not start: {why}"[:200]],
                    "risk": "red", "proposal_digest": proposal.digest}
            self.rows.add_judge_verdict(proposal_id, self.judge_model_id, body, self.clock())
            self._ensure_judge_evidence(proposal_id, body)
            raise
        result = judge_proposal(proposal, self.judge_model, initial_risk=initial_risk,
                                evidence_extracts=context["evidence_extracts"],
                                ground_extracts=context["ground_extracts"],
                                service_card=context["service_card"], action_card=context["action_card"])
        body = {**asdict(result), "reasons": list(result.reasons)}
        self.rows.add_judge_verdict(proposal_id, self.judge_model_id, body, self.clock())
        self._ensure_judge_evidence(proposal_id, body)
        return result

    def _ensure_judge_evidence(self, proposal_id: str, body: dict) -> None:
        evidence_id = "ev_judge_" + proposal_id
        if self.rows.get_evidence([evidence_id]):
            return
        proposal = self.rows.get_action_proposal(proposal_id)
        at = self.clock()
        evidence = EvidenceRecord(
            evidence_id=evidence_id, incident_id=proposal.input.incident_id, kind="observation",
            capability="judge.verdict", target=proposal.input.target,
            host=TargetRef.parse(proposal.input.target).host, executor="openai-judge", caller="judge",
            source_time=at, collected_at=at, status=body["verdict"],
            values={"proposal_digest": proposal.digest, "verdict": body["verdict"],
                    "risk": body["risk"], "checks": body["checks"], "reasons": body["reasons"]},
            model_text="; ".join(body["reasons"])[:500]).with_hash()
        self.rows.append_evidence(evidence)

    def request(self, proposal_id: str) -> str | None:
        existing = self.rows.get_action_approval_for_proposal(proposal_id)
        if existing:
            return existing["id"]
        proposal = self.rows.get_action_proposal(proposal_id)
        verify_frozen_proposal(proposal)
        if not agreed_verdict(self.rows.get_judge_verdict(proposal_id), proposal) or self.clock() >= proposal.expires_at:
            return None
        if (proposal.input.capability, proposal.input.target) not in self.executor.gate_open:
            return None
        approval_id = f"appr_{uuid4().hex}"
        self.rows.add_action_approval(approval_id, proposal.id, proposal.digest, self.clock(), proposal.expires_at)
        return approval_id

    def answer(self, approval_id: str, *, digest: str, principal: str, principal_kind: str,
               decision: str, confirmation_target: str | None = None) -> bool:
        """Offline only; the Phase 19 private route must add permission and step-up checks."""
        if principal_kind != "human" or not principal:
            raise RemediationRefused("a human principal is required")
        approval = self.rows.get_action_approval(approval_id)
        if approval is None or approval["proposal_digest"] != digest:
            raise RemediationRefused("approval digest mismatch")
        proposal = self.rows.get_action_proposal(approval["proposal_id"])
        verdict = self.rows.get_judge_verdict(proposal.id)
        if decision == "approved" and not agreed_verdict(verdict, proposal):
            raise RemediationRefused("the judge did not agree with this proposal")   # fail closed: no verdict, no approval
        if decision == "approved" and verdict["risk"] == "red":
            if confirmation_target != TargetRef.parse(proposal.input.target).name:
                raise RemediationRefused("red action requires typing the target name")
        return self.rows.answer_action_approval(approval_id, digest, principal, decision, self.clock())

    def approval_state(self, approval_id: str) -> str:
        row = self.rows.get_action_approval(approval_id)
        if row is None:
            raise RemediationRefused("approval row is missing")
        expires = row["expires_at"]
        if isinstance(expires, str):
            expires = datetime.fromisoformat(expires)
        return "expired" if row["state"] == "pending" and self.clock() >= expires else row["state"]

    def precheck(self, approval_id: str) -> Precheck:
        at = self.clock()
        proposal = self.executor._frozen(approval_id, at)
        check = self.snapshot(proposal, at)
        self.executor.validate_precheck(approval_id, proposal, check, at=at)
        return check

    def execute(self, approval_id: str) -> dict:
        at = self.clock()
        proposal = self.executor._frozen(approval_id, at)
        return self.executor.execute(approval_id, self.snapshot(proposal, at), at=at)

    def verify(self, action_id: str) -> str | None:
        at = self.clock()
        old = self.rows.get_action_outcome(action_id)
        if old:
            return old["outcome"]
        sample = self.sample(action_id, at)
        return self.executor.verify(action_id, sample, at=at) if sample is not None else None
