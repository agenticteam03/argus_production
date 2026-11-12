"""Offline authorization contract for a human terminal launch.

The API must supply verified identity, effective permissions, incident and lease
facts. This module issues no ticket, exposes no route and opens no shell.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime


TICKET_ID = re.compile(r"^tt_[0-9a-f]{32}$")
INCIDENT_ID = re.compile(r"^inc_[A-Za-z0-9_-]+$")
HANDLE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


class TerminalLaunchRefused(ValueError):
    """A terminal launch is unauthorized or lacks a required binding."""


@dataclass(frozen=True)
class LeaseProof:
    lease_id: str
    host: str
    owner: str
    expires_at: datetime


@dataclass(frozen=True)
class LaunchRequest:
    principal: str
    principal_kind: str
    auth_session: str
    ticket_id: str
    second_factor_ready: bool
    effective_permissions: frozenset[str]
    host: str
    incident_id: str
    incident_host: str
    reason: str
    step_up_token: str
    lease: LeaseProof


@dataclass(frozen=True)
class LaunchGrant:
    principal: str
    account: str
    host: str
    incident_id: str
    reason: str
    lease_id: str
    ticket_id: str
    step_up_object: str


class TerminalLaunchPolicy:
    """Checks reviewed authorization before consuming the object-bound step-up."""

    def __init__(self, accounts: Mapping[tuple[str, str], str], consume_step_up: Callable):
        self.accounts = dict(accounts)
        self.consume_step_up = consume_step_up

    def authorize(self, request: LaunchRequest, *, at: datetime) -> LaunchGrant:
        if request.principal_kind != "human" or not HANDLE.fullmatch(request.principal):
            raise TerminalLaunchRefused("a named human is required")
        if not request.auth_session or not request.second_factor_ready:
            raise TerminalLaunchRefused("a WebAuthn-ready human session is required")
        if not TICKET_ID.fullmatch(request.ticket_id):
            raise TerminalLaunchRefused("a fixed ticket id is required")
        if request.host not in {"vm-095", "vm-166"}:
            raise TerminalLaunchRefused("host is not allowed")
        if f"open_terminal:{request.host}" not in request.effective_permissions:
            raise TerminalLaunchRefused("host-specific terminal permission is required")
        account = self.accounts.get((request.principal, request.host))
        if account != f"op-{request.principal}":
            raise TerminalLaunchRefused("personal account mapping is unavailable")
        if not INCIDENT_ID.fullmatch(request.incident_id) or request.incident_host != request.host:
            raise TerminalLaunchRefused("incident and host differ")
        reason = request.reason.strip()
        if not 1 <= len(reason) <= 256 or any(ord(ch) < 32 or ord(ch) == 127 for ch in reason):
            raise TerminalLaunchRefused("a plain-text reason is required")
        lease = request.lease
        if (not lease.lease_id or lease.host != request.host or lease.owner != request.principal
                or at.tzinfo is None or lease.expires_at.tzinfo is None or lease.expires_at <= at):
            raise TerminalLaunchRefused("a current host lease is required")
        if not request.step_up_token:
            raise TerminalLaunchRefused("a fresh ticket-bound step-up is required")
        step_up_object = f"terminal:{request.ticket_id}"
        try:
            self.consume_step_up(request.step_up_token, request.principal, request.auth_session, step_up_object)
        except Exception as exc:
            raise TerminalLaunchRefused("a fresh ticket-bound step-up is required") from exc
        return LaunchGrant(request.principal, account, request.host, request.incident_id, reason,
                           lease.lease_id, request.ticket_id, step_up_object)
