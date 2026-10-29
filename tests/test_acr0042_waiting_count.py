"""ACR-0042: an approver learns how many approvals wait (the UI's bell) with an ordinary token and no second factor.

The count uses the private list's own filter (pending, still verifying, in the approver's scope) and carries nothing
else: no id, incident, action or target. Seeing and deciding an approval stays private and privileged.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from argus.adapters.inbound.http import build_api
from test_core import make_app  # noqa: F401
from test_phase19_approval_view import PASSWORD, _pending

PATH = "/api/v1/approvals/waiting"


def _client(app, scope="investigate"):
    app.action_rows = app.store
    password = PasswordHash.recommended().hash(PASSWORD)
    for user, kind, role, scopes in (("alice", "human", "approver", ["lab"]), ("bob", "human", "approver", ["other"]),
                                     ("olga", "human", "operator", ["lab"]), ("vera", "human", "viewer", ["lab"]),
                                     ("bot", "service", "approver", ["lab"])):
        app.store.upsert_principal(user, kind, role, scopes, password)
    client = TestClient(build_api(app))

    def login(user, scope=scope):
        data = {"username": user, "password": PASSWORD, **({"scope": scope} if scope else {})}
        token = client.post("/api/v1/auth/token", data=data).json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    return client, login


def test_an_approver_counts_the_waiting_approvals_in_scope_with_an_ordinary_token(make_app):  # noqa: F811
    app = make_app()
    client, login = _client(app)
    alice = login("alice")
    assert client.get(PATH, headers=alice).json() == {"waiting": 0}
    _pending(app, "appr_count_a")
    _pending(app, "appr_count_b")
    app.store.answer_action_approval("appr_count_b", app.store.get_action_approval("appr_count_b")["proposal_digest"],
                                     "alice", "denied", datetime.now(timezone.utc))
    result = client.get(PATH, headers=alice)
    assert result.status_code == 200, result.text
    assert result.json() == {"waiting": 1}                              # a count only: nothing else to read
    assert client.get(PATH, headers=login("alice", scope="read")).json() == {"waiting": 1}
    assert client.get(PATH, headers=login("bob")).json() == {"waiting": 0}            # outside bob's scope
    assert client.get("/api/v1/ops/approvals", headers=alice).status_code == 403      # the list stays privileged


def test_only_a_human_approver_may_count(make_app):  # noqa: F811
    app = make_app()
    client, login = _client(app)
    _pending(app, "appr_count_c")
    for user in ("olga", "vera"):
        assert client.get(PATH, headers=login(user)).status_code == 403
    assert client.get(PATH, headers=login("bot", scope=None)).status_code == 403
    assert client.get(PATH).status_code == 401


def test_me_lists_the_count_for_an_approver_only(make_app):  # noqa: F811
    app = make_app()
    client, login = _client(app)
    me = client.get("/api/v1/me", headers=login("alice")).json()
    assert "count_waiting_approvals" in me["actions"] and "approve_action" not in me["actions"]
    assert "count_waiting_approvals" not in client.get("/api/v1/me", headers=login("olga")).json()["actions"]


def test_without_action_rows_there_is_nothing_to_count(make_app):  # noqa: F811
    app = make_app()
    client, login = _client(app)
    app.action_rows = None
    client = TestClient(build_api(app))
    token = client.post("/api/v1/auth/token", data={"username": "alice", "password": PASSWORD,
                                                    "scope": "investigate"}).json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}
    assert client.get(PATH, headers=auth).status_code == 404
    assert "count_waiting_approvals" not in client.get("/api/v1/me", headers=auth).json()["actions"]
