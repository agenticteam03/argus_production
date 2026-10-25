"""Frozen-row action execution, usable only with an injected fake gateway in Phase 18.

The dispatcher has no model, prompt, or harness dependency.  No production
wiring constructs it while the policy's write gate is empty.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import uuid4

from argus.actions.remediation import FrozenProposal, RemediationRefused, verify_frozen_proposal


class ActionRows(Protocol):
    def get_action_approval(self, approval_id: str) -> dict | None: ...
    def get_action_proposal(self, proposal_id: str) -> FrozenProposal | None: ...
    def get_resume_intent(self, approval_id: str) -> dict | None: ...
    def get_action_for_approval(self, approval_id: str) -> dict | None: ...
    def get_action(self, action_id: str) -> dict | None: ...
    def reserve_action(self, action_id: str, proposal_id: str, approval_id: str, target: str,
                       at: datetime, *, daily_host_cap: int) -> bool: ...
    def finish_action(self, action_id: str, state: str, at: datetime, evidence: dict) -> bool: ...
    def active_target_holds(self, target: str, at: datetime) -> list[str]: ...
    def add_action_outcome(self, action_id: str, incident_id: str, origin: str,
                           outcome: str, body: dict, at: datetime) -> None: ...
    def get_action_outcome(self, action_id: str) -> dict | None: ...


class JournaledGateway(Protocol):
    def dispatch(self, action_id: str, proposal: FrozenProposal) -> str: ...
    def status(self, action_id: str) -> str | None: ...


@dataclass(frozen=True)
class Precheck:
    target_identity: dict[str, str]
    inventory_version: str
    policy_version: str
    evidence_version: str
    observed_at: datetime
    incident_open: bool
    class_detected: bool
    action_preconditions_met: bool
    host_lease_clear: bool


@dataclass(frozen=True)
class Verification:
    sampled_at: datetime
    detector_cleared: bool
    signal: str
    target: str
    actual: str


class ActionExecutor:
    """Claims before dispatch and reconciles by ID, without a blind retry."""

    def __init__(self, rows: ActionRows, gateway: JournaledGateway, *, gate_open: frozenset[tuple[str, str]],
                 daily_host_cap: int):
        self.rows, self.gateway = rows, gateway
        self.gate_open, self.daily_host_cap = gate_open, daily_host_cap

    def _frozen(self, approval_id: str, at: datetime) -> FrozenProposal:
        approval = self.rows.get_action_approval(approval_id)
        intent = self.rows.get_resume_intent(approval_id)
        if not approval or approval["state"] != "approved" or not approval["actor"]:
            raise RemediationRefused("there is no human-approved action")
        if not intent or intent["decision"] != "approved":
            raise RemediationRefused("approved resume intent is missing")
        proposal = self.rows.get_action_proposal(approval["proposal_id"])
        if proposal is None:
            raise RemediationRefused("frozen proposal is missing")
        verify_frozen_proposal(proposal)
        if approval["proposal_digest"] != proposal.digest:
            raise RemediationRefused("approval does not bind the frozen proposal")
        if at >= proposal.expires_at:
            raise RemediationRefused("proposal expired")
        return proposal

    def validate_precheck(self, approval_id: str, proposal: FrozenProposal, check: Precheck,
                          *, at: datetime) -> None:
        approval = self.rows.get_action_approval(approval_id)
        data = proposal.input
        if (data.capability, data.target) not in self.gate_open:
            raise RemediationRefused("write gate is closed")
        if not check.incident_open or not check.class_detected or not check.action_preconditions_met:
            raise RemediationRefused("incident, detector or action precondition changed")
        if not check.host_lease_clear:
            raise RemediationRefused("host lease is held")
        if (self.rows.active_target_holds(data.target, at) or self.rows.active_target_holds("*", at)
                or self.rows.active_target_holds(data.target.split("/", 1)[0], at)):
            raise RemediationRefused("an active hold prevents action")
        if check.target_identity != data.target_identity:
            raise RemediationRefused("target identity changed")
        if (check.inventory_version != data.inventory_version or check.policy_version != data.policy_version
                or check.evidence_version != data.evidence_version):
            raise RemediationRefused("reviewed inventory, policy or evidence version changed")
        requested_at = approval["requested_at"]
        if isinstance(requested_at, str):
            requested_at = datetime.fromisoformat(requested_at)
        if (check.observed_at.tzinfo is None or check.observed_at < requested_at
                or abs((at - check.observed_at).total_seconds()) > 30):
            raise RemediationRefused("precheck observation is not current")

    def execute(self, approval_id: str, check: Precheck, *, at: datetime) -> dict:
        existing = self.rows.get_action_for_approval(approval_id)
        if existing:
            return self.reconcile(existing["id"], at=at)
        proposal = self._frozen(approval_id, at)
        self.validate_precheck(approval_id, proposal, check, at=at)
        data = proposal.input
        action_id = f"act_{uuid4().hex}"
        if not self.rows.reserve_action(action_id, proposal.id, approval_id, data.target, at,
                                        daily_host_cap=self.daily_host_cap):
            raise RemediationRefused("target lock, cooldown, daily cap or approval was already used")
        try:
            reported = self.gateway.dispatch(action_id, proposal)
        except Exception:
            reported = None
        try:
            status = reported if reported in ("confirmed", "failed") else self.gateway.status(action_id)
        except Exception:
            status = None
        state = status if status in ("confirmed", "failed") else "indeterminate"
        self.rows.finish_action(action_id, state, at, {"gateway_status": status or "unknown"})
        return self.rows.get_action_for_approval(approval_id) or {"id": action_id, "state": state}

    def reconcile(self, action_id: str, *, at: datetime) -> dict:
        """A crashed attempt may be queried by ID. It is never sent again."""
        action = self.rows.get_action(action_id)
        if action is None:
            raise RemediationRefused("action ID is missing")
        if action["state"] != "attempting":
            return action
        status = self.gateway.status(action_id)
        state = status if status in ("confirmed", "failed") else "indeterminate"
        self.rows.finish_action(action_id, state, at, {"gateway_status": status or "unknown",
                                                       "reconciled": True})
        return self.rows.get_action(action_id)

    def verify(self, action_id: str, sample: Verification, *, at: datetime, origin: str = "drill") -> str:
        existing = self.rows.get_action_outcome(action_id)
        if existing:
            return existing["outcome"]
        action = self.rows.get_action(action_id)
        if not action or action["state"] != "confirmed" or not action["result_at"]:
            raise RemediationRefused("only confirmed actions can be verified")
        proposal = self.rows.get_action_proposal(action["proposal_id"])
        verify_frozen_proposal(proposal)
        prediction = proposal.input.prediction
        completed = action["result_at"]
        if isinstance(completed, str):
            completed = datetime.fromisoformat(completed)
        if sample.sampled_at <= completed:
            raise RemediationRefused("verification sample predates action completion")
        in_window = (sample.sampled_at - completed).total_seconds() <= prediction.within_seconds
        met = (in_window and sample.detector_cleared and sample.signal == prediction.signal
               and sample.target == prediction.target and sample.actual == prediction.expected)
        outcome = "recovered_verified" if met else "action_failed"
        self.rows.add_action_outcome(action_id, proposal.input.incident_id, origin, outcome,
                                     {"prediction_met": met, "sampled_at": sample.sampled_at.isoformat(),
                                      "signal": sample.signal, "target": sample.target, "actual": sample.actual,
                                      "detector_cleared": sample.detector_cleared}, at)
        return outcome
