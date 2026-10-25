"""Worker-side client for the exact-route, journaled action gateway.

This module is not wired into production while the repository write gate is
closed. The token is supplied only by the worker process, never by the model
or MCP tools child.
"""
from __future__ import annotations

import http.client
import json
from collections.abc import Callable

from argus.actions.remediation import FrozenProposal, verify_frozen_proposal
from services.action_gateway.core import ACTION_ID, validated_pairs


class GatewayClientRefused(ValueError):
    """The pair, response or transport did not establish a safe result."""


class HttpGatewayRequest:
    """A bounded request to the private action gateway; no redirect handling."""

    def __init__(self, host: str, port: int = 8705):
        self.host, self.port = host, port

    def __call__(self, method: str, path: str, headers: dict, body: bytes | None):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=10)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            payload = response.read(4097)
            if len(payload) > 4096:
                raise GatewayClientRefused("gateway response exceeds the limit")
            return response.status, payload
        finally:
            connection.close()


class GatewayClient:
    def __init__(self, request: Callable, token_reader: Callable[[], str], *, released: dict):
        self.request, self.token_reader = request, token_reader
        # The host is part of the single released pair; each gateway is host-local.
        hosts = {target.split("/", 1)[0] for _, target in released}
        if len(hosts) != 1:
            raise GatewayClientRefused("gateway client needs one exact host")
        self.released = validated_pairs(hosts.pop(), released)

    def _headers(self, action_id: str) -> dict[str, str]:
        if not ACTION_ID.fullmatch(action_id):
            raise GatewayClientRefused("invalid action id")
        token = self.token_reader()
        if not token:
            raise GatewayClientRefused("gateway credential unavailable")
        return {"Authorization": "Bearer " + token, "X-Argus-Action-Id": action_id,
                "Content-Type": "application/json"}

    def dispatch(self, action_id: str, proposal: FrozenProposal) -> str:
        verify_frozen_proposal(proposal)
        data = proposal.input
        route = self.released.get((data.capability, data.target))
        if route is None:
            raise GatewayClientRefused("action pair is not released")
        headers = self._headers(action_id)
        body = json.dumps({"capability": data.capability, "target": data.target,
                           "target_identity": data.target_identity}, separators=(",", ":")).encode("utf-8")
        try:
            code, raw = self.request("POST", route.removeprefix("POST "), headers, body)
            result = json.loads(raw).get("status") if code == 200 else None
        except Exception as exc:
            raise GatewayClientRefused("gateway dispatch outcome is uncertain") from exc
        if result not in ("confirmed", "failed"):
            raise GatewayClientRefused("gateway dispatch outcome is uncertain")
        return result

    def status(self, action_id: str) -> str | None:
        headers = self._headers(action_id)
        try:
            code, raw = self.request("GET", f"/actions/{action_id}", headers, None)
            if code == 404:
                return None
            result = json.loads(raw).get("status") if code == 200 else None
        except Exception as exc:
            raise GatewayClientRefused("gateway status is unavailable") from exc
        if result not in ("received", "confirmed", "failed"):
            raise GatewayClientRefused("gateway status is unavailable")
        return result
