"""PostgreSQL adapter for IncidentMemoryPort, AuditSinkPort, NotificationPort and principals (v1.8 §14; Phase 5).

Same interface as SqliteStore. The schema lives in deploy/migrations (applied by the owner, never by the agent);
this adapter connects as argus_runtime, which cannot UPDATE/DELETE evidence or audit. A small pool reconnects
after a Postgres restart.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Any

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from argus.domain.audit_chain import GENESIS, link_hash
from argus.domain.model import AuditRecord, EvidenceRecord, Incident, TargetRef, utcnow


AUDIT_CHAIN_LOCK = 0x41524755530A   # pg_advisory_xact_lock key of the audit chain (ACR-0018)

# T-0046 L4: link_event rows with the state of the row before them on the same link (time, then id), so a row that
# repeats it (the recorder's row at a restart) is not read as a transition. Same rule as the SQLite store.
_LINK_ROWS = ("SELECT id, owner, dependency, state, latency_ms, reason, at, LAG(state) OVER (PARTITION BY owner, "
              "dependency ORDER BY at, id) AS prev FROM link_event")


def append_chained(conn, record: AuditRecord) -> None:
    """ACR-0018 (migration 011): write one audit row chained to the last one, inside the caller's transaction. Every
    writer goes through here (the store, the owner-run maintenance commands): a row inserted any other way has no hash
    and `argus audit verify` reports it. The advisory lock is held until the caller commits."""
    body = record.model_dump(mode="json")
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (AUDIT_CHAIN_LOCK,))
    row = conn.execute("SELECT hash FROM audit WHERE hash IS NOT NULL ORDER BY seq DESC LIMIT 1").fetchone()
    prev = row[0] if row else GENESIS
    conn.execute("INSERT INTO audit (audit_id, incident_id, at, body, prev_hash, hash) VALUES (%s, %s, %s, %s, %s, %s)",
                 (record.audit_id, record.incident_id, record.at, Jsonb(body), prev,
                  link_hash(prev, record.audit_id, body)))


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

    # --- phase 18: frozen proposals and forward-only human answers -------------------------------
    def add_action_proposal(self, proposal) -> None:
        self._q("INSERT INTO action_proposal (proposal_id, incident_id, capability, target, digest, body, "
                "created_at, expires_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (proposal.id, proposal.input.incident_id, proposal.input.capability, proposal.input.target,
                 proposal.digest, Jsonb(proposal.model_dump(mode="json")), proposal.created_at, proposal.expires_at))

    def get_action_proposal(self, proposal_id: str):
        from argus.actions.remediation import FrozenProposal

        rows = self._q("SELECT body FROM action_proposal WHERE proposal_id=%s", (proposal_id,))
        return FrozenProposal.model_validate(rows[0][0]) if rows else None

    def latest_action_proposal_for_incident(self, incident_id: str):
        rows = self._q("SELECT proposal_id FROM action_proposal WHERE incident_id=%s "
                       "ORDER BY created_at DESC, proposal_id DESC LIMIT 1", (incident_id,))
        return self.get_action_proposal(rows[0][0]) if rows else None

    def add_judge_verdict(self, proposal_id: str, model_id: str, verdict: dict, at: datetime) -> None:
        self._q("INSERT INTO judge_verdict (proposal_id, model_id, verdict, body, reviewed_at) "
                "VALUES (%s,%s,%s,%s,%s)",
                (proposal_id, model_id, verdict["verdict"], Jsonb(verdict), at))

    def get_judge_verdict(self, proposal_id: str) -> dict[str, Any] | None:
        rows = self._q("SELECT body FROM judge_verdict WHERE proposal_id=%s", (proposal_id,))
        return rows[0][0] if rows else None

    def add_action_approval(self, approval_id: str, proposal_id: str, digest: str,
                            requested_at: datetime, expires_at: datetime) -> None:
        with self.pool.connection() as c, c.transaction():
            c.execute("INSERT INTO approval (approval_id, proposal_id, proposal_digest, state, requested_at, "
                      "expires_at) VALUES (%s,%s,%s,'pending',%s,%s)",
                      (approval_id, proposal_id, digest, requested_at, expires_at))
            c.execute("INSERT INTO notification_outbox (key, channel, payload, next_attempt_at) "
                      "VALUES (%s,'recording',%s,%s)",
                      (approval_id, Jsonb({"approval_id": approval_id, "proposal_digest": digest}), requested_at))

    def get_action_approval(self, approval_id: str) -> dict[str, Any] | None:
        rows = self._q("SELECT proposal_id, proposal_digest, state, actor, requested_at, expires_at, answered_at "
                       "FROM approval WHERE approval_id=%s", (approval_id,))
        if not rows:
            return None
        proposal_id, digest, state, actor, requested, expires, answered = rows[0]
        return {"id": approval_id, "proposal_id": proposal_id, "proposal_digest": digest, "state": state,
                "actor": actor, "requested_at": requested, "expires_at": expires, "answered_at": answered}

    def get_action_approval_for_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        rows = self._q("SELECT approval_id FROM approval WHERE proposal_id=%s", (proposal_id,))
        return self.get_action_approval(rows[0][0]) if rows else None

    def answer_action_approval(self, approval_id: str, digest: str, actor: str, decision: str,
                               at: datetime) -> bool:
        if decision not in ("approved", "denied") or not actor:
            raise ValueError("a human decision and actor are required")
        with self.pool.connection() as c, c.transaction():
            row = c.execute("UPDATE approval SET state=%s, actor=%s, answered_at=%s WHERE approval_id=%s "
                            "AND proposal_digest=%s AND state='pending' AND expires_at>%s RETURNING proposal_id",
                            (decision, actor, at, approval_id, digest, at)).fetchone()
            if row:
                c.execute("INSERT INTO resume_intent (approval_id, incident_id, decision, state) "
                          "SELECT %s, incident_id, %s, 'pending' FROM action_proposal WHERE proposal_id=%s",
                          (approval_id, decision, row[0]))
            return row is not None

    def get_resume_intent(self, approval_id: str) -> dict[str, Any] | None:
        rows = self._q("SELECT incident_id, decision, state, attempts, last_outcome FROM resume_intent "
                       "WHERE approval_id=%s", (approval_id,))
        if not rows:
            return None
        incident_id, decision, state, attempts, last_outcome = rows[0]
        return {"approval_id": approval_id, "incident_id": incident_id, "decision": decision,
                "state": state, "attempts": attempts, "last_outcome": last_outcome}

    def pending_resume_intents(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._q("SELECT approval_id FROM resume_intent WHERE state='pending' "
                       "ORDER BY approval_id LIMIT %s", (limit,))
        return [self.get_resume_intent(r[0]) for r in rows]

    def mark_resume_intent(self, approval_id: str, state: str, outcome: str) -> bool:
        if state not in ("pending", "done", "failed"):
            raise ValueError("invalid resume state")
        return bool(self._q("UPDATE resume_intent SET state=%s, attempts=attempts+1, last_outcome=%s "
                            "WHERE approval_id=%s AND state='pending' RETURNING approval_id",
                            (state, outcome, approval_id)))

    def pending_action_notifications(self, at: datetime, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._q("SELECT key, channel, payload, attempts FROM notification_outbox "
                       "WHERE delivered_at IS NULL AND next_attempt_at<=%s "
                       "ORDER BY next_attempt_at, key LIMIT %s", (at, limit))
        return [{"key": key, "channel": channel, "payload": payload, "attempts": attempts}
                for key, channel, payload, attempts in rows]

    def mark_action_notification(self, key: str, *, at: datetime, delivered: bool, result: str) -> bool:
        return bool(self._q("UPDATE notification_outbox SET attempts=attempts+1, last_result=%s, "
                            "delivered_at=CASE WHEN %s THEN %s ELSE delivered_at END, "
                            "next_attempt_at=%s WHERE key=%s AND delivered_at IS NULL RETURNING key",
                            (result, delivered, at, at + timedelta(minutes=5), key)))

    def add_action(self, action_id: str, proposal_id: str, approval_id: str) -> None:
        self._q("INSERT INTO action (action_id, proposal_id, approval_id, state) "
                "VALUES (%s,%s,%s,'unstarted')", (action_id, proposal_id, approval_id))

    def start_action(self, action_id: str, at: datetime) -> bool:
        return bool(self._q("UPDATE action SET state='attempting', attempted_at=%s "
                            "WHERE action_id=%s AND state='unstarted' RETURNING action_id", (at, action_id)))

    def finish_action(self, action_id: str, state: str, at: datetime, evidence: dict[str, Any]) -> bool:
        if state not in ("confirmed", "failed", "indeterminate"):
            raise ValueError("invalid terminal action state")
        return bool(self._q("UPDATE action SET state=%s, result_at=%s, evidence=%s "
                            "WHERE action_id=%s AND state='attempting' RETURNING action_id",
                            (state, at, Jsonb(evidence), action_id)))

    def get_action(self, action_id: str) -> dict[str, Any] | None:
        rows = self._q("SELECT proposal_id, approval_id, state, attempted_at, result_at, evidence "
                       "FROM action WHERE action_id=%s", (action_id,))
        if not rows:
            return None
        proposal_id, approval_id, state, attempted_at, result_at, evidence = rows[0]
        return {"id": action_id, "proposal_id": proposal_id, "approval_id": approval_id, "state": state,
                "attempted_at": attempted_at, "result_at": result_at, "evidence": evidence}

    def get_action_for_approval(self, approval_id: str) -> dict[str, Any] | None:
        rows = self._q("SELECT action_id FROM action WHERE approval_id=%s", (approval_id,))
        return self.get_action(rows[0][0]) if rows else None

    def reserve_action(self, action_id: str, proposal_id: str, approval_id: str, target: str,
                       at: datetime, *, daily_host_cap: int) -> bool:
        """Serialize claims by host and target before checking limits and inserting attempting."""
        if daily_host_cap < 1:
            return False
        host = target.split("/", 1)[0]
        with self.pool.connection() as c, c.transaction():
            # Host lock also serializes claims for different targets under the daily cap.
            c.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", ("action-host:" + host,))
            c.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", ("action-target:" + target,))
            active, recent, daily, used = c.execute(
                "SELECT "
                "(SELECT count(*) FROM action a JOIN action_proposal p USING (proposal_id) WHERE p.target=%s "
                "AND a.state IN ('attempting','indeterminate')), "
                "(SELECT count(*) FROM action a JOIN action_proposal p USING (proposal_id) WHERE p.target=%s "
                "AND a.attempted_at>%s), "
                "(SELECT count(*) FROM action a JOIN action_proposal p USING (proposal_id) WHERE "
                "split_part(p.target,'/',1)=%s AND a.attempted_at>=%s), "
                "(SELECT count(*) FROM action WHERE approval_id=%s)",
                (target, target, at - timedelta(minutes=10), host, at - timedelta(hours=24), approval_id)
            ).fetchone()
            if active or recent or daily >= daily_host_cap or used:
                return False
            c.execute("INSERT INTO action (action_id, proposal_id, approval_id, state, attempted_at) "
                      "VALUES (%s,%s,%s,'attempting',%s)", (action_id, proposal_id, approval_id, at))
            return True

    def add_target_hold(self, hold_id: str, target: str, reason: str, placed_by: str, at: datetime,
                        expires_at: datetime | None = None) -> None:
        self._q("INSERT INTO target_hold (hold_id, target, reason, placed_by, placed_at, expires_at) "
                "VALUES (%s,%s,%s,%s,%s,%s)", (hold_id, target, reason, placed_by, at, expires_at))

    def release_target_hold(self, hold_id: str, released_by: str, at: datetime) -> bool:
        return bool(self._q("UPDATE target_hold SET released_by=%s, released_at=%s "
                            "WHERE hold_id=%s AND released_at IS NULL RETURNING hold_id",
                            (released_by, at, hold_id)))

    def active_target_holds(self, target: str, at: datetime) -> list[str]:
        return [r[0] for r in self._q("SELECT hold_id FROM target_hold WHERE target=%s AND released_at IS NULL "
                                      "AND (expires_at IS NULL OR expires_at>%s) ORDER BY placed_at, hold_id",
                                      (target, at))]

    def add_action_outcome(self, action_id: str, incident_id: str, origin: str, outcome: str,
                           body: dict[str, Any], at: datetime) -> None:
        if origin not in ("lab", "drill", "production") or outcome not in (
                "recovered_verified", "action_failed", "indeterminate_escalated"):
            raise ValueError("invalid action outcome")
        self._q("INSERT INTO action_outcome (action_id, incident_id, origin, outcome, body, recorded_at) "
                "VALUES (%s,%s,%s,%s,%s,%s)", (action_id, incident_id, origin, outcome, Jsonb(body), at))

    def get_action_outcome(self, action_id: str) -> dict[str, Any] | None:
        rows = self._q("SELECT outcome, body, recorded_at FROM action_outcome WHERE action_id=%s", (action_id,))
        return {"outcome": rows[0][0], "body": rows[0][1], "recorded_at": rows[0][2]} if rows else None

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

    def add_deploy_event(self, host: str, commit: str, ref: str, actor: str, at: datetime) -> None:
        """ACR-0021 (T-0045 B7): a deploy of `commit` to `host` (`argus deploy record`); insert-only (migration 008)."""
        self._q("INSERT INTO deploy_event (host, commit_sha, ref, actor, at) VALUES (%s, %s, %s, %s, %s)",
                (host, commit, ref, actor, at))

    def deploy_events(self, host: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        """The host's deploys from `start` to `end`, oldest first."""
        rows = self._q("SELECT commit_sha, ref, actor, at FROM deploy_event WHERE host = %s AND at >= %s AND at <= %s "
                       "ORDER BY at, id", (host, start, end))
        return [{"commit": r[0], "ref": r[1], "actor": r[2], "at": r[3]} for r in rows]

    def add_link_event(self, owner: str, dependency: str, state: str, latency_ms: float | None, reason: str | None,
                       at: datetime) -> None:
        """ACR-0025 (T-0046 L2): a change of one declared link's state; insert-only (migration 009)."""
        self._q("INSERT INTO link_event (owner, dependency, state, latency_ms, reason, at) VALUES (%s, %s, %s, %s, %s, %s)",
                (owner, dependency, state, latency_ms, reason, at))

    def link_probe_cursors(self, owner: str) -> dict[str, dict[str, Any]]:
        """The last sampled state and timestamp processed for each dependency of an owner (T-0046, migration 014)."""
        rows = self._q("SELECT dependency,state,at FROM link_probe_cursor WHERE owner = %s", (owner,))
        return {dependency: {"state": state, "at": at} for dependency, state, at in rows}

    def record_link_probe(self, owner: str, dependency: str, state: str, latency_ms: float | None,
                          reason: str | None, at: datetime) -> bool:
        """Advance one link cursor; commit its transition row and chained audit atomically when state changed."""
        with self.pool.connection() as c, c.transaction():
            row = c.execute("SELECT state,at FROM link_probe_cursor WHERE owner=%s AND dependency=%s FOR UPDATE",
                            (owner, dependency)).fetchone()
            if row and at <= row[1]:
                return False
            previous = row[0] if row else None
            changed = previous != state
            if changed:
                c.execute("INSERT INTO link_event (owner,dependency,state,latency_ms,reason,at) "
                          "VALUES (%s,%s,%s,%s,%s,%s)", (owner, dependency, state, latency_ms, reason, at))
                append_chained(c, AuditRecord(
                    audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=None, at=at,
                    category="incident", event="link.changed", actor="scheduler",
                    detail={"owner": owner, "dependency": dependency, "from": previous, "to": state,
                            "latency_ms": latency_ms, "reason": reason}))
            c.execute("INSERT INTO link_probe_cursor (owner,dependency,state,at) VALUES (%s,%s,%s,%s) "
                      "ON CONFLICT (owner,dependency) DO UPDATE SET state=EXCLUDED.state, at=EXCLUDED.at",
                      (owner, dependency, state, at))
            return changed

    # --- hypotheses (ACR-0024 §3.5, T-0047 H2; migration 012) --------------------------------------------------------
    def add_hypotheses(self, incident_id: str, step: int, rows: list[dict[str, Any]], at: datetime) -> None:
        """One decision step's hypotheses with their score and rank; insert-only, in one transaction."""
        with self.pool.connection() as c, c.transaction():
            for r in rows:
                c.execute("INSERT INTO incident_hypothesis (incident_id, step, hypothesis_id, statement, cause_class, "
                          "target, relation, status, support_ids, against_ids, score, rank, chosen, at) "
                          "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                          (incident_id, step, r["hypothesis_id"], r["statement"], r["cause_class"], r["target"],
                           r["relation"], r["status"], list(r["support_ids"]), list(r["against_ids"]), r["score"],
                           r["rank"], bool(r["chosen"]), at))

    def hypotheses(self, incident_id: str) -> list[dict[str, Any]]:
        """Every stored hypothesis of an incident, by step, then rank."""
        rows = self._q("SELECT step, hypothesis_id, statement, cause_class, target, relation, status, support_ids, "
                       "against_ids, score, rank, chosen, at FROM incident_hypothesis WHERE incident_id = %s "
                       "ORDER BY step, rank, id", (incident_id,))
        return [{"step": r[0], "hypothesis_id": r[1], "statement": r[2], "cause_class": r[3], "target": r[4],
                 "relation": r[5], "status": r[6], "support_ids": list(r[7]), "against_ids": list(r[8]),
                 "score": r[9], "rank": r[10], "chosen": r[11], "at": r[12]} for r in rows]

    # --- sessions and the login limiter (ACR-0018, phase 16 step 1; migration 010) ---------------------------------
    def add_session(self, jti: str, principal: str, access: str, created_at: datetime, expires_at: datetime) -> None:
        self._q("INSERT INTO auth_session (jti, principal, access, created_at, expires_at) VALUES (%s, %s, %s, %s, %s)",
                (jti, principal, access, created_at, expires_at))

    def get_session(self, jti: str) -> dict[str, Any] | None:
        rows = self._q("SELECT jti, principal, access, created_at, expires_at, revoked_at, revoked_by, revoke_reason, "
                       "second_factor_at FROM auth_session WHERE jti = %s", (jti,))
        if not rows:
            return None
        r = rows[0]
        return {"jti": r[0], "principal": r[1], "access": r[2], "created_at": r[3], "expires_at": r[4],
                "revoked_at": r[5], "revoked_by": r[6], "revoke_reason": r[7], "second_factor_at": r[8]}

    def revoke_session(self, jti: str, by: str, reason: str, at: datetime) -> bool:
        return bool(self._q("UPDATE auth_session SET revoked_at = %s, revoked_by = %s, revoke_reason = %s "
                            "WHERE jti = %s AND revoked_at IS NULL RETURNING jti", (at, by, reason, jti)))

    def revoke_principal_sessions(self, principal: str, by: str, reason: str, at: datetime) -> int:
        return len(self._q("UPDATE auth_session SET revoked_at = %s, revoked_by = %s, revoke_reason = %s "
                           "WHERE principal = %s AND revoked_at IS NULL AND expires_at > %s RETURNING jti",
                           (at, by, reason, principal, at)))

    def set_session_second_factor(self, jti: str, at: datetime) -> bool:
        return bool(self._q("UPDATE auth_session SET second_factor_at = %s WHERE jti = %s AND revoked_at IS NULL "
                            "RETURNING jti", (at, jti)))

    # --- WebAuthn and the step-up token (ACR-0018, phase 16 step 3; migration 013) -----------------------------------
    def add_webauthn_credential(self, cred_id: str, principal: str, public_key: bytes, sign_count: int, label: str,
                                at: datetime) -> None:
        self._q("INSERT INTO webauthn_credential (id, principal, public_key, sign_count, label, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)", (cred_id, principal, public_key, sign_count, label, at))

    def webauthn_credentials(self, principal: str) -> list[dict[str, Any]]:
        """The principal's credentials that are not revoked, oldest first."""
        rows = self._q("SELECT id, principal, public_key, sign_count, label, created_at, last_used_at "
                       "FROM webauthn_credential WHERE principal = %s AND revoked_at IS NULL ORDER BY created_at, id",
                       (principal,))
        return [{"id": r[0], "principal": r[1], "public_key": bytes(r[2]), "sign_count": r[3], "label": r[4],
                 "created_at": r[5], "last_used_at": r[6]} for r in rows]

    def update_webauthn_sign_count(self, cred_id: str, sign_count: int, at: datetime) -> bool:
        return bool(self._q("UPDATE webauthn_credential SET sign_count = %s, last_used_at = %s "
                            "WHERE id = %s AND revoked_at IS NULL RETURNING id", (sign_count, at, cred_id)))

    def revoke_webauthn_credentials(self, principal: str, by: str, at: datetime) -> int:
        return len(self._q("UPDATE webauthn_credential SET revoked_at = %s, revoked_by = %s "
                           "WHERE principal = %s AND revoked_at IS NULL RETURNING id", (at, by, principal)))

    def add_webauthn_challenge(self, challenge_id: str, principal: str, session: str, kind: str, challenge: bytes,
                               obj: str | None, ticket: str | None, at: datetime, expires_at: datetime) -> None:
        self._q("INSERT INTO webauthn_challenge (id, principal, session, kind, challenge, object, ticket, created_at, "
                "expires_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (challenge_id, principal, session, kind, challenge, obj, ticket, at, expires_at))

    def take_webauthn_challenge(self, challenge_id: str, principal: str, session: str, kind: str,
                                at: datetime) -> dict[str, Any] | None:
        """Marks the challenge used and returns it, once (one UPDATE: two concurrent takes cannot both get it), while
        it is unexpired and this principal's, session's and ceremony's; else None."""
        rows = self._q("UPDATE webauthn_challenge SET used_at = %s WHERE id = %s AND principal = %s AND session = %s "
                       "AND kind = %s AND used_at IS NULL AND expires_at > %s RETURNING challenge, object, ticket",
                       (at, challenge_id, principal, session, kind, at))
        return {"challenge": bytes(rows[0][0]), "object": rows[0][1], "ticket": rows[0][2]} if rows else None

    def add_enrol_ticket(self, ticket_id: str, principal: str, issued_by: str, at: datetime,
                         expires_at: datetime) -> None:
        self._q("INSERT INTO webauthn_enrol_ticket (id, principal, issued_by, created_at, expires_at) "
                "VALUES (%s, %s, %s, %s, %s)", (ticket_id, principal, issued_by, at, expires_at))

    def enrol_ticket_valid(self, ticket_id: str, principal: str, at: datetime) -> bool:
        return bool(self._q("SELECT 1 FROM webauthn_enrol_ticket WHERE id = %s AND principal = %s AND used_at IS NULL "
                            "AND expires_at > %s", (ticket_id, principal, at)))

    def use_enrol_ticket(self, ticket_id: str, principal: str, at: datetime) -> bool:
        return bool(self._q("UPDATE webauthn_enrol_ticket SET used_at = %s WHERE id = %s AND principal = %s "
                            "AND used_at IS NULL AND expires_at > %s RETURNING id", (at, ticket_id, principal, at)))

    def add_step_up(self, token_id: str, principal: str, session: str, obj: str, at: datetime,
                    expires_at: datetime) -> None:
        self._q("INSERT INTO step_up_token (id, principal, session, object, created_at, expires_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)", (token_id, principal, session, obj, at, expires_at))

    def take_step_up(self, token_id: str, at: datetime) -> dict[str, Any] | None:
        """Marks the token used and returns its binding, once (one UPDATE), while unexpired; else None."""
        rows = self._q("UPDATE step_up_token SET used_at = %s WHERE id = %s AND used_at IS NULL AND expires_at > %s "
                       "RETURNING principal, session, object", (at, token_id, at))
        return {"principal": rows[0][0], "session": rows[0][1], "object": rows[0][2]} if rows else None

    def add_login_failure(self, key: str, at: datetime) -> None:
        self._q("INSERT INTO login_failure (key, at) VALUES (%s, %s)", (key, at))

    def login_failures(self, key: str, since: datetime) -> list[datetime]:
        return [r[0] for r in self._q("SELECT at FROM login_failure WHERE key = %s AND at > %s ORDER BY at", (key, since))]

    def clear_login_failures(self, key: str) -> None:
        self._q("DELETE FROM login_failure WHERE key = %s", (key,))

    def prune_login_failures(self, before: datetime) -> None:
        self._q("DELETE FROM login_failure WHERE at < %s", (before,))

    def link_events(self, target: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        """The transitions of the links `target` owns or is the dependency of, from `start` to `end`, oldest first.
        A row that repeats its link's previous state (the recorder's row at a restart) is not a transition."""
        rows = self._q("SELECT owner, dependency, state, latency_ms, reason, at FROM "
                       f"({_LINK_ROWS} WHERE owner = %s OR dependency = %s) AS e "
                       "WHERE (prev IS NULL OR prev <> state) AND at >= %s AND at <= %s ORDER BY at, id",
                       (target, target, start, end))
        return [{"owner": r[0], "dependency": r[1], "state": r[2], "latency_ms": r[3], "reason": r[4], "at": r[5]}
                for r in rows]

    def latest_link_events(self) -> dict[tuple[str, str], dict[str, Any]]:
        """T-0046 L4: the last recorded transition of every link, by (owner, dependency) (the map's `since`)."""
        rows = self._q("SELECT DISTINCT ON (owner, dependency) owner, dependency, state, at "
                       f"FROM ({_LINK_ROWS}) AS e WHERE prev IS NULL OR prev <> state "
                       "ORDER BY owner, dependency, at DESC, id DESC")
        return {(r[0], r[1]): {"state": r[2], "at": r[3]} for r in rows}

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
        """ACR-0018 (migration 011): the row is chained to the previous one. A transaction-level advisory lock makes
        the read of the last hash and the insert one step for every writer (api, worker, scheduler)."""
        with self.pool.connection() as c, c.transaction():
            append_chained(c, record)

    def audit_chain(self) -> list[tuple[str, Any, str | None, str | None]]:
        """ACR-0018: every audit row in write order, for `argus audit verify`."""
        return [tuple(r) for r in self._q("SELECT audit_id, body, prev_hash, hash FROM audit ORDER BY seq")]

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
    # without migration 007 the two refusals below would "pass" on a missing column: this read proves it is there
    ("re-check lineage column present (migration 007)", "SELECT parent_id FROM incident LIMIT 0", True),
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
    ("insert deploy event (ACR-0021, migration 008)", "INSERT INTO deploy_event (host, commit_sha, ref, actor, at) "
                                                      "VALUES ('vm-095', 'abcdef1', 'dbcheck', 'dbcheck', now())", True),
    ("deploy event is insert-only (UPDATE refused)", "UPDATE deploy_event SET ref = 'x' WHERE ref = 'dbcheck'", False),
    ("deploy event is insert-only (DELETE refused)", "DELETE FROM deploy_event WHERE ref = 'dbcheck'", False),
    ("insert link event (ACR-0025, migration 009)", "INSERT INTO link_event (owner, dependency, state, at) "
                                                    "VALUES ('dbcheck', 'dbcheck', 'ok', now())", True),
    ("link event is insert-only (UPDATE refused)", "UPDATE link_event SET state = 'broken' WHERE owner = 'dbcheck'",
     False),
    ("link event is insert-only (DELETE refused)", "DELETE FROM link_event WHERE owner = 'dbcheck'", False),
    ("insert link probe cursor (T-0046, migration 014)", "INSERT INTO link_probe_cursor (owner,dependency,state,at) "
                                                           "VALUES ('dbcheck','dbcheck','ok',now())", True),
    ("advance link probe cursor (migration 014)", "UPDATE link_probe_cursor SET state='broken', at=at + interval '1 second' "
                                                    "WHERE owner='dbcheck' AND dependency='dbcheck'", True),
    ("link probe cursor identity is fixed", "UPDATE link_probe_cursor SET owner='changed' "
                                             "WHERE owner='dbcheck' AND dependency='dbcheck'", False),
    ("link probe cursor cannot move backwards", "UPDATE link_probe_cursor SET at=at - interval '1 second' "
                                                  "WHERE owner='dbcheck' AND dependency='dbcheck'", False),
    ("link probe cursor is not deleted", "DELETE FROM link_probe_cursor WHERE owner='dbcheck' "
                                         "AND dependency='dbcheck'", False),
    ("insert session (ACR-0018, migration 010)", "INSERT INTO auth_session (jti, principal, access, created_at, "
                                                "expires_at) VALUES (md5('dbcheck'), 'dbcheck', 'read', now(), now())", True),
    ("a session may be revoked (its revocation columns)", "UPDATE auth_session SET revoked_at = now(), "
                                                          "revoked_by = 'dbcheck' WHERE jti = md5('dbcheck')", True),
    ("a session's identity is fixed (UPDATE principal refused)", "UPDATE auth_session SET principal = 'x' "
                                                                 "WHERE jti = md5('dbcheck')", False),
    ("a session is never deleted (DELETE refused)", "DELETE FROM auth_session WHERE jti = md5('dbcheck')", False),
    ("insert login failure (migration 010)", "INSERT INTO login_failure (key, at) VALUES ('u:dbcheck', now())", True),
    ("a login failure may be cleared (DELETE)", "DELETE FROM login_failure WHERE key = 'u:dbcheck'", True),
    ("a session's second factor may be set (migration 013)", "UPDATE auth_session SET second_factor_at = now() "
                                                              "WHERE jti = md5('dbcheck')", True),
    ("insert WebAuthn credential (ACR-0018, migration 013)", "INSERT INTO webauthn_credential (id, principal, "
                                                             "public_key, sign_count, created_at) VALUES "
                                                             "('dbcheck-credential-id', 'dbcheck', '\\x00', 0, now())",
     True),
    ("a credential's counter may move (UPDATE sign_count)", "UPDATE webauthn_credential SET sign_count = 1, "
                                                            "last_used_at = now() WHERE id = 'dbcheck-credential-id'", True),
    ("a credential's key is fixed (UPDATE public_key refused)", "UPDATE webauthn_credential SET public_key = '\\x01' "
                                                                "WHERE id = 'dbcheck-credential-id'", False),
    ("a credential's owner is fixed (UPDATE principal refused)", "UPDATE webauthn_credential SET principal = 'x' "
                                                                 "WHERE id = 'dbcheck-credential-id'", False),
    ("a credential is never deleted (DELETE refused)", "DELETE FROM webauthn_credential WHERE id = 'dbcheck-credential-id'",
     False),
    ("insert step-up token (migration 013)", "INSERT INTO step_up_token (id, principal, session, object, created_at, "
                                             "expires_at) VALUES (repeat('a', 64), 'dbcheck', 'dbcheck', 'test:dbcheck', "
                                             "now(), now() + interval '5 minutes')", True),
    ("a step-up token lives at most 5 minutes", "INSERT INTO step_up_token (id, principal, session, object, created_at, "
                                                "expires_at) VALUES (repeat('b', 64), 'dbcheck', 'dbcheck', "
                                                "'test:dbcheck', now(), now() + interval '6 minutes')", False),
    ("a step-up token's object is fixed (UPDATE object refused)", "UPDATE step_up_token SET object = 'x' "
                                                                  "WHERE id = repeat('a', 64)", False),
    ("a step-up token is never deleted (DELETE refused)", "DELETE FROM step_up_token WHERE id = repeat('a', 64)", False),
    ("insert enrolment ticket (migration 013)", "INSERT INTO webauthn_enrol_ticket (id, principal, issued_by, "
                                                "created_at, expires_at) VALUES (repeat('e', 64), 'dbcheck', "
                                                "'dbcheck-admin', now(), now() + interval '1 day')", True),
    ("an enrolment ticket may be used once (UPDATE used_at)", "UPDATE webauthn_enrol_ticket SET used_at = now() "
                                                              "WHERE id = repeat('e', 64)", True),
    ("an enrolment ticket's person is fixed (UPDATE principal refused)", "UPDATE webauthn_enrol_ticket SET "
                                                                         "principal = 'x' WHERE id = repeat('e', 64)",
     False),
    ("insert WebAuthn challenge (migration 013)", "INSERT INTO webauthn_challenge (id, principal, session, kind, "
                                                  "challenge, created_at, expires_at) VALUES ('wch_' || md5('dbcheck'), "
                                                  "'dbcheck', 'dbcheck', 'login', '\\x00', now(), "
                                                  "now() + interval '5 minutes')", True),
    ("a challenge may be used (UPDATE used_at)", "UPDATE webauthn_challenge SET used_at = now() "
                                                 "WHERE id = 'wch_' || md5('dbcheck')", True),
    ("a challenge's bytes are fixed (UPDATE challenge refused)", "UPDATE webauthn_challenge SET challenge = '\\x01' "
                                                                 "WHERE id = 'wch_' || md5('dbcheck')", False),
    ("a challenge is never deleted (DELETE refused)", "DELETE FROM webauthn_challenge "
                                                      "WHERE id = 'wch_' || md5('dbcheck')", False),
    ("nobody issues their own enrolment ticket", "INSERT INTO webauthn_enrol_ticket (id, principal, issued_by, "
                                                 "created_at, expires_at) VALUES (repeat('c', 64), 'dbcheck', 'dbcheck', "
                                                 "now(), now() + interval '1 day')", False),
    ("insert hypothesis (ACR-0024, migration 012)", "INSERT INTO incident_hypothesis (incident_id, step, "
                                                    "hypothesis_id, statement, cause_class, relation, status, score, "
                                                    "rank, at) VALUES ('inc_dbcheck', 1, 'h1', 'dbcheck', 'other', "
                                                    "'external', 'untested', 0, 1, now())", True),
    ("hypotheses are insert-only (UPDATE refused)", "UPDATE incident_hypothesis SET status = 'supported' "
                                                    "WHERE incident_id = 'inc_dbcheck'", False),
    ("hypotheses are insert-only (DELETE refused)", "DELETE FROM incident_hypothesis WHERE incident_id = 'inc_dbcheck'",
     False),
    ("insert action proposal (migration 014)", "INSERT INTO action_proposal (proposal_id, incident_id, "
                                               "capability, target, digest, body, created_at, expires_at) VALUES "
                                               "('prop_dbcheck', 'inc_dbcheck', 'container.start', "
                                               "'vm-166/container:argus-lab-cache', repeat('a',64), '{}', now(), "
                                               "now() + interval '30 minutes')", True),
    ("action proposal is insert-only (UPDATE refused)",
     "UPDATE action_proposal SET target = 'x' WHERE proposal_id = 'prop_dbcheck'", False),
    ("action proposal is insert-only (DELETE refused)",
     "DELETE FROM action_proposal WHERE proposal_id = 'prop_dbcheck'", False),
    ("insert judge verdict (migration 014)", "INSERT INTO judge_verdict (proposal_id, model_id, verdict, body, "
                                              "reviewed_at) VALUES ('prop_dbcheck','gpt-5.6-terra','agree','{}',now())", True),
    ("judge verdict is insert-only (UPDATE refused)",
     "UPDATE judge_verdict SET verdict = 'doubt' WHERE proposal_id = 'prop_dbcheck'", False),
    ("judge verdict is insert-only (DELETE refused)",
     "DELETE FROM judge_verdict WHERE proposal_id = 'prop_dbcheck'", False),
    ("insert approval (migration 014)", "INSERT INTO approval (approval_id, proposal_id, proposal_digest, "
                                       "state, requested_at, expires_at) VALUES ('appr_dbcheck', 'prop_dbcheck', "
                                       "repeat('a',64), 'pending', now(), now() + interval '30 minutes')", True),
    ("insert notification outbox (migration 014)",
     "INSERT INTO notification_outbox (key, channel, payload, next_attempt_at) "
     "VALUES ('appr_dbcheck', 'recording', '{}', now())", True),
    ("outbox delivery may be recorded", "UPDATE notification_outbox SET attempts = 1, delivered_at = now() "
                                         "WHERE key = 'appr_dbcheck'", True),
    ("outbox payload is fixed", "UPDATE notification_outbox SET payload = '{\"changed\":true}' "
                                "WHERE key = 'appr_dbcheck'", False),
    ("answer approval once", "UPDATE approval SET state = 'approved', actor = 'dbcheck', answered_at = now() "
                             "WHERE approval_id = 'appr_dbcheck'", True),
    ("insert resume intent (migration 014)", "INSERT INTO resume_intent (approval_id, incident_id, decision, state) "
                                            "VALUES ('appr_dbcheck', 'inc_dbcheck', 'approved', 'pending')", True),
    ("resume intent advances", "UPDATE resume_intent SET state = 'done', attempts = 1 "
                               "WHERE approval_id = 'appr_dbcheck'", True),
    ("resume intent decision is fixed", "UPDATE resume_intent SET decision = 'denied' "
                                        "WHERE approval_id = 'appr_dbcheck'", False),
    ("answered approval cannot reopen", "UPDATE approval SET state = 'pending', actor = NULL, answered_at = NULL "
                                        "WHERE approval_id = 'appr_dbcheck'", False),
    ("approval cannot be deleted", "DELETE FROM approval WHERE approval_id = 'appr_dbcheck'", False),
    ("insert action (migration 014)", "INSERT INTO action (action_id, proposal_id, approval_id, state) "
                                      "VALUES ('act_dbcheck', 'prop_dbcheck', 'appr_dbcheck', 'unstarted')", True),
    ("action starts", "UPDATE action SET state = 'attempting', attempted_at = now() "
                      "WHERE action_id = 'act_dbcheck'", True),
    ("action confirms", "UPDATE action SET state = 'confirmed', result_at = now() "
                        "WHERE action_id = 'act_dbcheck'", True),
    ("action cannot reopen", "UPDATE action SET state = 'attempting' WHERE action_id = 'act_dbcheck'", False),
    ("action identity fixed", "UPDATE action SET proposal_id = 'other' WHERE action_id = 'act_dbcheck'", False),
    ("insert target hold (migration 014)", "INSERT INTO target_hold (hold_id, target, reason, placed_by, placed_at) "
                                           "VALUES ('hold_dbcheck', 'vm-166/container:argus-lab-cache', 'test', "
                                           "'dbcheck', now())", True),
    ("release target hold", "UPDATE target_hold SET released_by = 'dbcheck', released_at = now() "
                            "WHERE hold_id = 'hold_dbcheck'", True),
    ("hold cannot be released twice", "UPDATE target_hold SET released_at = now() "
                                      "WHERE hold_id = 'hold_dbcheck'", False),
    ("hold target fixed", "UPDATE target_hold SET target = 'changed' WHERE hold_id = 'hold_dbcheck'", False),
    ("insert action outcome (migration 014)", "INSERT INTO action_outcome (action_id, incident_id, origin, "
                                               "outcome, body, recorded_at) VALUES ('act_dbcheck', 'inc_dbcheck', "
                                               "'lab', 'recovered_verified', '{}', now())", True),
    ("action outcome is insert-only (UPDATE refused)", "UPDATE action_outcome SET origin = 'production' "
                                                       "WHERE action_id = 'act_dbcheck'", False),
    ("action outcome is insert-only (DELETE refused)", "DELETE FROM action_outcome "
                                                       "WHERE action_id = 'act_dbcheck'", False),
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
