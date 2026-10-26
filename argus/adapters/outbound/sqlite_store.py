"""SQLite adapter for IncidentMemoryPort, AuditSinkPort, NotificationPort and principals (v1.8-lab §4).

Evidence and audit are insert-only (triggers). One process, WAL mode, a lock around each call.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
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
CREATE TABLE IF NOT EXISTS link_probe_cursor (
  owner TEXT NOT NULL, dependency TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('ok', 'slow', 'broken', 'unknown')),
  at TEXT NOT NULL, PRIMARY KEY (owner, dependency));
CREATE TRIGGER IF NOT EXISTS link_probe_cursor_identity_immutable BEFORE UPDATE OF owner, dependency ON link_probe_cursor
  BEGIN SELECT RAISE(ABORT, 'link_probe_cursor identity is immutable'); END;
CREATE TRIGGER IF NOT EXISTS link_probe_cursor_monotonic BEFORE UPDATE OF at ON link_probe_cursor
  WHEN NEW.at < OLD.at BEGIN SELECT RAISE(ABORT, 'link_probe_cursor cannot move backwards'); END;
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
CREATE TABLE IF NOT EXISTS webauthn_credential (
  id TEXT PRIMARY KEY, principal TEXT NOT NULL, public_key BLOB NOT NULL, sign_count INTEGER NOT NULL,
  label TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, last_used_at TEXT, revoked_at TEXT, revoked_by TEXT);
CREATE TABLE IF NOT EXISTS webauthn_challenge (
  id TEXT PRIMARY KEY, principal TEXT NOT NULL, session TEXT NOT NULL, kind TEXT NOT NULL, challenge BLOB NOT NULL,
  object TEXT, ticket TEXT, created_at TEXT NOT NULL, expires_at TEXT NOT NULL, used_at TEXT);
CREATE TABLE IF NOT EXISTS webauthn_enrol_ticket (
  id TEXT PRIMARY KEY, principal TEXT NOT NULL, issued_by TEXT NOT NULL, created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL, used_at TEXT);
CREATE TABLE IF NOT EXISTS step_up_token (
  id TEXT PRIMARY KEY, principal TEXT NOT NULL, session TEXT NOT NULL, object TEXT NOT NULL, created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL, used_at TEXT);
CREATE TABLE IF NOT EXISTS action_proposal (
  proposal_id TEXT PRIMARY KEY, incident_id TEXT NOT NULL, capability TEXT NOT NULL, target TEXT NOT NULL,
  digest TEXT NOT NULL CHECK (length(digest) = 64), body TEXT NOT NULL,
  created_at TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS action_proposal_incident ON action_proposal(incident_id, created_at);
CREATE TRIGGER IF NOT EXISTS action_proposal_no_update BEFORE UPDATE ON action_proposal
  BEGIN SELECT RAISE(ABORT, 'action_proposal is insert-only'); END;
CREATE TRIGGER IF NOT EXISTS action_proposal_no_delete BEFORE DELETE ON action_proposal
  BEGIN SELECT RAISE(ABORT, 'action_proposal is insert-only'); END;
CREATE TABLE IF NOT EXISTS judge_verdict (
  proposal_id TEXT PRIMARY KEY REFERENCES action_proposal(proposal_id), model_id TEXT NOT NULL,
  verdict TEXT NOT NULL CHECK (verdict IN ('agree','doubt','disagree')),
  body TEXT NOT NULL, reviewed_at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS judge_verdict_no_update BEFORE UPDATE ON judge_verdict
  BEGIN SELECT RAISE(ABORT, 'judge_verdict is insert-only'); END;
CREATE TRIGGER IF NOT EXISTS judge_verdict_no_delete BEFORE DELETE ON judge_verdict
  BEGIN SELECT RAISE(ABORT, 'judge_verdict is insert-only'); END;
CREATE TABLE IF NOT EXISTS approval (
  approval_id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL UNIQUE REFERENCES action_proposal(proposal_id),
  proposal_digest TEXT NOT NULL, state TEXT NOT NULL CHECK (state IN ('pending','approved','denied','expired','cancelled')),
  actor TEXT, requested_at TEXT NOT NULL, expires_at TEXT NOT NULL CHECK (expires_at > requested_at), answered_at TEXT);
CREATE INDEX IF NOT EXISTS approval_pending ON approval(state, expires_at);
CREATE TRIGGER IF NOT EXISTS approval_insert BEFORE INSERT ON approval
  WHEN NEW.state <> 'pending' OR NEW.actor IS NOT NULL OR NEW.answered_at IS NOT NULL
    OR NEW.proposal_digest IS NOT (SELECT digest FROM action_proposal WHERE proposal_id=NEW.proposal_id)
    OR NEW.expires_at IS NOT (SELECT expires_at FROM action_proposal WHERE proposal_id=NEW.proposal_id)
  BEGIN SELECT RAISE(ABORT, 'approval must bind the frozen proposal'); END;
CREATE TRIGGER IF NOT EXISTS approval_no_delete BEFORE DELETE ON approval
  BEGIN SELECT RAISE(ABORT, 'approval rows are never deleted'); END;
CREATE TRIGGER IF NOT EXISTS approval_forward BEFORE UPDATE ON approval
  WHEN OLD.state <> 'pending' OR NEW.state NOT IN ('approved','denied','expired','cancelled')
    OR NEW.proposal_id <> OLD.proposal_id OR NEW.proposal_digest <> OLD.proposal_digest
    OR NEW.requested_at <> OLD.requested_at OR NEW.expires_at <> OLD.expires_at
    OR NEW.answered_at IS NULL
    OR (NEW.state IN ('approved','denied') AND (NEW.actor IS NULL OR NEW.answered_at >= OLD.expires_at))
  BEGIN SELECT RAISE(ABORT, 'approval transition is not forward-only'); END;
CREATE TRIGGER IF NOT EXISTS approval_needs_agree BEFORE INSERT ON approval
  WHEN NOT EXISTS (SELECT 1 FROM judge_verdict v WHERE v.proposal_id = NEW.proposal_id AND v.verdict = 'agree'
                     AND json_extract(v.body, '$.proposal_digest') = NEW.proposal_digest
                     AND coalesce(json_extract(v.body, '$.risk'), '') <> 'forbidden')
  BEGIN SELECT RAISE(ABORT, 'an approval needs the judge''s agree on this proposal'); END;
CREATE TRIGGER IF NOT EXISTS approval_approved_needs_agree BEFORE UPDATE ON approval
  WHEN NEW.state = 'approved' AND NOT EXISTS (SELECT 1 FROM judge_verdict v WHERE v.proposal_id = NEW.proposal_id
                     AND v.verdict = 'agree' AND json_extract(v.body, '$.proposal_digest') = NEW.proposal_digest
                     AND coalesce(json_extract(v.body, '$.risk'), '') <> 'forbidden')
  BEGIN SELECT RAISE(ABORT, 'an approval needs the judge''s agree on this proposal'); END;
CREATE TABLE IF NOT EXISTS notification_outbox (
  key TEXT PRIMARY KEY, channel TEXT NOT NULL, payload TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT NOT NULL, last_result TEXT, delivered_at TEXT);
CREATE TRIGGER IF NOT EXISTS notification_outbox_forward BEFORE UPDATE ON notification_outbox
  WHEN NEW.key <> OLD.key OR NEW.channel <> OLD.channel OR NEW.payload <> OLD.payload
    OR OLD.delivered_at IS NOT NULL OR NEW.attempts <= OLD.attempts
  BEGIN SELECT RAISE(ABORT, 'notification outbox is forward-only'); END;
CREATE TABLE IF NOT EXISTS resume_intent (
  approval_id TEXT PRIMARY KEY REFERENCES approval(approval_id), incident_id TEXT NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('approved','denied','expired','cancelled')),
  state TEXT NOT NULL CHECK (state IN ('pending','done','failed')),
  attempts INTEGER NOT NULL DEFAULT 0, last_outcome TEXT);
CREATE TRIGGER IF NOT EXISTS resume_intent_insert BEFORE INSERT ON resume_intent
  WHEN NEW.state <> 'pending' OR NEW.decision IS NOT (SELECT state FROM approval WHERE approval_id=NEW.approval_id)
    OR NEW.incident_id IS NOT (SELECT p.incident_id FROM approval a
                              JOIN action_proposal p ON p.proposal_id=a.proposal_id
                              WHERE a.approval_id=NEW.approval_id)
  BEGIN SELECT RAISE(ABORT, 'resume intent does not match approval'); END;
CREATE TRIGGER IF NOT EXISTS resume_intent_forward BEFORE UPDATE ON resume_intent
  WHEN NEW.approval_id <> OLD.approval_id OR NEW.incident_id <> OLD.incident_id
    OR NEW.decision <> OLD.decision OR OLD.state <> 'pending'
    OR NEW.state NOT IN ('pending','done','failed') OR NEW.attempts <= OLD.attempts
  BEGIN SELECT RAISE(ABORT, 'resume intent is forward-only'); END;
CREATE TABLE IF NOT EXISTS action (
  action_id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL REFERENCES action_proposal(proposal_id),
  approval_id TEXT NOT NULL UNIQUE REFERENCES approval(approval_id),
  state TEXT NOT NULL CHECK (state IN ('unstarted','attempting','confirmed','failed','indeterminate')),
  attempted_at TEXT, result_at TEXT, evidence TEXT NOT NULL DEFAULT '{}');
CREATE TRIGGER IF NOT EXISTS action_insert BEFORE INSERT ON action
  WHEN NEW.state NOT IN ('unstarted','attempting')
    OR NEW.proposal_id IS NOT (SELECT proposal_id FROM approval WHERE approval_id=NEW.approval_id)
    OR (SELECT state FROM approval WHERE approval_id=NEW.approval_id) IS NOT 'approved'
    OR (NEW.state='attempting' AND NEW.attempted_at IS NULL)
  BEGIN SELECT RAISE(ABORT, 'action requires approved proposal'); END;
CREATE TRIGGER IF NOT EXISTS action_no_delete BEFORE DELETE ON action
  BEGIN SELECT RAISE(ABORT, 'action rows are never deleted'); END;
CREATE TRIGGER IF NOT EXISTS action_forward BEFORE UPDATE ON action
  WHEN NEW.proposal_id <> OLD.proposal_id OR NEW.approval_id <> OLD.approval_id
    OR NOT ((OLD.state = 'unstarted' AND NEW.state = 'attempting')
         OR (OLD.state = 'attempting' AND NEW.state IN ('confirmed','failed','indeterminate')))
    OR (OLD.state='unstarted' AND (NEW.attempted_at IS NULL OR NEW.result_at IS NOT NULL))
    OR (OLD.state='attempting' AND (NEW.attempted_at IS NOT OLD.attempted_at OR NEW.result_at IS NULL))
  BEGIN SELECT RAISE(ABORT, 'action transition is not forward-only'); END;
CREATE TABLE IF NOT EXISTS target_hold (
  hold_id TEXT PRIMARY KEY, target TEXT NOT NULL, reason TEXT NOT NULL, placed_by TEXT NOT NULL,
  placed_at TEXT NOT NULL, expires_at TEXT, released_by TEXT, released_at TEXT);
CREATE INDEX IF NOT EXISTS target_hold_active ON target_hold(target, placed_at) WHERE released_at IS NULL;
CREATE TRIGGER IF NOT EXISTS target_hold_no_delete BEFORE DELETE ON target_hold
  BEGIN SELECT RAISE(ABORT, 'target_hold rows are never deleted'); END;
CREATE TRIGGER IF NOT EXISTS target_hold_release BEFORE UPDATE ON target_hold
  WHEN OLD.released_at IS NOT NULL OR NEW.released_at IS NULL OR NEW.target <> OLD.target
    OR NEW.reason <> OLD.reason OR NEW.placed_by <> OLD.placed_by
    OR NEW.placed_at <> OLD.placed_at OR NEW.expires_at IS NOT OLD.expires_at
  BEGIN SELECT RAISE(ABORT, 'target hold can be released only once'); END;
CREATE TABLE IF NOT EXISTS action_outcome (
  action_id TEXT PRIMARY KEY REFERENCES action(action_id), incident_id TEXT NOT NULL,
  origin TEXT NOT NULL CHECK (origin IN ('lab','drill','production')),
  outcome TEXT NOT NULL CHECK (outcome IN ('recovered_verified','action_failed','indeterminate_escalated')),
  body TEXT NOT NULL, recorded_at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS action_outcome_insert BEFORE INSERT ON action_outcome
  WHEN (NEW.outcome='recovered_verified' AND
        (SELECT state FROM action WHERE action_id=NEW.action_id) IS NOT 'confirmed')
    OR (NEW.outcome='indeterminate_escalated' AND
        (SELECT state FROM action WHERE action_id=NEW.action_id) IS NOT 'indeterminate')
  BEGIN SELECT RAISE(ABORT, 'action outcome conflicts with ledger'); END;
CREATE TRIGGER IF NOT EXISTS action_outcome_no_update BEFORE UPDATE ON action_outcome
  BEGIN SELECT RAISE(ABORT, 'action_outcome is insert-only'); END;
CREATE TRIGGER IF NOT EXISTS action_outcome_no_delete BEFORE DELETE ON action_outcome
  BEGIN SELECT RAISE(ABORT, 'action_outcome is insert-only'); END;
CREATE TRIGGER IF NOT EXISTS webauthn_credential_no_delete BEFORE DELETE ON webauthn_credential
  BEGIN SELECT RAISE(ABORT, 'webauthn_credential rows are never deleted'); END;
CREATE TRIGGER IF NOT EXISTS webauthn_challenge_no_delete BEFORE DELETE ON webauthn_challenge
  BEGIN SELECT RAISE(ABORT, 'webauthn_challenge rows are never deleted'); END;
CREATE TRIGGER IF NOT EXISTS webauthn_enrol_ticket_no_delete BEFORE DELETE ON webauthn_enrol_ticket
  BEGIN SELECT RAISE(ABORT, 'webauthn_enrol_ticket rows are never deleted'); END;
CREATE TRIGGER IF NOT EXISTS step_up_token_no_delete BEFORE DELETE ON step_up_token
  BEGIN SELECT RAISE(ABORT, 'step_up_token rows are never deleted'); END;
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
            "revoked_at": ts(r[5]) if r[5] is not None else None, "revoked_by": r[6], "revoke_reason": r[7],
            "second_factor_at": ts(r[8]) if r[8] is not None else None}


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
        if "second_factor_at" not in {r[1] for r in self._db.execute("PRAGMA table_info(auth_session)")}:
            self._db.execute("ALTER TABLE auth_session ADD COLUMN second_factor_at TEXT")   # migration 013
        audit_cols = {r[1] for r in self._db.execute("PRAGMA table_info(audit)")}
        for col in ("prev_hash", "hash"):            # ACR-0018 (migration 011): the audit hash chain
            if col not in audit_cols:
                self._db.execute(f"ALTER TABLE audit ADD COLUMN {col} TEXT")

    def _q(self, sql: str, params: tuple = ()) -> list[tuple]:
        with self._lock:
            return self._db.execute(sql, params).fetchall()

    # --- phase 18: offline proposals and human answers --------------------------------------------
    def add_action_proposal(self, proposal) -> None:
        body = proposal.model_dump(mode="json")
        self._q("INSERT INTO action_proposal (proposal_id, incident_id, capability, target, digest, body, "
                "created_at, expires_at) VALUES (?,?,?,?,?,?,?,?)",
                (proposal.id, proposal.input.incident_id, proposal.input.capability, proposal.input.target,
                 proposal.digest, json.dumps(body), _utc(proposal.created_at), _utc(proposal.expires_at)))

    def get_action_proposal(self, proposal_id: str):
        from argus.actions.remediation import FrozenProposal

        rows = self._q("SELECT body FROM action_proposal WHERE proposal_id=?", (proposal_id,))
        return FrozenProposal.model_validate(json.loads(rows[0][0])) if rows else None

    def latest_action_proposal_for_incident(self, incident_id: str):
        rows = self._q("SELECT proposal_id FROM action_proposal WHERE incident_id=? "
                       "ORDER BY created_at DESC, proposal_id DESC LIMIT 1", (incident_id,))
        return self.get_action_proposal(rows[0][0]) if rows else None

    def add_judge_verdict(self, proposal_id: str, model_id: str, verdict: dict, at: datetime) -> None:
        self._q("INSERT INTO judge_verdict (proposal_id, model_id, verdict, body, reviewed_at) "
                "VALUES (?,?,?,?,?)", (proposal_id, model_id, verdict["verdict"], json.dumps(verdict), _utc(at)))

    def get_judge_verdict(self, proposal_id: str) -> dict[str, Any] | None:
        rows = self._q("SELECT body FROM judge_verdict WHERE proposal_id=?", (proposal_id,))
        return json.loads(rows[0][0]) if rows else None

    def add_action_approval(self, approval_id: str, proposal_id: str, digest: str,
                            requested_at: datetime, expires_at: datetime) -> None:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._db.execute("INSERT INTO approval (approval_id, proposal_id, proposal_digest, state, "
                                 "requested_at, expires_at) VALUES (?,?,?,'pending',?,?)",
                                 (approval_id, proposal_id, digest, _utc(requested_at), _utc(expires_at)))
                self._db.execute("INSERT INTO notification_outbox (key, channel, payload, next_attempt_at) "
                                 "VALUES (?,'recording',?,?)",
                                 (approval_id, json.dumps({"approval_id": approval_id, "proposal_digest": digest}),
                                  _utc(requested_at)))
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    def get_action_approval(self, approval_id: str) -> dict[str, Any] | None:
        rows = self._q("SELECT proposal_id, proposal_digest, state, actor, requested_at, expires_at, answered_at "
                       "FROM approval WHERE approval_id=?", (approval_id,))
        if not rows:
            return None
        proposal_id, digest, state, actor, requested, expires, answered = rows[0]
        return {"id": approval_id, "proposal_id": proposal_id, "proposal_digest": digest, "state": state,
                "actor": actor, "requested_at": requested, "expires_at": expires, "answered_at": answered}

    def get_action_approval_for_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        rows = self._q("SELECT approval_id FROM approval WHERE proposal_id=?", (proposal_id,))
        return self.get_action_approval(rows[0][0]) if rows else None

    def answer_action_approval(self, approval_id: str, digest: str, actor: str, decision: str,
                               at: datetime) -> bool:
        if decision not in ("approved", "denied") or not actor:
            raise ValueError("a human decision and actor are required")
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                cur = self._db.execute("UPDATE approval SET state=?, actor=?, answered_at=? WHERE approval_id=? "
                                       "AND proposal_digest=? AND state='pending' AND expires_at>?",
                                       (decision, actor, _utc(at), approval_id, digest, _utc(at)))
                if cur.rowcount == 1:
                    self._db.execute("INSERT INTO resume_intent (approval_id, incident_id, decision, state) "
                                     "SELECT ?, p.incident_id, ?, 'pending' FROM approval a "
                                     "JOIN action_proposal p ON a.proposal_id=p.proposal_id WHERE a.approval_id=?",
                                     (approval_id, decision, approval_id))
                self._db.execute("COMMIT")
                return cur.rowcount == 1
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    def get_resume_intent(self, approval_id: str) -> dict[str, Any] | None:
        rows = self._q("SELECT incident_id, decision, state, attempts, last_outcome FROM resume_intent "
                       "WHERE approval_id=?", (approval_id,))
        if not rows:
            return None
        incident_id, decision, state, attempts, last_outcome = rows[0]
        return {"approval_id": approval_id, "incident_id": incident_id, "decision": decision,
                "state": state, "attempts": attempts, "last_outcome": last_outcome}

    def pending_resume_intents(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._q("SELECT approval_id FROM resume_intent WHERE state='pending' "
                       "ORDER BY rowid LIMIT ?", (limit,))
        return [self.get_resume_intent(r[0]) for r in rows]

    def mark_resume_intent(self, approval_id: str, state: str, outcome: str) -> bool:
        if state not in ("pending", "done", "failed"):
            raise ValueError("invalid resume state")
        with self._lock:
            cur = self._db.execute("UPDATE resume_intent SET state=?, attempts=attempts+1, last_outcome=? "
                                   "WHERE approval_id=? AND state='pending'", (state, outcome, approval_id))
            return cur.rowcount == 1

    def pending_action_notifications(self, at: datetime, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._q("SELECT key, channel, payload, attempts FROM notification_outbox "
                       "WHERE delivered_at IS NULL AND next_attempt_at<=? ORDER BY next_attempt_at, key LIMIT ?",
                       (_utc(at), limit))
        return [{"key": key, "channel": channel, "payload": json.loads(payload), "attempts": attempts}
                for key, channel, payload, attempts in rows]

    def mark_action_notification(self, key: str, *, at: datetime, delivered: bool, result: str) -> bool:
        with self._lock:
            cur = self._db.execute("UPDATE notification_outbox SET attempts=attempts+1, last_result=?, "
                                   "delivered_at=CASE WHEN ? THEN ? ELSE delivered_at END, next_attempt_at=? "
                                   "WHERE key=? AND delivered_at IS NULL",
                                   (result, int(delivered), _utc(at), _utc(at + timedelta(minutes=5)), key))
            return cur.rowcount == 1

    def add_action(self, action_id: str, proposal_id: str, approval_id: str) -> None:
        self._q("INSERT INTO action (action_id, proposal_id, approval_id, state) "
                "VALUES (?,?,?,'unstarted')", (action_id, proposal_id, approval_id))

    def start_action(self, action_id: str, at: datetime) -> bool:
        with self._lock:
            cur = self._db.execute("UPDATE action SET state='attempting', attempted_at=? "
                                   "WHERE action_id=? AND state='unstarted'", (_utc(at), action_id))
            return cur.rowcount == 1

    def finish_action(self, action_id: str, state: str, at: datetime, evidence: dict[str, Any]) -> bool:
        if state not in ("confirmed", "failed", "indeterminate"):
            raise ValueError("invalid terminal action state")
        with self._lock:
            cur = self._db.execute("UPDATE action SET state=?, result_at=?, evidence=? "
                                   "WHERE action_id=? AND state='attempting'",
                                   (state, _utc(at), json.dumps(evidence), action_id))
            return cur.rowcount == 1

    def get_action(self, action_id: str) -> dict[str, Any] | None:
        rows = self._q("SELECT proposal_id, approval_id, state, attempted_at, result_at, evidence "
                       "FROM action WHERE action_id=?", (action_id,))
        if not rows:
            return None
        proposal_id, approval_id, state, attempted_at, result_at, evidence = rows[0]
        return {"id": action_id, "proposal_id": proposal_id, "approval_id": approval_id, "state": state,
                "attempted_at": attempted_at, "result_at": result_at, "evidence": json.loads(evidence)}

    def get_action_for_approval(self, approval_id: str) -> dict[str, Any] | None:
        rows = self._q("SELECT action_id FROM action WHERE approval_id=?", (approval_id,))
        return self.get_action(rows[0][0]) if rows else None

    def reserve_action(self, action_id: str, proposal_id: str, approval_id: str, target: str,
                       at: datetime, *, daily_host_cap: int) -> bool:
        """Atomically enforce single use, a target cooldown and a host daily cap."""
        if daily_host_cap < 1:
            return False
        host = target.split("/", 1)[0]
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                active = self._db.execute(
                    "SELECT COUNT(*) FROM action a JOIN action_proposal p ON p.proposal_id=a.proposal_id "
                    "WHERE p.target=? AND a.state IN ('attempting','indeterminate')",
                    (target,)).fetchone()[0]
                recent = self._db.execute(
                    "SELECT COUNT(*) FROM action a JOIN action_proposal p ON p.proposal_id=a.proposal_id "
                    "WHERE p.target=? AND a.attempted_at>?",
                    (target, _utc(at - timedelta(minutes=10)))).fetchone()[0]
                daily = self._db.execute(
                    "SELECT COUNT(*) FROM action a JOIN action_proposal p ON p.proposal_id=a.proposal_id "
                    "WHERE p.target LIKE ? AND a.attempted_at>=?",
                    (host + '/%', _utc(at - timedelta(hours=24)))).fetchone()[0]
                used = self._db.execute("SELECT 1 FROM action WHERE approval_id=?", (approval_id,)).fetchone()
                if active or recent or daily >= daily_host_cap or used:
                    self._db.execute("ROLLBACK")
                    return False
                self._db.execute("INSERT INTO action (action_id, proposal_id, approval_id, state, attempted_at) "
                                 "VALUES (?,?,?,'attempting',?)",
                                 (action_id, proposal_id, approval_id, _utc(at)))
                self._db.execute("COMMIT")
                return True
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    def add_target_hold(self, hold_id: str, target: str, reason: str, placed_by: str, at: datetime,
                        expires_at: datetime | None = None) -> None:
        self._q("INSERT INTO target_hold (hold_id, target, reason, placed_by, placed_at, expires_at) "
                "VALUES (?,?,?,?,?,?)", (hold_id, target, reason, placed_by, _utc(at),
                                          _utc(expires_at) if expires_at else None))

    def release_target_hold(self, hold_id: str, released_by: str, at: datetime) -> bool:
        with self._lock:
            cur = self._db.execute("UPDATE target_hold SET released_by=?, released_at=? "
                                   "WHERE hold_id=? AND released_at IS NULL",
                                   (released_by, _utc(at), hold_id))
            return cur.rowcount == 1

    def active_target_holds(self, target: str, at: datetime) -> list[str]:
        return [r[0] for r in self._q("SELECT hold_id FROM target_hold WHERE target=? AND released_at IS NULL "
                                      "AND (expires_at IS NULL OR expires_at>?) ORDER BY placed_at, hold_id",
                                      (target, _utc(at)))]

    def add_action_outcome(self, action_id: str, incident_id: str, origin: str, outcome: str,
                           body: dict[str, Any], at: datetime) -> None:
        if origin not in ("lab", "drill", "production") or outcome not in (
                "recovered_verified", "action_failed", "indeterminate_escalated"):
            raise ValueError("invalid action outcome")
        self._q("INSERT INTO action_outcome (action_id, incident_id, origin, outcome, body, recorded_at) "
                "VALUES (?,?,?,?,?,?)", (action_id, incident_id, origin, outcome, json.dumps(body), _utc(at)))

    def get_action_outcome(self, action_id: str) -> dict[str, Any] | None:
        rows = self._q("SELECT outcome, body, recorded_at FROM action_outcome WHERE action_id=?", (action_id,))
        if not rows:
            return None
        return {"outcome": rows[0][0], "body": json.loads(rows[0][1]), "recorded_at": rows[0][2]}

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

    def link_probe_cursors(self, owner: str) -> dict[str, dict[str, Any]]:
        """The last sampled state and timestamp processed for each dependency of an owner (T-0046, migration 014)."""
        rows = self._q("SELECT dependency,state,at FROM link_probe_cursor WHERE owner=?", (owner,))
        return {dependency: {"state": state, "at": datetime.fromisoformat(at)}
                for dependency, state, at in rows}

    def record_link_probe(self, owner: str, dependency: str, state: str, latency_ms: float | None,
                          reason: str | None, at: datetime) -> bool:
        """Advance one link cursor; commit its transition row and chained audit atomically when state changed."""
        from argus.domain.model import AuditRecord
        at_text = at.astimezone(timezone.utc).isoformat()
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                row = self._db.execute("SELECT state,at FROM link_probe_cursor WHERE owner=? AND dependency=?",
                                       (owner, dependency)).fetchone()
                if row and at_text <= row[1]:
                    self._db.execute("ROLLBACK")
                    return False
                previous = row[0] if row else None
                changed = previous != state
                if changed:
                    self._db.execute("INSERT INTO link_event(owner,dependency,state,latency_ms,reason,at) "
                                     "VALUES (?,?,?,?,?,?)", (owner, dependency, state, latency_ms, reason, at_text))
                    self.append(AuditRecord(
                        audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=None, at=at.astimezone(timezone.utc),
                        category="incident", event="link.changed", actor="scheduler",
                        detail={"owner": owner, "dependency": dependency, "from": previous, "to": state,
                                "latency_ms": latency_ms, "reason": reason}))
                self._db.execute("INSERT INTO link_probe_cursor(owner,dependency,state,at) VALUES (?,?,?,?) "
                                 "ON CONFLICT(owner,dependency) DO UPDATE SET state=excluded.state, at=excluded.at",
                                 (owner, dependency, state, at_text))
                self._db.execute("COMMIT")
                return changed
            except Exception:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

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
        rows = self._q("SELECT jti,principal,access,created_at,expires_at,revoked_at,revoked_by,revoke_reason,"
                       "second_factor_at FROM auth_session WHERE jti=?", (jti,))
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

    def set_session_second_factor(self, jti: str, at: datetime) -> bool:
        with self._lock:
            cur = self._db.execute("UPDATE auth_session SET second_factor_at=? WHERE jti=? AND revoked_at IS NULL",
                                   (_utc(at), jti))
            return cur.rowcount == 1

    # --- WebAuthn and the step-up token (ACR-0018, phase 16 step 3; migration 013) -----------------------------------
    def add_webauthn_credential(self, cred_id: str, principal: str, public_key: bytes, sign_count: int, label: str,
                                at: datetime) -> None:
        self._q("INSERT INTO webauthn_credential(id,principal,public_key,sign_count,label,created_at) "
                "VALUES (?,?,?,?,?,?)", (cred_id, principal, public_key, sign_count, label, _utc(at)))

    def webauthn_credentials(self, principal: str) -> list[dict[str, Any]]:
        """The principal's credentials that are not revoked, oldest first."""
        rows = self._q("SELECT id,principal,public_key,sign_count,label,created_at,last_used_at FROM webauthn_credential "
                       "WHERE principal=? AND revoked_at IS NULL ORDER BY created_at, id", (principal,))
        return [{"id": r[0], "principal": r[1], "public_key": bytes(r[2]), "sign_count": r[3], "label": r[4],
                 "created_at": datetime.fromisoformat(r[5]),
                 "last_used_at": datetime.fromisoformat(r[6]) if r[6] else None} for r in rows]

    def update_webauthn_sign_count(self, cred_id: str, sign_count: int, at: datetime) -> bool:
        with self._lock:
            cur = self._db.execute("UPDATE webauthn_credential SET sign_count=?, last_used_at=? "
                                   "WHERE id=? AND revoked_at IS NULL", (sign_count, _utc(at), cred_id))
            return cur.rowcount == 1

    def revoke_webauthn_credentials(self, principal: str, by: str, at: datetime) -> int:
        with self._lock:
            cur = self._db.execute("UPDATE webauthn_credential SET revoked_at=?, revoked_by=? "
                                   "WHERE principal=? AND revoked_at IS NULL", (_utc(at), by, principal))
            return cur.rowcount

    def add_webauthn_challenge(self, challenge_id: str, principal: str, session: str, kind: str, challenge: bytes,
                               obj: str | None, ticket: str | None, at: datetime, expires_at: datetime) -> None:
        self._q("INSERT INTO webauthn_challenge(id,principal,session,kind,challenge,object,ticket,created_at,expires_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (challenge_id, principal, session, kind, challenge, obj, ticket, _utc(at), _utc(expires_at)))

    def take_webauthn_challenge(self, challenge_id: str, principal: str, session: str, kind: str,
                                at: datetime) -> dict[str, Any] | None:
        """Marks the challenge used and returns it, once, while it is unexpired and this principal's, session's and
        ceremony's; else None."""
        with self._lock:
            rows = self._db.execute("SELECT challenge,object,ticket FROM webauthn_challenge WHERE id=? AND principal=? "
                                    "AND session=? AND kind=? AND used_at IS NULL AND expires_at>?",
                                    (challenge_id, principal, session, kind, _utc(at))).fetchall()
            if not rows:
                return None
            self._db.execute("UPDATE webauthn_challenge SET used_at=? WHERE id=?", (_utc(at), challenge_id))
            return {"challenge": bytes(rows[0][0]), "object": rows[0][1], "ticket": rows[0][2]}

    def add_enrol_ticket(self, ticket_id: str, principal: str, issued_by: str, at: datetime,
                         expires_at: datetime) -> None:
        self._q("INSERT INTO webauthn_enrol_ticket(id,principal,issued_by,created_at,expires_at) VALUES (?,?,?,?,?)",
                (ticket_id, principal, issued_by, _utc(at), _utc(expires_at)))

    def enrol_ticket_valid(self, ticket_id: str, principal: str, at: datetime) -> bool:
        return bool(self._q("SELECT 1 FROM webauthn_enrol_ticket WHERE id=? AND principal=? AND used_at IS NULL "
                            "AND expires_at>?", (ticket_id, principal, _utc(at))))

    def use_enrol_ticket(self, ticket_id: str, principal: str, at: datetime) -> bool:
        with self._lock:
            cur = self._db.execute("UPDATE webauthn_enrol_ticket SET used_at=? WHERE id=? AND principal=? "
                                   "AND used_at IS NULL AND expires_at>?", (_utc(at), ticket_id, principal, _utc(at)))
            return cur.rowcount == 1

    def add_step_up(self, token_id: str, principal: str, session: str, obj: str, at: datetime,
                    expires_at: datetime) -> None:
        self._q("INSERT INTO step_up_token(id,principal,session,object,created_at,expires_at) VALUES (?,?,?,?,?,?)",
                (token_id, principal, session, obj, _utc(at), _utc(expires_at)))

    def take_step_up(self, token_id: str, at: datetime) -> dict[str, Any] | None:
        """Marks the token used and returns its binding, once, while unexpired; else None."""
        with self._lock:
            rows = self._db.execute("SELECT principal,session,object FROM step_up_token WHERE id=? AND used_at IS NULL "
                                    "AND expires_at>?", (token_id, _utc(at))).fetchall()
            if not rows:
                return None
            self._db.execute("UPDATE step_up_token SET used_at=? WHERE id=?", (_utc(at), token_id))
            return {"principal": rows[0][0], "session": rows[0][1], "object": rows[0][2]}

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

    def audit_since(self, since: datetime, events: tuple[str, ...]) -> list[AuditRecord]:
        """ACR-0018 §18: the audit rows of these events written after `since`, oldest first (the security alerts)."""
        marks = ",".join("?" * len(events))
        rows = self._q(f"SELECT body FROM audit WHERE at > ? AND json_extract(body, '$.event') IN ({marks}) "
                       "ORDER BY at, rowid", (since.isoformat(), *events))
        return [AuditRecord.model_validate_json(r[0]) for r in rows]

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
