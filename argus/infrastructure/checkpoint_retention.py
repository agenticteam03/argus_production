"""OP-004: owner-only retention of final investigations' LangGraph checkpoints."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.types.json import Jsonb

from argus.domain.model import AuditRecord


TABLES = ("checkpoints", "checkpoint_blobs", "checkpoint_writes")
ELIGIBLE = ("SELECT id FROM incident WHERE status IN ('closed', 'escalated') "
            "AND NULLIF(body->>'closed_at', '')::timestamptz < %s")


def prune_checkpoints(conninfo: str, *, days: int = 30, dry_run: bool = True,
                      now: datetime | None = None) -> dict[str, int | bool]:
    """Preview by default; apply under one transaction with the owner role only.

    A final incident never resumes. Its checkpoints may be removed after the retention window; the incident,
    evidence, audit, and run-event records remain. The global advisory lock serializes maintenance runs.
    """
    if not isinstance(days, int) or days < 1:
        raise ValueError("checkpoint retention days must be a positive integer")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must include a timezone")
    cutoff = now - timedelta(days=days)

    with psycopg.connect(conninfo) as conn:
        if dry_run:
            conn.execute("SET TRANSACTION READ ONLY")
        role = conn.execute("SELECT current_user").fetchone()[0]
        if role != "argus_owner":
            raise PermissionError("checkpoint retention requires argus_owner")
        if not dry_run:
            conn.execute("SELECT pg_advisory_xact_lock(404, 1)")

        counts: dict[str, int | bool] = {"dry_run": dry_run}
        union = " UNION ".join(f"SELECT thread_id FROM {table} WHERE thread_id IN ({ELIGIBLE})" for table in TABLES)
        counts["threads"] = conn.execute(f"SELECT count(*) FROM ({union}) AS eligible_threads",
                                         (cutoff,) * len(TABLES)).fetchone()[0]
        for table, key in zip(TABLES, ("checkpoints", "blobs", "writes")):
            counts[key] = conn.execute(f"SELECT count(*) FROM {table} WHERE thread_id IN ({ELIGIBLE})",
                                       (cutoff,)).fetchone()[0]
        if dry_run:
            return counts

        for table, key in zip(TABLES, ("checkpoints", "blobs", "writes")):
            counts[key] = conn.execute(f"DELETE FROM {table} WHERE thread_id IN ({ELIGIBLE})", (cutoff,)).rowcount
        record = AuditRecord(audit_id=f"aud_{secrets.token_hex(12)}", incident_id=None, at=now,
                             category="decision", event="maintenance.checkpoints_pruned", actor="system",
                             detail={"threads_removed": counts["threads"], "retention_days": days,
                                     "checkpoints_removed": counts["checkpoints"],
                                     "blobs_removed": counts["blobs"], "writes_removed": counts["writes"]})
        conn.execute("INSERT INTO audit (audit_id, incident_id, at, body) VALUES (%s, NULL, %s, %s)",
                     (record.audit_id, record.at, Jsonb(record.model_dump(mode="json"))))
        return counts
