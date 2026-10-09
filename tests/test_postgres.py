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
