"""Phase 19 draft: a frozen approval can be inspected only through the private contract."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from argus.actions.remediation import freeze_proposal
from argus.adapters.inbound.http import build_api
from test_core import make_app  # noqa: F401
from test_phase18_remediation import candidate


PASSWORD = "a-long-password"


def _login(client, user):
    token = client.post("/api/v1/auth/token", data={"username": user, "password": PASSWORD}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_approval_view_is_unmounted_without_explicit_action_rows(make_app):  # noqa: F811
    app = make_app()
    app.store.upsert_principal("alice", "human", "operator", ["lab"], PasswordHash.recommended().hash(PASSWORD))
    client = TestClient(build_api(app))
    auth = _login(client, "alice")
    assert client.get("/api/v1/ops/approvals/appr_missing", headers=auth).status_code == 404
    assert client.post("/api/v1/ops/approvals/appr_missing/answer", headers=auth, json={}).status_code == 404
    assert "approve_action" not in client.get("/api/v1/me", headers=auth).json()["permissions"]


def test_approval_view_requires_human_privilege_and_refuses_corrupt_binding(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    app.action_rows = app.store  # explicit draft-only injection; production wiring has no action_rows
    password = PasswordHash.recommended().hash(PASSWORD)
    for user, kind, role in (("alice", "human", "operator"), ("vera", "human", "viewer"),
                             ("bot", "service", "operator")):
        app.store.upsert_principal(user, kind, role, ["lab"], password)
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
    alice, vera, bot = (_login(client, user) for user in ("alice", "vera", "bot"))
    assert client.get(path, headers=alice).status_code == 403  # no second factor
    monkeypatch.setattr(api.state.second_factor, "privileged_ready", lambda user, session: True)
    assert client.get(path, headers=vera).status_code == 403
    assert client.get(path, headers=bot).status_code == 403
    result = client.get(path, headers=alice)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["proposal"]["digest"] == proposal.digest
    assert body["proposal"]["input"]["target_identity"] == {"container_id": "cache-1"}
    assert body["judge"]["risk"] == "amber"
    assert body["state"] == "pending"
    assert "step_up_object" not in body  # no answer flow is enabled in this draft

    original = app.store.get_action_approval
    monkeypatch.setattr(app.store, "get_action_approval", lambda key: {
        **original(key), "proposal_digest": "0" * 64,
    })
    assert client.get(path, headers=alice).status_code == 409


def test_answer_needs_digest_and_single_use_step_up(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    app.action_rows = app.store
    app.store.upsert_principal("alice", "human", "operator", ["lab"], PasswordHash.recommended().hash(PASSWORD))
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
            "confirmation_target": "argus-lab-cache"}
    assert client.post(path, headers=auth, json=body).status_code == 403
    monkeypatch.setattr(api.state.second_factor, "privileged_ready", lambda user, session: True)
    seen = []
    monkeypatch.setattr(api.state.second_factor, "consume_step_up",
                        lambda token, user, session, obj: seen.append((token, user, session, obj)))
    assert client.post(path, headers=auth, json={**body, "proposal_digest": "0" * 64}).status_code == 409
    assert seen == []
    assert client.post(path, headers=auth, json={**body, "confirmation_target": "wrong"}).status_code == 409
    assert seen == []
    result = client.post(path, headers=auth, json=body)
    assert result.status_code == 200, result.text
    assert result.json() == {"state": "approved"}
    assert seen[0][0:2] == ("step-up", "alice")
    assert seen[0][3] == f"approval:appr_red:{proposal.digest}"
    assert app.store.get_action_approval("appr_red")["actor"] == "alice"
    assert client.post(path, headers=auth, json=body).status_code == 409
