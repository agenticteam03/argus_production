"""An incident's page shows its supervised action, and its audit says which operator approved it and what ran.

In the S4 rehearsal the approval was on the global audit only (no incident) and the execution left no line at all, so
the incident told nobody that an operator had approved a restart."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from argus.actions.remediation import freeze_proposal
from argus.adapters.inbound.http import build_api
from test_core import incident, make_app  # noqa: F401
from test_phase18_remediation import TARGET, candidate

PASSWORD = "a-long-password"


def test_the_answer_lands_on_the_incidents_audit_and_its_page_shows_the_action(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    app.action_rows = app.store
    app.store.upsert_principal("alice", "human", "approver", ["lab"], PasswordHash.recommended().hash(PASSWORD))
    inc = incident(app, "vm-166/container:argus-lab-api")
    now = datetime.now(timezone.utc)
    proposal = freeze_proposal(candidate(incident_id=inc.id), at=now)
    app.store.add_action_proposal(proposal)
    app.store.add_judge_verdict(proposal.id, "test-judge", {
        "verdict": "agree", "risk": "green", "reasons": ["The cache is down."], "checks": {},
        "proposal_digest": proposal.digest}, now)
    app.store.add_action_approval("appr_trail", proposal.id, proposal.digest, now, proposal.expires_at)
    api = build_api(app)
    client = TestClient(api)
    token = client.post("/api/v1/auth/token", data={"username": "alice", "password": PASSWORD}).json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}
    monkeypatch.setattr(api.state.second_factor, "privileged_ready", lambda user, session: True)
    monkeypatch.setattr(api.state.second_factor, "consume_step_up", lambda *a: None)

    page = client.get(f"/api/v1/incidents/{inc.id}", headers=auth).json()
    assert page["action"]["capability"] == "container.start" and page["action"]["target"] == TARGET
    assert page["action"]["judge"] == {"verdict": "agree", "risk": "green", "reasons": ["The cache is down."]}
    assert page["action"]["approval"]["state"] == "pending" and page["action"]["action"] is None

    answer = client.post("/api/v1/ops/approvals/appr_trail/answer", headers=auth, json={
        "decision": "approved", "proposal_digest": proposal.digest, "step_up_token": "step-up",
        "confirmation_target": TARGET})
    assert answer.status_code == 200, answer.text
    page = client.get(f"/api/v1/incidents/{inc.id}", headers=auth).json()
    assert page["action"]["approval"]["state"] == "approved" and page["action"]["approval"]["answered_by"] == "alice"
    [line] = [a for a in page["audit"] if a["event"] == "action.approval_answered"]
    assert line["actor"] == "alice" and line["detail"]["decision"] == "approved"
    assert "digest" not in str(page["action"])


def test_without_action_rows_the_page_has_no_action(make_app):  # noqa: F811
    app = make_app()
    app.action_rows = None
    app.store.upsert_principal("olga", "human", "operator", ["lab"], PasswordHash.recommended().hash(PASSWORD))
    inc = incident(app, "vm-166/container:argus-lab-api")
    client = TestClient(build_api(app))
    token = client.post("/api/v1/auth/token", data={"username": "olga", "password": PASSWORD}).json()["access_token"]
    assert "action" not in client.get(f"/api/v1/incidents/{inc.id}",
                                      headers={"Authorization": f"Bearer {token}"}).json()
