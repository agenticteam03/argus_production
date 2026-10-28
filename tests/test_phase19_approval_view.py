"""Phase 19 draft: a frozen approval can be inspected only through the private contract."""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from argus.actions.remediation import freeze_proposal
from argus.adapters.inbound.http import build_api
from argus.domain.model import AuditRecord
from test_core import make_app  # noqa: F401
from test_phase18_remediation import candidate


PASSWORD = "a-long-password"


def _login(client, user):
    token = client.post("/api/v1/auth/token", data={"username": user, "password": PASSWORD}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_approval_view_is_unmounted_without_explicit_action_rows(make_app):  # noqa: F811
    app = make_app()
    app.action_rows = None          # X-9: no approval rows (an empty write gate); a released pair would mount them
    app.store.upsert_principal("alice", "human", "approver", ["lab"], PasswordHash.recommended().hash(PASSWORD))
    client = TestClient(build_api(app))
    auth = _login(client, "alice")
    assert client.get("/api/v1/ops/approvals/appr_missing", headers=auth).status_code == 404
    assert client.post("/api/v1/ops/approvals/appr_missing/answer", headers=auth, json={}).status_code == 404
    assert client.post("/api/v1/ops/holds", headers=auth, json={}).status_code == 404
    assert "approve_action" not in client.get("/api/v1/me", headers=auth).json()["permissions"]
    assert "place_hold" not in client.get("/api/v1/me", headers=auth).json()["permissions"]


def test_approval_view_requires_human_privilege_and_refuses_corrupt_binding(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    app.action_rows = app.store  # explicit draft-only injection; production wiring has no action_rows
    password = PasswordHash.recommended().hash(PASSWORD)
    for user, kind, role, scopes in (("alice", "human", "approver", ["lab"]),
                                    ("vera", "human", "viewer", ["lab"]),
                                    ("olga", "human", "operator", ["lab"]),
                                    ("bot", "service", "approver", ["lab"]),
                                    ("bob", "human", "approver", ["other"])):
        app.store.upsert_principal(user, kind, role, scopes, password)
    proposal = freeze_proposal(candidate(), at=datetime.now(timezone.utc))
    app.store.add_action_proposal(proposal)
    app.store.add_judge_verdict(proposal.id, "test-judge", {
        "verdict": "agree", "risk": "amber", "reasons": ["Evidence supports the action"],
        "checks": {}, "proposal_digest": proposal.digest,
    }, datetime.now(timezone.utc))
    app.store.add_action_approval("appr_test", proposal.id, proposal.digest,
                                  datetime.now(timezone.utc), proposal.expires_at)
    api = build_api(app)
    client = TestClient(api)
    path = "/api/v1/ops/approvals/appr_test"
    alice, vera, olga, bot, bob = (_login(client, user) for user in ("alice", "vera", "olga", "bot", "bob"))
    assert client.get(path, headers=alice).status_code == 403  # no second factor
    monkeypatch.setattr(api.state.second_factor, "privileged_ready", lambda user, session: True)
    assert client.get(path, headers=vera).status_code == 403
    assert client.get(path, headers=olga).status_code == 403   # an operator is not an approver (ACR-0018 §5)
    assert "approve_action" not in client.get("/api/v1/me", headers=olga).json()["permissions"]
    assert client.get(path, headers=bot).status_code == 403
    assert client.get(path, headers=bob).status_code == 403
    result = client.get(path, headers=alice)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["proposal"]["digest"] == proposal.digest
    assert body["proposal"]["input"]["target_identity"] == {"container_id": "cache-1"}
    assert body["judge"]["risk"] == "amber"
    assert body["state"] == "pending"
    assert body["reversible"] is True                            # the rollback is a catalogue action (§3.10)
    assert "step_up_object" not in body  # no answer flow is enabled in this draft

    original = app.store.get_action_approval
    monkeypatch.setattr(app.store, "get_action_approval", lambda key: {
        **original(key), "proposal_digest": "0" * 64,
    })
    assert client.get(path, headers=alice).status_code == 409


def test_answer_needs_digest_and_single_use_step_up(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    app.action_rows = app.store
    app.store.upsert_principal("alice", "human", "approver", ["lab"], PasswordHash.recommended().hash(PASSWORD))
    proposal = freeze_proposal(candidate(), at=datetime.now(timezone.utc))
    app.store.add_action_proposal(proposal)
    app.store.add_judge_verdict(proposal.id, "test-judge", {
        "verdict": "agree", "risk": "red", "reasons": ["Requires explicit target confirmation"],
        "checks": {}, "proposal_digest": proposal.digest,
    }, datetime.now(timezone.utc))
    app.store.add_action_approval("appr_red", proposal.id, proposal.digest,
                                  datetime.now(timezone.utc), proposal.expires_at)
    api = build_api(app)
    client = TestClient(api)
    auth = _login(client, "alice")
    path = "/api/v1/ops/approvals/appr_red/answer"
    body = {"decision": "approved", "proposal_digest": proposal.digest, "step_up_token": "step-up",
            "confirmation_target": "vm-166/container:argus-lab-cache"}
    assert client.post(path, headers=auth, json=body).status_code == 403
    monkeypatch.setattr(api.state.second_factor, "privileged_ready", lambda user, session: True)
    seen = []
    monkeypatch.setattr(api.state.second_factor, "consume_step_up",
                        lambda token, user, session, obj: seen.append((token, user, session, obj)))
    assert client.post(path, headers=auth, json={**body, "proposal_digest": "0" * 64}).status_code == 409
    assert seen == []
    assert client.post(path, headers=auth, json={**body, "confirmation_target": "wrong"}).status_code == 409
    # the container name alone is not the target: the same name exists on both hosts
    assert client.post(path, headers=auth, json={**body, "confirmation_target": "argus-lab-cache"}).status_code == 409
    assert seen == []
    result = client.post(path, headers=auth, json=body)
    assert result.status_code == 200, result.text
    assert result.json() == {"state": "approved"}
    assert seen[0][0:2] == ("step-up", "alice")
    assert seen[0][3] == f"approval:appr_red:{proposal.digest}"
    assert app.store.get_action_approval("appr_red")["actor"] == "alice"
    [row] = [r[1] for r in app.store.audit_chain() if r[1]["event"] == "action.approval_answered"]
    assert row["actor"] == "alice" and row["detail"] == {
        "approval_id": "appr_red", "proposal_digest": proposal.digest, "decision": "approved", "reason": None,
        "client_cert": "none"}                                            # ACR-0038: no certificate on this request
    assert client.post(path, headers=auth, json=body).status_code == 409


def test_private_emergency_hold_is_step_up_bound_audited_and_blocks_actions(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    app.action_rows = app.store
    password = PasswordHash.recommended().hash(PASSWORD)
    app.store.upsert_principal("alice", "human", "approver", ["lab"], password)
    app.store.upsert_principal("bot", "service", "approver", ["lab"], password)
    api = build_api(app)
    client = TestClient(api)
    alice, bot = _login(client, "alice"), _login(client, "bot")
    path = "/api/v1/ops/holds"
    body = {"target": "*", "reason": "Emergency stop", "step_up_token": "once"}
    assert client.post(path, headers=alice, json=body).status_code == 403
    monkeypatch.setattr(api.state.second_factor, "privileged_ready", lambda user, session: True)
    seen = []
    monkeypatch.setattr(api.state.second_factor, "consume_step_up",
                        lambda token, user, session, obj: seen.append((token, user, obj)))
    assert client.post(path, headers=bot, json=body).status_code == 403
    assert client.post(path, headers=alice, json={**body, "target": "vm-166/container:unlisted"}).status_code == 422
    assert seen == []
    result = client.post(path, headers=alice, json=body)
    assert result.status_code == 201, result.text
    hold = result.json()
    assert hold["target"] == "*" and hold["id"].startswith("hold_")
    assert app.store.active_target_holds("*", datetime.now(timezone.utc)) == [hold["id"]]
    assert seen == [("once", "alice", "hold:" + hashlib.sha256(b"*").hexdigest())]
    assert any(row[1]["event"] == "action.hold_placed" and row[1]["actor"] == "alice"
               for row in app.store.audit_chain())
    listed = client.get(path, headers=alice, params={"target": "*"})
    assert listed.status_code == 200 and listed.json()[0]["id"] == hold["id"]


def test_a_hold_and_its_chained_audit_record_are_atomic(make_app):  # noqa: F811
    app = make_app()
    at = datetime.now(timezone.utc)
    audit = lambda suffix: AuditRecord(audit_id=f"aud_hold_{suffix}", incident_id=None, at=at,  # noqa: E731
                                       category="decision", event="action.hold_placed", actor="alice",
                                       detail={"target": "*"})
    app.store.place_target_hold("hold_atomic", "*", "stop", "alice", at, audit("one"))
    before = len(app.store.audit_chain())
    with pytest.raises(sqlite3.IntegrityError):
        app.store.place_target_hold("hold_atomic", "*", "stop", "alice", at, audit("two"))
    assert len(app.store.audit_chain()) == before
    assert app.store.active_target_holds("*", at) == ["hold_atomic"]


def test_a_new_hold_invalidates_an_unanswered_approval_before_step_up(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    app.action_rows = app.store
    app.store.upsert_principal("alice", "human", "approver", ["lab"], PasswordHash.recommended().hash(PASSWORD))
    now = datetime.now(timezone.utc)
    proposal = freeze_proposal(candidate(), at=now)
    app.store.add_action_proposal(proposal)
    app.store.add_judge_verdict(proposal.id, "test-judge", {
        "verdict": "agree", "risk": "green", "reasons": [], "checks": {}, "proposal_digest": proposal.digest,
    }, now)
    app.store.add_action_approval("appr_held", proposal.id, proposal.digest, now, proposal.expires_at)
    app.store.add_target_hold("hold_after_request", "*", "emergency", "alice", now)
    api = build_api(app)
    client = TestClient(api)
    auth = _login(client, "alice")
    monkeypatch.setattr(api.state.second_factor, "privileged_ready", lambda user, session: True)
    seen = []
    monkeypatch.setattr(api.state.second_factor, "consume_step_up", lambda *args: seen.append(args))
    response = client.post("/api/v1/ops/approvals/appr_held/answer", headers=auth, json={
        "decision": "approved", "proposal_digest": proposal.digest, "step_up_token": "unused",
    })
    assert response.status_code == 409 and "hold" in response.json()["detail"]
    assert seen == [] and app.store.get_action_approval("appr_held")["state"] == "pending"


def _pending(app, approval_id: str, risk: str = "green"):
    now = datetime.now(timezone.utc)
    proposal = freeze_proposal(candidate(), at=now)
    app.store.add_action_proposal(proposal)
    app.store.add_judge_verdict(proposal.id, "test-judge", {
        "verdict": "agree", "risk": risk, "reasons": [], "checks": {}, "proposal_digest": proposal.digest,
    }, now)
    app.store.add_action_approval(approval_id, proposal.id, proposal.digest, now, proposal.expires_at)
    return proposal


def _approver_client(app, monkeypatch, seen):
    app.action_rows = app.store
    app.store.upsert_principal("alice", "human", "approver", ["lab"], PasswordHash.recommended().hash(PASSWORD))
    api = build_api(app)
    client = TestClient(api)
    auth = _login(client, "alice")
    monkeypatch.setattr(api.state.second_factor, "privileged_ready", lambda user, session: True)
    monkeypatch.setattr(api.state.second_factor, "consume_step_up",
                        lambda token, user, session, obj: seen.append((token, user, obj)))
    return client, auth


def test_a_denial_needs_a_reason_and_is_audited(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    seen = []
    client, auth = _approver_client(app, monkeypatch, seen)
    proposal = _pending(app, "appr_deny")
    path = "/api/v1/ops/approvals/appr_deny/answer"
    body = {"decision": "denied", "proposal_digest": proposal.digest, "step_up_token": "once"}
    assert client.post(path, headers=auth, json=body).status_code == 422
    assert client.post(path, headers=auth, json={**body, "reason": "   "}).status_code == 422
    assert seen == []
    result = client.post(path, headers=auth, json={**body, "reason": "the cache owner is restoring it"})
    assert result.status_code == 200, result.text
    [row] = [r[1] for r in app.store.audit_chain() if r[1]["event"] == "action.approval_answered"]
    assert row["detail"]["decision"] == "denied" and row["detail"]["reason"] == "the cache owner is restoring it"


def test_an_answer_and_its_audit_row_are_atomic(make_app):  # noqa: F811
    app = make_app()
    proposal = _pending(app, "appr_atomic")
    at = datetime.now(timezone.utc)
    app.store.append(AuditRecord(audit_id="aud_taken", incident_id=None, at=at, category="decision",
                                 event="x", actor="alice", detail={}))
    taken = AuditRecord(audit_id="aud_taken", incident_id=None, at=at, category="decision",
                        event="action.approval_answered", actor="alice", detail={})
    with pytest.raises(sqlite3.IntegrityError):
        app.store.answer_action_approval("appr_atomic", proposal.digest, "alice", "approved", at, audit=taken)
    assert app.store.get_action_approval("appr_atomic")["state"] == "pending"
    assert app.store.get_resume_intent("appr_atomic") is None


def test_a_target_hold_is_released_with_a_step_up_and_audited(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    seen = []
    client, auth = _approver_client(app, monkeypatch, seen)
    target = "vm-166/container:argus-lab-cache"
    placed = client.post("/api/v1/ops/holds", headers=auth,
                         json={"target": target, "reason": "maintenance", "step_up_token": "one"}).json()
    path = f"/api/v1/ops/holds/{placed['id']}/release"
    assert client.post(path, headers=auth, json={"reason": "done"}).status_code == 422     # no step-up
    result = client.post(path, headers=auth, json={"reason": "done", "step_up_token": "two"})
    assert result.status_code == 200, result.text
    assert seen[-1] == ("two", "alice", f"hold-release:{placed['id']}")
    assert app.store.active_target_holds(target, datetime.now(timezone.utc)) == []
    assert any(r[1]["event"] == "action.hold_released" and r[1]["actor"] == "alice" for r in app.store.audit_chain())
    assert client.post(path, headers=auth, json={"reason": "again", "step_up_token": "three"}).status_code == 409


def test_the_emergency_stop_is_not_released_from_the_api(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    seen = []
    client, auth = _approver_client(app, monkeypatch, seen)
    placed = client.post("/api/v1/ops/holds", headers=auth,
                         json={"target": "*", "reason": "stop", "step_up_token": "one"}).json()
    result = client.post(f"/api/v1/ops/holds/{placed['id']}/release", headers=auth,
                         json={"reason": "over", "step_up_token": "two"})
    assert result.status_code == 409 and "CLI" in result.json()["detail"]
    assert app.store.active_target_holds("*", datetime.now(timezone.utc)) == [placed["id"]]
    assert seen == [("one", "alice", "hold:" + hashlib.sha256(b"*").hexdigest())]


def test_a_host_hold_blocks_an_approval_on_that_host(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    seen = []
    client, auth = _approver_client(app, monkeypatch, seen)
    assert client.post("/api/v1/ops/holds", headers=auth,
                       json={"target": "vm-999", "reason": "x", "step_up_token": "one"}).status_code == 422
    assert client.post("/api/v1/ops/holds", headers=auth,
                       json={"target": "vm-166", "reason": "lease", "step_up_token": "one"}).status_code == 201
    proposal = _pending(app, "appr_host")
    response = client.post("/api/v1/ops/approvals/appr_host/answer", headers=auth, json={
        "decision": "approved", "proposal_digest": proposal.digest, "step_up_token": "two"})
    assert response.status_code == 409 and "hold" in response.json()["detail"]
    listed = client.get("/api/v1/ops/holds", headers=auth, params={"target": "vm-166/container:argus-lab-cache"})
    assert [h["target"] for h in listed.json()] == ["vm-166"]          # the UI sees the hold that refuses it


def test_the_cli_places_and_releases_holds_with_an_audit_row(make_app, monkeypatch, capsys):  # noqa: F811
    import argus.__main__ as cli
    app = make_app()
    monkeypatch.setattr(cli, "make_store", lambda settings: app.store)
    monkeypatch.setattr(cli, "hold_inventory", lambda settings: app.inventory)
    cli.hold(cli.build_parser().parse_args(["hold", "place", "*", "--reason", "drill", "--as", "conantkd"]))
    [hold_id] = app.store.active_target_holds("*", datetime.now(timezone.utc))
    cli.hold(cli.build_parser().parse_args(["hold", "release", hold_id, "--reason", "drill over", "--as", "conantkd"]))
    assert app.store.active_target_holds("*", datetime.now(timezone.utc)) == []
    events = [r[1]["event"] for r in app.store.audit_chain() if r[1]["actor"] == "conantkd"]
    assert events == ["action.hold_placed", "action.hold_released"]
    assert hold_id in capsys.readouterr().out


def test_the_pending_list_shows_answerable_approvals_in_scope(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    seen = []
    client, auth = _approver_client(app, monkeypatch, seen)
    first = _pending(app, "appr_list_a", risk="amber")
    _pending(app, "appr_list_b")
    app.store.answer_action_approval("appr_list_b", app.store.get_action_approval("appr_list_b")["proposal_digest"],
                                     "alice", "denied", datetime.now(timezone.utc))
    listed = client.get("/api/v1/ops/approvals", headers=auth)
    assert listed.status_code == 200, listed.text
    assert listed.json() == [{
        "id": "appr_list_a", "incident_id": first.input.incident_id, "capability": "container.start",
        "target": first.input.target, "risk": "amber", "verdict": "agree",
        "expires_at": first.expires_at.isoformat()}]
    app.store.upsert_principal("bob", "human", "approver", ["other"], PasswordHash.recommended().hash(PASSWORD))
    assert client.get("/api/v1/ops/approvals", headers=_login(client, "bob")).json() == []   # outside bob's scope


def test_the_pending_list_is_filled_after_filtering_not_before(make_app, monkeypatch):  # noqa: F811
    """#347 review: 50 older approvals that the caller may not see (here: they no longer verify) must not hide a later
    one that the caller can answer."""
    import argus.application.approval_view as views
    hidden = {f"appr_hidden_{i:02d}" for i in range(55)}
    real = views.approval_view

    def view(rows, approval_id):                                        # the older 55 no longer verify
        if approval_id in hidden:
            raise views.ApprovalViewRefused("binding changed")
        return real(rows, approval_id)
    monkeypatch.setattr(views, "approval_view", view)                   # before build_api imports it
    app = make_app()
    client, auth = _approver_client(app, monkeypatch, [])
    start = datetime.now(timezone.utc) - timedelta(minutes=5)
    for i in range(55):
        proposal = freeze_proposal(candidate(), at=start)
        app.store.add_action_proposal(proposal)
        app.store.add_judge_verdict(proposal.id, "test-judge", {
            "verdict": "agree", "risk": "green", "reasons": [], "checks": {}, "proposal_digest": proposal.digest,
        }, start)
        app.store.add_action_approval(f"appr_hidden_{i:02d}", proposal.id, proposal.digest,
                                      start + timedelta(seconds=i), proposal.expires_at)
    _pending(app, "appr_visible")
    assert [a["id"] for a in client.get("/api/v1/ops/approvals", headers=auth).json()] == ["appr_visible"]
    now = datetime.now(timezone.utc)
    first = app.store.list_pending_approvals(now, limit=10)
    rest = app.store.list_pending_approvals(now, limit=100, after=first[-1])
    assert len(first) == 10 and first[-1] not in rest and len(first) + len(rest) == 56      # keyset pages


def test_the_store_lists_only_pending_unexpired_approvals(make_app):  # noqa: F811
    app = make_app()
    _pending(app, "appr_store_a")
    now = datetime.now(timezone.utc)
    assert app.store.list_pending_approvals(now) == ["appr_store_a"]
    assert app.store.list_pending_approvals(now + timedelta(days=1)) == []
