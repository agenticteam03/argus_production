"""ACR-0043 (CON-2): one console command from input to stored history row and audit.

parse -> quota -> handler (reads go through the runner's guarded invoke) -> history row -> audit. The route calls
`ConsoleService.run`; nothing here knows HTTP.
"""
from __future__ import annotations

import logging
import copy
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock
from typing import Any

from argus.console.config import ConsoleConfig
from argus.console.analysis_runner import AnalysisRunner, NotRetryable, UnknownCommand  # noqa: F401
from argus.console.handlers import ConsolePorts, HandlerError, execute
from argus.console.parser import ConsoleRefused, parse
from argus.console.registry import LAB_SERVICES, META, READ, WRITE
from argus.domain.model import AuditRecord, IncidentStatus, TargetRef, utcnow

log = logging.getLogger("argus.console")


class QuotaRefused(Exception):
    def __init__(self, which: str, retry_after: int):
        super().__init__(which)
        self.which, self.retry_after = which, retry_after


class BudgetRefused(Exception):
    """The incident's own read budget is used up (counting the reads still in flight)."""


@dataclass(frozen=True)
class ConsoleResponse:
    command_id: str
    input: str
    command: str | None          # the registry id; None when the parser refused the input
    cls: str | None
    status: str
    output: list[str]
    started_at: Any
    finished_at: Any
    proposal_id: str | None = None
    approval_id: str | None = None
    judge_verdict: str | None = None
    http_status: int = 200


def lines_of(text: str) -> list[str]:
    """A stored output (one text, newline-joined) as the lines `execute` answers; no output is no lines."""
    return text.split("\n") if text else []


def truncate(lines: list[str], limit: int) -> tuple[str, bool]:
    """The output as stored: one text, cut at `limit` bytes (never inside a character)."""
    text = "\n".join(lines)
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text, False
    return raw[:limit].decode("utf-8", errors="ignore"), True


class ConsoleService:
    def __init__(self, app_ctx, config: ConsoleConfig):
        self.app, self.config = app_ctx, config
        self._lock = Lock()
        self._pending: dict[str, int] = {}      # reads admitted and not yet stored, per person
        self._pending_incident: dict[str, int] = {}     # the same, per incident (the budget below)
        self.analysis = AnalysisRunner(app_ctx, config)      # CON-4b: Argus's comment after each command
        self._proposal_locks_guard = Lock()
        self._proposal_locks: dict[str, Lock] = {}

    # --- audit -------------------------------------------------------------------------------------------------
    def _audit(self, event: str, person: str, incident_id: str | None, **detail: Any) -> None:
        self.app.store.append(AuditRecord(
            audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=incident_id, at=utcnow(), category="access",
            event=event, actor=person[:64], detail={"source": "operator_console", **detail}))

    def forbidden(self, person: str, incident_id: str | None, reason: str) -> None:
        """A request refused before the service (not a person's own session): audited like every other call."""
        self._audit("console.forbidden", person, None, status=403, reason=reason[:200],
                    path_incident=str(incident_id)[:64])      # unvalidated at this point, so only as text

    def _redact(self, text: str) -> str:
        """A typed line is redacted before it is stored, audited or shown: a pasted token or password is never kept."""
        redactor = getattr(self.app.runner, "redactor", None)
        if redactor is None:
            from argus.capabilities.redaction import Redactor
            redactor = Redactor()
        return redactor.text(text)[0]

    # --- quota: stored reads plus the ones in flight, so concurrent requests cannot pass the same last slot -----
    def _admit(self, person: str, incident_id: str) -> None:
        store, cfg, now = self.app.store, self.config, utcnow()
        with self._lock:
            pending = self._pending.get(person, 0)
            for which, limit, span in (("per_minute", cfg.reads_per_minute, timedelta(minutes=1)),
                                       ("per_hour", cfg.reads_per_hour, timedelta(hours=1))):
                since = now - span
                if store.console_read_count(person=person, since=since) + pending >= limit:
                    oldest = store.console_oldest_read(person=person, since=since)
                    wait = 1 if oldest is None else max(1, int((oldest + span - now).total_seconds()) + 1)
                    raise QuotaRefused(which, wait)
            in_flight = self._pending_incident.get(incident_id, 0)
            if store.console_read_count(incident_id=incident_id) + in_flight >= cfg.incident_read_budget:
                raise BudgetRefused()
            self._pending[person] = pending + 1
            self._pending_incident[incident_id] = in_flight + 1

    def _release(self, person: str, incident_id: str) -> None:
        with self._lock:
            self._pending[person] = max(0, self._pending.get(person, 1) - 1)
            self._pending_incident[incident_id] = max(0, self._pending_incident.get(incident_id, 1) - 1)

    @staticmethod
    def _write_pair(command_id: str, inventory, host: str) -> tuple[str, str] | None:
        """The console vocabulary maps each write id to one fixed, reviewed action and lab service."""
        actions = {
            "cache.restart": ("container.start", "cache"),
            "worker.restart": ("container.restart", "worker"),
            "net.reconnect": ("network.restore", "api"),
        }
        selected = actions.get(command_id)
        if selected is None:
            return None
        capability, alias = selected
        name = LAB_SERVICES[alias]
        targets = [target for target in inventory.targets()
                   if target.ref.kind == "container" and target.ref.host == host and target.ref.name == name]
        return (capability, str(targets[0].ref)) if len(targets) == 1 else None

    def _write(self, parsed, principal, incident, command_id: str, confirmation: str | None,
               suggestion_id: str | None, *, refusal: str | None = None,
               refusal_status: int = 403) -> ConsoleResponse:
        person, started = principal.id, utcnow()

        def record(*args, **kwargs):
            kwargs.setdefault("suggestion_id", suggestion_id)
            return self._write_result(*args, **kwargs)

        self._audit("console.write.before", person, incident.id, command_id=command_id, command=parsed.id,
                    proposal_id=None, phase=("authorization" if refusal else
                                             "proposal" if confirmation == "yes" else "confirmation"))
        if refusal:
            return record(parsed, principal, incident, command_id, started, "rejected", [refusal],
                          audit_phase="authorization", http_status=refusal_status)
        pair = self._write_pair(parsed.id, self.app.inventory, self.config.lab_host)
        prompt = {
            "cache.restart": "This will start the stopped cache. It needs an approver. Type yes to create the proposal.",
            "worker.restart": "This will restart the job worker. It needs an approver. Type yes to create the proposal.",
            "net.reconnect": "This will restore the API's declared network. It needs an approver. Type yes to create the proposal.",
        }.get(parsed.id)
        if pair is None or prompt is None:
            return record(parsed, principal, incident, command_id, started, "rejected",
                          ["write command has no released target"])
        capability, target = pair
        action_path = getattr(self.app.runner, "action_path", None)
        gate = getattr(getattr(action_path, "executor", None), "gate_open", frozenset())
        if pair not in gate:
            return record(parsed, principal, incident, command_id, started, "rejected",
                          ["this action and target are not released in write_gate.open"])
        if incident.status == IncidentStatus.closed:
            return record(parsed, principal, incident, command_id, started, "rejected",
                          ["write commands are refused on a closed incident"])
        if parsed.id == "cache.restart" and self._evidence_state(incident.id, target) == "running":
            return record(parsed, principal, incident, command_id, started, "rejected",
                                      ["restart on the cache is not released while it is running"])
        if confirmation != "yes":
            return record(parsed, principal, incident, command_id, started, "needs_confirmation", [prompt])
        if action_path is None:
            return record(parsed, principal, incident, command_id, started, "rejected",
                          ["the supervised action path is not available"])

        with self._proposal_locks_guard:
            proposal_lock = self._proposal_locks.setdefault(incident.id, Lock())
        with proposal_lock:
            rows = self.app.store
            previous = rows.latest_action_proposal_for_incident(incident.id)
            if previous is not None and started < previous.expires_at:
                approval = rows.get_action_approval_for_proposal(previous.id)
                approval_expires = approval.get("expires_at") if approval is not None else None
                if isinstance(approval_expires, str):
                    approval_expires = datetime.fromisoformat(approval_expires)
                if (previous.input.capability, previous.input.target) != pair:
                    return record(parsed, principal, incident, command_id, started, "rejected",
                                              ["an action proposal for this incident is already active"])
                if approval is None:
                    proposal_id = previous.id
                elif approval["state"] == "pending" and approval_expires is not None and started < approval_expires:
                    proposal_id = previous.id
                else:
                    return record(parsed, principal, incident, command_id, started, "rejected",
                                              ["an action proposal for this incident is already active"])
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
                    log.info("console proposal refused for %s: %s", parsed.id, type(exc).__name__)
                    return record(parsed, principal, incident, command_id, started, "rejected",
                                              ["the incident evidence does not support this released action"])
                if not proposal_id:
                    if parsed.id == "cache.restart" and self._evidence_state(incident.id, target) == "running":
                        return record(parsed, principal, incident, command_id, started, "rejected",
                                                  ["restart on the cache is not released while it is running"])
                    return record(parsed, principal, incident, command_id, started, "rejected",
                                              ["the incident evidence does not support this released action"])

            proposal = rows.get_action_proposal(proposal_id)
            if proposal is None or (proposal.input.capability, proposal.input.target) != pair:
                return record(parsed, principal, incident, command_id, started, "rejected",
                                          ["the proposal does not match this command's released action"])
            judge_started = utcnow()
            try:
                verdict = action_path.judge(proposal_id)
            except Exception as exc:
                return record(parsed, principal, incident, command_id, started, "rejected",
                                          [f"the judge review failed ({type(exc).__name__}); no approval was requested"],
                                          proposal_id=proposal_id, audit_phase="judge_failed")
            wait_s = max(0.0, (utcnow() - judge_started).total_seconds())
            if verdict.verdict == "disagree" or verdict.risk == "forbidden":
                output = [f"judge: {verdict.verdict} ({wait_s:.2f}s); no approval was requested"]
                return record(parsed, principal, incident, command_id, started, "rejected", output,
                                          proposal_id=proposal_id, judge_verdict=verdict.verdict, audit_phase="judged")
            try:
                approval_id = action_path.request(proposal_id)
            except Exception as exc:
                log.info("console approval request refused: %s", type(exc).__name__)
                approval_id = None
            if not approval_id:
                output = [f"judge: {verdict.verdict} ({wait_s:.2f}s)",
                          "the proposal was not sent for approval"]
                return record(parsed, principal, incident, command_id, started, "rejected", output,
                                          proposal_id=proposal_id, judge_verdict=verdict.verdict,
                                          audit_phase="approval_refused")
            output = [f"judge: {verdict.verdict} ({wait_s:.2f}s)",
                      f"Proposal {proposal_id} is waiting for approval at /api/v1/ops/approvals/{approval_id}.",
                      f"proposal_id={proposal_id}", f"approval_id={approval_id}"]
            return record(parsed, principal, incident, command_id, started, "ok", output,
                                      proposal_id=proposal_id, approval_id=approval_id,
                                      judge_verdict=verdict.verdict, audit_phase="pending")

    def _evidence_state(self, incident_id: str, target: str) -> str | None:
        found = [row for row in self.app.store.list_evidence(incident_id)
                 if row.capability == "container.status" and row.target == target and row.status == "ok"]
        if not found:
            return None
        latest = max(found, key=lambda row: row.source_time or row.collected_at)
        return (latest.values.get("values") or {}).get("state")

    def _write_result(self, parsed, principal, incident, command_id, started, status, output, *, proposal_id=None,
                      approval_id=None, judge_verdict=None, audit_phase="finished", suggestion_id=None,
                      http_status=200):
        finished = utcnow()
        shown = parsed.text
        raw, cut = truncate(output, self.config.output_max_bytes)
        row = {"command_id": command_id, "incident_id": incident.id, "person": principal.id, "input": shown,
               "command": parsed.id, "cls": WRITE, "status": status, "output": raw,
               "output_truncated": cut, "suggestion_id": suggestion_id, "started_at": started, "finished_at": finished}
        self.app.store.add_console_command(row)
        if status == "ok" and approval_id:
            try:                                # a proposal, not an action: held until the action has executed
                self.analysis.hold_write(row, incident, principal.id, approval_id)
            except Exception:
                log.exception("console analysis of %s not held", command_id)
        self._audit("console.command", principal.id, incident.id, command_id=command_id, command=parsed.id,
                    cls=WRITE, status=status, proposal_id=proposal_id)
        self._audit("console.write.after", principal.id, incident.id, command_id=command_id, command=parsed.id,
                    proposal_id=proposal_id, approval_id=approval_id, judge_verdict=judge_verdict, status=status,
                    proposed_by=principal.id if proposal_id else None, phase=audit_phase)
        return ConsoleResponse(command_id, shown, parsed.id, WRITE, status, output, started, finished,
                               proposal_id, approval_id, judge_verdict, http_status)

    # --- ports -------------------------------------------------------------------------------------------------
    def _ports(self, incident, person: str) -> ConsolePorts:
        app = self.app
        invoke = getattr(app.runner, "invoke", None)
        containers = {t.ref.name: t.ref for t in app.inventory.targets() if t.ref.kind == "container" and t.ref.host == self.config.lab_host}

        def service_ref(alias: str) -> str:
            name = LAB_SERVICES[alias]
            if name not in containers:
                raise HandlerError(f"{name} is not in the inventory")
            return str(containers[name])

        def read(capability: str, target: str, **args: Any):
            if invoke is None:
                raise HandlerError("reads are not available in this process")
            from argus.application.invoke_capability import InvocationContext
            ctx = InvocationContext(incident=incident, caller=f"console:{person}",
                                    scope={TargetRef.parse(target)}, counters={})
            observation, _ = invoke(ctx, capability, {"target": target, **args})
            return observation

        host = f"{self.config.lab_host}/host:{self.config.lab_host}"
        return ConsolePorts(read=read, service_ref=service_ref, host_ref=host,
                            topology=app.topology.view,
                            history=lambda incident_id: app.store.console_history(incident_id, self.config.history_limit),
                            now=utcnow, metrics=app.metrics)

    # --- the flow ----------------------------------------------------------------------------------------------
    def run(self, principal, incident, text: str, suggestion_id: str | None = None,
            confirmation: str | None = None, *, granted: frozenset[str] = frozenset(),
            role_grants: frozenset[str] | None = None) -> ConsoleResponse:
        person, command_id = principal.id, f"cmd_{uuid.uuid4().hex[:16]}"
        try:
            parsed = parse(text)
        except ConsoleRefused as exc:
            at = utcnow()
            shown, message = self._redact(text), self._redact(str(exc))     # the message may echo the typed token
            output, cut = truncate([message], self.config.output_max_bytes)
            self.app.store.add_console_command({           # the refusal is history too (Activity shows `rejected`)
                "command_id": command_id, "incident_id": incident.id, "person": person, "input": shown,
                "command": None, "cls": None, "status": "rejected", "output": output, "output_truncated": cut,
                "suggestion_id": suggestion_id, "started_at": at, "finished_at": at})
            self._audit("console.refused", person, incident.id, command_id=command_id, reason=message[:200])
            return ConsoleResponse(command_id, shown, None, None, "rejected", [message], at, at)
        counted = parsed.cls == READ
        if parsed.cls == WRITE:
            refusal = None
            if principal.kind != "human" or (role_grants is not None and "propose_action" not in role_grants):
                refusal = "the console write needs propose_action"
            elif "propose_action" not in granted:
                refusal = "the permission propose_action needs a passkey session"
            return self._write(parsed, principal, incident, command_id, confirmation, suggestion_id,
                               refusal=refusal)
        if counted:
            try:
                self._admit(person, incident.id)
            except QuotaRefused as refused:
                self._audit("console.quota_refused", person, incident.id, command_id=command_id,
                            command=parsed.id, quota=refused.which)
                raise
            except BudgetRefused:
                at = utcnow()
                self._audit("console.budget_refused", person, incident.id, command_id=command_id, command=parsed.id)
                return ConsoleResponse(command_id, parsed.text or text, parsed.id, parsed.cls, "rejected",
                                       [f"read budget for this incident reached ({self.config.incident_read_budget})"],
                                       at, at)
        try:
            before = self.analysis.before(parsed, incident) if parsed.cls != META else None
            result = execute(parsed, incident.id, principal, self._ports(incident, person))
            output, cut = truncate(result.output_lines, self.config.output_max_bytes)
            row = {
                "command_id": command_id, "incident_id": incident.id, "person": person, "input": parsed.text or text,
                "command": parsed.id, "cls": parsed.cls, "status": result.status, "output": output,
                "output_truncated": cut, "suggestion_id": suggestion_id,
                "started_at": result.started_at, "finished_at": result.finished_at}
            self.app.store.add_console_command(row)
        finally:
            if counted:
                self._release(person, incident.id)
        self._audit("console.command", person, incident.id, command_id=command_id, command=parsed.id,
                    cls=parsed.cls, status=result.status)
        if self.analysis.eligible(parsed, result.status):
            try:                                # the command's own answer never depends on its analysis
                self.analysis.submit(row, parsed, before, person)
            except Exception:
                log.exception("console analysis of %s not started", command_id)
        return ConsoleResponse(command_id, parsed.text or text, parsed.id, parsed.cls, result.status,
                           result.output_lines, result.started_at, result.finished_at)

    # --- CON-4b: a person asks Argus to look again at a command's result -------------------------------------
    def recheck(self, principal, incident, command_id: str) -> dict:
        """Re-run the analysis of one command (retryable ones only). Checked against the read quota like a
        read (refused at the limit) but it adds no history row, so it does not use any of it; only a retryable
        analysis can be asked again."""
        try:
            self._admit(principal.id, incident.id)
        except BudgetRefused:
            pass                                 # it adds no read: the incident's read budget does not limit it
        else:
            self._release(principal.id, incident.id)
        view = self.analysis.recheck(incident, command_id, principal.id)
        self._audit("console.recheck", principal.id, incident.id, command_id=command_id)
        return view
