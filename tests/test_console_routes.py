"""CON-2 (ACR-0043): the console's routes. Private prefix only, `investigate` on a person's own full session, the
audit and the read quota; every read goes through the runner's guarded invoke (faked here)."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from argus.adapters.inbound.http import build_api
from argus.console.registry import catalog
from test_core import incident, make_app  # noqa: F401

PASSWORD = "a-long-password"
PRIVATE = {"X-Argus-Ops": "1"}
PUBLIC = {"X-Argus-Ops": "0"}


def url(inc, what):
    return f"/api/v1/ops/console/incidents/{getattr(inc, 'id', inc)}/{what}"
API = "vm-166/container:argus-lab-api"


def audit(app, inc):
    """The incident's console audit rows."""
    events = ("console.command", "console.refused", "console.quota_refused", "console.budget_refused")
    return [r for r in app.store.audit_since(datetime(2020, 1, 1, tzinfo=timezone.utc), events)
            if r.incident_id == inc.id]


def fake_invoke(app, answers=None, calls=None):
    """Replaces the runner's guarded invoke: answers every read from a table, records each one."""
    def invoke(ctx, name, arguments):
        if calls is not None:
            calls.append((name, arguments["target"], ctx.caller))
        values = (answers or {}).get(name, {"state": "running", "health": "healthy", "restart_count": 0,
                                           "started_at": "S-START"})
        return SimpleNamespace(status="ok", model_text=f"{name} text", values=values, error_category=None), None
    app.runner.invoke = invoke


def setup(app, monkeypatch, *, flag="1", **env):
    monkeypatch.setenv("ARGUS_OPERATOR_CONSOLE", flag)
    for key, value in env.items():
        monkeypatch.setenv(key, str(value))
    app.settings.ops_peer = "testclient"            # TestClient's peer plays the edge
    password = PasswordHash.recommended().hash(PASSWORD)
    for user, kind, role in (("olga", "human", "operator"), ("vera", "human", "viewer"),
                             ("bot", "service", "operator"), ("agent", "agent", "operator")):
        app.store.upsert_principal(user, kind, role, ["lab"], password)
    return TestClient(build_api(app))


def login(client, user="olga", scope=None):
    data = {"username": user, "password": PASSWORD, **({"scope": scope} if scope else {})}
    return {"Authorization": f"Bearer {client.post('/api/v1/auth/token', data=data).json()['access_token']}"}


def run(client, headers, inc, text, **extra):
    return client.post(url(inc, "execute"), headers={**headers, **PRIVATE}, json={"input": text, **extra})


@pytest.fixture
def ctx(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    inc = incident(app, API)
    calls: list = []
    fake_invoke(app, calls=calls)
    client = setup(app, monkeypatch)
    return SimpleNamespace(app=app, inc=inc, client=client, calls=calls, auth=login(client))


def test_the_catalogue_is_the_registry(ctx):
    got = ctx.client.get(url(ctx.inc, "commands"), headers={**ctx.auth, **PRIVATE})
    assert got.status_code == 200 and got.json() == {"commands": catalog()}
    assert set(got.json()["commands"][0]) == {"id", "usage", "class", "scenario", "summary"}


def test_a_read_runs_through_invoke_and_answers_with_its_output(ctx):
    got = run(ctx.client, ctx.auth, ctx.inc, "cache status")

    assert got.status_code == 200
    body = got.json()
    assert set(body) == {"command_id", "input", "command", "class", "status", "output", "started_at", "finished_at"}
    assert (body["input"], body["command"], body["class"]) == ("cache status", "cache.status", "read")
    assert body["status"] == "ok" and body["command_id"].startswith("cmd_")
    assert "state=running" in "\n".join(body["output"]) and "S-START" in "\n".join(body["output"])
    assert body["started_at"] <= body["finished_at"]
    assert ctx.calls == [("container.status", "vm-166/container:argus-lab-cache", "console:olga")]


def test_the_command_is_stored_in_the_incident_history_and_history_reads_it_back(ctx):
    command_id = run(ctx.client, ctx.auth, ctx.inc, "cache status", suggestion_id="sug_1").json()["command_id"]

    rows = ctx.app.store.console_history(ctx.inc.id)
    assert [(r["command_id"], r["person"], r["command"], r["cls"], r["status"], r["suggestion_id"]) for r in rows] == [
        (command_id, "olga", "cache.status", "read", "ok", "sug_1")]
    assert rows[0]["output_truncated"] is False
    shown = run(ctx.client, ctx.auth, ctx.inc, "history").json()
    assert shown["status"] == "ok" and "cache status" in "\n".join(shown["output"])


def test_a_long_output_is_stored_cut_at_4_kb_with_the_flag(ctx):
    fake_invoke(ctx.app, {"metrics.cpu_history": {"points": []}})
    ctx.app.runner.invoke = lambda c, n, a: (SimpleNamespace(status="ok", model_text="x" * 6000, values={"points": []},
                                                             error_category=None), None)
    got = run(ctx.client, ctx.auth, ctx.inc, "api cpu").json()

    assert len("\n".join(got["output"])) > 4096                   # the person sees everything
    row = ctx.app.store.console_history(ctx.inc.id)[0]
    assert len(row["output"].encode()) <= 4096 and row["output_truncated"] is True


def test_every_call_is_audited_with_the_console_as_its_source(ctx):
    command_id = run(ctx.client, ctx.auth, ctx.inc, "cache status").json()["command_id"]

    rows = [r for r in audit(ctx.app, ctx.inc) if r.event == "console.command"]
    assert len(rows) == 1
    assert rows[0].actor == "olga" and rows[0].category == "access"
    assert rows[0].detail["source"] == "operator_console" and rows[0].detail["command_id"] == command_id
    assert rows[0].detail["cls"] == "read" and rows[0].detail["command"] == "cache.status"


def test_a_parse_error_is_a_rejected_answer_with_the_terminal_message_and_no_history(ctx):
    got = run(ctx.client, ctx.auth, ctx.inc, "rm -rf /")

    assert got.status_code == 200 and got.json()["status"] == "rejected" and got.json()["output"]
    assert ctx.calls == [] and ctx.app.store.console_history(ctx.inc.id) == []
    assert any(r.event == "console.refused" for r in audit(ctx.app, ctx.inc))


def test_a_write_command_without_a_passkey_session_is_refused(ctx):
    response = run(ctx.client, ctx.auth, ctx.inc, "cache restart")

    assert response.status_code == 403 and "passkey session" in response.json()["detail"]
    assert ctx.calls == []
    assert ctx.app.store.console_history(ctx.inc.id) == []


def test_an_unknown_incident_is_404(ctx):
    for what, call in (("execute", ctx.client.post), ("commands", ctx.client.get), ("history", ctx.client.get)):
        kwargs = {"json": {"input": "help"}} if what == "execute" else {}
        assert call(url("inc_nope", what), headers={**ctx.auth, **PRIVATE}, **kwargs).status_code == 404
    assert ctx.client.get(url("not-an-id", "history"), headers={**ctx.auth, **PRIVATE}).status_code == 404


def test_a_bad_body_is_422(ctx):
    for body in ({}, {"input": "help", "shell": True}, {"input": "help", "incident_id": ctx.inc.id},
                 {"input": "x" * 201}):
        assert ctx.client.post(url(ctx.inc, "execute"), headers={**ctx.auth, **PRIVATE}, json=body).status_code == 422


# --- who may use it --------------------------------------------------------------------------------------------
def test_a_viewer_is_refused(ctx):
    viewer = login(ctx.client, "vera")
    assert run(ctx.client, viewer, ctx.inc, "help").status_code == 403
    assert ctx.client.get(url(ctx.inc, "commands"), headers={**viewer, **PRIVATE}).status_code == 403


@pytest.mark.parametrize("user", ["bot", "agent"])
def test_service_and_agent_principals_are_refused(ctx, user):
    auth = login(ctx.client, user)
    assert run(ctx.client, auth, ctx.inc, "help").status_code == 403
    assert ctx.client.get(url(ctx.inc, "commands"), headers={**auth, **PRIVATE}).status_code == 403
    assert ctx.client.get(url(ctx.inc, "history"), headers={**auth, **PRIVATE}).status_code == 403
    assert ctx.calls == []


@pytest.mark.parametrize("scope", ["read", "investigate"])
def test_a_scoped_token_is_refused_the_console_is_for_the_persons_own_session(ctx, scope):
    auth = login(ctx.client, scope=scope)
    assert run(ctx.client, auth, ctx.inc, "help").status_code == 403
    assert ctx.client.get(url(ctx.inc, "commands"), headers={**auth, **PRIVATE}).status_code == 403
    assert ctx.client.get(url(ctx.inc, "history"), headers={**auth, **PRIVATE}).status_code == 403


def test_the_public_path_answers_404(ctx):
    for headers in (PUBLIC, {}):
        assert ctx.client.get(url(ctx.inc, "commands"), headers={**ctx.auth, **headers}).status_code == 404
        assert ctx.client.get(url(ctx.inc, "history"), headers={**ctx.auth, **headers}).status_code == 404
        assert ctx.client.post(url(ctx.inc, "execute"), headers={**ctx.auth, **headers},
                               json={"input": "help"}).status_code == 404
    assert ctx.calls == []


def test_a_peer_that_is_not_the_edge_cannot_claim_the_private_path(ctx):
    ctx.app.settings.ops_peer = "argus-v18-ui"
    assert ctx.client.get(url(ctx.inc, "commands"), headers={**ctx.auth, **PRIVATE}).status_code == 404


def test_without_the_flag_the_routes_do_not_exist(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    client = setup(app, monkeypatch, flag="0")
    auth = login(client)
    assert client.get(url("inc_x", "commands"), headers={**auth, **PRIVATE}).status_code == 404
    assert client.get(url("inc_x", "history"), headers={**auth, **PRIVATE}).status_code == 404
    assert client.post(url("inc_x", "execute"), headers={**auth, **PRIVATE}, json={"input": "help"}
                       ).status_code == 404


def test_no_token_is_401(ctx):
    assert ctx.client.get(url(ctx.inc, "commands"), headers=PRIVATE).status_code == 401


# --- the read quota --------------------------------------------------------------------------------------------
def test_reads_over_the_quota_answer_429_with_retry_after_and_an_audit_row(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    inc = incident(app, API)
    calls: list = []
    fake_invoke(app, calls=calls)
    client = setup(app, monkeypatch, ARGUS_CONSOLE_READS_PER_MINUTE=2)
    auth = login(client)

    assert [run(client, auth, inc, "cache status").status_code for _ in range(2)] == [200, 200]
    got = run(client, auth, inc, "cache status")

    assert got.status_code == 429 and 1 <= int(got.headers["Retry-After"]) <= 61
    assert len(calls) == 2
    refused = [r for r in audit(app, inc) if r.event == "console.quota_refused"]
    assert len(refused) == 1 and refused[0].actor == "olga" and refused[0].detail["quota"] == "per_minute"


def test_help_history_and_clear_are_not_counted(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    inc = incident(app, API)
    fake_invoke(app)
    client = setup(app, monkeypatch, ARGUS_CONSOLE_READS_PER_MINUTE=1)
    auth = login(client)

    assert [run(client, auth, inc, t).status_code for t in ("help", "history", "clear", "help")] == [200] * 4
    assert run(client, auth, inc, "cache status").status_code == 200
    assert run(client, auth, inc, "help").status_code == 200
    assert run(client, auth, inc, "cache status").status_code == 429


def test_the_quota_is_per_person(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    inc = incident(app, API)
    fake_invoke(app)
    client = setup(app, monkeypatch, ARGUS_CONSOLE_READS_PER_MINUTE=1)
    app.store.upsert_principal("sam", "human", "operator", ["lab"], PasswordHash.recommended().hash(PASSWORD))
    olga, sam = login(client), login(client, "sam")

    assert run(client, olga, inc, "cache status").status_code == 200
    assert run(client, olga, inc, "cache status").status_code == 429
    assert run(client, sam, inc, "cache status").status_code == 200


def test_the_incident_read_budget_is_separate_and_rejects_without_invoking(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    inc = incident(app, API)
    calls: list = []
    fake_invoke(app, calls=calls)
    client = setup(app, monkeypatch, ARGUS_CONSOLE_INCIDENT_READS=1)
    auth = login(client)

    assert run(client, auth, inc, "cache status").json()["status"] == "ok"
    got = run(client, auth, inc, "cache status")
    assert got.status_code == 200 and got.json()["status"] == "rejected" and "budget" in got.json()["output"][0]
    assert len(calls) == 1


def test_the_history_route_returns_the_entries_of_the_mockup_spec_oldest_first(ctx):
    from types import SimpleNamespace

    ctx.app.runner.action_path = SimpleNamespace(executor=SimpleNamespace(gate_open=frozenset({
        ("container.start", "vm-166/container:argus-lab-cache")})))
    ctx.client.app.state.second_factor.privileged_ready = lambda *_: True
    first = run(ctx.client, ctx.auth, ctx.inc, "cache status").json()
    write = run(ctx.client, ctx.auth, ctx.inc, "cache restart")
    assert write.json()["status"] == "needs_confirmation"
    other = incident(ctx.app, API)
    run(ctx.client, ctx.auth, other, "cache status")

    got = ctx.client.get(url(ctx.inc, "history"), headers={**ctx.auth, **PRIVATE})

    assert got.status_code == 200 and list(got.json()) == ["entries"]
    entries = got.json()["entries"]
    assert [e["input"] for e in entries] == ["cache status", "cache restart"]
    assert set(entries[0]) == {"command_id", "input", "command", "class", "status", "output", "by", "started_at",
                               "finished_at"}                              # `analysis` is CON-4's: absent until stored
    assert (entries[0]["command_id"], entries[0]["by"], entries[0]["class"], entries[0]["status"]) == (
        first["command_id"], "olga", "read", "ok")
    assert entries[1]["class"] == "write" and entries[1]["status"] == "needs_confirmation"
    assert isinstance(entries[0]["output"], str) and "state=running" in entries[0]["output"]


def test_a_refused_input_answers_with_a_null_command_and_class(ctx):
    got = run(ctx.client, ctx.auth, ctx.inc, "status; rm").json()
    assert (got["status"], got["input"], got["command"], got["class"]) == ("rejected", "status; rm", None, None)
    assert len(got["output"]) == 1
