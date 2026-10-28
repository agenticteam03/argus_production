"""The supervised action of one incident, for its detail page: what was proposed, what the judge said, who answered the
approval, what the gateway did and what the verification found. Read from the frozen rows only; nothing here acts.
Operators see it with the evidence; it carries no token, digest or gateway journal."""
from __future__ import annotations

from typing import Any


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def incident_action(rows, incident_id: str) -> dict[str, Any] | None:
    """The incident's newest proposal and its trail, or None when it has none."""
    proposal = rows.latest_action_proposal_for_incident(incident_id)
    if proposal is None:
        return None
    data = proposal.input
    view: dict[str, Any] = {
        "proposal_id": proposal.id, "capability": data.capability, "target": data.target,
        "root_cause": data.root_cause, "rationale": data.rationale, "preview": data.preview,
        "created_at": _iso(proposal.created_at), "expires_at": _iso(proposal.expires_at),
        "judge": None, "approval": None, "action": None, "outcome": None,
    }
    verdict = rows.get_judge_verdict(proposal.id)
    if verdict:
        view["judge"] = {"verdict": verdict.get("verdict"), "risk": verdict.get("risk"),
                         "reasons": list(verdict.get("reasons") or [])}
    approval = rows.get_action_approval_for_proposal(proposal.id)
    if approval is None:
        return view
    view["approval"] = {"id": approval["id"], "state": approval["state"], "answered_by": approval["actor"],
                        "requested_at": _iso(approval["requested_at"]), "answered_at": _iso(approval["answered_at"])}
    action = rows.get_action_for_approval(approval["id"])
    if action is None:
        return view
    view["action"] = {"id": action["id"], "state": action["state"], "attempted_at": _iso(action["attempted_at"]),
                      "result_at": _iso(action["result_at"])}
    outcome = rows.get_action_outcome(action["id"])
    if outcome:
        view["outcome"] = {"outcome": outcome["outcome"], "recorded_at": _iso(outcome["recorded_at"])}
    return view
