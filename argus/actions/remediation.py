"""Offline Phase 18 supervised remediation contract.

This module has no target executor or network client.  The real write gate stays
closed; the fake gateway exists solely for failure-injection tests.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from argus.domain.model import TargetRef


class RemediationRefused(ValueError):
    """A proposal, approval or attempted action failed a deterministic guard."""


class Prediction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    signal: str = Field(min_length=1)
    target: str = Field(min_length=1)
    expected: str = Field(min_length=1)
    within_seconds: int = Field(gt=0, le=3600)


class Alternative(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(min_length=1)
    why_not: str = Field(min_length=1)


class ProposalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    incident_id: str = Field(min_length=1)
    capability: str = Field(min_length=1)
    target: str = Field(min_length=1)
    target_identity: dict[str, str]
    arguments: dict[str, object]
    root_cause: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    evidence_refs: list[str]
    grounds: list[str]
    prediction: Prediction
    alternatives: list[Alternative]
    preview: str = Field(min_length=1)
    rollback: str = Field(min_length=1)
    inventory_version: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    evidence_version: str = Field(min_length=1)


class FrozenProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    input: ProposalInput
    basis: Literal["runbook", "memory", "reference", "operator"]
    created_at: datetime
    expires_at: datetime
    digest: str


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def _basis(grounds: list[str]) -> str:
    return next(prefix for prefix in ("runbook", "memory", "reference", "operator")
                if any(ground.startswith(prefix + ":") for ground in grounds))


def _proposal_digest(data: ProposalInput, created: datetime, expires: datetime) -> str:
    return hashlib.sha256(_canonical({"input": data.model_dump(mode="json"),
                                      "basis": _basis(data.grounds),
                                      "created_at": created.isoformat(),
                                      "expires_at": expires.isoformat()})).hexdigest()


def verify_frozen_proposal(proposal: FrozenProposal) -> None:
    """Refuse a mutable nested payload even if its stored digest was left intact."""
    try:
        expected = _proposal_digest(proposal.input, proposal.created_at, proposal.expires_at)
        matches_basis = proposal.basis == _basis(proposal.input.grounds)
    except (StopIteration, TypeError, ValueError) as exc:
        raise RemediationRefused("proposal digest does not match its body") from exc
    if not matches_basis or not hmac.compare_digest(expected, proposal.digest):
        raise RemediationRefused("proposal digest does not match its body")


def freeze_proposal(data: ProposalInput, *, at: datetime) -> FrozenProposal:
    """Freeze every field shown to the approver in a stable digest."""
    if at.tzinfo is None:
        raise RemediationRefused("a timezone-aware creation time is required")
    try:
        target = TargetRef.parse(data.target)
    except ValueError as exc:
        raise RemediationRefused("invalid host-qualified action target") from exc
    if target.host == "vm-095":
        raise RemediationRefused("vm-095 is Argus's own host")
    if target.kind != "container" or not target.name.startswith("argus-lab-"):
        raise RemediationRefused("Phase 18 accepts only named lab containers")
    if not data.target_identity or not all(data.target_identity.values()):
        raise RemediationRefused("target identity is required")
    if not data.evidence_refs or not all(data.evidence_refs):
        raise RemediationRefused("cited evidence is required")
    if len(data.evidence_refs) > 20 or len(data.grounds) > 10:
        raise RemediationRefused("proposal cites too many sources")
    if not data.grounds or not all(g.startswith(("runbook:", "memory:", "reference:", "operator:"))
                                   for g in data.grounds):
        raise RemediationRefused("verified grounds are required")
    if not 1 <= len(data.alternatives) <= 3:
        raise RemediationRefused("one to three alternatives are required")
    if len(_canonical(data.model_dump(mode="json"))) > 12_000:
        raise RemediationRefused("proposal exceeds the review size limit")
    created = at.astimezone(timezone.utc)
    expires = created + timedelta(minutes=30)
    digest = _proposal_digest(data, created, expires)
    return FrozenProposal(id=f"prop_{uuid4().hex}", input=data.model_copy(deep=True), basis=_basis(data.grounds),
                          created_at=created,
                          expires_at=expires,
                          digest=digest)


_RISK = ("green", "amber", "red", "forbidden")
_JUDGE_CHECKS = frozenset({"cause_supported", "action_addresses_cause", "grounds_support_action",
                           "less_invasive_exists", "risk_understated"})


@dataclass(frozen=True)
class JudgeResult:
    verdict: Literal["agree", "doubt", "disagree"]
    checks: dict[str, bool] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()
    risk: str = "green"
    proposal_digest: str = ""

    @classmethod
    def agree(cls, digest: str) -> JudgeResult:
        return cls("agree", proposal_digest=digest)


def judge_proposal(proposal: FrozenProposal, model: Callable[[dict], dict], *, initial_risk: str,
                   evidence_extracts: dict[str, str], ground_extracts: dict[str, str],
                   service_card: dict, action_card: dict) -> JudgeResult:
    """Give a second model only frozen, bounded data; malformed output becomes doubt."""
    verify_frozen_proposal(proposal)
    if initial_risk not in _RISK:
        raise RemediationRefused("invalid risk colour")
    if set(evidence_extracts) != set(proposal.input.evidence_refs) or any(
            not value or len(value) > 500 for value in evidence_extracts.values()):
        raise RemediationRefused("bounded cited evidence extracts are required")
    if set(ground_extracts) != set(proposal.input.grounds) or any(
            not value or len(value) > 500 for value in ground_extracts.values()):
        raise RemediationRefused("bounded ground extracts are required")
    if not service_card or not action_card:
        raise RemediationRefused("reviewed service and action cards are required")
    if len(_canonical({"service_card": service_card, "action_card": action_card})) > 8_000:
        raise RemediationRefused("review cards exceed the size limit")
    packet = {"proposal_digest": proposal.digest, "proposal": proposal.input.model_dump(mode="json"),
              "evidence_extracts": evidence_extracts, "ground_extracts": ground_extracts,
              "service_card": service_card, "action_card": action_card}
    try:
        answer = model(packet)
        if not isinstance(answer, dict) or set(answer) != {"verdict", "checks", "reasons"} or answer.get(
                "verdict") not in ("agree", "doubt", "disagree"):
            raise ValueError("invalid judge verdict")
        checks, reasons = answer.get("checks"), answer.get("reasons")
        if not isinstance(checks, dict) or set(checks) != _JUDGE_CHECKS or not all(
                isinstance(v, bool) for v in checks.values()):
            raise ValueError("invalid judge checks")
        if not isinstance(reasons, list) or len(reasons) > 5 or not all(
                isinstance(r, str) and 0 < len(r.strip()) <= 300 for r in reasons):
            raise ValueError("invalid judge reasons")
        verdict = answer["verdict"]
        if verdict == "agree" and (not all(checks[k] for k in (
                "cause_supported", "action_addresses_cause", "grounds_support_action"))
                or checks["less_invasive_exists"] or checks["risk_understated"]):
            raise ValueError("agree conflicts with its checks")
        if verdict != "agree" and not reasons:
            raise ValueError("a doubt or disagreement needs a reason")
        risk = _RISK[min(3, _RISK.index(initial_risk) + (verdict == "disagree"))]
        return JudgeResult(verdict, checks, tuple(reasons), risk, proposal.digest)
    except Exception:
        return JudgeResult("doubt", reasons=("The judge did not return a valid decision.",),
                           risk=initial_risk, proposal_digest=proposal.digest)


@dataclass
class Approval:
    id: str
    proposal: FrozenProposal
    state: Literal["pending", "approved", "denied", "expired", "cancelled"] = "pending"
    actor: str | None = None


class FakeActionGateway:
    """A journaled test double; no Docker client, socket or remote route exists."""

    def __init__(self, *, ambiguous: bool = False):
        self.ambiguous = ambiguous
        self.calls: list[str] = []
        self.journal: dict[str, str] = {}

    def dispatch(self, action_id: str, proposal: FrozenProposal) -> str:
        if action_id in self.journal:
            raise RemediationRefused("action id already accepted by gateway")
        self.calls.append(action_id)
        self.journal[action_id] = "unknown" if self.ambiguous else "confirmed"
        return self.journal[action_id]

    def status(self, action_id: str) -> str | None:
        return self.journal.get(action_id)


class RemediationFlow:
    """Offline state machine for a single released-pair simulation.

    Production never instantiates this test harness.  Its nonempty gate is a
    simulation input, independent of the repository's closed policy gate.
    """

    def __init__(self, *, gateway: FakeActionGateway, gate_open: frozenset | set):
        self.gateway = gateway
        self.gate_open = frozenset(gate_open)
        self.approvals: dict[str, Approval] = {}
        self.actions: dict[str, str] = {}
        self.holds: set[str] = set()

    def hold(self, target: str) -> None:
        self.holds.add(target)

    def request_approval(self, proposal: FrozenProposal, judge: JudgeResult, *, at: datetime) -> Approval:
        verify_frozen_proposal(proposal)
        if (proposal.input.capability, proposal.input.target) not in self.gate_open:
            raise RemediationRefused("write gate is closed for this action and target")
        if judge.proposal_digest != proposal.digest:
            raise RemediationRefused("judge reviewed another proposal digest")
        if judge.verdict != "agree":
            raise RemediationRefused("judge did not agree")
        if at >= proposal.expires_at:
            raise RemediationRefused("proposal expired")
        approval = Approval(f"appr_{uuid4().hex}", proposal)
        self.approvals[approval.id] = approval
        return approval

    def answer(self, approval_id: str, *, digest: str, principal: str, principal_kind: str,
               at: datetime) -> None:
        approval = self.approvals[approval_id]
        if approval.state != "pending":
            raise RemediationRefused("approval is not pending")
        if at >= approval.proposal.expires_at:
            approval.state = "expired"
            raise RemediationRefused("approval expired")
        if digest != approval.proposal.digest:
            raise RemediationRefused("proposal digest mismatch")
        if principal_kind != "human" or not principal:
            raise RemediationRefused("a human principal is required")
        approval.state, approval.actor = "approved", principal

    def execute(self, approval_id: str, *, at: datetime, identity: dict[str, str], inventory_version: str,
                policy_version: str, evidence_version: str, incident_open: bool) -> str:
        approval = self.approvals[approval_id]
        proposal = approval.proposal
        verify_frozen_proposal(proposal)
        data = proposal.input
        if approval.state != "approved":
            raise RemediationRefused("approval is not approved")
        if approval_id in self.actions:
            raise RemediationRefused("action already attempted")
        if at >= proposal.expires_at:
            raise RemediationRefused("proposal expired")
        if not incident_open:
            raise RemediationRefused("incident is no longer open")
        if (data.capability, data.target) not in self.gate_open:
            raise RemediationRefused("write gate is closed")
        if data.target in self.holds:
            raise RemediationRefused("target has an active hold")
        if identity != data.target_identity:
            raise RemediationRefused("target identity changed")
        if inventory_version != data.inventory_version or policy_version != data.policy_version:
            raise RemediationRefused("inventory or policy changed")
        if evidence_version != data.evidence_version:
            raise RemediationRefused("evidence changed")
        action_id = f"act_{uuid4().hex}"
        self.actions[approval_id] = "attempting"
        try:
            status = self.gateway.dispatch(action_id, proposal)
        except Exception:
            status = self.gateway.status(action_id) or "unknown"
        self.actions[approval_id] = status if status in ("confirmed", "failed") else "indeterminate"
        return self.actions[approval_id]
