"""CON-2 (ACR-0043, migration 020): each completed console command is kept with its incident, insert-only."""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from argus.adapters.outbound.sqlite_store import SqliteStore

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)


def row(command_id="cmd_1", incident_id="inc_1", person="olga", cls="read", status="ok", at=NOW, **extra):
    return {"command_id": command_id, "incident_id": incident_id, "person": person, "input": "cache status",
            "command": "cache.status", "cls": cls, "status": status, "output": "line one\nline two",
            "output_truncated": False, "suggestion_id": None, "started_at": at,
            "finished_at": at + timedelta(seconds=1), **extra}


@pytest.fixture
def store(tmp_path):
    return SqliteStore(str(tmp_path / "argus.db"))


def test_a_stored_command_reads_back_with_its_incident_oldest_first(store):
    store.add_console_command(row("cmd_2", at=NOW + timedelta(minutes=1)))
    store.add_console_command(row("cmd_1", at=NOW))
    store.add_console_command(row("cmd_3", incident_id="inc_other"))

    got = store.console_history("inc_1")

    assert [r["command_id"] for r in got] == ["cmd_1", "cmd_2"]
    first = got[0]
    assert (first["incident_id"], first["person"], first["input"], first["command"], first["cls"],
            first["status"], first["output"], first["output_truncated"], first["suggestion_id"]) == (
        "inc_1", "olga", "cache status", "cache.status", "read", "ok", "line one\nline two", False, None)
    assert first["started_at"] == NOW and first["finished_at"] == NOW + timedelta(seconds=1)


def test_history_is_limited_to_the_newest_rows(store):
    for i in range(5):
        store.add_console_command(row(f"cmd_{i}", at=NOW + timedelta(minutes=i)))
    assert [r["command_id"] for r in store.console_history("inc_1", limit=2)] == ["cmd_3", "cmd_4"]


def test_the_read_count_filters_by_person_incident_and_time_and_counts_reads_only(store):
    store.add_console_command(row("a", at=NOW - timedelta(minutes=90)))
    store.add_console_command(row("b", at=NOW - timedelta(minutes=30)))
    store.add_console_command(row("c", at=NOW - timedelta(seconds=10), person="alice"))
    store.add_console_command(row("d", at=NOW - timedelta(seconds=5), cls="write", status="rejected"))
    store.add_console_command(row("e", at=NOW - timedelta(seconds=4), incident_id="inc_2"))

    assert store.console_read_count(person="olga", since=NOW - timedelta(hours=1)) == 2     # b, e
    assert store.console_read_count(person="olga") == 3                                      # a, b, e
    assert store.console_read_count(incident_id="inc_1") == 3                                # a, b, c (d is a write)
    assert store.console_read_count(person="alice", incident_id="inc_1", since=NOW - timedelta(minutes=1)) == 1
    assert store.console_oldest_read(person="olga", since=NOW - timedelta(hours=1)) == NOW - timedelta(minutes=30)


def test_a_command_id_is_stored_once(store):
    store.add_console_command(row("cmd_1"))
    with pytest.raises(sqlite3.IntegrityError):
        store.add_console_command(row("cmd_1"))


def test_the_table_is_insert_only(store):
    store.add_console_command(row("cmd_1"))
    for sql in ("UPDATE console_command SET status = 'error'", "DELETE FROM console_command"):
        with pytest.raises(sqlite3.DatabaseError, match="insert-only"):
            store._q(sql)


def test_a_status_or_class_outside_the_known_values_is_refused(store):
    with pytest.raises(sqlite3.IntegrityError):
        store.add_console_command(row("cmd_1", status="done"))
    with pytest.raises(sqlite3.IntegrityError):
        store.add_console_command(row("cmd_2", cls="shell"))


def test_a_refused_input_is_stored_with_no_command_and_no_class(store):
    store.add_console_command(row("cmd_1", command=None, cls=None, status="rejected", input="status; rm",
                                  output="syntax not allowed: ;"))
    store.add_console_command(row("cmd_2"))

    got = store.console_history("inc_1")

    assert (got[0]["command"], got[0]["cls"], got[0]["status"], got[0]["input"], got[0]["output"]) == (
        None, None, "rejected", "status; rm", "syntax not allowed: ;")
    assert store.console_read_count(person="olga") == 1                 # a refusal is not a read


# --- CON-4b (migration 021): the analysis of a command, updated while it runs ---------------------------------------
def test_an_analysis_is_stored_whole_and_replaced_as_it_moves_on(store):
    store.add_console_command(row("cmd_1"))
    store.add_console_command(row("cmd_2"))
    store.add_console_command(row("cmd_3", incident_id="inc_other"))
    store.put_console_analysis("cmd_1", "inc_1", "waiting", {"before": {"samples": []}, "after": []}, NOW)
    store.put_console_analysis("cmd_3", "inc_other", "done", {"result": {"comment": "x"}}, NOW)
    store.put_console_analysis("cmd_1", "inc_1", "done", {"before": {"samples": []}, "after": [1, 2],
                                                         "result": {"comment": "The cache is stopped."}}, NOW)

    got = store.console_analyses("inc_1")

    assert list(got) == ["cmd_1"]                                       # cmd_2 has none; cmd_3 is another incident's
    assert got["cmd_1"]["status"] == "done" and got["cmd_1"]["after"] == [1, 2]
    assert got["cmd_1"]["result"]["comment"] == "The cache is stopped."
    assert store.console_analyses("inc_none") == {}


def test_an_analysis_is_never_deleted_and_its_status_is_one_of_four(store):
    store.add_console_command(row("cmd_1"))
    store.put_console_analysis("cmd_1", "inc_1", "waiting", {}, NOW)
    with pytest.raises(sqlite3.DatabaseError, match="never deleted"):
        store._q("DELETE FROM console_analysis")
    with pytest.raises(sqlite3.IntegrityError):
        store.put_console_analysis("cmd_1", "inc_1", "maybe", {}, NOW)
