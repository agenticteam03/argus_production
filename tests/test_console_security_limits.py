"""Security and limit regression coverage for the Operator console."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pwdlib import PasswordHash

from argus.console.handlers import HANDLERS
from argus.console.parser import ConsoleRefused, parse
from argus.console.registry import COMMANDS, WRITE
from test_console_routes import PRIVATE, audit, fake_invoke, login, run, setup, url
from test_console_write_path import CASES, _case
from test_core import incident, make_app  # noqa: F401


ROOT = Path(__file__).resolve().parents[1]
API = "vm-166/container:argus-lab-api"


@pytest.fixture
def ctx(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    inc = incident(app, API)
    calls = []
    fake_invoke(app, calls=calls)
    client = setup(app, monkeypatch)
    return SimpleNamespace(app=app, inc=inc, calls=calls, client=client, auth=login(client))


def test_every_registered_usage_parses_and_catalogue_is_documented():
    for command in COMMANDS:
        usage = command.usage.replace("<service>", "api").replace(" [--since HH:MM]", " --since 10:30")
        parsed = parse(usage)
        assert parsed.id == command.id
        if command.service_arg:
            assert parsed.args["service"] == "api"
    assert set(HANDLERS) == {c.id for c in COMMANDS if c.cls != WRITE}
    assert {c.id for c in COMMANDS if c.cls == WRITE} == {"cache.restart", "worker.restart", "net.reconnect"}
    docs = (ROOT / "docs" / "API-FOR-UI.md").read_text(encoding="utf-8")
    assert "GET /api/v1/ops/console/incidents/{id}/commands" in docs
    assert "the operator console's allowed commands" in docs


@pytest.mark.parametrize("bad", list(";&|<>$`(){}[]\\\"'*?!~#\n\r\t\x00./"))
def test_each_shell_character_is_refused_alone_and_inside_a_word(bad):
    # Characters can be rejected by either the syntax guard or the allowlisted grammar.
    for text in (bad, f"status{bad}"):
        outcomes = []
        for _ in range(2):
            with pytest.raises(ConsoleRefused) as caught:
                parse(text)
            outcomes.append(str(caught.value))
        assert outcomes[0] == outcomes[1]


@pytest.mark.parametrize("text", [
    "..", "/", "%00", "status\nhelp", "status\thelp", "status；help", "status｜help", "status＆help",
    "status" + chr(0xFF1B) + "help", "status" + chr(0xFF5C) + "help", "status" + chr(0xFF06) + "help",
    "map ../api", "map db", "map api extra", "map",
    pytest.param("CACHE STATUS", marks=pytest.mark.xfail(
        strict=True, reason="Parser normalizes uppercase input; security card requires uppercase to be refused.")),
    "cache restart && x",
    "$(x)", "`x`", "cache restart ; net reconnect api", "status " + "x" * 300,
])
def test_hostile_and_malformed_text_is_refused_with_repeatable_reason(text):
    reasons = []
    for _ in range(2):
        with pytest.raises(ConsoleRefused) as caught:
            parse(text)
        reasons.append(str(caught.value))
    assert reasons[0] == reasons[1] and reasons[0]


def test_refused_inputs_never_reach_a_handler(ctx):
    for text in ("cache restart && x", "map production"):
        response = run(ctx.client, ctx.auth, ctx.inc, text)
        assert response.status_code == 200 and response.json()["status"] == "rejected"
    assert ctx.calls == []
    assert all(row.detail["source"] == "operator_console" for row in audit(ctx.app, ctx.inc))


def test_read_only_and_non_approver_people_cannot_propose_writes(ctx):
    viewer = login(ctx.client, "vera")
    read_only = run(ctx.client, viewer, ctx.inc, "cache restart")
    non_approver = run(ctx.client, ctx.auth, ctx.inc, "cache restart")
    assert read_only.status_code == 403
    assert non_approver.status_code == 403 and "propose_action" in non_approver.json()["detail"]
    assert ctx.app.store.latest_action_proposal_for_incident(ctx.inc.id) is None


def test_yes_on_a_read_is_not_treated_as_a_write_confirmation(ctx):
    response = ctx.client.post(url(ctx.inc, "execute"), headers={**ctx.auth, **PRIVATE},
                               json={"input": "cache status", "confirmation": "yes"})
    assert response.status_code == 200 and response.json()["command"] == "cache.status"
    assert ctx.app.store.latest_action_proposal_for_incident(ctx.inc.id) is None


@pytest.mark.xfail(
    strict=True,
    reason="The API currently accepts confirmation=yes without server-side proof that it showed a prompt first.",
)
def test_yes_without_a_prior_confirmation_prompt_does_not_create_a_proposal(make_app, monkeypatch):  # noqa: F811
    case = _case(make_app, monkeypatch, *CASES[0].values)
    response = case.client.post(url(case.incident, "execute"), headers={**case.auth, **PRIVATE},
                                json={"input": "cache restart", "confirmation": "yes"})
    assert response.json()["status"] == "rejected"
    assert case.app.store.latest_action_proposal_for_incident(case.incident.id) is None


def test_different_write_is_refused_while_an_incident_proposal_is_active(make_app, monkeypatch):  # noqa: F811
    case = _case(make_app, monkeypatch, *CASES[0].values)
    first = case.client.post(url(case.incident, "execute"), headers={**case.auth, **PRIVATE},
                             json={"input": "cache restart", "confirmation": "yes"}).json()
    assert first["status"] == "ok"
    second = case.client.post(url(case.incident, "execute"), headers={**case.auth, **PRIVATE},
                              json={"input": "worker restart", "confirmation": "yes"}).json()
    assert second["status"] == "rejected"
    assert "proposal for this incident is already active" in second["output"][0]
    assert case.app.store.latest_action_proposal_for_incident(case.incident.id).id == first["proposal_id"]


def test_read_quota_21st_per_minute_and_other_person_unaffected(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    inc = incident(app, API)
    fake_invoke(app)
    client = setup(app, monkeypatch, ARGUS_CONSOLE_READS_PER_MINUTE=20)
    olga = login(client)
    app.store.upsert_principal("sam", "human", "operator", ["lab"],
                               PasswordHash.recommended().hash("a-long-password"))
    sam = login(client, "sam")
    assert [run(client, olga, inc, "cache status").status_code for _ in range(20)] == [200] * 20
    refused = run(client, olga, inc, "cache status")
    assert refused.status_code == 429 and int(refused.headers["Retry-After"]) > 0
    assert run(client, sam, inc, "cache status").status_code == 200
    row = next(r for r in audit(app, inc) if r.event == "console.quota_refused")
    assert row.detail["source"] == "operator_console" and row.detail["quota"] == "per_minute"


def test_read_quota_201st_per_hour(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    inc = incident(app, API)
    fake_invoke(app)
    client = setup(app, monkeypatch, ARGUS_CONSOLE_READS_PER_MINUTE=1000,
                   ARGUS_CONSOLE_READS_PER_HOUR=200, ARGUS_CONSOLE_INCIDENT_READS=500)
    auth = login(client)
    assert [run(client, auth, inc, "cache status").status_code for _ in range(200)] == [200] * 200
    refused = run(client, auth, inc, "cache status")
    assert refused.status_code == 429 and int(refused.headers["Retry-After"]) > 0
    row = next(r for r in audit(app, inc) if r.event == "console.quota_refused")
    assert row.detail["source"] == "operator_console" and row.detail["quota"] == "per_hour"


def test_all_routes_are_missing_when_flag_is_off(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    client = setup(app, monkeypatch, flag="0")
    auth = login(client)
    for route, method in (("commands", "get"), ("history", "get"), ("execute", "post")):
        request = getattr(client, method)
        kwargs = {"json": {"input": "help"}} if method == "post" else {}
        assert request(url("missing-inc", route), headers={**auth, **PRIVATE}, **kwargs).status_code == 404


def test_console_audit_rows_have_operator_console_source(ctx):
    run(ctx.client, ctx.auth, ctx.inc, "cache status")
    audits = audit(ctx.app, ctx.inc)
    assert all(row.detail["source"] == "operator_console" for row in audits)


@pytest.mark.xfail(
    strict=True,
    reason="Console output is currently stored verbatim; redaction of fixture secrets is not implemented.",
)
def test_console_redacts_secrets_returned_by_a_read(ctx, monkeypatch):
    secrets = (ctx.auth["Authorization"].split(" ", 1)[1], API, "fixture-private-env-2e9a")
    monkeypatch.setenv("ARGUS_TEST_SECRET", secrets[2])
    ctx.app.runner.invoke = lambda *_args, **_kwargs: (SimpleNamespace(
        status="ok", model_text="read completed", values={"state": " ".join(secrets)}, error_category=None), None)
    run(ctx.client, ctx.auth, ctx.inc, "cache status")
    stored = ctx.app.store.console_history(ctx.inc.id)[0]["output"]
    rows = audit(ctx.app, ctx.inc)
    assert all(secret not in stored and all(secret not in str(row.detail) for row in rows) for secret in secrets)
