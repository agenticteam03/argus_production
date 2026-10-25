"""Read-only presentation of a frozen approval for the Phase 19 private UI."""
from __future__ import annotations

import hmac
from datetime import datetime, timezone

from argus.actions.remediation import RemediationRefused, verify_frozen_proposal
from argus.domain.model import TargetRef


class ApprovalViewRefused(ValueError):
    """Stored approval data cannot be presented as a valid frozen request."""


def approval_view(rows, approval_id: str) -> dict:
    approval = rows.get_action_approval(approval_id)
    if approval is None:
        raise ApprovalViewRefused("approval is unavailable")
    proposal = rows.get_action_proposal(approval["proposal_id"])
    if proposal is None:
        raise ApprovalViewRefused("proposal is unavailable")
    try:
        verify_frozen_proposal(proposal)
    except RemediationRefused as exc:
        raise ApprovalViewRefused("proposal integrity failed") from exc
    if not hmac.compare_digest(approval["proposal_digest"], proposal.digest):
        raise ApprovalViewRefused("approval digest mismatch")
    judge = rows.get_judge_verdict(proposal.id)
    if judge is None or not hmac.compare_digest(judge.get("proposal_digest", ""), proposal.digest):
        raise ApprovalViewRefused("judge digest mismatch")
    expires = approval["expires_at"]
    if isinstance(expires, str):
        expires = datetime.fromisoformat(expires)
    state = "expired" if approval["state"] == "pending" and expires <= datetime.now(timezone.utc) else approval["state"]
    return {
        "id": approval["id"], "state": state, "expires_at": expires.isoformat(),
        "proposal": proposal.model_dump(mode="json"),
        "judge": {"verdict": judge["verdict"], "risk": judge["risk"], "reasons": judge["reasons"]},
    }


def answerable_approval(rows, approval_id: str, digest: str, decision: str,
                        confirmation_target: str | None) -> None:
    """Validate the stored package before consuming a human's one-use step-up."""
    view = approval_view(rows, approval_id)
    if view["state"] != "pending":
        raise ApprovalViewRefused("approval is no longer pending")
    if not hmac.compare_digest(view["proposal"]["digest"], digest):
        raise ApprovalViewRefused("approval digest mismatch")
    if decision == "approved":
        if view["judge"]["verdict"] != "agree" or view["judge"]["risk"] == "forbidden":
            raise ApprovalViewRefused("judge has not agreed to this action")
        if (view["judge"]["risk"] == "red"
                and confirmation_target != TargetRef.parse(view["proposal"]["input"]["target"]).name):
            raise ApprovalViewRefused("red action requires typing the target name")
