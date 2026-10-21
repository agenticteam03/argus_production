"""ACR-0018 (phase 16): owner-only retention of `auth_session` rows, like OP-004's checkpoint retention.

Every login writes one `auth_session` row and the runtime role can never delete one (migration 010), so the table grows
with every login. A session whose token expired long ago can no longer be used or revoked; the audit keeps the login
(`access.login`) and any refusal (`security.session_refused`), so its row may go after the retention window.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import psycopg

from argus.adapters.outbound.postgres_store import append_chained
from argus.domain.model import AuditRecord

ELIGIBLE = "FROM auth_session WHERE expires_at < %s"


def prune_sessions(conninfo: str, *, days: int = 90, dry_run: bool = True,
                   now: datetime | None = None) -> dict[str, int | bool]:
    """Preview by default; apply under one transaction with the owner role only. A row goes when its token expired
    more than `days` ago (revoked or not); a live or recently expired session stays."""
    if not isinstance(days, int) or days < 1:
        raise ValueError("session retention days must be a positive integer")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must include a timezone")
    cutoff = now - timedelta(days=days)

    with psycopg.connect(conninfo) as conn:
        if dry_run:
            conn.execute("SET TRANSACTION READ ONLY")
        role = conn.execute("SELECT current_user").fetchone()[0]
        if role != "argus_owner":
            raise PermissionError("session retention requires argus_owner")
        if not dry_run:
            conn.execute("SELECT pg_advisory_xact_lock(404, 1)")    # the maintenance lock of checkpoint_retention

        counts: dict[str, int | bool] = {"dry_run": dry_run}
        counts["sessions"], counts["revoked"] = conn.execute(
            f"SELECT count(*), count(revoked_at) {ELIGIBLE}", (cutoff,)).fetchone()
        if dry_run:
            return counts

        counts["sessions"] = conn.execute(f"DELETE {ELIGIBLE}", (cutoff,)).rowcount
        record = AuditRecord(audit_id=f"aud_{secrets.token_hex(12)}", incident_id=None, at=now,
                             category="access", event="maintenance.sessions_pruned", actor="system",
                             detail={"sessions_removed": counts["sessions"], "revoked_removed": counts["revoked"],
                                     "retention_days": days})
        append_chained(conn, record)
        return counts
