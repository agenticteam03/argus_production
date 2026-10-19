"""PostgreSQL adapter for IncidentMemoryPort, AuditSinkPort, NotificationPort and principals (v1.8 §14; Phase 5).

Same interface as SqliteStore. The schema lives in deploy/migrations (applied by the owner, never by the agent);
this adapter connects as argus_runtime, which cannot UPDATE/DELETE evidence or audit. A small pool reconnects
after a Postgres restart.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from argus.domain.model import AuditRecord, EvidenceRecord, Incident, IncidentStatus, TargetRef, utcnow


class PostgresStore:
    def __init__(self, conninfo: str, min_size: int = 1, max_size: int = 4):
        self.pool = ConnectionPool(conninfo, min_size=min_size, max_size=max_size, open=True,
                                   kwargs={"autocommit": True}, check=ConnectionPool.check_connection,
                                   name="argus")
        self.pool.wait(timeout=30)
        self.conninfo = conninfo
        self._checkpoint_pool: ConnectionPool | None = None

    def checkpointer(self):
        """LangGraph's Postgres checkpointer (T-0013) on its own small pool, configured as the library requires
        (autocommit, dict rows, no server-side prepared statements). Its tables come from migration 002; it never
        runs DDL (the runtime role has none)."""
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg.rows import dict_row
        if self._checkpoint_pool is None:
            self._checkpoint_pool = ConnectionPool(
                self.conninfo, min_size=1, max_size=2, open=True, name="argus-checkpoints",
                kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
                check=ConnectionPool.check_connection)
            self._checkpoint_pool.wait(timeout=30)
        return PostgresSaver(self._checkpoint_pool)

    def close(self) -> None:
        if self._checkpoint_pool is not None:
            self._checkpoint_pool.close()
        self.pool.close()

    def _q(self, sql: str, params: tuple = ()) -> list[tuple]:
        with self.pool.connection() as c:
            cur = c.execute(sql, params)
            return cur.fetchall() if cur.description else []

    # --- incidents -------------------------------------------------------------------------------
    def create_incident(self, incident: Incident, idempotency_key: str | None) -> tuple[Incident, bool]:
        row = self._q("INSERT INTO incident (id, target, status, opened_at, idempotency_key, body, parent_id) "
                      "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (idempotency_key) DO NOTHING RETURNING id",
                      (incident.id, str(incident.target), incident.status, incident.opened_at, idempotency_key,
                       Jsonb(incident.model_dump(mode="json")), incident.parent_id))
        if row:
            return incident, False
        existing = self._q("SELECT body FROM incident WHERE idempotency_key = %s", (idempotency_key,))
        return Incident.model_validate(existing[0][0]), True

    def get_incident(self, incident_id: str) -> Incident | None:
        row = self._q("SELECT body FROM incident WHERE id = %s", (incident_id,))
        return Incident.model_validate(row[0][0]) if row else None

    def update_incident(self, incident: Incident) -> None:
        self._q("UPDATE incident SET status = %s, body = %s WHERE id = %s",
                (incident.status, Jsonb(incident.model_dump(mode="json")), incident.id))

    def list_incidents(self, limit: int = 50, parent_id: str | None = None) -> list[Incident]:
        if parent_id is not None:                                # ACR-0021 B5: the re-checks of one incident
            rows = self._q("SELECT body FROM incident WHERE parent_id = %s ORDER BY opened_at DESC LIMIT %s",
                           (parent_id, limit))
        else:
            rows = self._q("SELECT body FROM incident ORDER BY opened_at DESC LIMIT %s", (limit,))
        return [Incident.model_validate(r[0]) for r in rows]

    def claim_next_queued(self, worker_id: str = "local", lease_s: int = 300) -> Incident | None:
        """Atomic claim (FOR UPDATE SKIP LOCKED) for `lease_s` seconds: safe with several workers (T-0014, §6.2)."""
        row = self._q("UPDATE incident SET status = 'running', body = jsonb_set(body, '{status}', '\"running\"'), "
                      "claimed_by = %s, claimed_until = now() + make_interval(secs => %s) "
                      "WHERE id = (SELECT id FROM incident WHERE status = 'queued' ORDER BY opened_at "
                      "            FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING body", (worker_id, lease_s))
        return Incident.model_validate(row[0][0]) if row else None

    def renew_claim(self, incident_id: str, worker_id: str, lease_s: int = 300,
                    now: datetime | None = None) -> bool:
        """Extend a live claim. False: the claim is no longer this worker's (expired and taken), so it must stop.
        `now` is for tests; by default the database clock decides, as in the claim (OP-009: one clock per lease)."""
        row = self._q("UPDATE incident SET claimed_until = COALESCE(%s::timestamptz, now()) + make_interval(secs => %s) "
                      "WHERE id = %s AND status = 'running' AND claimed_by = %s "
                      "AND claimed_until >= COALESCE(%s::timestamptz, now()) RETURNING id",
                      (now, lease_s, incident_id, worker_id, now))
        return bool(row)

    def requeue_expired(self, now: datetime | None = None) -> int:
        """Crash recovery: running incidents whose claim expired (or that never had one) go back to the queue."""
        rows = self._q("UPDATE incident SET status = 'queued', body = jsonb_set(body, '{status}', '\"queued\"'), "
                       "claimed_by = NULL, claimed_until = NULL "
                       "WHERE status = 'running' AND (claimed_until IS NULL "
                       "OR claimed_until < COALESCE(%s::timestamptz, now())) RETURNING id",
                       (now,))
        return len(rows)

    def requeue_running(self) -> int:
        """Crash recovery for the single-process `argus serve`: every run in progress starts again from intake."""
        rows = self._q("UPDATE incident SET status = 'queued', body = jsonb_set(body, '{status}', '\"queued\"') "
                       "WHERE status = 'running' RETURNING id")
        return len(rows)

    def active_incident(self, target: TargetRef) -> Incident | None:
        """The target's queued or running incident, if any (T-0014: the scheduler's skip-if-active, §6.5)."""
        row = self._q("SELECT body FROM incident WHERE target = %s AND status IN ('queued', 'running') "
                      "ORDER BY opened_at LIMIT 1", (str(target),))
        return Incident.model_validate(row[0][0]) if row else None

    def latest_concluded_incident(self, target: TargetRef) -> Incident | None:
        """The target's most recent closed or escalated incident (ACR-0004: the episode an alert may still join)."""
        row = self._q("SELECT body FROM incident WHERE target = %s AND status IN ('closed', 'escalated') "
                      "ORDER BY opened_at DESC LIMIT 1", (str(target),))
        return Incident.model_validate(row[0][0]) if row else None

    def similar_incidents(self, target: TargetRef, incident_class: str, k: int) -> list[Incident]:
        rows = self._q("SELECT body FROM incident WHERE target = %s AND body->>'incident_class' = %s "
                       "AND body->>'closed_at' IS NOT NULL ORDER BY opened_at DESC LIMIT %s",
                       (str(target), incident_class, k))
        return [Incident.model_validate(r[0]) for r in rows]

    # --- alert occurrences (OP-011, §6.4; migration 004) -----------------------------------------------
    def incident_for_trigger(self, identity: str) -> str | None:
        """The incident an alert identity already belongs to: as an occurrence, or as the key that opened it."""
        row = self._q("SELECT incident_id FROM alert_occurrence WHERE identity = %s UNION ALL "
                      "SELECT id FROM incident WHERE idempotency_key = %s LIMIT 1", (identity, identity))
        return row[0][0] if row else None

    def add_alert_occurrence(self, identity: str, incident_id: str, fingerprint: str, starts_at: datetime,
                             labels: dict[str, str], disposition: str, received_at: datetime | None = None) -> bool:
        """Insert-only; False when the identity is already recorded (a concurrent copy of the same alert)."""
        row = self._q("INSERT INTO alert_occurrence (identity, incident_id, fingerprint, starts_at, alertname, labels, "
                      "disposition, received_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                      "ON CONFLICT (identity) DO NOTHING RETURNING identity",
                      (identity, incident_id, fingerprint, starts_at, labels.get("alertname", ""), Jsonb(labels),
                       disposition, received_at or utcnow()))
        return bool(row)

    def alert_occurrences(self, incident_id: str) -> list[dict[str, Any]]:
        rows = self._q("SELECT identity, fingerprint, starts_at, alertname, labels, disposition, status, received_at, "
                       "resolved_at FROM alert_occurrence WHERE incident_id = %s ORDER BY received_at, identity",
                       (incident_id,))
        keys = ("identity", "fingerprint", "starts_at", "alertname", "labels", "disposition", "status", "received_at",
                "resolved_at")
        return [dict(zip(keys, r)) for r in rows]

    def firing_occurrences(self, host: str, received_before: datetime) -> list[dict[str, Any]]:
        """The host's occurrences still firing that were recorded before `received_before` (T-0026, pull)."""
        rows = self._q("SELECT identity, incident_id FROM alert_occurrence WHERE status = 'firing' "
                       "AND labels->>'argus_host' = %s AND received_at <= %s ORDER BY received_at, identity",
                       (host, received_before))
        return [{"identity": r[0], "incident_id": r[1]} for r in rows]

    def resolve_alert_occurrence(self, identity: str, resolved_at: datetime) -> dict[str, Any] | None:
        """firing → resolved (migration 005: forward only). None when unknown or already resolved."""
        row = self._q("UPDATE alert_occurrence SET status = 'resolved', resolved_at = %s "
                      "WHERE identity = %s AND status = 'firing' RETURNING incident_id, fingerprint, alertname",
                      (resolved_at, identity))
        return {"incident_id": row[0][0], "fingerprint": row[0][1], "alertname": row[0][2]} if row else None

    def monitoring_state(self, host: str) -> dict[str, Any] | None:
        """ACR-0009: the stored heartbeat state of a host (migration 006)."""
        row = self._q("SELECT state FROM monitoring_state WHERE host = %s", (host,))
        return dict(row[0][0]) if row else None

    def save_monitoring_state(self, host: str, state: dict[str, Any]) -> None:
        self._q("INSERT INTO monitoring_state (host, state, updated_at) VALUES (%s, %s, now()) "
                "ON CONFLICT (host) DO UPDATE SET state = EXCLUDED.state, updated_at = now()", (host, Jsonb(state)))

    def close_queued_incident(self, incident_id: str, outcome: str, diagnosis: str, closed_at: datetime) -> bool:
        """Close an incident no worker has claimed (T-0026). False when it is no longer queued (claimed meanwhile)."""
        patch = {"status": "closed", "outcome": outcome, "diagnosis": diagnosis,
                 "closed_at": closed_at.isoformat()}
        row = self._q("UPDATE incident SET status = 'closed', body = body || %s WHERE id = %s AND status = 'queued' "
                      "RETURNING id", (Jsonb(patch), incident_id))
        return bool(row)

    def evidence_state(self, incident_id: str) -> tuple[int, datetime | None]:
        """(evidence_version, last_evidence_at): 1 + the attached occurrences, and the newest occurrence's time."""
        row = self._q("SELECT count(*) FILTER (WHERE disposition = 'attached'), max(received_at) "
                      "FROM alert_occurrence WHERE incident_id = %s", (incident_id,))
        return 1 + int(row[0][0]), row[0][1]

    # --- evidence ----------------------------------------------------------------------------------
    def append_evidence(self, record: EvidenceRecord) -> None:
        self._q("INSERT INTO evidence (evidence_id, incident_id, collected_at, host, executor, sha256, body) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (record.evidence_id, record.incident_id, record.collected_at, record.host, record.executor,
                 record.sha256, Jsonb(record.model_dump(mode="json"))))

    def get_evidence(self, evidence_ids: list[str]) -> list[EvidenceRecord]:
        if not evidence_ids:
            return []
        rows = self._q("SELECT body FROM evidence WHERE evidence_id = ANY(%s)", (list(evidence_ids),))
        return [EvidenceRecord.model_validate(r[0]) for r in rows]

    def list_evidence(self, incident_id: str) -> list[EvidenceRecord]:
        rows = self._q("SELECT body FROM evidence WHERE incident_id = %s ORDER BY collected_at", (incident_id,))
        return [EvidenceRecord.model_validate(r[0]) for r in rows]

    # --- audit -----------------------------------------------------------------------------------
    def append(self, record: AuditRecord) -> None:
        self._q("INSERT INTO audit (audit_id, incident_id, at, body) VALUES (%s, %s, %s, %s)",
                (record.audit_id, record.incident_id, record.at, Jsonb(record.model_dump(mode="json"))))

    def list_for(self, incident_id: str) -> list[AuditRecord]:
        rows = self._q("SELECT body FROM audit WHERE incident_id = %s ORDER BY at", (incident_id,))
        return [AuditRecord.model_validate(r[0]) for r in rows]

    # --- run events (telemetry of the v1.8 nodes; not audit) ---------------------------------------
    def append_run_event(self, incident_id: str, node: str, phase: str, data: dict[str, Any]) -> None:
        with self.pool.connection() as c, c.transaction():
            c.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (incident_id,))
            c.execute("INSERT INTO run_event (incident_id, seq, at, node, phase, data) "
                      "SELECT %s, COALESCE(MAX(seq), 0) + 1, %s, %s, %s, %s FROM run_event WHERE incident_id = %s",
                      (incident_id, utcnow(), node, phase, Jsonb(json.loads(json.dumps(data, default=str))),
                       incident_id))

    def list_run_events(self, incident_id: str, after_seq: int = 0) -> list[dict]:
        rows = self._q("SELECT seq, at, node, phase, data FROM run_event WHERE incident_id = %s AND seq > %s "
                       "ORDER BY seq", (incident_id, after_seq))
        return [{"incident_id": incident_id, "seq": s, "at": a.isoformat(), "node": n, "phase": ph, "data": d}
                for s, a, n, ph, d in rows]

    # --- notifications (recording adapter) -------------------------------------------------------------
    def notify(self, key: str, payload: dict[str, Any]) -> None:
        self._q("INSERT INTO notification (key, at, payload) VALUES (%s, %s, %s) ON CONFLICT (key) DO NOTHING",
                (key, utcnow(), Jsonb(json.loads(json.dumps(payload, default=str)))))

    def notifications(self, limit: int = 50) -> list[dict]:
        rows = self._q("SELECT key, at, payload FROM notification ORDER BY at DESC LIMIT %s", (limit,))
        return [{"key": k, "at": a.isoformat(), "payload": p} for k, a, p in rows]

    # --- principals --------------------------------------------------------------------------------
    def upsert_principal(self, pid: str, kind: str, role: str, scopes: list[str], password_hash: str) -> None:
        self._q("INSERT INTO principal (id, kind, role, scopes, password_hash, disabled) "
                "VALUES (%s, %s, %s, %s, %s, false) ON CONFLICT (id) DO UPDATE SET kind = excluded.kind, "
                "role = excluded.role, scopes = excluded.scopes, password_hash = excluded.password_hash, "
                "disabled = false", (pid, kind, role, Jsonb(scopes), password_hash))

    def set_disabled(self, pid: str, disabled: bool) -> None:
        self._q("UPDATE principal SET disabled = %s WHERE id = %s", (disabled, pid))

    def get_principal(self, pid: str) -> dict | None:
        row = self._q("SELECT id, kind, role, scopes, password_hash, disabled FROM principal WHERE id = %s", (pid,))
        if not row:
            return None
        i, k, r, s, h, d = row[0]
        return {"id": i, "kind": k, "role": r, "scopes": s, "password_hash": h, "disabled": bool(d)}


def import_sqlite(sqlite_path: str, store: PostgresStore) -> dict[str, int]:
    """One-shot copy of the lab SQLite history into Postgres (idempotent: existing rows are skipped).
    Rows keep their ids, timestamps and sequence numbers; nothing is deleted from either side."""
    import sqlite3
    src = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    counts: dict[str, int] = {}

    def copy(table: str, select: str, insert: str, convert) -> None:
        n = 0
        with store.pool.connection() as c:
            for row in src.execute(select):
                cur = c.execute(insert + " ON CONFLICT DO NOTHING", convert(row))
                n += cur.rowcount
        counts[table] = n

    has_parent = any(c[1] == "parent_id" for c in src.execute("PRAGMA table_info(incident)"))
    copy("incident", "SELECT id, target, status, opened_at, idempotency_key, body, "         # oldest first: a parent
         + ("parent_id" if has_parent else "NULL") + " FROM incident ORDER BY opened_at",  # exists before its re-check
         "INSERT INTO incident (id, target, status, opened_at, idempotency_key, body, parent_id) "
         "VALUES (%s,%s,%s,%s,%s,%s,%s)",
         lambda r: (r[0], r[1], r[2], r[3], r[4], Jsonb(json.loads(r[5])), r[6]))
    copy("evidence", "SELECT evidence_id, incident_id, collected_at, sha256, body FROM evidence",
         "INSERT INTO evidence (evidence_id, incident_id, collected_at, host, executor, sha256, body) "
         "VALUES (%s,%s,%s,%s,%s,%s,%s)",
         lambda r: (r[0], r[1], r[2], json.loads(r[4]).get("host"), json.loads(r[4]).get("executor"), r[3],
                    Jsonb(json.loads(r[4]))))
    copy("audit", "SELECT audit_id, incident_id, at, body FROM audit",
         "INSERT INTO audit (audit_id, incident_id, at, body) VALUES (%s,%s,%s,%s)",
         lambda r: (r[0], r[1], r[2], Jsonb(json.loads(r[3]))))
    copy("principal", "SELECT id, kind, role, scopes, password_hash, disabled FROM principal",
         "INSERT INTO principal (id, kind, role, scopes, password_hash, disabled) VALUES (%s,%s,%s,%s,%s,%s)",
         lambda r: (r[0], r[1], r[2], Jsonb(json.loads(r[3])), r[4], bool(r[5])))
    copy("run_event", "SELECT incident_id, seq, at, node, phase, data FROM run_event",
         "INSERT INTO run_event (incident_id, seq, at, node, phase, data) VALUES (%s,%s,%s,%s,%s,%s)",
         lambda r: (r[0], r[1], r[2], r[3], r[4], Jsonb(json.loads(r[5]))))
    copy("notification", "SELECT key, at, payload FROM notification",
         "INSERT INTO notification (key, at, payload) VALUES (%s,%s,%s)",
         lambda r: (r[0], r[1], Jsonb(json.loads(r[2]))))
    src.close()
    return counts


CHECKS_SQL: list[tuple[str, str, bool]] = [
    # (name, statement run as argus_runtime inside a savepoint, must_succeed)
    ("insert incident", "INSERT INTO incident (id, target, status, opened_at, body) VALUES "
                        "('inc_dbcheck', 'vm-095/container:dbcheck', 'closed', now(), '{}')", True),
    ("insert evidence", "INSERT INTO evidence (evidence_id, incident_id, collected_at, sha256, body) VALUES "
                        "('ev_dbcheck', 'inc_dbcheck', now(), repeat('a', 64), '{}')", True),
    ("insert audit", "INSERT INTO audit (audit_id, incident_id, at, body) VALUES "
                     "('aud_dbcheck', 'inc_dbcheck', now(), '{}')", True),
    ("UPDATE evidence refused", "UPDATE evidence SET sha256 = repeat('b', 64) WHERE evidence_id = 'ev_dbcheck'", False),
    ("DELETE evidence refused", "DELETE FROM evidence WHERE evidence_id = 'ev_dbcheck'", False),
    ("TRUNCATE evidence refused", "TRUNCATE evidence", False),
    ("UPDATE audit refused", "UPDATE audit SET at = now() WHERE audit_id = 'aud_dbcheck'", False),
    ("DELETE audit refused", "DELETE FROM audit WHERE audit_id = 'aud_dbcheck'", False),
    ("DELETE incident refused", "DELETE FROM incident WHERE id = 'inc_dbcheck'", False),
    ("closed incident cannot reopen", "UPDATE incident SET status = 'queued' WHERE id = 'inc_dbcheck'", False),
    ("re-check of a missing incident refused (ACR-0021)", "INSERT INTO incident (id, target, status, opened_at, body, "
                                                         "parent_id) VALUES ('inc_dbcheck2', 'vm-095/container:dbcheck',"
                                                         " 'queued', now(), '{}', 'inc_nosuch')", False),
    ("an incident's parent cannot change (ACR-0021)", "UPDATE incident SET parent_id = 'inc_dbcheck' "
                                                      "WHERE id = 'inc_dbcheck'", False),
    ("evidence without a SHA-256 refused", "INSERT INTO evidence (evidence_id, incident_id, collected_at, sha256, body) "
                                           "VALUES ('ev_dbcheck2', 'inc_dbcheck', now(), 'nothash', '{}')", False),
    ("DDL refused (CREATE TABLE)", "CREATE TABLE dbcheck_x (i int)", False),
    ("insert checkpoint (T-0013)", "INSERT INTO checkpoints (thread_id, checkpoint_id, checkpoint) VALUES "
                                   "('dbcheck', 'c1', '{}')", True),
    ("DELETE checkpoint refused", "DELETE FROM checkpoints WHERE thread_id = 'dbcheck'", False),
    ("insert alert occurrence (OP-011)", "INSERT INTO alert_occurrence (identity, incident_id, fingerprint, starts_at, "
                                         "labels, disposition, received_at) VALUES "
                                         "('alert:dbcheck', 'inc_dbcheck', 'fp', now(), '{}', 'started', now())", True),
    ("resolve alert occurrence (T-0026)", "UPDATE alert_occurrence SET status = 'resolved', resolved_at = now() "
                                          "WHERE identity = 'alert:dbcheck'", True),
    ("resolved occurrence cannot fire again", "UPDATE alert_occurrence SET status = 'firing' "
                                              "WHERE identity = 'alert:dbcheck'", False),
    ("occurrence's incident cannot change", "UPDATE alert_occurrence SET incident_id = 'inc_x' "
                                            "WHERE identity = 'alert:dbcheck'", False),
    ("DELETE alert occurrence refused", "DELETE FROM alert_occurrence WHERE identity = 'alert:dbcheck'", False),
    ("runtime role is not superuser", "DO $$ BEGIN IF (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) "
                                      "THEN RAISE EXCEPTION 'superuser'; END IF; END $$", True),
]


def check(conninfo: str) -> list[tuple[str, bool, str]]:
    """Proves the Phase 5 guarantees against the LIVE database as the runtime role. Everything happens inside one
    transaction that is rolled back, so the check leaves no rows behind."""
    import psycopg
    results = []
    with psycopg.connect(conninfo) as c:                     # autocommit off: one transaction
        for name, sql, must_succeed in CHECKS_SQL:
            c.execute("SAVEPOINT s")
            try:
                c.execute(sql)
                ok, detail = must_succeed, "succeeded"
                c.execute("RELEASE SAVEPOINT s")
            except psycopg.Error as e:
                c.execute("ROLLBACK TO SAVEPOINT s")
                ok, detail = not must_succeed, (e.diag.message_primary or type(e).__name__)
            results.append((name, ok, detail))
        c.rollback()
    return results
