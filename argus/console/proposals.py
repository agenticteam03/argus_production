"""ACR-0043 (CON-6): a confirmed console write becomes one proposal of the supervised action path, judged, then sent for
approval; never an action. It runs where the action path is: in the worker on vm-095 (§12.6: the API holds no action
path), through a `propose` console job; in the same process when that process has the path (`argus serve`, tests).

The answer is a plain dict, so it crosses the job table unchanged: `status`, `output` (lines), and when they exist
`proposal_id`, `approval_id`, `judge_verdict`, and the `audit_phase` of the console's `console.write.after` record.
"""
from __future__ import annotations

import copy
import logging
from datetime import datetime
from threading import Lock
from typing import Any

from argus.domain.model import utcnow

log = logging.getLogger("argus.console")


def evidence_state(store, incident_id: str, target: str) -> str | None:
    """The latest recorded `container.status` state of `target` in the incident's evidence, or None."""
    found = [row for row in store.list_evidence(incident_id)
             if row.capability == "container.status" and row.target == target and row.status == "ok"]
    if not found:
        return None
    latest = max(found, key=lambda row: row.source_time or row.collected_at)
    return (latest.values.get("values") or {}).get("state")


def _answer(status: str, output: list[str], audit_phase: str = "finished", **ids: Any) -> dict[str, Any]:
    return {"status": status, "output": output, "audit_phase": audit_phase,
            **{key: value for key, value in ids.items() if value is not None}}


def propose_write(app, incident, pair: tuple[str, str], command: str, started: datetime, lock: Lock) -> dict[str, Any]:
    """The proposal for `pair`, reused while it is active, judged and sent for approval (or the refusal)."""
    action_path = getattr(app.runner, "action_path", None)
    if action_path is None:
        return _answer("rejected", ["the supervised action path is not available"])
    if pair not in getattr(getattr(action_path, "executor", None), "gate_open", frozenset()):
        return _answer("rejected", ["this action and target are not released in write_gate.open"])
    rows = app.store
    with lock:
        previous = rows.latest_action_proposal_for_incident(incident.id)
        if previous is not None and started < previous.expires_at:
            approval = rows.get_action_approval_for_proposal(previous.id)
            approval_expires = approval.get("expires_at") if approval is not None else None
            if isinstance(approval_expires, str):
                approval_expires = datetime.fromisoformat(approval_expires)
            if (previous.input.capability, previous.input.target) != pair:
                return _answer("rejected", ["an action proposal for this incident is already active"])
            if approval is None:
                proposal_id = previous.id
            elif approval["state"] == "pending" and approval_expires is not None and started < approval_expires:
                proposal_id = previous.id
            else:
                return _answer("rejected", ["an action proposal for this incident is already active"])
        else:
            audits = rows.list_for(incident.id)
            recalled = {p["runbook_id"] for row in audits if row.event == "recall.passages"
                        for p in (row.detail or {}).get("passages", []) if p.get("runbook_id")}
            state = {"passages": [{"runbook_id": value} for value in sorted(recalled)]}

            # Restrict the normal candidate builder before it freezes anything. The proposer and all subsequent
            # digest, policy, judge and approval work remain the existing OfflineActionPath implementation.
            scoped = copy.copy(action_path)
            delegate = action_path.action_policy

            class PairPolicy:
                def __getattr__(self, name):
                    return getattr(delegate, name)

                def next_actions(self, *args, **kwargs):
                    return [candidate for candidate in delegate.next_actions(*args, **kwargs)
                            if (candidate.get("action"), candidate.get("target")) == pair]

            scoped.action_policy = PairPolicy()
            try:
                proposal_id = scoped.propose(incident, state)
            except Exception as exc:
                log.info("console proposal refused for %s: %s", command, type(exc).__name__)
                return _answer("rejected", ["the incident evidence does not support this released action"])
            if not proposal_id:
                if command == "cache.restart" and evidence_state(rows, incident.id, pair[1]) == "running":
                    return _answer("rejected", ["restart on the cache is not released while it is running"])
                return _answer("rejected", ["the incident evidence does not support this released action"])

        proposal = rows.get_action_proposal(proposal_id)
        if proposal is None or (proposal.input.capability, proposal.input.target) != pair:
            return _answer("rejected", ["the proposal does not match this command's released action"])
        judge_started = utcnow()
        try:
            verdict = action_path.judge(proposal_id)
        except Exception as exc:
            return _answer("rejected", [f"the judge review failed ({type(exc).__name__}); no approval was requested"],
                           "judge_failed", proposal_id=proposal_id)
        wait_s = max(0.0, (utcnow() - judge_started).total_seconds())
        if verdict.verdict == "disagree" or verdict.risk == "forbidden":
            return _answer("rejected", [f"judge: {verdict.verdict} ({wait_s:.2f}s); no approval was requested"],
                           "judged", proposal_id=proposal_id, judge_verdict=verdict.verdict)
        try:
            approval_id = action_path.request(proposal_id)
        except Exception as exc:
            log.info("console approval request refused: %s", type(exc).__name__)
            approval_id = None
        if not approval_id:
            return _answer("rejected", [f"judge: {verdict.verdict} ({wait_s:.2f}s)", "the proposal was not sent for approval"],
                           "approval_refused", proposal_id=proposal_id, judge_verdict=verdict.verdict)
        return _answer("ok", [f"judge: {verdict.verdict} ({wait_s:.2f}s)",
                              f"Proposal {proposal_id} is waiting for approval at /api/v1/ops/approvals/{approval_id}.",
                              f"proposal_id={proposal_id}", f"approval_id={approval_id}"],
                       "pending", proposal_id=proposal_id, approval_id=approval_id, judge_verdict=verdict.verdict)
