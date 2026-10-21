"""T-0046 step L2 (ACR-0025): `link_event`, the insert-only record of link-state transitions (migration 009), on both
stores. The Postgres half (grants, the state check) is in tests/test_postgres.py."""
from __future__ import annotations

import sqlite3
from datetime import timedelta

import pytest

from argus.adapters.outbound.sqlite_store import SqliteStore
from argus.domain.model import utcnow
from test_core import ROOT

API, CACHE, DB = "vm-166/container:argus-lab-api", "vm-166/container:argus-lab-cache", "vm-166/container:argus-lab-db"


@pytest.fixture()
def store(tmp_path):
    return SqliteStore(str(tmp_path / "links.db"))


def test_the_store_keeps_transitions_and_reads_them_by_owner_or_dependency(store):
    now = utcnow()
    store.add_link_event(API, CACHE, "ok", 1.2, None, now - timedelta(hours=2))
    store.add_link_event(API, CACHE, "broken", None, "connection refused", now - timedelta(minutes=10))
    store.add_link_event("vm-166/container:argus-lab-leaker", DB, "slow", 250.0, None, now - timedelta(minutes=5))
    got = store.link_events(API, now - timedelta(hours=1), now)
    assert [(e["owner"], e["dependency"], e["state"], e["latency_ms"], e["reason"]) for e in got] == [
        (API, CACHE, "broken", None, "connection refused")]
    assert got[0]["at"].tzinfo is not None
    assert [e["state"] for e in store.link_events(CACHE, now - timedelta(hours=3), now)] == ["ok", "broken"]  # as dependency
    assert store.link_events(DB, now - timedelta(hours=1), now)[0]["owner"].endswith("leaker")
    assert store.link_events("vm-095/container:other", now - timedelta(days=1), now) == []


def test_transitions_come_oldest_first(store):
    now = utcnow()
    for i, state in enumerate(["ok", "slow", "broken", "ok"]):
        store.add_link_event(API, CACHE, state, None, None, now - timedelta(minutes=10 - i))
    assert [e["state"] for e in store.link_events(API, now - timedelta(hours=1), now)] == ["ok", "slow", "broken", "ok"]


@pytest.mark.parametrize("sql", ["UPDATE link_event SET state = 'ok'", "DELETE FROM link_event"])
def test_the_table_is_insert_only(store, tmp_path, sql):
    store.add_link_event(API, CACHE, "broken", None, None, utcnow())
    with sqlite3.connect(tmp_path / "links.db") as c, pytest.raises(sqlite3.IntegrityError, match="insert-only"):
        c.execute(sql)


def test_a_state_outside_the_four_is_refused(store):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        store.add_link_event(API, CACHE, "down", None, None, utcnow())


def test_the_migration_is_insert_only_for_the_runtime_role():
    sql = (ROOT / "deploy" / "migrations" / "009_link_event.sql").read_text(encoding="utf-8")
    grants = [line for line in sql.splitlines() if line.startswith("GRANT")]
    assert grants == ["GRANT SELECT, INSERT ON link_event TO argus_runtime;",
                      "GRANT USAGE ON SEQUENCE link_event_id_seq TO argus_runtime;"]
    assert "CHECK (state IN ('ok', 'slow', 'broken', 'unknown'))" in sql


def test_db_check_proves_the_insert_before_counting_its_refusals():
    """As for deploy_event: without migration 009 the refusals would "pass" on a missing table, so the insert, which must
    succeed, comes first."""
    from argus.adapters.outbound.postgres_store import CHECKS_SQL
    names = [n for n, _, _ in CHECKS_SQL]
    insert = names.index("insert link event (ACR-0025, migration 009)")
    assert CHECKS_SQL[insert][2] is True
    for refusal in ("link event is insert-only (UPDATE refused)", "link event is insert-only (DELETE refused)"):
        assert insert < names.index(refusal) and CHECKS_SQL[names.index(refusal)][2] is False
