"""ACR-0018 §18, phase 16: security events raise an alert through the Argus-owned Alertmanager to the team's route.

On the scheduler's schedule (`security_alerts` in `schedules.yaml`, off by default) it reads the audit rows of the
alerting events written since its last pass and posts one alert per row to the home host's Alertmanager
(`POST /api/v2/alerts`). The alert carries `argus_security="true"`: Alertmanager routes it to the team's receiver, and
Argus's own intake never turns it into an incident. It names the event, the actor, the time and the audit row; never
the row's detail (a login's detail holds the client address, which is personal data). The actor is named only when the
store knows it as a principal, else `unknown`: a failed or locked login's actor is the text typed in the username box,
which can be an attacker's text or a password typed in the wrong field.

A restarted scheduler looks back `lookback` (one hour) and posts again what it finds: the label set includes the audit
id, so Alertmanager merges a repeat into the alert it already has and notifies once. An event older than that while the
scheduler was down is not alerted; it stays in the audit and `argus audit verify` still checks it.

The cursor is the newest `at` sent (`at > since`). With two writers, a row that commits after a pass with an earlier
`at`, or a second row with exactly the cursor's `at`, is missed. Accepted at this volume (a few rows a day); such a row
is still in the audit.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Callable

import httpx

from argus.domain.model import utcnow

log = logging.getLogger("argus.security_alerts")

ALERT_EVENTS = (
    "security.audit_chain_broken",                   # §17.1 layer 13: a row edited, removed or inserted
    "security.audit_digest_failed", "security.audit_digest_skipped",       # the off-host digest did not ship
    "security.audit_digest_conflict", "security.audit_digest_unconfigured",
    "security.session_refused",                      # a revoked or expired session used again
    "access.sessions_revoked",                       # an administrator ended a principal's sessions
    "access.login_locked",                           # the persisted login limiter locked an account or address
    "access.ops_login_failed",                       # ACR-0032: a refused private login
    "access.read_only_refused", "access.investigate_scope_refused",        # refused requests over a permission
    "security.webauthn_reset",                       # a principal's keys reset by another administrator
    "security.fabricated_tool", "security.unknown_or_write_capability",    # the model asked for what does not exist
    "security.console_refused",                      # T-0016: a refused use of the operator console
)


class SecurityAlerts:
    def __init__(self, store, alertmanager_url: str, client: httpx.Client | None = None,
                 lookback: timedelta = timedelta(hours=1), hold: timedelta = timedelta(hours=1),
                 clock: Callable[[], datetime] = utcnow):
        self.store, self.url = store, alertmanager_url.rstrip("/")
        self.client = client or httpx.Client(timeout=8.0)
        self.lookback, self.hold, self.clock = lookback, hold, clock
        self._since: datetime | None = None

    def run_once(self) -> str:
        start = self.clock() - self.lookback
        since = max(self._since, start) if self._since else start
        rows = self.store.audit_since(since, ALERT_EVENTS)
        if not rows:
            return "0 security alert(s)"
        known: dict[str, bool] = {}
        for r in rows:
            if r.actor and r.actor not in known:
                known[r.actor] = self.store.get_principal(r.actor) is not None
        alerts = [{
            "labels": {"alertname": "ArgusSecurityEvent", "argus_security": "true", "event": r.event,
                       "audit_id": r.audit_id},
            "annotations": {"summary": f"{r.event} by {r.actor[:64] if known.get(r.actor) else 'unknown'} "
                                       f"at {r.at:%Y-%m-%d %H:%M:%S}Z"},
            "startsAt": r.at.isoformat(), "endsAt": (r.at + self.hold).isoformat()} for r in rows]
        r = self.client.post(f"{self.url}/api/v2/alerts", json=alerts)
        r.raise_for_status()                    # not sent: the cursor stays, the next pass sends them again
        self._since = max(row.at for row in rows)
        return f"{len(rows)} security alert(s) sent"

    def notify_approval_waiting(self, message: str, approval_id: str, expires_at: datetime,
                                resolved: bool = False) -> None:
        """Send an approval notice through the existing Alertmanager security route; `resolved` posts the same
        alert (same labels) with `endsAt` now, so the group stops listing an answered approval as waiting."""
        now = self.clock()
        alert = {
            "labels": {"alertname": "ArgusApprovalWaiting", "argus_security": "true",
                       "approval_id": approval_id},
            "annotations": {"summary": message},
            "startsAt": now.isoformat(),
            "endsAt": now.isoformat() if resolved else expires_at.isoformat(),
        }
        response = self.client.post(f"{self.url}/api/v2/alerts", json=[alert])
        response.raise_for_status()

    def notify_escalation(self, message: str, incident_id: str) -> None:
        """Send an escalation notice (an incident a proposed action did not reach) on the same route; it ends after
        `hold`, like a security event."""
        now = self.clock()
        alert = {
            "labels": {"alertname": "ArgusIncidentEscalated", "argus_security": "true", "incident_id": incident_id},
            "annotations": {"summary": message},
            "startsAt": now.isoformat(), "endsAt": (now + self.hold).isoformat(),
        }
        response = self.client.post(f"{self.url}/api/v2/alerts", json=[alert])
        response.raise_for_status()
