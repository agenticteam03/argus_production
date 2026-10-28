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
    monkeypatch.setattr(action_path_module, "approvable_verdict", lambda _verdict, _proposal: True)
    rows = FakeRows()
    path = object.__new__(OfflineActionPath)
    path.rows = rows
    path.executor = SimpleNamespace(gate_open=frozenset({("container.start", TARGET)}))
    path.clock = lambda: NOW
    path.approval_notifier = notifier
    return path, rows


def test_new_approval_sends_one_safe_message_and_answers_do_not_send_again(monkeypatch):
    messages = []
    def fake_sender(message, _approval_id, _expires_at, resolved=False):
        if not resolved:
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
    assert message == ("Argus: an approval is waiting; it expires at 12:30Z. "
                       "Open the Actions screen on the private path.")
    for detail in ("inc_123", "container", "start", TARGET, "argus-lab", "yellow", "agree", "risk", "/api/",
                   "2026-10-27", "https://", "@", "secret"):
        assert detail not in message.lower()


def test_a_doubted_approval_says_so_and_still_carries_no_detail(monkeypatch):
    """ACR-0039: the team learns the judge doubted it before anyone opens the private screen; nothing else is added."""
    messages = []
    path, rows = _path(monkeypatch, lambda message, *_a, **_k: messages.append(message))
    rows.verdict = {"verdict": "doubt", "risk": "amber"}
    assert path.request("prop_123")
    assert messages == ["Argus: an approval is waiting; it expires at 12:30Z. The independent judge doubted it. "
                        "Open the Actions screen on the private path."]
    for detail in ("inc_123", "container", TARGET, "argus-lab", "amber", "/api/"):
        assert detail not in messages[0].lower()


def test_answer_posts_the_alert_again_as_resolved_once(monkeypatch):
    calls = []
    path, _rows = _path(monkeypatch, lambda *a, **k: calls.append((a, k)))
    approval_id = path.request("prop_123")
    args = dict(digest="proposal-digest", principal="reviewer", principal_kind="human",
                decision="approved", confirmation_target="argus-lab-cache")

    assert path.answer(approval_id, **args)
    assert not path.answer(approval_id, **args)       # already answered: no second resolve

    assert len(calls) == 2
    (_m, aid, expires), kwargs = calls[1]
    assert (aid, expires, kwargs) == (approval_id, NOW + timedelta(minutes=30), {"resolved": True})
    assert "yellow" not in calls[1][0][0] and TARGET not in calls[1][0][0]


def test_a_refused_answer_does_not_resolve(monkeypatch):
    calls = []
    path, _rows = _path(monkeypatch, lambda *a, **k: calls.append((a, k)))
    approval_id = path.request("prop_123")
    try:
        path.answer(approval_id, digest="wrong", principal="reviewer", principal_kind="human", decision="approved")
    except action_path_module.RemediationRefused:
        pass
    assert len(calls) == 1


def test_a_failing_sender_never_blocks_the_answer(monkeypatch, caplog):
    def broken(*_a, **_k):
        raise RuntimeError("down")
    path, _rows = _path(monkeypatch, broken)
    approval_id = path.request("prop_123")
    assert approval_id
    assert path.answer(approval_id, digest="proposal-digest", principal="reviewer", principal_kind="human",
                       decision="approved", confirmation_target="argus-lab-cache")
    assert "approval notification failed" in caplog.text


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
    sender.notify_approval_waiting("answered", APPROVAL_ID, expiry, resolved=True)

    assert len(client.calls) == 2
    url, alerts = client.calls[0]
    assert url == "alertmanager/api/v2/alerts"
    assert alerts[0]["labels"]["argus_security"] == "true"
    assert alerts[0]["labels"]["approval_id"] == APPROVAL_ID
    assert alerts[0]["annotations"]["summary"] == "approval waiting"
    assert alerts[0]["endsAt"] == expiry.isoformat()
    _url, resolved = client.calls[1]
    assert resolved[0]["labels"] == alerts[0]["labels"]       # same alert, so the group drops it
    assert resolved[0]["endsAt"] == NOW.isoformat()


def test_a_held_back_proposal_tells_the_team_without_detail_and_a_failing_sender_is_only_logged(monkeypatch, caplog):
    sent = []
    path, _rows = _path(monkeypatch)
    path.escalation_notifier = lambda message, incident_id: sent.append((message, incident_id))
    path.held_back("inc_123")
    assert sent == [("Argus: an incident needs a person; its proposed action was not sent for approval. "
                     "Open the incident on the private path.", "inc_123")]
    for detail in ("container", "start", TARGET, "argus-lab", "doubt", "judge", "/api/", "https://"):
        assert detail not in sent[0][0].lower()

    def broken(*_a):
        raise RuntimeError("down")
    path.escalation_notifier = broken
    path.held_back("inc_123")
    assert "escalation notification failed" in caplog.text


def test_the_escalation_notice_rides_the_same_route_and_ends_after_the_hold():
    class Client:
        def __init__(self):
            self.calls = []

        def post(self, url, *, json):
            self.calls.append((url, json))
            return SimpleNamespace(raise_for_status=lambda: None)

    client = Client()
    SecurityAlerts(object(), "alertmanager", client=client, clock=lambda: NOW).notify_escalation("needs a person",
                                                                                                "inc_123")
    url, alerts = client.calls[0]
    assert url == "alertmanager/api/v2/alerts"
    assert alerts[0]["labels"] == {"alertname": "ArgusIncidentEscalated", "argus_security": "true",
                                   "incident_id": "inc_123"}
    assert alerts[0]["annotations"]["summary"] == "needs a person"
    assert alerts[0]["endsAt"] == (NOW + timedelta(hours=1)).isoformat()
