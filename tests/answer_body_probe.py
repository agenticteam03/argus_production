"""TASK-150: the answer route's whole response and the audit rows it leaves, as plain data (ids and times dropped).

`tests/fixtures/approval_answer_golden.json` was produced by running `observe` on `origin/main` (before the
two-person rule existed); the branch test compares the setting-OFF run against it.
"""
from __future__ import annotations

VOLATILE = {"proposal_id", "approval_id", "command_id", "proposal_digest", "client_cert", "incident_id", "audit_id",
            "at", "hold_id", "expires_at"}


def _clean(value):
    if isinstance(value, dict):
        return {k: ("<volatile>" if k in VOLATILE else _clean(v)) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def observe(case, answer_headers, decision, reason=None):
    """Propose `cache restart` as the case's person, answer it, and return the answer and the new audit rows."""
    from test_console_write_path import PRIVATE, url
    proposed = case.client.post(url(case.incident, "execute"), headers={**case.auth, **PRIVATE},
                                json={"input": "cache restart", "confirmation": "yes"}).json()
    proposal = case.app.store.get_action_proposal(proposed["proposal_id"])
    before = {row.audit_id for row in case.app.store.list_for(case.incident.id)}
    body = {"decision": decision, "proposal_digest": proposal.digest, "step_up_token": "offline-step-up"}
    if reason:
        body["reason"] = reason
    response = case.client.post(f"/api/v1/ops/approvals/{proposed['approval_id']}/answer",
                                headers={**answer_headers, **PRIVATE}, json=body)
    rows = [{"category": r.category, "event": r.event, "actor": r.actor, "detail": _clean(r.detail or {})}
            for r in case.app.store.list_for(case.incident.id) if r.audit_id not in before]
    state = case.app.store.get_action_approval_for_proposal(proposal.id)["state"]
    return {"status": response.status_code, "body": _clean(response.json()), "audit": rows, "state": state}
