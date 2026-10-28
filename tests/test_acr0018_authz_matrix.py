"""ACR-0018 §4 / phase 16 exit proof: the authorization matrix — every API route × role × token kind.

The table below is the declared rule of each route: the permission it needs (or None: any logged-in principal) and
the token kinds that may call it. The test proves the API agrees for every combination, without a token (401), and
that every route of the API is in the table: a new route cannot ship without declaring its permission.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from argus.adapters.inbound.http import ROLE_PERMISSIONS, build_api
from test_core import make_app  # noqa: F401  (fixture)

PASSWORD = "a-long-password"
ROLES = {"vera": "viewer", "olga": "operator", "abe": "approver"}
ALL = ("read", "investigate", "full")
# (method, path) → (permission or None, the token kinds whose access allows it)
MATRIX = {
    ("POST", "/api/v1/auth/logout"): (None, ALL),
    ("GET", "/api/v1/me"): (None, ALL),
    ("POST", "/api/v1/investigations"): ("investigate", ("investigate", "full")),
    ("POST", "/api/v1/incidents/{incident_id}/resolve"): ("resolve_incident", ("investigate", "full")),   # ACR-0041
    ("GET", "/api/v1/targets"): ("view", ALL),
    ("GET", "/api/v1/host-metrics"): ("view", ALL),
    ("GET", "/api/v1/incidents"): ("view", ALL),
    ("GET", "/api/v1/incidents/{incident_id}"): ("view", ALL),
    ("GET", "/api/v1/incidents/{incident_id}/events"): ("view", ALL),
    ("GET", "/api/v1/topology"): ("view", ALL),
    ("GET", "/api/v1/incidents/{incident_id}/metrics"): ("view", ALL),
    ("GET", "/api/v1/target-metrics"): ("view", ALL),
    ("GET", "/api/v1/overview"): ("view", ALL),
    ("GET", "/api/v1/evidence/{evidence_id}"): ("view_evidence", ALL),
    ("GET", "/api/v1/escalations"): ("view", ALL),
    # phase 16 step 3: every token may run its own ceremonies; the ceremony itself needs a credential, a ticket or a
    # step-up (tests/test_acr0018_webauthn.py). Unconfigured here, they answer 503 or 422, never 401 or 403.
    **{("POST", f"/api/v1/auth/webauthn/{c}/{s}"): (None, ALL) for c in ("register", "login", "step-up")
       for s in ("options", "verify")},
    ("GET", "/api/v1/auth/webauthn/credentials"): (None, ALL),
}
UNAUTHENTICATED = {("POST", "/api/v1/auth/token"), ("GET", "/healthz")}
BODY = {("POST", "/api/v1/investigations"): {"target": "vm-166/container:argus-lab-worker", "reason": "matrix"},
        ("POST", "/api/v1/incidents/{incident_id}/resolve"): {"reason": "matrix"}}


@pytest.fixture()
def ui(make_app):
    app = make_app()
    app.action_rows = None      # the routes without the private approval routes (an open gate mounts them; X-9)
    pw = PasswordHash.recommended().hash(PASSWORD)
    for user, role in ROLES.items():
        app.store.upsert_principal(user, "human", role, ["lab"], pw)
    api = build_api(app)
    return api, TestClient(api)


def _routes(api) -> set[tuple[str, str]]:
    return {(m, r.path) for r in api.routes for m in getattr(r, "methods", set()) - {"HEAD"}
            if r.path.startswith("/api/") or r.path == "/healthz"}


def _call(client, method: str, path: str, token: str | None):
    url = path.replace("{incident_id}", "inc_matrix").replace("{evidence_id}", "ev_matrix")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.request(method, url, headers=headers, json=BODY.get((method, path)))


def _token(client, user: str, access: str) -> str:
    data = {"username": user, "password": PASSWORD, **({} if access == "full" else {"scope": access})}
    r = client.post("/api/v1/auth/token", data=data)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_every_route_is_declared(ui):
    api, _ = ui
    assert _routes(api) == set(MATRIX) | UNAUTHENTICATED


def test_every_declared_permission_exists():
    granted = set().union(*ROLE_PERMISSIONS.values())
    assert {perm for perm, _ in MATRIX.values() if perm} <= granted


@pytest.mark.parametrize("method, path", sorted(MATRIX))
def test_without_a_token_every_route_is_401(ui, method, path):
    _, client = ui
    assert _call(client, method, path, None).status_code == 401


@pytest.mark.parametrize("user", sorted(ROLES))
@pytest.mark.parametrize("access", ALL)
def test_the_matrix(ui, user, access):
    """Each call gets a fresh token (logout ends one). Allowed means the API did not refuse it: not 401 or 403."""
    _, client = ui
    granted = ROLE_PERMISSIONS[ROLES[user]]
    wrong = []
    for (method, path), (perm, kinds) in sorted(MATRIX.items()):
        allowed = access in kinds and (perm is None or perm in granted)
        code = _call(client, method, path, _token(client, user, access)).status_code
        if allowed == (code in (401, 403)):
            wrong.append(f"{method} {path}: {code}, expected {'allowed' if allowed else 'refused'}")
    assert wrong == []
