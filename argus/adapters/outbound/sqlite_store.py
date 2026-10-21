"""SQLite adapter for IncidentMemoryPort, AuditSinkPort, NotificationPort and principals (v1.8-lab §4).

Evidence and audit are insert-only (triggers). One process, WAL mode, a lock around each call.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from argus.domain.audit_chain import GENESIS, canonical, link_hash
from argus.domain.model import (AuditRecord, EvidenceRecord, Incident, IncidentStatus, TargetRef, utcnow)

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS incident (
  id TEXT PRIMARY KEY, target TEXT NOT NULL, status TEXT NOT NULL, opened_at TEXT NOT NULL,
  idempotency_key TEXT UNIQUE, body TEXT NOT NULL, claimed_by TEXT, claimed_until TEXT,
  parent_id TEXT REFERENCES incident(id));
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
CREATE TABLE IF NOT EXISTS alert_occurrence (
  identity TEXT PRIMARY KEY, incident_id TEXT NOT NULL, fingerprint TEXT NOT NULL, starts_at TEXT NOT NULL,
  alertname TEXT NOT NULL DEFAULT '', labels TEXT NOT NULL, disposition TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'firing', received_at TEXT NOT NULL, resolved_at TEXT);
CREATE INDEX IF NOT EXISTS alert_occurrence_incident ON alert_occurrence(incident_id, received_at);
CREATE TABLE IF NOT EXISTS monitoring_state (host TEXT PRIMARY KEY, state TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS deploy_event (
  id INTEGER PRIMARY KEY AUTOINCREMENT, host TEXT NOT NULL, commit_sha TEXT NOT NULL, ref TEXT NOT NULL,
  actor TEXT NOT NULL, at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS deploy_event_host ON deploy_event(host, at);
CREATE TRIGGER IF NOT EXISTS deploy_event_no_update BEFORE UPDATE ON deploy_event
  BEGIN SELECT RAISE(ABORT, 'deploy_event is insert-only'); END;
CREATE TRIGGER IF NOT EXISTS deploy_event_no_delete BEFORE DELETE ON deploy_event
  BEGIN SELECT RAISE(ABORT, 'deploy_event is insert-only'); END;
CREATE TABLE IF NOT EXISTS link_event (
  id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL, dependency TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('ok', 'slow', 'broken', 'unknown')), latency_ms REAL, reason TEXT,
  at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS link_event_owner ON link_event(owner, at);
CREATE INDEX IF NOT EXISTS link_event_dependency ON link_event(dependency, at);
CREATE TRIGGER IF NOT EXISTS link_event_no_update BEFORE UPDATE ON link_event
  BEGIN SELECT RAISE(ABORT, 'link_event is insert-only'); END;
CREATE TRIGGER IF NOT EXISTS link_event_no_delete BEFORE DELETE ON link_event
  BEGIN SELECT RAISE(ABORT, 'link_event is insert-only'); END;
CREATE TABLE IF NOT EXISTS incident_hypothesis (
  id INTEGER PRIMARY KEY AUTOINCREMENT, incident_id TEXT NOT NULL, step INTEGER NOT NULL,
  hypothesis_id TEXT NOT NULL, statement TEXT NOT NULL, cause_class TEXT NOT NULL, target TEXT,
  relation TEXT NOT NULL CHECK (relation IN ('self', 'dependency', 'host', 'external')),
  status TEXT NOT NULL CHECK (status IN ('supported', 'ruled_out', 'untested')),
  support_ids TEXT NOT NULL, against_ids TEXT NOT NULL, score REAL NOT NULL, rank INTEGER NOT NULL,
  chosen INTEGER NOT NULL, at TEXT NOT NULL, UNIQUE (incident_id, step, hypothesis_id));
CREATE INDEX IF NOT EXISTS incident_hypothesis_incident ON incident_hypothesis(incident_id, step);
CREATE TRIGGER IF NOT EXISTS incident_hypothesis_no_update BEFORE UPDATE ON incident_hypothesis
  BEGIN SELECT RAISE(ABORT, 'incident_hypothesis is insert-only'); END;
CREATE TRIGGER IF NOT EXISTS incident_hypothesis_no_delete BEFORE DELETE ON incident_hypothesis
  BEGIN SELECT RAISE(ABORT, 'incident_hypothesis is insert-only'); END;
CREATE TABLE IF NOT EXISTS auth_session (
  jti TEXT PRIMARY KEY, principal TEXT NOT NULL, access TEXT NOT NULL, created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL, revoked_at TEXT, revoked_by TEXT, revoke_reason TEXT);
CREATE INDEX IF NOT EXISTS auth_session_principal ON auth_session(principal, created_at);
CREATE TRIGGER IF NOT EXISTS auth_session_no_delete BEFORE DELETE ON auth_session
  BEGIN SELECT RAISE(ABORT, 'auth_session rows are never deleted'); END;
CREATE TABLE IF NOT EXISTS login_failure (
  id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL, at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS login_failure_key ON login_failure(key, at);
CREATE TRIGGER IF NOT EXISTS evidence_no_update BEFORE UPDATE ON evidence
  BEGIN SELECT RAISE(ABORT, 'evidence is insert-only'); END;
CREATE TRIGGER IF NOT EXISTS evidence_no_delete BEFORE DELETE ON evidence
  BEGIN SELECT RAISE(ABORT, 'evidence is insert-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit
  BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit
  BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
"""


def _utc(at: datetime) -> str:
    return at.astimezone(timezone.utc).isoformat()


def _session(r, ts) -> dict[str, Any]:
    """One auth_session row as a dict; `ts` turns a stored time into a datetime (SQLite stores text)."""
    return {"jti": r[0], "principal": r[1], "access": r[2], "created_at": ts(r[3]), "expires_at": ts(r[4]),
            "revoked_at": ts(r[5]) if r[5] is not None else None, "revoked_by": r[6], "revoke_reason": r[7]}


# T-0046 L4: link_event rows with the state of the row before them on the same link (time, then id), so a row that
# repeats it (the recorder's row at a restart) is not read as a transition. Same rule as the Postgres store.
_LINK_ROWS = ("SELECT id, owner, dependency, state, latency_ms, reason, at, LAG(state) OVER (PARTITION BY owner, "
              "dependency ORDER BY at, id) AS prev FROM link_event")


class SqliteStore:
    def __init__(self, path: str):
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.executescript(SCHEMA)
        cols = {r[1] for r in self._db.execute("PRAGMA table_info(incident)")}
        # T-0014, ACR-0021 B5: files created before them. SQLite enforces no foreign key here (no `PRAGMA foreign_keys`,
        # and an added column has no REFERENCES): a re-check's parent is checked by the API only (Postgres: 007's key)
        for col in ("claimed_by", "claimed_until", "parent_id"):
            if col not in cols:
                self._db.execute(f"ALTER TABLE incident ADD COLUMN {col} TEXT")
        self._db.execute("CREATE INDEX IF NOT EXISTS incident_parent ON incident(parent_id, opened_at)")
        if "resolved_at" not in {r[1] for r in self._db.execute("PRAGMA table_info(alert_occurrence)")}:
            self._db.execute("ALTER TABLE alert_occurrence ADD COLUMN resolved_at TEXT")     # T-0026 (migration 005)
        audit_cols = {r[1] for r in self._db.execute("PRAGMA table_info(audit)")}
        for col in ("prev_hash", "hash"):            # ACR-0018 (migration 011): the audit hash chain
            if col not in audit_cols:
                self._db.execute(f"ALTER TABLE audit ADD COLUMN {col} TEXT")

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
            self._q("INSERT INTO incident(id,target,status,opened_at,idempotency_key,body,parent_id) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (incident.id, str(incident.target), incident.status, incident.opened_at.isoformat(),
                     idempotency_key, incident.model_dump_json(), incident.parent_id))
            return incident, False

    def get_incident(self, incident_id: str) -> Incident | None:
        row = self._q("SELECT body FROM incident WHERE id=?", (incident_id,))
        return Incident.model_validate_json(row[0][0]) if row else None

    def update_incident(self, incident: Incident) -> None:
        self._q("UPDATE incident SET status=?, body=? WHERE id=?",
                (incident.status, incident.model_dump_json(), incident.id))

    def list_incidents(self, limit: int = 50, parent_id: str | None = None) -> list[Incident]:
        if parent_id is not None:                                # ACR-0021 B5: the re-checks of one incident
            rows = self._q("SELECT body FROM incident WHERE parent_id=? ORDER BY opened_at DESC LIMIT ?",
                           (parent_id, limit))
        else:
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

    def active_incident(self, target: TargetRef) -> Incident | None:
        """The target's queued or running incident, if any (T-0014: the scheduler's skip-if-active, §6.5)."""
        row = self._q("SELECT body FROM incident WHERE target=? AND status IN (?,?) ORDER BY opened_at LIMIT 1",
                      (str(target), IncidentStatus.queued.value, IncidentStatus.running.value))
        return Incident.model_validate_json(row[0][0]) if row else None

    def latest_concluded_incident(self, target: TargetRef) -> Incident | None:
        """The target's most recent closed or escalated incident (ACR-0004: the episode an alert may still join)."""
        row = self._q("SELECT body FROM incident WHERE target=? AND status IN (?,?) ORDER BY opened_at DESC LIMIT 1",
                      (str(target), IncidentStatus.closed.value, IncidentStatus.escalated.value))
        return Incident.model_validate_json(row[0][0]) if row else None

    def similar_incidents(self, target: TargetRef, incident_class: str, k: int) -> list[Incident]:
        rows = self._q("SELECT body FROM incident WHERE target=? ORDER BY opened_at DESC LIMIT 20", (str(target),))
        out = [Incident.model_validate_json(r[0]) for r in rows]
        return [i for i in out if i.incident_class == incident_class and i.closed_at][:k]

    # --- alert occurrences (OP-011, §6.4) -----------------------------------------------------------
    def incident_for_trigger(self, identity: str) -> str | None:
        """The incident an alert identity already belongs to: as an occurrence, or as the key that opened it."""
        row = self._q("SELECT incident_id FROM alert_occurrence WHERE identity=? UNION ALL "
                      "SELECT id FROM incident WHERE idempotency_key=? LIMIT 1", (identity, identity))
        return row[0][0] if row else None

    def add_alert_occurrence(self, identity: str, incident_id: str, fingerprint: str, starts_at: datetime,
                             labels: dict[str, str], disposition: str, received_at: datetime | None = None) -> bool:
        """Insert-only; False when the identity is already recorded (a concurrent copy of the same alert)."""
        with self._lock:
            if self._q("SELECT 1 FROM alert_occurrence WHERE identity=?", (identity,)):
                return False
            self._q("INSERT INTO alert_occurrence(identity,incident_id,fingerprint,starts_at,alertname,labels,"
                    "disposition,received_at) VALUES (?,?,?,?,?,?,?,?)",
                    (identity, incident_id, fingerprint, starts_at.isoformat(), labels.get("alertname", ""),
                     json.dumps(labels), disposition, (received_at or utcnow()).isoformat()))
            return True

    def alert_occurrences(self, incident_id: str) -> list[dict[str, Any]]:
        rows = self._q("SELECT identity,fingerprint,starts_at,alertname,labels,disposition,status,received_at,"
                       "resolved_at FROM alert_occurrence WHERE incident_id=? ORDER BY received_at, rowid",
                       (incident_id,))
        return [{"identity": r[0], "fingerprint": r[1], "starts_at": datetime.fromisoformat(r[2]), "alertname": r[3],
                 "labels": json.loads(r[4]), "disposition": r[5], "status": r[6],
                 "received_at": datetime.fromisoformat(r[7]),
                 "resolved_at": datetime.fromisoformat(r[8]) if r[8] else None} for r in rows]

    def firing_occurrences(self, host: str, received_before: datetime) -> list[dict[str, Any]]:
        """The host's occurrences still firing that were recorded before `received_before` (T-0026, pull)."""
        rows = self._q("SELECT identity,incident_id,received_at FROM alert_occurrence WHERE status='firing' "
                       "AND json_extract(labels, '$.argus_host')=? ORDER BY received_at, rowid", (host,))
        return [{"identity": r[0], "incident_id": r[1]} for r in rows
                if datetime.fromisoformat(r[2]) <= received_before]

    def resolve_alert_occurrence(self, identity: str, resolved_at: datetime) -> dict[str, Any] | None:
        """firing → resolved, forward only. None when unknown or already resolved."""
        with self._lock:
            row = self._q("SELECT incident_id,fingerprint,alertname FROM alert_occurrence "
                          "WHERE identity=? AND status='firing'", (identity,))
            if not row:
                return None
            self._q("UPDATE alert_occurrence SET status='resolved', resolved_at=? WHERE identity=?",
                    (resolved_at.isoformat(), identity))
            return {"incident_id": row[0][0], "fingerprint": row[0][1], "alertname": row[0][2]}

    def monitoring_state(self, host: str) -> dict[str, Any] | None:
        """ACR-0009: the stored heartbeat state of a host (migration 006)."""
        row = self._q("SELECT state FROM monitoring_state WHERE host=?", (host,))
        return json.loads(row[0][0]) if row else None

    def save_monitoring_state(self, host: str, state: dict[str, Any]) -> None:
        self._q("INSERT INTO monitoring_state(host,state,updated_at) VALUES (?,?,?) ON CONFLICT(host) DO UPDATE SET "
                "state=excluded.state, updated_at=excluded.updated_at",
                (host, json.dumps(state), datetime.now(timezone.utc).isoformat()))

    def add_deploy_event(self, host: str, commit: str, ref: str, actor: str, at: datetime) -> None:
        """ACR-0021 (T-0045 B7): a deploy of `commit` to `host` (`argus deploy record`); insert-only."""
        self._q("INSERT INTO deploy_event(host,commit_sha,ref,actor,at) VALUES (?,?,?,?,?)",
                (host, commit, ref, actor, at.astimezone(timezone.utc).isoformat()))

    def deploy_events(self, host: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        """The host's deploys from `start` to `end`, oldest first."""
        rows = self._q("SELECT commit_sha,ref,actor,at FROM deploy_event WHERE host=? AND at>=? AND at<=? "
                       "ORDER BY at, id", (host, start.astimezone(timezone.utc).isoformat(),
                                           end.astimezone(timezone.utc).isoformat()))
        return [{"commit": r[0], "ref": r[1], "actor": r[2], "at": datetime.fromisoformat(r[3])} for r in rows]

    def add_link_event(self, owner: str, dependency: str, state: str, latency_ms: float | None, reason: str | None,
                       at: datetime) -> None:
        """ACR-0025 (T-0046 L2): a change of one declared link's state; insert-only."""
        self._q("INSERT INTO link_event(owner,dependency,state,latency_ms,reason,at) VALUES (?,?,?,?,?,?)",
                (owner, dependency, state, latency_ms, reason, at.astimezone(timezone.utc).isoformat()))

    # --- hypotheses (ACR-0024 §3.5, T-0047 H2) -----------------------------------------------------------------------
    def add_hypotheses(self, incident_id: str, step: int, rows: list[dict[str, Any]], at: datetime) -> None:
        """One decision step's hypotheses with their score and rank; insert-only."""
        with self._lock:
            for r in rows:
                self._q("INSERT INTO incident_hypothesis(incident_id,step,hypothesis_id,statement,cause_class,target,"
                        "relation,status,support_ids,against_ids,score,rank,chosen,at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (incident_id, step, r["hypothesis_id"], r["statement"], r["cause_class"], r["target"],
                         r["relation"], r["status"], json.dumps(r["support_ids"]), json.dumps(r["against_ids"]),
                         r["score"], r["rank"], int(r["chosen"]), at.astimezone(timezone.utc).isoformat()))

    def hypotheses(self, incident_id: str) -> list[dict[str, Any]]:
        """Every stored hypothesis of an incident, by step, then rank."""
        rows = self._q("SELECT step,hypothesis_id,statement,cause_class,target,relation,status,support_ids,against_ids,"
                       "score,rank,chosen,at FROM incident_hypothesis WHERE incident_id=? ORDER BY step, rank, id",
                       (incident_id,))
        return [{"step": r[0], "hypothesis_id": r[1], "statement": r[2], "cause_class": r[3], "target": r[4],
                 "relation": r[5], "status": r[6], "support_ids": json.loads(r[7]), "against_ids": json.loads(r[8]),
                 "score": r[9], "rank": r[10], "chosen": bool(r[11]), "at": datetime.fromisoformat(r[12])}
                for r in rows]

    # --- sessions and the login limiter (ACR-0018, phase 16 step 1) ------------------------------------------------
    def add_session(self, jti: str, principal: str, access: str, created_at: datetime, expires_at: datetime) -> None:
        self._q("INSERT INTO auth_session(jti,principal,access,created_at,expires_at) VALUES (?,?,?,?,?)",
                (jti, principal, access, _utc(created_at), _utc(expires_at)))

    def get_session(self, jti: str) -> dict[str, Any] | None:
        rows = self._q("SELECT jti,principal,access,created_at,expires_at,revoked_at,revoked_by,revoke_reason "
                       "FROM auth_session WHERE jti=?", (jti,))
        return _session(rows[0], datetime.fromisoformat) if rows else None

    def revoke_session(self, jti: str, by: str, reason: str, at: datetime) -> bool:
        with self._lock:
            cur = self._db.execute("UPDATE auth_session SET revoked_at=?, revoked_by=?, revoke_reason=? "
                                   "WHERE jti=? AND revoked_at IS NULL", (_utc(at), by, reason, jti))
            return cur.rowcount == 1

    def revoke_principal_sessions(self, principal: str, by: str, reason: str, at: datetime) -> int:
        with self._lock:
            cur = self._db.execute("UPDATE auth_session SET revoked_at=?, revoked_by=?, revoke_reason=? "
                                   "WHERE principal=? AND revoked_at IS NULL AND expires_at>?",
                                   (_utc(at), by, reason, principal, _utc(at)))
            return cur.rowcount

    def add_login_failure(self, key: str, at: datetime) -> None:
        self._q("INSERT INTO login_failure(key,at) VALUES (?,?)", (key, _utc(at)))

    def login_failures(self, key: str, since: datetime) -> list[datetime]:
        rows = self._q("SELECT at FROM login_failure WHERE key=? AND at>? ORDER BY at", (key, _utc(since)))
        return [datetime.fromisoformat(r[0]) for r in rows]

    def clear_login_failures(self, key: str) -> None:
        self._q("DELETE FROM login_failure WHERE key=?", (key,))

    def prune_login_failures(self, before: datetime) -> None:
        self._q("DELETE FROM login_failure WHERE at<?", (_utc(before),))

    def link_events(self, target: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        """The transitions of the links `target` owns or is the dependency of, from `start` to `end`, oldest first.
        A row that repeats its link's previous state (the recorder's row at a restart) is not a transition."""
        rows = self._q("SELECT owner,dependency,state,latency_ms,reason,at FROM "
                       f"({_LINK_ROWS} WHERE owner=? OR dependency=?) "
                       "WHERE (prev IS NULL OR prev<>state) AND at>=? AND at<=? ORDER BY at, id",
                       (target, target, start.astimezone(timezone.utc).isoformat(),
                        end.astimezone(timezone.utc).isoformat()))
        return [{"owner": r[0], "dependency": r[1], "state": r[2], "latency_ms": r[3], "reason": r[4],
                 "at": datetime.fromisoformat(r[5])} for r in rows]

    def latest_link_events(self) -> dict[tuple[str, str], dict[str, Any]]:
        """T-0046 L4: the last recorded transition of every link, by (owner, dependency) (the map's `since`)."""
        rows = self._q("SELECT owner,dependency,state,at FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY owner, "
                       f"dependency ORDER BY at DESC, id DESC) AS n FROM ({_LINK_ROWS}) WHERE prev IS NULL OR "
                       "prev<>state) WHERE n=1")
        return {(r[0], r[1]): {"state": r[2], "at": datetime.fromisoformat(r[3])} for r in rows}

    def close_queued_incident(self, incident_id: str, outcome: str, diagnosis: str, closed_at: datetime) -> bool:
        """Close an incident no worker has claimed (T-0026). False when it is no longer queued (claimed meanwhile)."""
        with self._lock:
            row = self._q("SELECT body FROM incident WHERE id=? AND status='queued'", (incident_id,))
            if not row:
                return False
            body = {**json.loads(row[0][0]), "status": "closed", "outcome": outcome, "diagnosis": diagnosis,
                    "closed_at": closed_at.isoformat()}
            self._q("UPDATE incident SET status='closed', body=? WHERE id=?", (json.dumps(body), incident_id))
            return True

    def evidence_state(self, incident_id: str) -> tuple[int, datetime | None]:
        """(evidence_version, last_evidence_at): 1 + the attached occurrences, and the newest occurrence's time."""
        row = self._q("SELECT COALESCE(SUM(disposition='attached'),0), MAX(received_at) FROM alert_occurrence "
                      "WHERE incident_id=?", (incident_id,))
        return 1 + int(row[0][0]), datetime.fromisoformat(row[0][1]) if row[0][1] else None

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
        body = record.model_dump(mode="json")
        with self._lock:                               # ACR-0018: one chained row at a time
            row = self._db.execute("SELECT hash FROM audit WHERE hash IS NOT NULL ORDER BY rowid DESC LIMIT 1").fetchone()
            prev = row[0] if row else GENESIS
            self._db.execute("INSERT INTO audit(audit_id,incident_id,at,body,prev_hash,hash) VALUES (?,?,?,?,?,?)",
                             (record.audit_id, record.incident_id, record.at.isoformat(), canonical(body), prev,
                              link_hash(prev, record.audit_id, body)))

    def audit_chain(self) -> list[tuple[str, Any, str | None, str | None]]:
        """ACR-0018: every audit row in write order, for `argus audit verify`."""
        return [(a, json.loads(b), p, h) for a, b, p, h in
                self._q("SELECT audit_id, body, prev_hash, hash FROM audit ORDER BY rowid")]

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
