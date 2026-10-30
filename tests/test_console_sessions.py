"""T-0016 (ACR-0043 access): who opened the operator console, when, why, and who was refused.

- Opening a console session records the person, the incident and the reason they typed (`console.session_opened`, an
  audit row of the incident, so it shows in its Audit tab); closing it records why (`console.session_closed`).
- A refused use of the console by an authenticated principal (a viewer, a service or agent, a narrowed token) is a
  security event (`security.console_refused`) that the security alerts send to the team's Telegram route.
- The same gates as the other console routes: the flag, the private path, a person's own full session.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from argus.infrastructure.security_alerts import ALERT_EVENTS
from test_console_routes import PRIVATE, PUBLIC, login, setup, url
from test_core import incident, make_app  # noqa: F401

API = "vm-166/container:argus-lab-api"
EVENTS = ("console.session_opened", "console.session_closed", "security.console_refused")


def rows(app, event):
    return [r for r in app.store.audit_since(datetime(2020, 1, 1, tzinfo=timezone.utc), EVENTS) if r.event == event]


@pytest.fixture
def ctx(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    inc = incident(app, API)
    client = setup(app, monkeypatch)
    return app, inc, client, login(client)


def open_session(client, headers, inc, reason="Check why the cache is down"):
    return client.post(url(inc, "sessions"), headers={**headers, **PRIVATE}, json={"reason": reason})


def test_opening_a_session_records_the_person_the_incident_and_the_reason(ctx):
    app, inc, client, auth = ctx
    got = open_session(client, auth, inc)
    assert got.status_code == 200
    body = got.json()
    assert body["session_id"].startswith("csn_") and body["limit_min"] == 30
    assert body["opened_at"] < body["expires_at"]
    [row] = rows(app, "console.session_opened")
    assert (row.actor, row.incident_id, row.category) == ("olga", inc.id, "access")
    assert row.detail["reason"] == "Check why the cache is down" and row.detail["session"] == body["session_id"]


@pytest.mark.parametrize("reason", ["", "ok", "x" * 301])
def test_the_reason_is_required_and_bounded(ctx, reason):
    app, inc, client, auth = ctx
    assert open_session(client, auth, inc, reason).status_code == 422
    assert rows(app, "console.session_opened") == []


@pytest.mark.parametrize("why", ["disconnect", "time_limit", "signed_out"])
def test_closing_a_session_records_why(ctx, why):
    app, inc, client, auth = ctx
    sid = open_session(client, auth, inc).json()["session_id"]
    got = client.post(url(inc, f"sessions/{sid}/close"), headers={**auth, **PRIVATE}, json={"why": why})
    assert got.status_code == 200 and got.json() == {"closed": True}
    [row] = rows(app, "console.session_closed")
    assert row.actor == "olga" and row.incident_id == inc.id and row.detail == {"session": sid, "why": why}


def test_an_unknown_close_reason_or_session_id_is_refused(ctx):
    app, inc, client, auth = ctx
    sid = open_session(client, auth, inc).json()["session_id"]
    assert client.post(url(inc, f"sessions/{sid}/close"), headers={**auth, **PRIVATE},
                       json={"why": "whatever"}).status_code == 422
    assert client.post(url(inc, "sessions/not-a-session/close"), headers={**auth, **PRIVATE},
                       json={"why": "disconnect"}).status_code == 404


@pytest.mark.parametrize("user", ["vera", "bot", "agent"])
def test_a_refused_use_of_the_console_is_a_security_event(ctx, user):
    app, inc, client, _ = ctx
    got = open_session(client, login(client, user), inc)
    assert got.status_code == 403
    [row] = rows(app, "security.console_refused")
    assert row.actor == user and row.category == "security" and row.detail["path"].endswith("/sessions")
    assert rows(app, "console.session_opened") == []


def test_a_narrowed_token_is_refused_and_alerted_too(ctx):
    """A UI's investigate token: its POST stops at the token scope (already an alerting event); its GET at the console."""
    app, inc, client, _ = ctx
    narrowed = login(client, "olga", "investigate")
    assert open_session(client, narrowed, inc).status_code == 403
    assert client.get(url(inc, "commands"), headers={**narrowed, **PRIVATE}).status_code == 403
    [row] = rows(app, "security.console_refused")
    assert row.detail["reason"] == "the console is for a person's own session"
    assert "access.investigate_scope_refused" in ALERT_EVENTS


def test_the_other_console_routes_audit_a_refusal_too(ctx):
    app, inc, client, _ = ctx
    assert client.get(url(inc, "commands"), headers={**login(client, "vera"), **PRIVATE}).status_code == 403
    assert len(rows(app, "security.console_refused")) == 1


def test_a_console_refusal_reaches_the_teams_alert_route():
    assert "security.console_refused" in ALERT_EVENTS


def test_off_the_private_path_or_with_the_flag_off_the_routes_do_not_exist(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    inc = incident(app, API)
    client = setup(app, monkeypatch)
    auth = login(client)
    assert client.post(url(inc, "sessions"), headers={**auth, **PUBLIC}, json={"reason": "x" * 10}).status_code == 404
    off = setup(make_app(), monkeypatch, flag="0")
    assert off.post(url(inc, "sessions"), headers={**login(off), **PRIVATE}, json={"reason": "x" * 10}).status_code == 404
