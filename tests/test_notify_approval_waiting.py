from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from argus.infrastructure.security_alerts import SecurityAlerts
from argus.orchestration import action_path as action_path_module
from argus.orchestration.action_path import OfflineActionPath


NOW = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
APPROVAL_ID = "appr_0123456789abcdef0123456789abcdef"
TARGET = "vm-166/container:argus-lab-cache"


class FakeRows:
    def __init__(self):
        self.approval = None
        self.answers = 0
        self.proposal = SimpleNamespace(
            id="prop_123",
            digest="proposal-digest",
            expires_at=NOW + timedelta(minutes=30),
            input=SimpleNamespace(incident_id="inc_123", capability="container.start", target=TARGET),
        )
        self.verdict = {"verdict": "agree", "risk": "yellow"}

    def get_action_approval_for_proposal(self, _proposal_id):
        return self.approval

    def get_action_proposal(self, _proposal_id):
        return self.proposal

    def get_judge_verdict(self, _proposal_id):
        return self.verdict

    def add_action_approval(self, approval_id, proposal_id, digest, created_at, expires_at):
        self.approval = {"id": approval_id, "proposal_id": proposal_id, "proposal_digest": digest,
                         "created_at": created_at, "expires_at": expires_at, "state": "pending"}

    def get_action_approval(self, _approval_id):
        return self.approval

    def answer_action_approval(self, _approval_id, _digest, _principal, _decision, _at):
        self.answers += 1
        if self.answers == 1:
            self.approval["state"] = "approved"
            return True
        return False


def _path(monkeypatch, notifier=None):
    monkeypatch.setattr(action_path_module, "verify_frozen_proposal", lambda _proposal: None)
    monkeypatch.setattr(action_path_module, "agreed_verdict", lambda _verdict, _proposal: True)
    rows = FakeRows()
    path = object.__new__(OfflineActionPath)
    path.rows = rows
    path.executor = SimpleNamespace(gate_open=frozenset({("container.start", TARGET)}))
    path.clock = lambda: NOW
    path.approval_notifier = notifier
    return path, rows


def test_new_approval_sends_one_safe_message_and_answers_do_not_send_again(monkeypatch):
    messages = []
    def fake_sender(message, _approval_id, _expires_at):
        messages.append(message)

    path, _rows = _path(monkeypatch, fake_sender)

    approval_id = path.request("prop_123")
    assert approval_id
    assert path.answer(approval_id, digest="proposal-digest", principal="reviewer", principal_kind="human",
                       decision="approved", confirmation_target="argus-lab-cache")
    assert not path.answer(approval_id, digest="proposal-digest", principal="reviewer", principal_kind="human",
                           decision="approved", confirmation_target="argus-lab-cache")

    assert len(messages) == 1
    message = messages[0]
    for field in ("inc_123", "container.start", TARGET, "yellow", "agree", "2026-10-27", 
                  f"/api/v1/ops/approvals/{approval_id}"):
        assert field in message
    assert "https://" not in message
    assert "@" not in message
    assert "secret" not in message.lower()


def test_missing_sender_does_not_block_approval_and_logs(monkeypatch, caplog):
    caplog.set_level("INFO")
    path, _rows = _path(monkeypatch)

    assert path.request("prop_123")
    assert "approval notification sender is not configured" in caplog.text


def test_security_alert_sender_uses_existing_alertmanager_telegram_route():
    class Response:
        def raise_for_status(self):
            pass

    class Client:
        def __init__(self):
            self.calls = []

        def post(self, url, *, json):
            self.calls.append((url, json))
            return Response()

    client = Client()
    sender = SecurityAlerts(object(), "alertmanager", client=client, clock=lambda: NOW)
    expiry = NOW + timedelta(minutes=30)

    sender.notify_approval_waiting("approval waiting", APPROVAL_ID, expiry)

    assert len(client.calls) == 1
    url, alerts = client.calls[0]
    assert url == "alertmanager/api/v2/alerts"
    assert alerts[0]["labels"]["argus_security"] == "true"
    assert alerts[0]["labels"]["approval_id"] == APPROVAL_ID
    assert alerts[0]["annotations"]["summary"] == "approval waiting"
    assert alerts[0]["endsAt"] == expiry.isoformat()
