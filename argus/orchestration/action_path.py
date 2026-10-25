"""Phase 18 opt-in LangGraph action branch, exercised with a fake gateway only."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from argus.actions.execution import ActionExecutor, Precheck, Verification
from argus.actions.remediation import (FrozenProposal, JudgeResult, ProposalInput, RemediationRefused,
                                       freeze_proposal, judge_proposal, verify_frozen_proposal)
from argus.domain.model import IncidentOutcome, TargetRef


class OfflineActionPath:
    """The graph keeps only row IDs; every continuation re-reads durable rows.

    All callbacks are injected by a test or an offline evaluation. The production
    wiring deliberately never constructs this class in Phase 18.
    """

    def __init__(self, *, rows, action_policy, inventory, proposer: Callable,
                 judge_model: Callable[[dict], dict], judge_model_id: str,
                 judge_context: Callable[[FrozenProposal], dict], snapshot: Callable[[FrozenProposal, datetime], Precheck],
                 sample: Callable[[str, datetime], Verification | None], gateway,
                 gate_open: frozenset[tuple[str, str]], daily_host_cap: int,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
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
            if not isinstance(value, int) or isinstance(value, bool) or not bounds["min"] <= value <= bounds["max"]:
                raise RemediationRefused("action argument is outside the reviewed bounds")
        proposal = freeze_proposal(proposal_input, at=self.clock())
        self.rows.add_action_proposal(proposal)
        return proposal.id

    def judge(self, proposal_id: str) -> JudgeResult:
        existing = self.rows.get_judge_verdict(proposal_id)
        if existing:
            return JudgeResult(**{key: existing[key] for key in (
                "verdict", "checks", "reasons", "risk", "proposal_digest")})
        proposal = self.rows.get_action_proposal(proposal_id)
        verify_frozen_proposal(proposal)
        context = self.judge_context(proposal)
        result = judge_proposal(proposal, self.judge_model, initial_risk=context["initial_risk"],
                                evidence_extracts=context["evidence_extracts"],
                                ground_extracts=context["ground_extracts"],
                                service_card=context["service_card"], action_card=context["action_card"])
        self.rows.add_judge_verdict(proposal_id, self.judge_model_id,
                                    {**asdict(result), "reasons": list(result.reasons)}, self.clock())
        return result

    def request(self, proposal_id: str) -> str | None:
        existing = self.rows.get_action_approval_for_proposal(proposal_id)
        if existing:
            return existing["id"]
        proposal = self.rows.get_action_proposal(proposal_id)
        verify_frozen_proposal(proposal)
        verdict = self.rows.get_judge_verdict(proposal_id)
        if (not verdict or verdict["proposal_digest"] != proposal.digest or verdict["verdict"] != "agree"
                or verdict["risk"] == "forbidden" or self.clock() >= proposal.expires_at):
            return None
        if (proposal.input.capability, proposal.input.target) not in self.executor.gate_open:
            return None
        approval_id = f"appr_{uuid4().hex}"
        self.rows.add_action_approval(approval_id, proposal.id, proposal.digest, self.clock(), proposal.expires_at)
        return approval_id

    def answer(self, approval_id: str, *, digest: str, principal: str, principal_kind: str,
               decision: str) -> bool:
        """Offline only; the Phase 19 private route must add permission and step-up checks."""
        if principal_kind != "human" or not principal:
            raise RemediationRefused("a human principal is required")
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
