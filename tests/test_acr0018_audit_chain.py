"""ACR-0018 §17.1 layer 13 (phase 16 step 1): the audit hash chain.

Each audit row carries the previous row's hash and its own; `argus audit verify` recomputes the chain and names the
first row that was edited, removed or inserted outside the store. Rows from before migration 011 are counted, not
chained. (The Postgres side, with concurrent writers and an owner who disables the insert-only trigger, is in
tests/test_postgres.py.)
"""
from __future__ import annotations

import sqlite3
import uuid

import pytest

from argus.adapters.outbound.sqlite_store import SqliteStore
from argus.domain.audit_chain import GENESIS, link_hash, verify
from argus.domain.model import AuditRecord, utcnow


def record(event="access.login_failed", actor="alice") -> AuditRecord:
    return AuditRecord(audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=None, at=utcnow(), category="access",
                       event=event, actor=actor, detail={"client": "198.51.100.7"})


@pytest.fixture()
def store(tmp_path):
    s = SqliteStore(str(tmp_path / "a.db"))
    for i in range(5):
        s.append(record(actor=f"user{i}"))
    return s, str(tmp_path / "a.db")


def _raw(path: str):
    """The database as a host administrator sees it: the append-only triggers can be dropped."""
    c = sqlite3.connect(path, isolation_level=None)
    c.execute("DROP TRIGGER audit_no_update")
    c.execute("DROP TRIGGER audit_no_delete")
    return c


def test_the_chain_of_a_clean_store_verifies(store):
    s, _ = store
    rows = s.audit_chain()
    assert rows[0][2] == GENESIS and all(rows[i][2] == rows[i - 1][3] for i in range(1, len(rows)))
    assert verify(rows) == (5, 0, [])


def test_an_edited_row_breaks_the_chain_at_that_row(store):
    s, path = store
    victim = s.audit_chain()[2][0]
    _raw(path).execute("UPDATE audit SET body = replace(body, 'user2', 'mallory') WHERE audit_id = ?", (victim,))
    chained, _, problems = verify(s.audit_chain())
    assert problems == [f"{victim}: hash does not match its body (the row was edited)"]


def test_a_removed_row_breaks_the_chain_at_the_next_one(store):
    s, path = store
    rows = s.audit_chain()
    _raw(path).execute("DELETE FROM audit WHERE audit_id = ?", (rows[1][0],))
    problems = verify(s.audit_chain())[2]
    assert problems and problems[0].startswith(rows[2][0]) and "prev_hash" in problems[0]


def test_a_row_inserted_outside_the_store_is_named(store):
    s, path = store
    _raw(path).execute("INSERT INTO audit(audit_id,incident_id,at,body) VALUES ('aud_forged', NULL, '2026-10-21', '{}')")
    assert verify(s.audit_chain())[2] == ["aud_forged: no hash after the chain started (inserted outside the store)"]


def test_rows_from_before_the_chain_are_counted_not_chained(tmp_path):
    path = str(tmp_path / "old.db")
    with sqlite3.connect(path) as c:                   # a lab file from before migration 011
        c.execute("CREATE TABLE audit (audit_id TEXT PRIMARY KEY, incident_id TEXT, at TEXT NOT NULL, body TEXT NOT NULL)")
        c.execute("INSERT INTO audit VALUES ('aud_old1', NULL, '2026-10-01', '{}')")
        c.execute("INSERT INTO audit VALUES ('aud_old2', NULL, '2026-10-02', '{}')")
    s = SqliteStore(path)
    s.append(record())
    s.append(record())
    assert verify(s.audit_chain()) == (2, 2, [])


def test_the_hash_covers_the_previous_hash_the_id_and_the_body():
    base = link_hash(GENESIS, "aud_1", {"a": 1})
    assert base != link_hash("1" * 64, "aud_1", {"a": 1})
    assert base != link_hash(GENESIS, "aud_2", {"a": 1})
    assert base != link_hash(GENESIS, "aud_1", {"a": 2})
    assert base == link_hash(GENESIS, "aud_1", {"a": 1})        # key order and spacing do not matter (canonical)


# --- the scheduled verification (ACR-0018 §17.1 layer 13) ---------------------------------------------------------------
def _events(path: str) -> list[str]:
    import json
    with sqlite3.connect(path) as c:
        return [json.loads(b)["event"] for (b,) in c.execute("SELECT body FROM audit ORDER BY rowid")]


def test_the_scheduled_check_records_a_verified_chain(store):
    from argus.infrastructure.scheduler import AuditChainCheck
    s, path = store
    assert AuditChainCheck(s).run_once().startswith("security.audit_chain_verified: 5 chained")
    assert _events(path)[-1] == "security.audit_chain_verified"
    assert verify(s.audit_chain())[2] == []                        # its own record is chained too


def test_the_scheduled_check_records_a_broken_chain(store):
    from argus.infrastructure.scheduler import AuditChainCheck
    s, path = store
    victim = s.audit_chain()[1][0]
    _raw(path).execute("UPDATE audit SET body = replace(body, 'user1', 'mallory') WHERE audit_id = ?", (victim,))
    assert AuditChainCheck(s).run_once().startswith("security.audit_chain_broken")
    assert _events(path)[-1] == "security.audit_chain_broken"


@pytest.mark.parametrize("text, want", [
    ("", None),
    ("audit_chain: {enabled: false}", None),
    ("audit_chain: {enabled: true}", 86400),
    ("audit_chain: {enabled: true, every_s: 7200}", 7200),
])
def test_the_audit_chain_setting(text, want):
    from argus.infrastructure.scheduler import load_audit_chain
    assert load_audit_chain(text) == want


@pytest.mark.parametrize("text, words", [
    ("audit_chain: {enabled: true, every_s: 60}", "minimum"),
    ("audit_chain: {enabled: true, evry_s: 7200}", "unknown field"),
])
def test_a_bad_audit_chain_setting_refuses_the_file(text, words):
    from argus.infrastructure.scheduler import load_audit_chain
    with pytest.raises(ValueError, match=words):
        load_audit_chain(text)


def test_the_shipped_schedules_verify_the_chain_daily():
    from argus.infrastructure.scheduler import load_audit_chain
    from test_core import ROOT
    assert load_audit_chain((ROOT / "deploy" / "scheduler" / "schedules.yaml").read_text(encoding="utf-8")) == 86400
