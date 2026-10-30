"""T-0016: the operator console's whole path as the deployed UI walks it, on the real API (in process).

What the UI cannot try from a laptop (the SSH tunnel bypasses the edge, so the private path never holds there):
- `/me` tells the access dialog how many keys a person has and whether this session was confirmed with one;
- the ordinary session (the UI's investigate token) is refused by the console, and that refusal alerts the team;
- the private login (ACR-0032), confirmed with a key, opens the console: `help` lists the commands, a command runs;
- the record of the console session: who, when, the reason, each command and the end, all in the incident's audit.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from argus.adapters.inbound.http import build_api
from argus.infrastructure.security_alerts import ALERT_EVENTS
from test_console_routes import fake_invoke, url
from test_core import incident, make_app  # noqa: F401

PASSWORD = "a-long-password"
PRIVATE = {"X-Argus-Ops": "1", "X-Argus-Edge": "1", "X-Real-IP": "192.0.2.10"}   # through the edge's private path
EDGE = {"X-Argus-Edge": "1", "X-Real-IP": "192.0.2.10"}                          # through the public edge


def deployed(app, monkeypatch, keys=2):
    """The API as vm-095 runs it with the console on: second factor configured, the edge's name, the action routes."""
    monkeypatch.setenv("ARGUS_OPERATOR_CONSOLE", "1")
    app.settings.webauthn_rp_id, app.settings.webauthn_origin = "argus.example", "https://argus.example"
    app.settings.ops_peer = "testclient"
    app.action_rows = app.store
    app.store.upsert_principal("alice", "human", "approver", ["lab"], PasswordHash.recommended().hash(PASSWORD))
    api = build_api(app)
    monkeypatch.setattr(api.state.second_factor, "credentials", lambda principal: [{}] * keys)
    return TestClient(api)


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def ui_login(client):
    """The ordinary login the UI makes through the public edge (ACR-0012: scope=investigate)."""
    r = client.post("/api/v1/auth/token", data={"username": "alice", "password": PASSWORD, "scope": "investigate"},
                    headers=EDGE)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def private_login(app, client, confirmed=True):
    r = client.post("/api/v1/ops/auth/token", data={"username": "alice", "password": PASSWORD}, headers=PRIVATE)
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    if confirmed:   # what the WebAuthn login ceremony records (tests/test_acr0018_webauthn.py covers the ceremony)
        import jwt
        from argus.domain.model import utcnow
        app.store.set_session_second_factor(jwt.decode(token, options={"verify_signature": False})["jti"], utcnow())
    return token


@pytest.mark.parametrize("keys", [0, 1, 2])
def test_me_tells_the_access_dialog_the_keys_and_the_confirmation(make_app, monkeypatch, keys):  # noqa: F811
    client = deployed(make_app(), monkeypatch, keys)
    me = client.get("/api/v1/me", headers={**bearer(ui_login(client)), **EDGE}).json()
    assert me["second_factor"] == {"enrolled": keys, "verified": False} and me["access"] == "investigate"


def test_the_ordinary_session_cannot_use_the_console_and_the_refusal_alerts(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    inc = incident(app, "vm-166/container:argus-lab-api")
    client = deployed(app, monkeypatch)
    token = ui_login(client)
    assert client.get(url(inc, "commands"), headers={**bearer(token), **PRIVATE}).status_code == 403
    rows = app.store.audit_since(inc.opened_at.replace(year=2020), ("security.console_refused",))
    assert rows and rows[-1].actor == "alice" and "security.console_refused" in ALERT_EVENTS


def test_a_private_session_confirmed_with_a_key_opens_the_console_and_everything_is_recorded(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    inc = incident(app, "vm-166/container:argus-lab-api")
    fake_invoke(app)
    client = deployed(app, monkeypatch)

    unconfirmed = private_login(app, client, confirmed=False)
    me = client.get("/api/v1/me", headers={**bearer(unconfirmed), **PRIVATE}).json()
    assert me["access"] == "ops" and me["second_factor"] == {"enrolled": 2, "verified": False}   # case 3: the key next

    token = private_login(app, client)
    auth = {**bearer(token), **PRIVATE}
    me = client.get("/api/v1/me", headers=auth).json()
    assert me["access"] == "ops" and me["second_factor"] == {"enrolled": 2, "verified": True}    # case 4: the reason

    commands = client.get(url(inc, "commands"), headers=auth).json()["commands"]
    usages = {c["usage"] for c in commands}
    assert {"help", "status", "cache status", "worker status", "net diff <service>"} <= usages

    opened = client.post(url(inc, "sessions"), headers=auth, json={"reason": "Check the API"}).json()
    helped = client.post(url(inc, "execute"), headers=auth, json={"input": "help"}).json()
    assert helped["status"] == "ok" and any("cache status" in line for line in helped["output"])
    status = client.post(url(inc, "execute"), headers=auth, json={"input": "status"}).json()
    assert status["status"] == "ok" and status["output"]
    refused = client.post(url(inc, "execute"), headers=auth, json={"input": "ls -la"}).json()
    assert refused["status"] == "rejected"
    client.post(url(inc, f"sessions/{opened['session_id']}/close"), headers=auth, json={"why": "disconnect"})

    # the incident's Audit tab: who, when, why, each command and the end
    audit = client.get(f"/api/v1/incidents/{inc.id}", headers=auth).json()["audit"]
    events = [(a["event"], a["actor"]) for a in audit]
    assert ("console.session_opened", "alice") in events and ("console.session_closed", "alice") in events
    assert sum(1 for e, _ in events if e == "console.command") >= 2
    assert ("console.refused", "alice") in events                                     # `ls -la` is on record too
    opened_row = next(a for a in audit if a["event"] == "console.session_opened")
    assert opened_row["detail"]["reason"] == "Check the API" and opened_row["at"]
    # the history the console shows: each input, its output and who typed it
    history = client.get(url(inc, "history"), headers=auth).json()["entries"]
    assert [h["input"] for h in history] == ["help", "status", "ls -la"] and {h["by"] for h in history} == {"alice"}


def test_one_variable_turns_the_console_on_for_the_api_and_the_ui_build():
    """The deployed UI is built in the image: without VITE_ARGUS_CONSOLE it never shows the console. The UI build takes
    it from ARGUS_OPERATOR_CONSOLE, the API's own flag, so both are on or off together (off by default)."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "deploy/ui/Dockerfile").read_text(encoding="utf-8")
    assert "ARG VITE_ARGUS_CONSOLE=0" in dockerfile and "ENV VITE_ARGUS_CONSOLE=$VITE_ARGUS_CONSOLE" in dockerfile
    assert dockerfile.index("ENV VITE_ARGUS_CONSOLE") < dockerfile.index("RUN npm run build")
    compose = (root / "deploy/ui/compose.ui.yml").read_text(encoding="utf-8")
    assert 'VITE_ARGUS_CONSOLE: "${ARGUS_OPERATOR_CONSOLE:-0}"' in compose
    core = (root / "deploy/vm-095/compose.core.yml").read_text(encoding="utf-8")
    agent = core[core.index("  argus-v18-agent:"):core.index("argus-v18-worker:")]
    assert "ARGUS_OPERATOR_CONSOLE: ${ARGUS_OPERATOR_CONSOLE:-0}" in agent      # the API itself sees the flag
