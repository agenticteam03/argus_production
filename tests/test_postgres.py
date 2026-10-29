"""Phase 5: the Postgres system of record, against a REAL database. Skipped unless ARGUS_TEST_PG_OWNER_DSN points to a
throwaway Postgres (the fixture drops and recreates its public schema). Example (laptop):
  docker run -d --name argus-pgtest -e POSTGRES_USER=argus_owner -e POSTGRES_DB=argus -e POSTGRES_PASSWORD=ownerpw
      -p 127.0.0.1:55432:5432 postgres:16-alpine
  ARGUS_TEST_PG_OWNER_DSN="host=127.0.0.1 port=55432 dbname=argus user=argus_owner password=ownerpw" pytest
"""
from __future__ import annotations

import os
import secrets
from datetime import timedelta
from pathlib import Path

import pytest

OWNER_DSN = os.getenv("ARGUS_TEST_PG_OWNER_DSN")
pytestmark = pytest.mark.skipif(not OWNER_DSN, reason="ARGUS_TEST_PG_OWNER_DSN not set (needs a throwaway Postgres)")
ROOT = Path(__file__).resolve().parents[1]
RUNBOOKS = ROOT / "argus" / "runbooks"          # the reviewed runbook library (D-002)


@pytest.fixture(scope="module")
def runtime_dsn():
    import psycopg
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    pw = secrets.token_hex(16)
    with psycopg.connect(OWNER_DSN, autocommit=True) as c:
        c.execute("DROP SCHEMA public CASCADE")
        c.execute("CREATE SCHEMA public")
        for f in sorted((ROOT / "deploy" / "migrations").glob("*.sql")):     # in order, like ops/db-migrate.sh
            c.execute(f.read_text(encoding="utf-8"))
        c.execute(f"ALTER ROLE argus_runtime PASSWORD '{pw}'")
    d = conninfo_to_dict(OWNER_DSN)
    d.update(user="argus_runtime", password=pw)
    return make_conninfo(**d)


@pytest.fixture()
def store(runtime_dsn):
    from argus.adapters.outbound.postgres_store import PostgresStore
    s = PostgresStore(runtime_dsn)
    yield s
    s.close()


def _incident(target="vm-166/container:argus-lab-worker", status="queued", minutes_ago=0):
    from argus.domain.model import Incident, RequestKind, TargetRef, TriggerKind, utcnow
    return Incident(id=f"inc_{secrets.token_hex(6)}", target=TargetRef.parse(target), trigger_kind=TriggerKind.manual,
                    request_kind=RequestKind.report, reason="t", principal="tester", trigger_id="t",
                    opened_at=utcnow() - timedelta(minutes=minutes_ago), status=status)


def test_remediation_migration_015_freezes_proposal_and_answers_once(runtime_dsn, store):
    """Phase 18 storage cannot rewrite the reviewed proposal or reopen a terminal approval."""
    import psycopg
    from argus.actions.remediation import Alternative, Prediction, ProposalInput, freeze_proposal
    from argus.domain.model import utcnow

    inc = _incident(target="vm-166/container:argus-lab-cache")
    store.create_incident(inc, None)
    now = utcnow()
    proposal = freeze_proposal(ProposalInput(
        incident_id=inc.id, capability="container.start", target=str(inc.target),
        target_identity={"container_id": "cache-1"}, arguments={}, root_cause=str(inc.target),
        rationale="Start the stopped cache", evidence_refs=["ev_cache"], grounds=["runbook:RB-003"],
        prediction=Prediction(signal="dependency_probe_min", target=str(inc.target), expected="healthy",
                              within_seconds=120),
        alternatives=[Alternative(action="wait", why_not="The dependency remains unavailable")],
        preview="Start existing container", rollback="container.stop", inventory_version="inv-1",
        policy_version="pol-1", evidence_version="ev-1"), at=now)
    store.add_action_proposal(proposal)
    assert store.get_action_proposal(proposal.id).digest == proposal.digest
    with pytest.raises(Exception, match="judge"):                  # migration 016: no approval before the agree
        store.add_action_approval("appr_early14", proposal.id, proposal.digest, now, proposal.expires_at)
    store.add_judge_verdict(proposal.id, "gpt-5.6-terra", {"verdict": "agree", "checks": {}, "reasons": [],
                                                           "proposal_digest": proposal.digest}, now)
    assert store.get_judge_verdict(proposal.id)["verdict"] == "agree"
    store.add_action_approval("appr_test14", proposal.id, proposal.digest, now, proposal.expires_at)
    from argus.application.holds import hold_audit
    answered = hold_audit("action.approval_answered", "operator", now, approval_id="appr_test14", decision="approved")
    assert store.answer_action_approval("appr_test14", proposal.digest, "operator", "approved", now, audit=answered)
    assert any(aid == answered.audit_id for aid, _, _, _ in store.audit_chain())     # phase 19: in the same commit
    assert not store.answer_action_approval("appr_test14", proposal.digest, "operator", "approved", now)
    assert store.get_resume_intent("appr_test14")["decision"] == "approved"
    store.add_target_hold("hold_test14", str(inc.target), "review", "operator", now)
    assert store.active_target_holds(str(inc.target), now) == ["hold_test14"]
    assert store.release_target_hold("hold_test14", "operator", now)
    assert not store.release_target_hold("hold_test14", "operator", now)
    assert store.reserve_action("act_test14", proposal.id, "appr_test14", str(inc.target), now,
                                daily_host_cap=1)
    assert not store.reserve_action("act_test14_again", proposal.id, "appr_test14", str(inc.target), now,
                                    daily_host_cap=1)
    assert store.get_action("act_test14")["state"] == "attempting"
    assert store.finish_action("act_test14", "confirmed", now, {"gateway": "confirmed"})
    assert not store.finish_action("act_test14", "failed", now, {})
    store.add_action_outcome("act_test14", inc.id, "lab", "recovered_verified", {"prediction_met": True}, now)
    with psycopg.connect(runtime_dsn, autocommit=True) as c:
        for sql in ("UPDATE action_proposal SET target = 'changed' WHERE proposal_id = %s",
                    "DELETE FROM action_proposal WHERE proposal_id = %s"):
            with pytest.raises(psycopg.Error):
                c.execute(sql, (proposal.id,))
        with pytest.raises(psycopg.Error):
            c.execute("UPDATE approval SET state = 'pending' WHERE approval_id = 'appr_test14'")
        with pytest.raises(psycopg.Error):
            c.execute("UPDATE judge_verdict SET verdict = 'doubt' WHERE proposal_id = %s", (proposal.id,))


def test_phase19_pending_approvals_page_by_keyset(store):
    """#347 review: the pending list pages on (requested_at, approval_id), so the route can filter before it fills."""
    from argus.actions.remediation import Alternative, Prediction, ProposalInput, freeze_proposal
    from argus.domain.model import utcnow

    now = utcnow()
    ids = []
    for i in range(3):
        inc = _incident(target="vm-166/container:argus-lab-cache")
        store.create_incident(inc, None)
        proposal = freeze_proposal(ProposalInput(
            incident_id=inc.id, capability="container.start", target=str(inc.target),
            target_identity={"container_id": f"cache-{i}"}, arguments={}, root_cause=str(inc.target),
            rationale="Start the stopped cache", evidence_refs=["ev_cache"], grounds=["runbook:RB-003"],
            prediction=Prediction(signal="dependency_probe_min", target=str(inc.target), expected="healthy",
                                  within_seconds=120),
            alternatives=[Alternative(action="wait", why_not="The dependency remains unavailable")],
            preview="Start existing container", rollback="container.stop", inventory_version="inv-1",
            policy_version="pol-1", evidence_version="ev-1"), at=now)
        store.add_action_proposal(proposal)
        store.add_judge_verdict(proposal.id, "gpt-5.6-terra", {"verdict": "agree", "checks": {}, "reasons": [],
                                                               "proposal_digest": proposal.digest}, now)
        ids.append(f"appr_page_{i}")
        store.add_action_approval(ids[-1], proposal.id, proposal.digest, now + timedelta(seconds=i),
                                  proposal.expires_at)
    mine = [a for a in store.list_pending_approvals(now, limit=100) if a in ids]
    assert mine == ids
    assert [a for a in store.list_pending_approvals(now, limit=100, after=ids[0]) if a in ids] == ids[1:]
    assert [a for a in store.list_pending_approvals(now, limit=100, after=ids[1]) if a in ids] == ids[2:]


def test_phase19_hold_and_chained_audit_commit_together(store):
    import psycopg
    from argus.domain.model import AuditRecord, utcnow

    now = utcnow()
    audit = AuditRecord(audit_id="aud_phase19_hold", incident_id=None, at=now,
                        category="decision", event="action.hold_placed", actor="operator", detail={"target": "*"})
    store.place_target_hold("hold_phase19", "*", "emergency", "operator", now, audit)
    assert store.list_active_target_holds("*", now)[0]["id"] == "hold_phase19"
    store.place_target_hold("hold_phase19_host", "vm-166", "lease", "operator", now,
                            audit.model_copy(update={"audit_id": "aud_phase19_host"}))
    listed = store.list_active_target_holds("vm-166/container:argus-lab-cache", now)
    assert [h["target"] for h in listed] == ["*", "vm-166"]          # a container's view shows its host's hold
    assert any(body["event"] == "action.hold_placed" for _, body, _, _ in store.audit_chain())
    with pytest.raises(psycopg.Error):
        store.place_target_hold("hold_phase19", "*", "duplicate", "operator", now,
                                audit.model_copy(update={"audit_id": "aud_phase19_duplicate"}))
    assert not any(aid == "aud_phase19_duplicate" for aid, _, _, _ in store.audit_chain())
    released = audit.model_copy(update={"audit_id": "aud_phase19_release", "event": "action.hold_released"})
    assert store.release_target_hold("hold_phase19", "operator", now, audit=released)
    assert store.get_target_hold("hold_phase19")["released_at"] is not None
    assert any(aid == "aud_phase19_release" for aid, _, _, _ in store.audit_chain())
    assert not store.release_target_hold("hold_phase19", "operator", now,
                                         audit=released.model_copy(update={"audit_id": "aud_phase19_again"}))
    assert not any(aid == "aud_phase19_again" for aid, _, _, _ in store.audit_chain())


def test_an_approval_accepts_a_judge_doubt_but_never_a_disagreement_migration_018(store):
    """ACR-0039: a doubt lets a person decide (the approval row may exist and be approved); a disagreement, another
    digest or a forbidden colour are still refused by the database."""
    from argus.actions.remediation import Alternative, Prediction, ProposalInput, freeze_proposal
    from argus.domain.model import utcnow

    inc = _incident(target="vm-166/container:argus-lab-cache")
    store.create_incident(inc, None)
    now = utcnow()

    def proposal(rationale):
        p = freeze_proposal(ProposalInput(
            incident_id=inc.id, capability="container.start", target=str(inc.target),
            target_identity={"container_id": "cache-1"}, arguments={}, root_cause=str(inc.target),
            rationale=rationale, evidence_refs=["ev_cache"], grounds=["runbook:RB-003"],
            prediction=Prediction(signal="dependency_probe_min", target=str(inc.target), expected="healthy",
                                  within_seconds=120),
            alternatives=[Alternative(action="wait", why_not="The dependency remains unavailable")],
            preview="Start existing container", rollback="container.stop", inventory_version="inv-1",
            policy_version="pol-1", evidence_version="ev-1"), at=now)
        store.add_action_proposal(p)
        return p

    doubted = proposal("Start the stopped cache (doubted)")
    store.add_judge_verdict(doubted.id, "gpt-5.6-terra", {"verdict": "doubt", "checks": {}, "reasons": ["unsure"],
                                                          "risk": "amber", "proposal_digest": doubted.digest}, now)
    store.add_action_approval("appr_doubt18", doubted.id, doubted.digest, now, doubted.expires_at)
    assert store.answer_action_approval("appr_doubt18", doubted.digest, "operator", "approved", now)
    for verdict, risk, digest in (("disagree", "amber", None), ("doubt", "forbidden", None),
                                  ("doubt", "amber", "c" * 64)):
        p = proposal(f"Start the stopped cache ({verdict}, {risk}, {bool(digest)})")
        store.add_judge_verdict(p.id, "gpt-5.6-terra", {"verdict": verdict, "checks": {}, "reasons": ["no"],
                                                        "risk": risk, "proposal_digest": digest or p.digest}, now)
        with pytest.raises(Exception, match="judge"):
            store.add_action_approval(f"appr_{secrets.token_hex(4)}", p.id, p.digest, now, p.expires_at)


def test_an_escalated_incident_closes_once_with_a_resolution_migration_019(runtime_dsn, store):
    """ACR-0041: escalated -> closed only with a person's resolution, once; every other final change still refused."""
    import psycopg
    from argus.domain.model import IncidentStatus, utcnow

    inc = _incident(target="vm-166/container:argus-lab-cache", status="escalated")
    store.create_incident(inc, None)
    with psycopg.connect(runtime_dsn, autocommit=True) as c:
        with pytest.raises(psycopg.Error, match="final"):
            c.execute("UPDATE incident SET status = 'closed' WHERE id = %s", (inc.id,))
    done = store.resolve_incident(inc.id, "olga", "restarted by hand", utcnow())
    assert done is not None and store.get_incident(inc.id).status == IncidentStatus.closed
    assert store.get_incident(inc.id).resolution.by == "olga"
    assert store.resolve_incident(inc.id, "olga", "again", utcnow()) is None
    with psycopg.connect(runtime_dsn, autocommit=True) as c:
        with pytest.raises(psycopg.Error, match="final"):
            c.execute("UPDATE incident SET status = 'escalated' WHERE id = %s", (inc.id,))


def test_an_ops_session_is_accepted_by_migration_017(store):
    """ACR-0032: the private login's `ops` session; any other unknown access is still refused."""
    import psycopg
    from argus.domain.model import utcnow

    now = utcnow()
    store.add_session("a" * 32, "alice", "ops", now, now + timedelta(minutes=30))
    assert store.get_session("a" * 32)["access"] == "ops"
    assert store.touch_session("a" * 32, now + timedelta(minutes=14), timedelta(minutes=15))    # idle timeout
    assert store.get_session("a" * 32)["last_seen_at"] == now + timedelta(minutes=14)
    assert not store.touch_session("a" * 32, now + timedelta(minutes=30), timedelta(minutes=15))
    with pytest.raises(psycopg.Error):
        store.add_session("b" * 32, "alice", "root", now, now + timedelta(minutes=30))


def test_incident_lifecycle_and_forward_only(store):
    import psycopg
    from argus.domain.model import IncidentStatus
    inc = _incident(minutes_ago=600)                       # oldest queued ⇒ claimed first
    key = f"k_{secrets.token_hex(4)}"
    assert store.create_incident(inc, key) == (inc, False)
    again, dup = store.create_incident(_incident(), key)
    assert dup and again.id == inc.id
    claimed = store.claim_next_queued()
    assert claimed.id == inc.id and claimed.status == IncidentStatus.running
    assert store.get_incident(inc.id).status == IncidentStatus.running
    assert store.requeue_running() >= 1 and store.get_incident(inc.id).status == IncidentStatus.queued
    inc.status = IncidentStatus.closed
    store.update_incident(inc)
    inc.status = IncidentStatus.queued
    with pytest.raises(psycopg.Error, match="final"):
        store.update_incident(inc)                         # a closed incident never reopens


def test_recheck_lineage_migration_007(runtime_dsn, store):
    """ACR-0021 (T-0045 B5): a re-check names an existing parent (foreign key), is listed by it newest first, and the
    link never changes (the forward-only trigger)."""
    import psycopg
    parent = _incident(minutes_ago=30)
    store.create_incident(parent, None)
    first, second = _incident(minutes_ago=20), _incident(minutes_ago=10)
    for child in (first, second):
        child.parent_id = parent.id
        store.create_incident(child, None)
    assert [i.id for i in store.list_incidents(10, parent_id=parent.id)] == [second.id, first.id]
    assert store.get_incident(first.id).parent_id == parent.id
    orphan = _incident()
    orphan.parent_id = "inc_nosuchparent"
    with pytest.raises(psycopg.Error, match="foreign key"):
        store.create_incident(orphan, None)
    with psycopg.connect(runtime_dsn, autocommit=True) as c:
        with pytest.raises(psycopg.Error, match="immutable"):
            c.execute("UPDATE incident SET parent_id = NULL WHERE id = %s", (first.id,))
        with pytest.raises(psycopg.Error, match="immutable"):
            c.execute("UPDATE incident SET parent_id = %s WHERE id = %s", (first.id, parent.id))


def test_deploy_events_migration_008(runtime_dsn, store):
    """ACR-0021 (T-0045 B7): deploy events are kept by host and time, and are insert-only for the runtime role (no
    UPDATE or DELETE grant); a commit that is not hex is refused by the table itself."""
    import psycopg
    from argus.domain.model import utcnow
    now = utcnow()
    store.add_deploy_event("vm-095", "dfa7332", "main", "alice", now - timedelta(minutes=5))
    store.add_deploy_event("vm-166", "dfa7332", "main", "alice", now - timedelta(minutes=5))
    got = store.deploy_events("vm-095", now - timedelta(hours=1), now)
    assert [(e["commit"], e["ref"], e["actor"]) for e in got] == [("dfa7332", "main", "alice")]
    assert got[0]["at"].tzinfo is not None
    with psycopg.connect(runtime_dsn, autocommit=True) as c:
        for sql in ("UPDATE deploy_event SET ref = 'x'", "DELETE FROM deploy_event"):
            with pytest.raises(psycopg.Error, match="permission denied"):
                c.execute(sql)
        with pytest.raises(psycopg.Error, match="check constraint"):
            c.execute("INSERT INTO deploy_event (host, commit_sha, ref, actor, at) "
                      "VALUES ('vm-095', 'not-hex', 'main', 'alice', now())")


def test_link_events_migration_009(runtime_dsn, store):
    """ACR-0025 (T-0046 L2): link-state transitions are kept by owner, dependency and time, and are insert-only for the
    runtime role (no UPDATE or DELETE grant); a state outside the four is refused by the table itself."""
    import psycopg
    from argus.domain.model import utcnow
    now = utcnow()
    api, cache = "vm-166/container:pg-api", "vm-166/container:pg-cache"
    store.add_link_event(api, cache, "broken", None, "timeout", now - timedelta(minutes=5))
    store.add_link_event(api, cache, "ok", 3.5, None, now - timedelta(minutes=1))
    got = store.link_events(cache, now - timedelta(hours=1), now)
    assert [(e["owner"], e["state"], e["latency_ms"], e["reason"]) for e in got] == [
        (api, "broken", None, "timeout"), (api, "ok", 3.5, None)]
    assert got[0]["at"].tzinfo is not None
    with psycopg.connect(runtime_dsn, autocommit=True) as c:
        for sql in ("UPDATE link_event SET state = 'ok'", "DELETE FROM link_event"):
            with pytest.raises(psycopg.Error, match="permission denied"):
                c.execute(sql)
        with pytest.raises(psycopg.Error, match="check constraint"):
            c.execute("INSERT INTO link_event (owner, dependency, state, at) VALUES ('a', 'b', 'down', now())")


def test_console_command_migration_020(runtime_dsn, store):
    """ACR-0043 (CON-2): every completed console command is kept with its incident and person; insert-only for the
    runtime role (no UPDATE or DELETE grant); a status or class outside the known values is refused by the table."""
    import psycopg
    from argus.domain.model import utcnow
    now = utcnow()

    def row(command_id, **extra):
        return {"command_id": command_id, "incident_id": "inc_pgconsole", "person": "olga", "input": "cache status",
                "command": "cache.status", "cls": "read", "status": "ok", "output": "line", "output_truncated": False,
                "suggestion_id": None, "started_at": now, "finished_at": now, **extra}
    store.add_console_command(row("cmd_pg1"))
    store.add_console_command(row("cmd_pg2", cls="write", status="rejected"))
    got = store.console_history("inc_pgconsole")
    assert [(r["command_id"], r["cls"], r["status"]) for r in got] == [("cmd_pg1", "read", "ok"),
                                                                       ("cmd_pg2", "write", "rejected")]
    assert got[0]["started_at"].tzinfo is not None
    assert store.console_read_count(incident_id="inc_pgconsole") == 1
    with psycopg.connect(runtime_dsn, autocommit=True) as c:
        for sql in ("UPDATE console_command SET status = 'error'", "DELETE FROM console_command"):
            with pytest.raises(psycopg.Error, match="permission denied"):
                c.execute(sql)
        with pytest.raises(psycopg.Error, match="check constraint"):
            c.execute("INSERT INTO console_command (command_id, incident_id, person, input, command, cls, status, "
                      "output, started_at, finished_at) VALUES ('x', 'i', 'p', 'i', 'c', 'shell', 'ok', '', now(), now())")


def test_link_probe_cursor_migration_014(runtime_dsn, store):
    """T-0046: cursor advances atomically with a transition and allows only monotonic sample-time updates."""
    import psycopg
    from argus.domain.model import utcnow
    owner, dependency = "vm-166/container:cursor-owner", "vm-166/container:cursor-dependency"
    at = utcnow()
    assert store.record_link_probe(owner, dependency, "ok", 2.0, None, at) is True
    assert store.record_link_probe(owner, dependency, "ok", 2.0, None, at + timedelta(seconds=15)) is False
    assert store.record_link_probe(owner, dependency, "broken", None, "timeout", at + timedelta(seconds=30)) is True
    cursor = store.link_probe_cursors(owner)[dependency]
    assert cursor == {"state": "broken", "at": at + timedelta(seconds=30)}
    events = store.link_events(dependency, at - timedelta(seconds=1), at + timedelta(minutes=1))
    assert [event["state"] for event in events] == ["ok", "broken"]
    assert [event for event in store.audit_chain() if event[1].get("event") == "link.changed"][-1][1]["at"] == \
        (at + timedelta(seconds=30)).isoformat().replace("+00:00", "Z")
    with psycopg.connect(runtime_dsn, autocommit=True) as c:
        with pytest.raises(psycopg.Error, match="permission denied"):
            c.execute("UPDATE link_probe_cursor SET owner='changed' WHERE owner=%s", (owner,))
        with pytest.raises(psycopg.Error, match="cannot move backwards"):
            c.execute("UPDATE link_probe_cursor SET at=at - interval '1 second' WHERE owner=%s", (owner,))
        with pytest.raises(psycopg.Error, match="permission denied"):
            c.execute("DELETE FROM link_probe_cursor WHERE owner=%s", (owner,))


def test_hypotheses_migration_012(runtime_dsn, store):
    """ACR-0024 §3.5 (T-0047 H2): one row per hypothesis per decision step, read by step then rank; insert-only for
    the runtime role; an id, relation or status outside the vocabulary is refused by the table itself."""
    import psycopg
    from argus.domain.model import utcnow
    inc = _incident()
    store.create_incident(inc, None)
    now = utcnow()
    row = {"hypothesis_id": "h2", "statement": "its database is down", "cause_class": "other", "target": None,
           "relation": "external", "status": "untested", "support_ids": [], "against_ids": ["ev_a"], "score": -0.5,
           "rank": 2, "chosen": False}
    store.add_hypotheses(inc.id, 1, [row, {**row, "hypothesis_id": "h1", "target": str(inc.target),
                                           "relation": "self", "support_ids": ["ev_b"], "rank": 1, "chosen": True}], now)
    got = store.hypotheses(inc.id)
    assert [(r["hypothesis_id"], r["rank"], r["chosen"], r["support_ids"], r["against_ids"]) for r in got] == [
        ("h1", 1, True, ["ev_b"], ["ev_a"]), ("h2", 2, False, [], ["ev_a"])]
    assert got[1]["target"] is None and got[0]["at"].tzinfo is not None
    with psycopg.connect(runtime_dsn, autocommit=True) as c:
        for sql in ("UPDATE incident_hypothesis SET status = 'supported'", "DELETE FROM incident_hypothesis"):
            with pytest.raises(psycopg.Error, match="permission denied"):
                c.execute(sql)
        with pytest.raises(psycopg.Error, match="check constraint"):
            c.execute("INSERT INTO incident_hypothesis (incident_id, step, hypothesis_id, statement, cause_class, "
                      f"relation, status, score, rank, at) VALUES ('{inc.id}', 1, 'h9', 's', 'other', 'self', "
                      "'untested', 0, 1, now())")


def test_sessions_and_login_failures_migration_010(runtime_dsn, store):
    """ACR-0018 (phase 16 step 1): a session is inserted, revoked once and never deleted; the runtime role may set only
    its revocation columns. Failed logins are inserted, read in a window and cleared."""
    import uuid

    import psycopg
    from argus.domain.model import utcnow
    now = utcnow()
    jti, other = uuid.uuid4().hex, uuid.uuid4().hex
    store.add_session(jti, "pg-alice", "read", now, now + timedelta(minutes=30))
    store.add_session(other, "pg-alice", "full", now, now + timedelta(minutes=30))
    assert store.get_session(jti)["access"] == "read" and store.get_session(jti)["revoked_at"] is None
    assert store.revoke_session(jti, "pg-alice", "logout", now) is True
    assert store.revoke_session(jti, "pg-alice", "again", now) is False
    assert store.revoke_principal_sessions("pg-alice", "admin", "test", now) == 1          # only the open one
    assert store.get_session(other)["revoked_by"] == "admin"
    with psycopg.connect(runtime_dsn, autocommit=True) as c:
        for sql in (f"UPDATE auth_session SET principal = 'x' WHERE jti = '{jti}'", "DELETE FROM auth_session"):
            with pytest.raises(psycopg.Error, match="permission denied"):
                c.execute(sql)
        with pytest.raises(psycopg.Error, match="check constraint"):
            c.execute("INSERT INTO auth_session (jti, principal, access, created_at, expires_at) "
                      "VALUES ('not-a-jti', 'x', 'read', now(), now())")
    store.add_login_failure("u:pg-bob", now - timedelta(minutes=20))
    store.add_login_failure("u:pg-bob", now - timedelta(minutes=1))
    assert len(store.login_failures("u:pg-bob", now - timedelta(minutes=15))) == 1
    store.prune_login_failures(now - timedelta(minutes=15))                # the old one goes
    assert len(store.login_failures("u:pg-bob", now - timedelta(hours=1))) == 1
    store.clear_login_failures("u:pg-bob")
    assert store.login_failures("u:pg-bob", now - timedelta(hours=1)) == []


def test_webauthn_and_step_up_migration_013(runtime_dsn, store):
    """ACR-0018 (phase 16 step 3): a credential's key and owner are fixed and it is revoked, never deleted; a challenge,
    a ticket and a step-up token are taken once (one UPDATE each) and only while unexpired; the database itself refuses
    a step-up longer than 5 minutes and a self-issued ticket."""
    import uuid

    import psycopg
    from argus.domain.model import utcnow
    now = utcnow()
    jti = uuid.uuid4().hex
    store.add_session(jti, "pg-carol", "read", now, now + timedelta(minutes=30))
    assert store.set_session_second_factor(jti, now) is True
    assert store.get_session(jti)["second_factor_at"] is not None
    store.add_webauthn_credential("pg-carol-credential-1", "pg-carol", b"\x01cose", 0, "laptop", now)
    assert [c["label"] for c in store.webauthn_credentials("pg-carol")] == ["laptop"]
    assert store.update_webauthn_sign_count("pg-carol-credential-1", 3, now) is True
    assert store.webauthn_credentials("pg-carol")[0]["sign_count"] == 3
    cid = f"wch_{uuid.uuid4().hex}"
    store.add_webauthn_challenge(cid, "pg-carol", jti, "login", b"chal", None, None, now, now + timedelta(minutes=5))
    assert store.take_webauthn_challenge(cid, "pg-carol", jti, "step_up", now) is None          # another ceremony
    assert store.take_webauthn_challenge(cid, "pg-carol", jti, "login", now)["challenge"] == b"chal"
    assert store.take_webauthn_challenge(cid, "pg-carol", jti, "login", now) is None            # once
    store.add_enrol_ticket("a" * 64, "pg-carol", "pg-admin", now, now + timedelta(hours=24))
    assert store.enrol_ticket_valid("a" * 64, "pg-carol", now) and not store.enrol_ticket_valid("a" * 64, "x", now)
    assert store.use_enrol_ticket("a" * 64, "pg-carol", now) is True
    assert store.use_enrol_ticket("a" * 64, "pg-carol", now) is False
    store.add_step_up("b" * 64, "pg-carol", jti, "test:pg", now, now + timedelta(minutes=5))
    assert store.take_step_up("b" * 64, now + timedelta(minutes=6)) is None                    # expired
    assert store.take_step_up("b" * 64, now)["object"] == "test:pg"
    assert store.take_step_up("b" * 64, now) is None                                           # once
    assert store.revoke_webauthn_credentials("pg-carol", "pg-admin", now) == 1
    assert store.webauthn_credentials("pg-carol") == []
    with psycopg.connect(runtime_dsn, autocommit=True) as c:
        for sql in ("UPDATE webauthn_credential SET public_key = '\\x02'", "UPDATE webauthn_credential SET principal = 'x'",
                    "DELETE FROM webauthn_credential", "DELETE FROM step_up_token", "DELETE FROM webauthn_challenge",
                    "UPDATE step_up_token SET object = 'x'"):
            with pytest.raises(psycopg.Error, match="permission denied"):
                c.execute(sql)
        with pytest.raises(psycopg.Error, match="check constraint"):
            c.execute("INSERT INTO step_up_token (id, principal, session, object, created_at, expires_at) "
                      "VALUES (repeat('c', 64), 'x', 'x', 'test:x', now(), now() + interval '6 minutes')")
        with pytest.raises(psycopg.Error, match="check constraint"):
            c.execute("INSERT INTO webauthn_enrol_ticket (id, principal, issued_by, created_at, expires_at) "
                      "VALUES (repeat('d', 64), 'x', 'x', now(), now())")


def test_audit_chain_migration_011(store):
    """ACR-0018 §17.1 layer 13: concurrent writers never fork the chain (an advisory lock per row), and an owner who
    disables the insert-only trigger and edits a row is caught by the verifier."""
    import uuid
    from concurrent.futures import ThreadPoolExecutor

    import psycopg
    from argus.domain.audit_chain import verify
    from argus.domain.model import AuditRecord, utcnow

    def write(i):
        store.append(AuditRecord(audit_id=f"aud_pg_{uuid.uuid4().hex[:12]}", incident_id=None, at=utcnow(),
                                 category="access", event="access.chain_test", actor=f"writer{i}"))
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write, range(40)))
    chained, before, problems = verify(store.audit_chain())
    assert problems == [] and chained >= 40
    victim = [r for r in store.audit_chain() if r[1].get("actor") == "writer7"][0][0]
    with psycopg.connect(OWNER_DSN, autocommit=True) as c:
        c.execute("ALTER TABLE audit DISABLE TRIGGER audit_insert_only")
        try:
            c.execute("UPDATE audit SET body = jsonb_set(body, '{actor}', '\"mallory\"') WHERE audit_id = %s", (victim,))
        finally:
            c.execute("ALTER TABLE audit ENABLE TRIGGER audit_insert_only")
    assert verify(store.audit_chain())[2] == [f"{victim}: hash does not match its body (the row was edited)"]


def test_latest_link_events(store):
    """T-0046 L4: the map's `since` is the last recorded transition of each link (one row per link, the newest)."""
    from argus.domain.model import utcnow
    now = utcnow()
    web, db, cache = "vm-166/container:pg-l4-web", "vm-166/container:pg-l4-db", "vm-166/container:pg-l4-cache"
    store.add_link_event(web, db, "ok", 2.0, None, now - timedelta(minutes=9))
    store.add_link_event(web, db, "broken", None, "timeout", now - timedelta(minutes=4))
    store.add_link_event(web, cache, "slow", 220.0, None, now - timedelta(minutes=2))
    latest = store.latest_link_events()
    assert latest[(web, db)]["state"] == "broken" and latest[(web, cache)]["state"] == "slow"
    assert abs((latest[(web, db)]["at"] - (now - timedelta(minutes=4))).total_seconds()) < 1
    # a restart repeats a state: not a transition, for `since` nor for the history (#227 review)
    store.add_link_event(web, db, "broken", None, "timeout", now - timedelta(minutes=1))
    assert abs((store.latest_link_events()[(web, db)]["at"] - (now - timedelta(minutes=4))).total_seconds()) < 1
    states = [r["state"] for r in store.link_events(web, now - timedelta(minutes=10), now) if r["dependency"] == db]
    assert states == ["ok", "broken"]


def test_worker_lease(store):
    """T-0014: a claim is a lease; only expired claims go back to the queue (tests/test_worker_lease.py, SQLite)."""
    from argus.domain.model import IncidentStatus, utcnow
    store.requeue_expired(now=utcnow() + timedelta(days=1))        # the module's earlier rows: out of the way
    while store.claim_next_queued("drain", lease_s=86400 * 30):
        pass
    first, second = _incident(minutes_ago=10), _incident(minutes_ago=9)
    store.create_incident(first, None)
    store.create_incident(second, None)
    assert store.claim_next_queued("worker-a", lease_s=60).id == first.id
    assert store.claim_next_queued("worker-b", lease_s=60).id == second.id
    assert store.claim_next_queued("worker-c", lease_s=60) is None
    later = utcnow() + timedelta(seconds=50)
    assert store.renew_claim(first.id, "worker-a", lease_s=60, now=later) is True
    assert store.renew_claim(first.id, "worker-b", lease_s=60, now=later) is False
    assert store.requeue_expired(now=later + timedelta(seconds=30)) == 1          # second expired, first renewed
    assert store.get_incident(second.id).status == IncidentStatus.queued
    assert store.get_incident(first.id).status == IncidentStatus.running
    assert store.claim_next_queued("worker-c", lease_s=60).id == second.id
    assert store.renew_claim(second.id, "worker-b", lease_s=60) is False          # worker-b lost it
    busy = store.active_incident(first.target)                                    # T-0014 step 3: skip-if-active
    assert busy is not None and busy.status in (IncidentStatus.queued, IncidentStatus.running)
    assert store.active_incident(_incident(target="vm-095/container:t0014-never-used").target) is None


def test_alert_occurrences(runtime_dsn, store):
    """OP-011 (migration 004): one row per alert identity, insert-only; the evidence version counts the attaches."""
    import psycopg
    from argus.domain.model import utcnow
    inc = _incident(target="vm-166/container:op011-pg")
    store.create_incident(inc, f"alert:fp-a:{inc.opened_at.isoformat()}")
    assert store.evidence_state(inc.id) == (1, None)
    assert store.incident_for_trigger(f"alert:fp-a:{inc.opened_at.isoformat()}") == inc.id   # the opening key
    t = utcnow()
    assert store.add_alert_occurrence("alert:fp-a:t", inc.id, "fp-a", t, {"alertname": "A"}, "started", t)
    assert store.add_alert_occurrence("alert:fp-b:t", inc.id, "fp-b", t, {"alertname": "B", "dependency": "db"},
                                      "attached", t + timedelta(seconds=1))
    assert not store.add_alert_occurrence("alert:fp-b:t", inc.id, "fp-b", t, {}, "attached")   # already recorded
    assert store.incident_for_trigger("alert:fp-b:t") == inc.id and store.incident_for_trigger("alert:x") is None
    occ = store.alert_occurrences(inc.id)
    assert [(o["alertname"], o["disposition"]) for o in occ] == [("A", "started"), ("B", "attached")]
    assert occ[1]["labels"]["dependency"] == "db"
    version, last = store.evidence_state(inc.id)
    assert version == 2 and last == t + timedelta(seconds=1)
    with psycopg.connect(runtime_dsn, autocommit=True) as c, pytest.raises(psycopg.Error, match="permission"):
        c.execute("DELETE FROM alert_occurrence")
    assert store.latest_concluded_incident(inc.target) is None                  # ACR-0004: queued is not concluded
    from argus.domain.model import IncidentStatus
    inc.status, inc.incident_class, inc.closed_at = IncidentStatus.escalated, "dependency_unavailable", t
    store.update_incident(inc)
    assert store.latest_concluded_incident(inc.target).id == inc.id


def test_alert_occurrence_resolution(runtime_dsn, store):
    """T-0026 (migration 005): the runtime role resolves an occurrence, forward only, and changes nothing else."""
    import psycopg
    from argus.domain.model import IncidentOutcome, IncidentStatus, utcnow
    inc = _incident(target="vm-166/container:t0026-pg")
    store.create_incident(inc, None)
    t = utcnow()
    labels = {"alertname": "A", "argus_host": "vm-166"}
    store.add_alert_occurrence("alert:t26-a", inc.id, "fp-a", t, labels, "started", t)
    store.add_alert_occurrence("alert:t26-b", inc.id, "fp-b", t, {**labels, "argus_host": "vm-095"}, "attached",
                               t + timedelta(seconds=5))
    assert [o["identity"] for o in store.firing_occurrences("vm-166", t + timedelta(seconds=1))] == ["alert:t26-a"]
    assert store.firing_occurrences("vm-166", t - timedelta(seconds=1)) == []      # recorded after the read
    occ = store.resolve_alert_occurrence("alert:t26-a", t + timedelta(minutes=1))
    assert occ == {"incident_id": inc.id, "fingerprint": "fp-a", "alertname": "A"}
    assert store.resolve_alert_occurrence("alert:t26-a", t) is None                  # already resolved
    by_id = {o["identity"]: o for o in store.alert_occurrences(inc.id)}
    assert by_id["alert:t26-a"]["status"] == "resolved"
    assert by_id["alert:t26-a"]["resolved_at"] == t + timedelta(minutes=1)
    with psycopg.connect(runtime_dsn, autocommit=True) as c:
        for sql in ("UPDATE alert_occurrence SET status = 'firing' WHERE identity = 'alert:t26-a'",
                    "UPDATE alert_occurrence SET incident_id = 'inc_x' WHERE identity = 'alert:t26-b'",
                    "UPDATE alert_occurrence SET status = 'resolved' WHERE identity = 'alert:t26-b'",  # no resolved_at
                    "DELETE FROM alert_occurrence WHERE identity = 'alert:t26-b'"):
            with pytest.raises(psycopg.Error):
                c.execute(sql)
    assert store.close_queued_incident(inc.id, "resolved_externally", "every alert resolved", t)
    after = store.get_incident(inc.id)
    assert after.status == IncidentStatus.closed and after.outcome == IncidentOutcome.resolved_externally
    assert after.closed_at == t and after.target == inc.target
    assert not store.close_queued_incident(inc.id, "resolved_externally", "again", t)   # no longer queued


def test_worker_lease_uses_the_database_clock(store):
    """OP-009: without `now`, renew and requeue use the database clock, the same one the claim used."""
    from argus.domain.model import IncidentStatus, utcnow
    store.requeue_expired(now=utcnow() + timedelta(days=1))
    while store.claim_next_queued("drain", lease_s=86400 * 30):
        pass
    live, gone = _incident(minutes_ago=8), _incident(minutes_ago=7)
    store.create_incident(live, None)
    store.create_incident(gone, None)
    assert store.claim_next_queued("worker-a", lease_s=600).id == live.id
    assert store.claim_next_queued("worker-b", lease_s=0).id == gone.id           # expires at once
    assert store.renew_claim(live.id, "worker-a", lease_s=600) is True
    store._q("UPDATE incident SET claimed_until = now() - interval '1 second' WHERE id = %s", (gone.id,))
    assert store.renew_claim(gone.id, "worker-b", lease_s=600) is False
    assert store.requeue_expired() == 1
    assert store.get_incident(gone.id).status == IncidentStatus.queued
    assert store.get_incident(live.id).status == IncidentStatus.running


def test_evidence_audit_events_principals(store):
    import psycopg
    from argus.domain.model import AuditRecord, EvidenceRecord, utcnow
    inc = _incident()
    store.create_incident(inc, None)
    ev = EvidenceRecord(evidence_id=f"ev_{secrets.token_hex(6)}", incident_id=inc.id, kind="observation",
                        capability="container.status", target=str(inc.target), host="vm-166", executor="docker_read",
                        caller="model", source_time=None, collected_at=utcnow(), status="ok",
                        values={"oom_killed": True}, model_text="x").with_hash()
    store.append_evidence(ev)
    assert store.get_evidence([ev.evidence_id])[0].sha256 == ev.sha256
    assert [e.evidence_id for e in store.list_evidence(inc.id)] == [ev.evidence_id]
    with pytest.raises(psycopg.Error):
        store.append_evidence(ev.model_copy(update={"evidence_id": "ev_bad", "sha256": "nothash"}))
    with pytest.raises(psycopg.Error, match="permission denied"):
        store._q("DELETE FROM evidence WHERE evidence_id = %s", (ev.evidence_id,))
    store.append(AuditRecord(audit_id=f"aud_{secrets.token_hex(6)}", incident_id=inc.id, at=utcnow(),
                             category="decision", event="decision.test", policy_version="p"))
    assert store.list_for(inc.id)[0].event == "decision.test"
    for node in ("detect", "recall", "record"):
        store.append_run_event(inc.id, node, "enter", {"when": utcnow()})
    evs = store.list_run_events(inc.id)
    assert [e["seq"] for e in evs] == [1, 2, 3] and evs[0]["node"] == "detect"
    assert [e["seq"] for e in store.list_run_events(inc.id, after_seq=2)] == [3]
    store.notify("n1", {"a": 1})
    store.notify("n1", {"a": 2})                           # idempotent
    assert [n["payload"] for n in store.notifications() if n["key"] == "n1"] == [{"a": 1}]
    store.upsert_principal("alice", "human", "operator", ["lab"], "hash")
    store.set_disabled("alice", True)
    assert store.get_principal("alice") == {"id": "alice", "kind": "human", "role": "operator", "scopes": ["lab"],
                                           "password_hash": "hash", "disabled": True}


def test_database_guarantees_check(runtime_dsn):
    import psycopg
    from argus.adapters.outbound.postgres_store import check
    results = check(runtime_dsn)
    assert all(ok for _, ok, _ in results), [r for r in results if not r[1]]
    with psycopg.connect(runtime_dsn) as c:                # the check left nothing behind
        assert c.execute("SELECT count(*) FROM incident WHERE id = 'inc_dbcheck'").fetchone()[0] == 0


def test_full_run_and_sqlite_import(runtime_dsn, tmp_path, monkeypatch):
    """A whole SC-01-like run on the SQLite store, imported into Postgres; then a run directly on Postgres."""
    from test_core import FakeMetrics, FakeTargetAgent, incident
    from argus.adapters.outbound.llm import ScriptedLLM
    from argus.adapters.outbound.postgres_store import PostgresStore, import_sqlite
    from argus.adapters.outbound.sqlite_store import SqliteStore
    from argus.domain.model import IncidentOutcome
    from argus.infrastructure.wiring import Settings, build
    from argus.tooling.executors import ExecutorRegistry
    monkeypatch.setenv("ARGUS_JWT_KEY", "x" * 40)

    def script(ctx):
        t = "vm-166/container:argus-lab-worker"
        if "container.status" not in ctx:
            return {"calls": [("get_container_status", {"target": t})]}
        ids = [line.split('"')[1] for line in ctx.splitlines() if line.startswith("<evidence id=")]
        return {"calls": [("conclude", {"diagnosis": "OOM-killed by its 64 MiB limit", "evidence_ids": ids[-1:],
                                        "confidence": "high", "root_cause_target": t})]}

    def app_with(store):
        reg = ExecutorRegistry()
        for k in ("docker_read", "host_probe", "network_probe", "prometheus"):
            reg.register(k, lambda url, tok, k=k: FakeTargetAgent(url, tok, k))
        s = Settings(config_dir=ROOT / "config", secrets_dir=tmp_path / "none",
                     runbooks_dir=RUNBOOKS, max_reads_per_step=2)
        m = FakeMetrics({"vm-166/container:argus-lab-worker": {"restarts_10m": 5, "oom_killed": 1, "last_exit_code": 137}})
        return build(s, llm=ScriptedLLM(script), metrics=m, executors=reg, store=store, require_credentials=False)

    lite = SqliteStore(str(tmp_path / "lab.db"))
    lab = app_with(lite)
    old = lab.runner.run(incident(lab, "vm-166/container:argus-lab-worker").id)
    who = f"user_{secrets.token_hex(3)}"
    lite.upsert_principal(who, "human", "operator", ["lab"], "argon-hash")
    pg = PostgresStore(runtime_dsn)
    counts = import_sqlite(str(tmp_path / "lab.db"), pg)
    assert counts["incident"] == 1 and counts["evidence"] >= 2 and counts["audit"] > 0 and counts["principal"] == 1
    assert import_sqlite(str(tmp_path / "lab.db"), pg)["incident"] == 0                    # idempotent
    moved = pg.get_incident(old.id)
    assert moved.outcome == IncidentOutcome.diagnosed and moved.diagnosis == old.diagnosis
    assert [e.sha256 for e in pg.list_evidence(old.id)] == [e.sha256 for e in lite.list_evidence(old.id)]
    assert len(pg.list_run_events(old.id)) == len(lite.list_run_events(old.id))
    assert pg.get_principal(who)["password_hash"] == "argon-hash"            # users (alice) carry over

    app = app_with(pg)
    new = app.runner.run(incident(app, "vm-166/container:argus-lab-worker").id)
    assert new.outcome == IncidentOutcome.diagnosed and new.root_cause_target == "vm-166/container:argus-lab-worker"
    assert all(e.sha256 and e.host == "vm-166" for e in pg.list_evidence(new.id) if e.kind == "observation")
    pg.close()


def test_graph_runner_resumes_from_postgres_after_a_restart(runtime_dsn, tmp_path, monkeypatch):
    """T-0013 step 3: the checkpoint lives in Postgres, so a NEW process (new app, new pool) resumes the run."""
    from test_core import FakeMetrics, FakeTargetAgent, incident
    from argus.adapters.outbound.llm import ScriptedLLM
    from argus.adapters.outbound.postgres_store import PostgresStore
    from argus.domain.model import IncidentOutcome
    from argus.infrastructure.wiring import Settings, build
    from argus.tooling.executors import ExecutorRegistry
    monkeypatch.setenv("ARGUS_JWT_KEY", "x" * 40)
    monkeypatch.setenv("ARGUS_RUNNER", "langgraph")
    t = "vm-166/container:argus-lab-worker"
    state = {"crash": True}

    class Crash(BaseException):
        pass

    def script(ctx):
        if "container.status" not in ctx:
            return {"calls": [("get_container_status", {"target": t})]}
        if state["crash"]:
            state["crash"] = False
            raise Crash("process died")
        ids = [line.split('"')[1] for line in ctx.splitlines() if line.startswith("<evidence id=")]
        return {"calls": [("conclude", {"diagnosis": "OOM-killed by its 64 MiB limit", "evidence_ids": ids[-1:],
                                        "confidence": "high", "root_cause_target": t})]}

    def new_process():
        reg = ExecutorRegistry()
        for k in ("docker_read", "host_probe", "network_probe", "prometheus"):
            reg.register(k, lambda url, tok, k=k: FakeTargetAgent(url, tok, k))
        s = Settings(config_dir=ROOT / "config", secrets_dir=tmp_path / "none", runbooks_dir=RUNBOOKS,
                     max_reads_per_step=2)
        m = FakeMetrics({t: {"restarts_10m": 5, "oom_killed": 1, "last_exit_code": 137}})
        return build(s, llm=ScriptedLLM(script), metrics=m, executors=reg, store=PostgresStore(runtime_dsn),
                     require_credentials=False)

    first = new_process()
    assert type(first.runner.checkpointer).__name__ == "PostgresSaver"
    inc = incident(first, t)
    FakeTargetAgent.calls = []
    with pytest.raises(Crash):
        first.runner.run(inc.id)
    reads = len(FakeTargetAgent.calls)
    assert reads >= 1
    second = new_process()                                   # the restarted worker: nothing shared in memory
    done = second.runner.run(inc.id)
    assert done.outcome == IncidentOutcome.diagnosed
    assert len(FakeTargetAgent.calls) == reads               # the completed read was not repeated
    assert "incident.resumed" in [a.event for a in second.store.list_for(inc.id)]


def test_monitoring_state_and_the_escalated_incident(store):
    """T-0035 / ACR-0009 (migration 006): the runtime role keeps a host's heartbeat state, and a lost heartbeat's
    incident is stored already escalated (no worker can claim it)."""
    from argus.application.monitoring import MonitoringConfig, MonitoringWatch
    from argus.domain.model import IncidentStatus, utcnow
    host = f"vm-{secrets.token_hex(3)}"
    assert store.monitoring_state(host) is None
    store.save_monitoring_state(host, {"state": "alive", "fresh_ticks": 2})
    store.save_monitoring_state(host, {"state": "lost", "fresh_ticks": 0})
    assert store.monitoring_state(host) == {"state": "lost", "fresh_ticks": 0}
    while store.claim_next_queued("drain", lease_s=86400 * 30):
        pass
    t = [utcnow()]
    w = MonitoringWatch(store, MonitoringConfig(), now=lambda: t[0])
    store.save_monitoring_state(host, {})
    for _ in range(7):
        w.observe(host, [])
        t[0] += timedelta(minutes=1)
    inc = store.get_incident(store.monitoring_state(host)["incident_id"])
    assert inc.status == IncidentStatus.escalated and inc.incident_class == "monitoring_blind_spot"
    assert store.claim_next_queued("worker") is None
