"""ACR-0043 (CON-2): one console command from input to stored history row and audit.

parse -> quota -> handler (reads go through the runner's guarded invoke) -> history row -> audit. The route calls
`ConsoleService.run`; nothing here knows HTTP.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta
from threading import Lock
from typing import Any

from argus.console.config import ConsoleConfig
from argus.console.handlers import ConsolePorts, HandlerError, execute
from argus.console.parser import ConsoleRefused, parse
from argus.console.registry import LAB_SERVICES, READ
from argus.domain.model import AuditRecord, TargetRef, utcnow

log = logging.getLogger("argus.console")


class QuotaRefused(Exception):
    def __init__(self, which: str, retry_after: int):
        super().__init__(which)
        self.which, self.retry_after = which, retry_after


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

    # --- audit -------------------------------------------------------------------------------------------------
    def _audit(self, event: str, person: str, incident_id: str, **detail: Any) -> None:
        self.app.store.append(AuditRecord(
            audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=incident_id, at=utcnow(), category="access",
            event=event, actor=person[:64], detail={"source": "operator_console", **detail}))

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
            self._pending[person] = pending + 1

    def _release(self, person: str) -> None:
        with self._lock:
            self._pending[person] = max(0, self._pending.get(person, 1) - 1)

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
                            now=utcnow)

    # --- the flow ----------------------------------------------------------------------------------------------
    def run(self, principal, incident, text: str, suggestion_id: str | None = None) -> ConsoleResponse:
        person, command_id = principal.id, f"cmd_{uuid.uuid4().hex[:16]}"
        try:
            parsed = parse(text)
        except ConsoleRefused as exc:
            at = utcnow()
            output, cut = truncate([str(exc)], self.config.output_max_bytes)
            self.app.store.add_console_command({           # the refusal is history too (Activity shows `rejected`)
                "command_id": command_id, "incident_id": incident.id, "person": person, "input": text,
                "command": None, "cls": None, "status": "rejected", "output": output, "output_truncated": cut,
                "suggestion_id": suggestion_id, "started_at": at, "finished_at": at})
            self._audit("console.refused", person, incident.id, command_id=command_id, reason=str(exc)[:200])
            return ConsoleResponse(command_id, text, None, None, "rejected", [str(exc)], at, at)
        counted = parsed.cls == READ
        if counted:
            try:
                self._admit(person, incident.id)
            except QuotaRefused as refused:
                self._audit("console.quota_refused", person, incident.id, command_id=command_id,
                            command=parsed.id, quota=refused.which)
                raise
            if self.app.store.console_read_count(incident_id=incident.id) >= self.config.incident_read_budget:
                self._release(person)
                at = utcnow()
                self._audit("console.budget_refused", person, incident.id, command_id=command_id, command=parsed.id)
                return ConsoleResponse(command_id, parsed.text or text, parsed.id, parsed.cls, "rejected",
                                       [f"read budget for this incident reached ({self.config.incident_read_budget})"],
                                       at, at)
        try:
            result = execute(parsed, incident.id, principal, self._ports(incident, person))
            output, cut = truncate(result.output_lines, self.config.output_max_bytes)
            self.app.store.add_console_command({
                "command_id": command_id, "incident_id": incident.id, "person": person, "input": parsed.text or text,
                "command": parsed.id, "cls": parsed.cls, "status": result.status, "output": output,
                "output_truncated": cut, "suggestion_id": suggestion_id,
                "started_at": result.started_at, "finished_at": result.finished_at})
        finally:
            if counted:
                self._release(person)
        self._audit("console.command", person, incident.id, command_id=command_id, command=parsed.id,
                    cls=parsed.cls, status=result.status)
        return ConsoleResponse(command_id, parsed.text or text, parsed.id, parsed.cls, result.status,
                           result.output_lines, result.started_at, result.finished_at)
