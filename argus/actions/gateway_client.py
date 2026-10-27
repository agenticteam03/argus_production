"""The worker's client of the action gateway (ACR-0019 §3.9, phase 19).

It sends only what the frozen proposal holds: the catalogue's exact route for the capability, the host-qualified
target and its identity, with the action ID and the worker-only token. It never receives model output. A refusal is a
definite `failed` (the gateway sent nothing); a duplicate or an ambiguous answer is left to `status`, so an action is
never sent twice. Nothing in production constructs it while `write_gate.open` is empty.
"""
from __future__ import annotations

import re
from pathlib import Path

import httpx

from argus.actions.catalog import ACTION_ROUTES
from argus.actions.remediation import FrozenProposal, RemediationRefused

TOKEN_MIN = 32
TARGET = re.compile(r"^[a-z0-9-]+/container:(argus-lab-[A-Za-z0-9_.-]+)$")


class HttpActionGateway:
    def __init__(self, base_url: str, token_file: str | Path, *, timeout_s: float = 20.0):
        try:
            token = Path(token_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ValueError("the action token is unreadable") from exc
        if len(token) < TOKEN_MIN:
            raise ValueError("the action token is too short")
        self.base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}
        self._timeout = timeout_s

    def __repr__(self) -> str:                       # the token never appears in a log or a traceback
        return f"HttpActionGateway({self.base_url!r})"

    def route_for(self, proposal: FrozenProposal) -> str:
        data = proposal.input
        template, match = ACTION_ROUTES.get(data.capability), TARGET.fullmatch(data.target)
        if template is None or match is None:
            raise RemediationRefused("no reviewed gateway route for this capability and target")
        return template.format(name=match[1])

    def dispatch(self, action_id: str, proposal: FrozenProposal) -> str:
        data = proposal.input
        r = httpx.post(self.base_url + self.route_for(proposal), timeout=self._timeout,
                       headers={**self._headers, "X-Argus-Action-Id": action_id},
                       json={"capability": data.capability, "target": data.target,
                             "target_identity": dict(data.target_identity)})
        if r.status_code == 200 and r.json().get("status") in ("confirmed", "failed"):
            return r.json()["status"]
        if r.status_code == 409:
            raise RemediationRefused("action id already accepted by gateway")
        if r.status_code in (403, 404):
            return "failed"                             # refused before anything reached Docker
        raise ConnectionError(f"ambiguous gateway answer {r.status_code}")

    def status(self, action_id: str) -> str | None:
        r = httpx.get(f"{self.base_url}/actions/{action_id}", headers=self._headers, timeout=self._timeout)
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise ConnectionError(f"gateway status unavailable {r.status_code}")
        return r.json().get("status")
