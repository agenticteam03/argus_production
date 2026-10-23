"""Fail-closed session contracts for the supervised operator terminal.

This module deliberately contains no network or SSH implementation.  It is the
offline core that later adapters must use to validate tickets and record every
accepted byte.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Mapping, Protocol


Direction = Literal["input", "output"]


class SessionRefused(RuntimeError):
    """Raised when a terminal session or frame violates the broker contract."""


class RecordingFailed(RuntimeError):
    """Raised after a recording failure has forced a session closed."""


class AuditFailed(RuntimeError):
    """Raised when a required lifecycle event cannot be persisted."""


@dataclass(frozen=True, slots=True)
class TerminalTicket:
    ticket_id: str
    principal: str
    session_id: str
    host: str
    account: str
    reason: str
    incident_id: str
    lease_id: str
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class RecordingFrame:
    session_id: str
    sequence: int
    direction: Direction
    payload: bytes
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class RecordingManifest:
    session_id: str
    principal: str
    host: str
    account: str
    incident_id: str
    lease_id: str
    opened_at: datetime
    closed_at: datetime
    close_reason: str
    input_bytes: int
    output_bytes: int
    frame_count: int


@dataclass(frozen=True, slots=True)
class AuditEvent:
    kind: str
    occurred_at: datetime
    session_id: str
    principal: str
    host: str
    account: str
    incident_id: str
    lease_id: str
    reason: str


@dataclass(slots=True)
class TerminalSession:
    ticket_id: str
    session_id: str
    principal: str
    host: str
    account: str
    reason: str
    incident_id: str
    lease_id: str
    opened_at: datetime
    expires_at: datetime
    state: Literal["open", "closed"] = "open"
    close_reason: str | None = None
    closed_at: datetime | None = None
    input_bytes: int = 0
    output_bytes: int = 0
    frame_count: int = 0


class Recorder(Protocol):
    def append(self, frame: RecordingFrame) -> None: ...

    def finalize(self, manifest: RecordingManifest) -> None: ...


class AuditSink(Protocol):
    def emit(self, event: AuditEvent) -> None: ...


class ShellChannel(Protocol):
    def send(self, payload: bytes) -> None: ...

    def receive(self) -> bytes: ...

    def close(self) -> None: ...


class ShellConnector(Protocol):
    def connect(self, session: TerminalSession) -> ShellChannel: ...


class FixedAccountMap:
    """Allow only explicitly configured principal, host and account tuples."""

    def __init__(self, accounts: Mapping[tuple[str, str], str]):
        self._accounts = dict(accounts)
        self._hosts = {host for _, host in accounts}

    def validate(self, principal: str, host: str, account: str) -> None:
        if host not in self._hosts:
            raise SessionRefused(f"host is not allowed: {host}")
        if self._accounts.get((principal, host)) != account:
            raise SessionRefused("account mapping is not allowed")


class SessionRegistry:
    """Own ticket consumption and recording state for active sessions."""

    def __init__(
        self,
        accounts: FixedAccountMap,
        recorder: Recorder,
        audit: AuditSink,
        *,
        max_sessions_per_principal: int,
        session_ttl: timedelta,
    ):
        if max_sessions_per_principal < 1:
            raise ValueError("max_sessions_per_principal must be positive")
        if not timedelta(0) < session_ttl <= timedelta(minutes=30):
            raise ValueError("session_ttl must be positive and at most 30 minutes")
        self._accounts = accounts
        self._recorder = recorder
        self._audit = audit
        self._max_sessions = max_sessions_per_principal
        self._session_ttl = session_ttl
        self._sessions: dict[str, TerminalSession] = {}
        self._used_tickets: set[str] = set()

    def open(self, ticket: TerminalTicket, now: datetime) -> TerminalSession:
        try:
            self._validate_open(ticket, now)
        except SessionRefused as exc:
            self._emit(self._event("terminal.session_refused", ticket, now, str(exc)))
            raise

        session = TerminalSession(
            ticket_id=ticket.ticket_id,
            session_id=ticket.session_id,
            principal=ticket.principal,
            host=ticket.host,
            account=ticket.account,
            reason=ticket.reason,
            incident_id=ticket.incident_id,
            lease_id=ticket.lease_id,
            opened_at=now,
            expires_at=now + self._session_ttl,
        )
        self._emit(self._event("terminal.session_opened", ticket, now, ticket.reason))
        self._sessions[session.session_id] = session
        self._used_tickets.add(ticket.ticket_id)
        return session

    def _validate_open(self, ticket: TerminalTicket, now: datetime) -> None:
        for field in ("ticket_id", "principal", "session_id", "reason", "incident_id", "lease_id"):
            if not getattr(ticket, field).strip():
                raise SessionRefused(f"{field} is required")
        if ticket.expires_at - ticket.issued_at > timedelta(seconds=60):
            raise SessionRefused("ticket lifetime exceeds 60 seconds")
        if ticket.issued_at > now:
            raise SessionRefused("ticket is not valid yet")
        if now >= ticket.expires_at:
            raise SessionRefused("ticket expired")
        if ticket.ticket_id in self._used_tickets:
            raise SessionRefused("ticket was already used")
        if ticket.session_id in self._sessions:
            raise SessionRefused("session id already exists")
        self._accounts.validate(ticket.principal, ticket.host, ticket.account)
        concurrent = sum(
            session.state == "open" and session.principal == ticket.principal
            for session in self._sessions.values()
        )
        if concurrent >= self._max_sessions:
            raise SessionRefused("concurrent session limit reached")

    def _event(self, kind: str, ticket: TerminalTicket, at: datetime, reason: str) -> AuditEvent:
        return AuditEvent(
            kind=kind,
            occurred_at=at,
            session_id=ticket.session_id,
            principal=ticket.principal,
            host=ticket.host,
            account=ticket.account,
            incident_id=ticket.incident_id,
            lease_id=ticket.lease_id,
            reason=reason,
        )

    def _session_event(self, kind: str, session: TerminalSession, at: datetime, reason: str) -> AuditEvent:
        return AuditEvent(
            kind=kind,
            occurred_at=at,
            session_id=session.session_id,
            principal=session.principal,
            host=session.host,
            account=session.account,
            incident_id=session.incident_id,
            lease_id=session.lease_id,
            reason=reason,
        )

    def _emit(self, event: AuditEvent) -> None:
        try:
            self._audit.emit(event)
        except Exception as exc:
            raise AuditFailed("terminal lifecycle audit failed") from exc

    def get(self, session_id: str) -> TerminalSession:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise SessionRefused("session does not exist") from exc

    def record(
        self,
        session_id: str,
        direction: Direction,
        payload: bytes,
        recorded_at: datetime,
    ) -> RecordingFrame:
        session = self.get(session_id)
        if session.state != "open":
            raise SessionRefused("session is not open")
        if recorded_at >= session.expires_at:
            self.close(session_id, "absolute_timeout", recorded_at)
            raise SessionRefused("session expired")
        if direction not in ("input", "output"):
            raise SessionRefused("recording direction is invalid")
        if not isinstance(payload, bytes):
            raise SessionRefused("recording payload must be bytes")

        frame = RecordingFrame(
            session_id=session_id,
            sequence=session.frame_count + 1,
            direction=direction,
            payload=payload,
            recorded_at=recorded_at,
        )
        try:
            self._recorder.append(frame)
        except Exception as exc:
            session.state = "closed"
            session.close_reason = "recording_failed"
            session.closed_at = recorded_at
            self._emit(
                self._session_event("terminal.recording_failed", session, recorded_at, "recording_failed")
            )
            raise RecordingFailed("recording failed; session closed") from exc

        session.frame_count += 1
        if direction == "input":
            session.input_bytes += len(payload)
        else:
            session.output_bytes += len(payload)
        return frame

    def close(self, session_id: str, reason: str, closed_at: datetime) -> RecordingManifest:
        session = self.get(session_id)
        if session.state != "open":
            raise SessionRefused("session is not open")
        if not reason.strip():
            raise SessionRefused("close reason is required")

        session.state = "closed"
        session.close_reason = reason
        session.closed_at = closed_at
        manifest = RecordingManifest(
            session_id=session.session_id,
            principal=session.principal,
            host=session.host,
            account=session.account,
            incident_id=session.incident_id,
            lease_id=session.lease_id,
            opened_at=session.opened_at,
            closed_at=closed_at,
            close_reason=reason,
            input_bytes=session.input_bytes,
            output_bytes=session.output_bytes,
            frame_count=session.frame_count,
        )
        try:
            self._recorder.finalize(manifest)
        except Exception as exc:
            session.close_reason = "recording_failed"
            self._emit(self._session_event("terminal.recording_failed", session, closed_at, "recording_failed"))
            raise RecordingFailed("recording finalization failed; session closed") from exc
        self._emit(self._session_event("terminal.session_closed", session, closed_at, reason))
        return manifest
