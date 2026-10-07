"""SQLite adapter for IncidentMemoryPort, AuditSinkPort, NotificationPort and principals (v1.8-lab §4).

Evidence and audit are insert-only (triggers). One process, WAL mode, a lock around each call.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Any

from argus.domain.model import (AuditRecord, EvidenceRecord, Incident, IncidentStatus, TargetRef, utcnow)

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS incident (
  id TEXT PRIMARY KEY, target TEXT NOT NULL, status TEXT NOT NULL, opened_at TEXT NOT NULL,
  idempotency_key TEXT UNIQUE, body TEXT NOT NULL, claimed_by TEXT, claimed_until TEXT);
CREATE INDEX IF NOT EXISTS incident_status ON incident(status, opened_at);
CREATE TABLE IF NOT EXISTS evidence (
  evidence_id TEXT PRIMARY KEY, incident_id TEXT NOT NULL, collected_at TEXT NOT NULL,
  sha256 TEXT NOT NULL, body TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS evidence_incident ON evidence(incident_id, collected_at);
CREATE TABLE IF NOT EXISTS audit (
  audit_id TEXT PRIMARY KEY, incident_id TEXT, at TEXT NOT NULL, body TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS audit_incident ON audit(incident_id, at);
CREATE TABLE IF NOT EXISTS principal (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, role TEXT NOT NULL, scopes TEXT NOT NULL,
  password_hash TEXT NOT NULL, disabled INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS run_event (
  incident_id TEXT NOT NULL, seq INTEGER NOT NULL, at TEXT NOT NULL, node TEXT NOT NULL, phase TEXT NOT NULL,
  data TEXT NOT NULL, PRIMARY KEY (incident_id, seq));
CREATE TABLE IF NOT EXISTS notification (key TEXT PRIMARY KEY, at TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS evidence_no_update BEFORE UPDATE ON evidence
  BEGIN SELECT RAISE(ABORT, 'evidence is insert-only'); END;
CREATE TRIGGER IF NOT EXISTS evidence_no_delete BEFORE DELETE ON evidence
  BEGIN SELECT RAISE(ABORT, 'evidence is insert-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit
  BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit
  BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
"""


class SqliteStore:
    def __init__(self, path: str):
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.executescript(SCHEMA)
        cols = {r[1] for r in self._db.execute("PRAGMA table_info(incident)")}
        for col in ("claimed_by", "claimed_until"):              # T-0014: files created before the worker lease
            if col not in cols:
                self._db.execute(f"ALTER TABLE incident ADD COLUMN {col} TEXT")

    def _q(self, sql: str, params: tuple = ()) -> list[tuple]:
        with self._lock:
            return self._db.execute(sql, params).fetchall()

    # --- incidents -------------------------------------------------------------------------------
    def create_incident(self, incident: Incident, idempotency_key: str | None) -> tuple[Incident, bool]:
        with self._lock:
            if idempotency_key:
                row = self._q("SELECT body FROM incident WHERE idempotency_key=?", (idempotency_key,))
                if row:
                    return Incident.model_validate_json(row[0][0]), True
            self._q("INSERT INTO incident(id,target,status,opened_at,idempotency_key,body) VALUES (?,?,?,?,?,?)",
                    (incident.id, str(incident.target), incident.status, incident.opened_at.isoformat(),
                     idempotency_key, incident.model_dump_json()))
            return incident, False

    def get_incident(self, incident_id: str) -> Incident | None:
        row = self._q("SELECT body FROM incident WHERE id=?", (incident_id,))
        return Incident.model_validate_json(row[0][0]) if row else None

    def update_incident(self, incident: Incident) -> None:
        self._q("UPDATE incident SET status=?, body=? WHERE id=?",
                (incident.status, incident.model_dump_json(), incident.id))

    def list_incidents(self, limit: int = 50) -> list[Incident]:
        rows = self._q("SELECT body FROM incident ORDER BY opened_at DESC LIMIT ?", (limit,))
        return [Incident.model_validate_json(r[0]) for r in rows]

    def claim_next_queued(self, worker_id: str = "local", lease_s: int = 300) -> Incident | None:
        """Claim the oldest queued incident for `lease_s` seconds (T-0014: the claim is a lease, §6.2)."""
        with self._lock:
            row = self._q("SELECT body FROM incident WHERE status=? ORDER BY opened_at LIMIT 1",
                          (IncidentStatus.queued.value,))
            if not row:
                return None
            inc = Incident.model_validate_json(row[0][0])
            inc.status = IncidentStatus.running
            self.update_incident(inc)
            self._q("UPDATE incident SET claimed_by=?, claimed_until=? WHERE id=?",
                    (worker_id, (utcnow() + timedelta(seconds=lease_s)).isoformat(), inc.id))
            return inc

    def renew_claim(self, incident_id: str, worker_id: str, lease_s: int = 300,
                    now: datetime | None = None) -> bool:
        """Extend a live claim. False: the claim is no longer this worker's (expired and taken), so it must stop."""
        now = now or utcnow()
        with self._lock:
            row = self._q("SELECT 1 FROM incident WHERE id=? AND status=? AND claimed_by=? AND claimed_until>=?",
                          (incident_id, IncidentStatus.running.value, worker_id, now.isoformat()))
            if row:
                self._q("UPDATE incident SET claimed_until=? WHERE id=?",
                        ((now + timedelta(seconds=lease_s)).isoformat(), incident_id))
            return bool(row)

    def requeue_expired(self, now: datetime | None = None) -> int:
        """Crash recovery: running incidents whose claim expired (or that never had one) go back to the queue."""
        now = now or utcnow()
        with self._lock:
            rows = self._q("SELECT body FROM incident WHERE status=? AND (claimed_until IS NULL OR claimed_until<?)",
                           (IncidentStatus.running.value, now.isoformat()))
            for (body,) in rows:
                inc = Incident.model_validate_json(body)
                inc.status = IncidentStatus.queued
                self.update_incident(inc)
                self._q("UPDATE incident SET claimed_by=NULL, claimed_until=NULL WHERE id=?", (inc.id,))
            return len(rows)

    def requeue_running(self) -> int:
        """Crash recovery for the single-process `argus serve`: every run in progress starts again from intake."""
        rows = self._q("SELECT body FROM incident WHERE status=?", (IncidentStatus.running.value,))
        for (body,) in rows:
            inc = Incident.model_validate_json(body)
            inc.status = IncidentStatus.queued
            self.update_incident(inc)
        return len(rows)

    def similar_incidents(self, target: TargetRef, incident_class: str, k: int) -> list[Incident]:
        rows = self._q("SELECT body FROM incident WHERE target=? ORDER BY opened_at DESC LIMIT 20", (str(target),))
        out = [Incident.model_validate_json(r[0]) for r in rows]
        return [i for i in out if i.incident_class == incident_class and i.closed_at][:k]

    # --- evidence ----------------------------------------------------------------------------------
    def append_evidence(self, record: EvidenceRecord) -> None:
        self._q("INSERT INTO evidence(evidence_id,incident_id,collected_at,sha256,body) VALUES (?,?,?,?,?)",
                (record.evidence_id, record.incident_id, record.collected_at.isoformat(), record.sha256,
                 record.model_dump_json()))

    def get_evidence(self, evidence_ids: list[str]) -> list[EvidenceRecord]:
        if not evidence_ids:
            return []
        marks = ",".join("?" * len(evidence_ids))
        rows = self._q(f"SELECT body FROM evidence WHERE evidence_id IN ({marks})", tuple(evidence_ids))
        return [EvidenceRecord.model_validate_json(r[0]) for r in rows]

    def list_evidence(self, incident_id: str) -> list[EvidenceRecord]:
        rows = self._q("SELECT body FROM evidence WHERE incident_id=? ORDER BY collected_at", (incident_id,))
        return [EvidenceRecord.model_validate_json(r[0]) for r in rows]

    # --- audit -----------------------------------------------------------------------------------
    def append(self, record: AuditRecord) -> None:
        self._q("INSERT INTO audit(audit_id,incident_id,at,body) VALUES (?,?,?,?)",
                (record.audit_id, record.incident_id, record.at.isoformat(), record.model_dump_json()))

    def list_for(self, incident_id: str) -> list[AuditRecord]:
        rows = self._q("SELECT body FROM audit WHERE incident_id=? ORDER BY at", (incident_id,))
        return [AuditRecord.model_validate_json(r[0]) for r in rows]

    # --- run events (telemetry of the v1.8 nodes; not audit) ---------------------------------------
    def append_run_event(self, incident_id: str, node: str, phase: str, data: dict[str, Any]) -> None:
        with self._lock:
            seq = self._q("SELECT COALESCE(MAX(seq), 0) + 1 FROM run_event WHERE incident_id=?", (incident_id,))[0][0]
            self._q("INSERT INTO run_event(incident_id,seq,at,node,phase,data) VALUES (?,?,?,?,?,?)",
                    (incident_id, seq, utcnow().isoformat(), node, phase, json.dumps(data, default=str)))

    def list_run_events(self, incident_id: str, after_seq: int = 0) -> list[dict]:
        rows = self._q("SELECT seq, at, node, phase, data FROM run_event WHERE incident_id=? AND seq>? ORDER BY seq",
                       (incident_id, after_seq))
        return [{"incident_id": incident_id, "seq": s, "at": a, "node": n, "phase": ph, "data": json.loads(d)}
                for s, a, n, ph, d in rows]

    # --- notifications (recording adapter) -------------------------------------------------------------
    def notify(self, key: str, payload: dict[str, Any]) -> None:
        self._q("INSERT OR IGNORE INTO notification(key,at,payload) VALUES (?,?,?)",
                (key, utcnow().isoformat(), json.dumps(payload, default=str)))

    def notifications(self, limit: int = 50) -> list[dict]:
        rows = self._q("SELECT key, at, payload FROM notification ORDER BY at DESC LIMIT ?", (limit,))
        return [{"key": k, "at": a, "payload": json.loads(p)} for k, a, p in rows]

    # --- principals --------------------------------------------------------------------------------
    def upsert_principal(self, pid: str, kind: str, role: str, scopes: list[str], password_hash: str) -> None:
        self._q("INSERT INTO principal(id,kind,role,scopes,password_hash,disabled) VALUES (?,?,?,?,?,0) "
                "ON CONFLICT(id) DO UPDATE SET kind=excluded.kind, role=excluded.role, scopes=excluded.scopes, "
                "password_hash=excluded.password_hash, disabled=0",
                (pid, kind, role, json.dumps(scopes), password_hash))

    def set_disabled(self, pid: str, disabled: bool) -> None:
        self._q("UPDATE principal SET disabled=? WHERE id=?", (1 if disabled else 0, pid))

    def get_principal(self, pid: str) -> dict | None:
        row = self._q("SELECT id,kind,role,scopes,password_hash,disabled FROM principal WHERE id=?", (pid,))
        if not row:
            return None
        i, k, r, s, h, d = row[0]
        return {"id": i, "kind": k, "role": r, "scopes": json.loads(s), "password_hash": h, "disabled": bool(d)}
