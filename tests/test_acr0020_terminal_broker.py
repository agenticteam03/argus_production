from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from services.terminal_broker.core import (
    AuditFailed,
    AuditEvent,
    FixedAccountMap,
    RecordingFailed,
    SessionRefused,
    SessionRegistry,
    TerminalSession,
    TerminalTicket,
)


NOW = datetime(2026, 10, 23, 16, 0, tzinfo=UTC)


class Recorder:
    def __init__(self, fail_after: int | None = None):
        self.fail_after = fail_after
        self.frames = []
        self.manifests = []

    def append(self, frame):
        if self.fail_after is not None and len(self.frames) >= self.fail_after:
            raise OSError("recording store unavailable")
        self.frames.append(frame)

    def finalize(self, manifest):
        self.manifests.append(manifest)


class Audit:
    def __init__(self):
        self.events: list[AuditEvent] = []

    def emit(self, event: AuditEvent):
        self.events.append(event)


class FailedAudit:
    def emit(self, event: AuditEvent):
        raise OSError("audit store unavailable")


class FakeShell:
    def __init__(self):
        self.sent: list[bytes] = []
        self.outputs: list[bytes] = []
        self.closed = False

    def send(self, payload: bytes):
        self.sent.append(payload)

    def receive(self) -> bytes:
        return self.outputs.pop(0)

    def close(self):
        self.closed = True


class FakeShellConnector:
    def __init__(self):
        self.connections: list[tuple[str, str, str]] = []
        self.channel = FakeShell()

    def connect(self, session: TerminalSession) -> FakeShell:
        self.connections.append((session.session_id, session.host, session.account))
        return self.channel


def ticket(**changes) -> TerminalTicket:
    values = {
        "ticket_id": "tt_001",
        "principal": "conantkd",
        "session_id": "ts_001",
        "host": "vm-166",
        "account": "op-conantkd",
        "reason": "Repair incident inc_001",
        "incident_id": "inc_001",
        "lease_id": "lease_vm166_001",
        "issued_at": NOW,
        "expires_at": NOW + timedelta(seconds=60),
    }
    values.update(changes)
    return TerminalTicket(**values)


def registry(recorder=None, audit=None) -> SessionRegistry:
    accounts = FixedAccountMap({("conantkd", "vm-166"): "op-conantkd"})
    return SessionRegistry(accounts, recorder or Recorder(), audit or Audit(), max_sessions_per_principal=2)


def test_ticket_is_bound_to_a_fixed_host_and_account():
    sessions = registry()

    with pytest.raises(SessionRefused, match="account mapping"):
        sessions.open(ticket(account="root"), NOW)
    with pytest.raises(SessionRefused, match="host"):
        sessions.open(ticket(host="vm-999"), NOW)


def test_expired_or_replayed_ticket_is_refused():
    sessions = registry()

    with pytest.raises(SessionRefused, match="expired"):
        sessions.open(ticket(expires_at=NOW), NOW)

    opened = sessions.open(ticket(), NOW)
    assert opened.state == "open"
    with pytest.raises(SessionRefused, match="used"):
        sessions.open(ticket(), NOW + timedelta(seconds=1))


def test_ticket_lifetime_cannot_exceed_sixty_seconds():
    sessions = registry()

    with pytest.raises(SessionRefused, match="60 seconds"):
        sessions.open(ticket(expires_at=NOW + timedelta(seconds=61)), NOW)


def test_reason_incident_and_lease_are_mandatory():
    sessions = registry()

    for field in ("reason", "incident_id", "lease_id"):
        with pytest.raises(SessionRefused, match=field):
            sessions.open(ticket(**{field: ""}), NOW)


def test_concurrent_sessions_are_bounded_per_principal():
    sessions = registry()
    sessions.open(ticket(ticket_id="tt_001", session_id="ts_001"), NOW)
    sessions.open(ticket(ticket_id="tt_002", session_id="ts_002"), NOW)

    with pytest.raises(SessionRefused, match="concurrent"):
        sessions.open(ticket(ticket_id="tt_003", session_id="ts_003"), NOW)


def test_input_and_output_are_recorded_before_they_are_accepted():
    recorder = Recorder()
    sessions = registry(recorder)
    sessions.open(ticket(), NOW)

    sessions.record("ts_001", "input", b"systemctl status app\n", NOW + timedelta(seconds=1))
    sessions.record("ts_001", "output", b"active\n", NOW + timedelta(seconds=2))
    manifest = sessions.close("ts_001", "operator_logout", NOW + timedelta(seconds=3))

    assert [(f.direction, f.payload) for f in recorder.frames] == [
        ("input", b"systemctl status app\n"),
        ("output", b"active\n"),
    ]
    assert manifest.incident_id == "inc_001"
    assert manifest.input_bytes == 21
    assert manifest.output_bytes == 7
    assert recorder.manifests == [manifest]


def test_recording_failure_closes_the_session_fail_closed():
    recorder = Recorder(fail_after=0)
    sessions = registry(recorder)
    sessions.open(ticket(), NOW)

    with pytest.raises(RecordingFailed, match="closed"):
        sessions.record("ts_001", "input", b"whoami\n", NOW + timedelta(seconds=1))

    assert sessions.get("ts_001").state == "closed"
    assert sessions.get("ts_001").close_reason == "recording_failed"


def test_lifecycle_and_refusal_events_are_emitted():
    audit = Audit()
    sessions = registry(audit=audit)

    with pytest.raises(SessionRefused):
        sessions.open(ticket(account="root"), NOW)
    sessions.open(ticket(), NOW)
    sessions.close("ts_001", "operator_logout", NOW + timedelta(seconds=1))

    assert [event.kind for event in audit.events] == [
        "terminal.session_refused",
        "terminal.session_opened",
        "terminal.session_closed",
    ]
    assert audit.events[0].reason == "account mapping is not allowed"
    assert audit.events[1].incident_id == "inc_001"


def test_audit_failure_prevents_a_session_from_opening():
    sessions = registry(audit=FailedAudit())

    with pytest.raises(AuditFailed, match="audit failed"):
        sessions.open(ticket(), NOW)
    with pytest.raises(SessionRefused, match="does not exist"):
        sessions.get("ts_001")


def test_fake_shell_and_recording_adapters_preserve_the_validated_binding():
    recorder = Recorder()
    sessions = registry(recorder=recorder)
    opened = sessions.open(ticket(), NOW)
    connector = FakeShellConnector()

    channel = connector.connect(opened)
    channel.outputs.append(b"op-conantkd@vm-166$ ")
    sessions.record("ts_001", "output", channel.receive(), NOW + timedelta(seconds=1))
    channel.send(b"whoami\n")
    sessions.record("ts_001", "input", channel.sent[-1], NOW + timedelta(seconds=2))
    channel.close()

    assert connector.connections == [("ts_001", "vm-166", "op-conantkd")]
    assert [frame.payload for frame in recorder.frames] == [b"op-conantkd@vm-166$ ", b"whoami\n"]
    assert channel.closed is True


def test_closed_session_accepts_no_more_bytes():
    sessions = registry()
    sessions.open(ticket(), NOW)
    sessions.close("ts_001", "administrator_killed", NOW + timedelta(seconds=1))

    with pytest.raises(SessionRefused, match="not open"):
        sessions.record("ts_001", "output", b"late", NOW + timedelta(seconds=2))
