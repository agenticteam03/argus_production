"""T-0014 step 1: the worker's claim is a lease (ARCHITECTURE §6.2).

A worker claims a queued incident for a limited time and renews the claim while it runs. Another worker never takes
an incident whose claim is still live; an incident whose claim expired (its worker died) goes back to the queue and
is resumed from its LangGraph checkpoint without repeating the reads already done. The same store interface is
proved against Postgres in tests/test_postgres.py.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from argus.adapters.outbound.llm import ScriptedLLM
from argus.adapters.outbound.sqlite_store import SqliteStore
from argus.domain.model import IncidentOutcome, IncidentStatus, utcnow
from test_core import FakeTargetAgent, incident, make_app  # noqa: F401  (make_app = fixture)
from test_graph_runner import WORKER_166, Crash, _diagnose_script, _metrics


@pytest.fixture()
def store(tmp_path):
    return SqliteStore(str(tmp_path / "lease.db"))


def _queued(store, n=1):
    from test_postgres import _incident
    out = []
    for i in range(n):
        inc = _incident(minutes_ago=10 - i)
        store.create_incident(inc, None)
        out.append(inc)
    return out


def test_two_workers_never_claim_the_same_incident(store):
    first, second = _queued(store, 2)
    a = store.claim_next_queued("worker-a", lease_s=60)
    b = store.claim_next_queued("worker-b", lease_s=60)
    assert (a.id, b.id) == (first.id, second.id)
    assert store.claim_next_queued("worker-c", lease_s=60) is None


def test_a_live_claim_is_not_taken_back(store):
    (inc,) = _queued(store)
    store.claim_next_queued("worker-a", lease_s=60)
    assert store.requeue_expired() == 0
    assert store.get_incident(inc.id).status == IncidentStatus.running


def test_an_expired_claim_goes_back_to_the_queue(store):
    (inc,) = _queued(store)
    store.claim_next_queued("worker-a", lease_s=60)
    assert store.requeue_expired(now=utcnow() + timedelta(seconds=61)) == 1
    assert store.get_incident(inc.id).status == IncidentStatus.queued
    assert store.claim_next_queued("worker-b", lease_s=60).id == inc.id


def test_renewing_keeps_the_claim_and_only_its_owner_can_renew(store):
    (inc,) = _queued(store)
    store.claim_next_queued("worker-a", lease_s=60)
    later = utcnow() + timedelta(seconds=50)
    assert store.renew_claim(inc.id, "worker-a", lease_s=60, now=later) is True
    assert store.renew_claim(inc.id, "worker-b", lease_s=60, now=later) is False
    assert store.requeue_expired(now=later + timedelta(seconds=30)) == 0          # renewed: still live
    assert store.requeue_expired(now=later + timedelta(seconds=61)) == 1


def test_a_lost_claim_cannot_be_renewed(store):
    (inc,) = _queued(store)
    store.claim_next_queued("worker-a", lease_s=60)
    store.requeue_expired(now=utcnow() + timedelta(seconds=61))
    store.claim_next_queued("worker-b", lease_s=60)
    assert store.renew_claim(inc.id, "worker-a", lease_s=60) is False             # worker-a must stop


def test_a_running_row_without_a_lease_counts_as_expired(store):
    """Rows left 'running' by the single-process `argus serve` (no lease columns set) are recovered too."""
    (inc,) = _queued(store)
    store.claim_next_queued("worker-a", lease_s=60)
    store._q("UPDATE incident SET claimed_by=NULL, claimed_until=NULL WHERE id=?", (inc.id,))
    assert store.requeue_expired() == 1


def test_an_existing_sqlite_file_gets_the_lease_columns(tmp_path):
    import sqlite3
    path = str(tmp_path / "old.db")
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE incident (id TEXT PRIMARY KEY, target TEXT NOT NULL, status TEXT NOT NULL, "
               "opened_at TEXT NOT NULL, idempotency_key TEXT UNIQUE, body TEXT NOT NULL)")
    db.commit()
    db.close()
    store = SqliteStore(path)
    cols = {r[1] for r in store._q("PRAGMA table_info(incident)")}
    assert {"claimed_by", "claimed_until"} <= cols


def test_a_dead_workers_run_is_resumed_by_another_worker_without_repeating_reads(make_app, monkeypatch):
    monkeypatch.setenv("ARGUS_RUNNER", "langgraph")
    state = {"crashed": False}

    def script(ctx):
        if "container.status" in ctx and not state["crashed"]:
            state["crashed"] = True
            raise Crash("worker-a died after the first read")
        return _diagnose_script(ctx)

    app = make_app(llm=ScriptedLLM(script), metrics=_metrics())
    inc = incident(app, WORKER_166)
    claimed = app.store.claim_next_queued("worker-a", lease_s=60)
    with pytest.raises(Crash):
        app.runner.run(claimed.id)
    reads_before = len(FakeTargetAgent.calls)

    assert app.store.claim_next_queued("worker-b", lease_s=60) is None              # worker-a's claim is still live
    assert app.store.requeue_expired(now=utcnow() + timedelta(seconds=61)) == 1
    again = app.store.claim_next_queued("worker-b", lease_s=60)
    assert again.id == inc.id
    done = app.runner.run(again.id)
    assert done.outcome == IncidentOutcome.diagnosed
    assert len(FakeTargetAgent.calls) == reads_before                                # the completed read was not repeated
    assert "incident.resumed" in [a.event for a in app.store.list_for(inc.id)]
