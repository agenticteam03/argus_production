"""ACR-0018 §3 / phase 16 step 5a: the signed daily digest of the audit hash chain.

For each closed UTC day the digest says which chained row was the last one on or before it (its id, its hash, how many
rows the chain holds up to it, how many were written that day), signed with the audit digest key (Ed25519) and put
once under a name of its own in a store outside the VMs. A person with `sudo` who rewrites the chain, hashes included,
cannot also rewrite what was shipped. This step builds the digest, the job and the sinks; the OCI sink is step 5b.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import date, datetime, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from argus.adapters.outbound.sqlite_store import SqliteStore
from argus.domain.audit_chain import GENESIS, link_hash
from argus.domain.audit_digest import (build_digest, check_against_chain, digest_days, object_name, sign, to_bytes,
                                       verify_signed)
from argus.domain.model import AuditRecord

UTC = timezone.utc


def at(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 10, day, hour, tzinfo=UTC)


def record(n: int, when: datetime, event: str = "access.login") -> AuditRecord:
    return AuditRecord(audit_id=f"aud_{n:04d}", incident_id=None, at=when, category="access", event=event,
                       actor=f"user{n}")


def chain(whens: list[datetime]) -> list[tuple]:
    """Rows as `Store.audit_chain()` returns them, built by hand."""
    rows, prev = [], GENESIS
    for i, when in enumerate(whens):
        body = record(i, when).model_dump(mode="json")
        h = link_hash(prev, f"aud_{i:04d}", body)
        rows.append((f"aud_{i:04d}", body, prev, h))
        prev = h
    return rows


# --- the digest of a day ----------------------------------------------------------------------------------------------
def test_the_digest_of_a_day_names_the_last_chained_row_on_or_before_it():
    rows = chain([at(20, 9), at(20, 17), at(22, 10)])
    d20, d21, d22 = (build_digest(rows, date(2026, 10, n)) for n in (20, 21, 22))
    assert d20 == {"version": 1, "day": "2026-10-20", "last_audit_id": "aud_0001", "last_hash": rows[1][3],
                   "chained_rows": 2, "rows_that_day": 2}
    assert (d21["last_audit_id"], d21["last_hash"], d21["chained_rows"], d21["rows_that_day"]) == (
        "aud_0001", rows[1][3], 2, 0)                          # a quiet day repeats the last hash: a gap stays visible
    assert (d22["last_audit_id"], d22["chained_rows"], d22["rows_that_day"]) == ("aud_0002", 3, 1)
    assert build_digest(rows, date(2026, 10, 19)) is None      # the chain had not started


def test_rows_from_before_the_chain_are_not_part_of_a_digest():
    rows = [("aud_old", {"at": at(19).isoformat()}, None, None), *chain([at(20), at(20, 18)])]
    d = build_digest(rows, date(2026, 10, 20))
    assert (d["chained_rows"], d["rows_that_day"]) == (2, 2)
    assert digest_days(rows, date(2026, 10, 22)) == [date(2026, 10, 20), date(2026, 10, 21)]


def test_a_row_dated_out_of_order_does_not_move_an_earlier_day():
    rows = chain([at(20), at(22), at(21)])                     # the third row was written last, dated before the second
    assert build_digest(rows, date(2026, 10, 21))["last_audit_id"] == "aud_0000"
    assert build_digest(rows, date(2026, 10, 22))["last_audit_id"] == "aud_0002"


def test_the_days_to_ship_are_the_closed_ones_from_the_first_chained_row():
    rows = chain([at(20), at(22)])
    assert digest_days(rows, date(2026, 10, 23)) == [date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22)]
    assert digest_days(rows, date(2026, 10, 20)) == []         # today is never closed
    assert digest_days([], date(2026, 10, 23)) == []


def test_the_object_has_a_name_of_its_own_per_day():
    assert object_name(date(2026, 10, 20)) == "audit-digest/2026/2026-10-20.json"


# --- signing and checking ---------------------------------------------------------------------------------------------
def test_a_signed_digest_verifies_only_with_its_own_key_and_body():
    key = Ed25519PrivateKey.generate()
    body = build_digest(chain([at(20)]), date(2026, 10, 20))
    signed = sign(body, key)
    assert signed == sign(body, key) and to_bytes(signed) == to_bytes(sign(body, key))   # deterministic bytes
    assert verify_signed(signed, key.public_key())
    assert not verify_signed(signed, Ed25519PrivateKey.generate().public_key())
    assert not verify_signed({**signed, "digest": {**body, "chained_rows": 9}}, key.public_key())
    assert not verify_signed({**signed, "signature": "AAAA"}, key.public_key())
    assert not verify_signed({"digest": body}, key.public_key())


def test_a_digest_is_checked_against_the_chain_it_describes():
    rows = chain([at(20), at(20, 18), at(21)])
    signed = sign(build_digest(rows, date(2026, 10, 20)), Ed25519PrivateKey.generate())
    assert check_against_chain(signed, rows) == []
    rewritten = [rows[0], (rows[1][0], rows[1][1], rows[1][2], "f" * 64), rows[2]]    # the chain rewritten, hash included
    assert check_against_chain(signed, rewritten) == [
        "2026-10-20: the chain holds a different hash for aud_0001 than the one shipped"]
    assert check_against_chain(signed, rows[:1]) == ["2026-10-20: aud_0001 is not in the chain (rows removed)"]
    assert check_against_chain(signed, [rows[1], rows[0], rows[2]]) == [
        "2026-10-20: the chain holds 1 rows up to aud_0001, the digest says 2"]


# --- the job ------------------------------------------------------------------------------------------------------------
class MemorySink:
    off_host = True

    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.fail: Exception | None = None

    def put_once(self, name: str, data: bytes) -> str:
        if self.fail:
            raise self.fail
        if name in self.objects:
            return "exists_same" if self.objects[name] == data else "exists_different"
        self.objects[name] = data
        return "stored"


@pytest.fixture()
def world(tmp_path):
    store = SqliteStore(str(tmp_path / "a.db"))
    for n, when in enumerate([at(20, 9), at(20, 17), at(22, 10)]):
        store.append(record(n, when))
    return store, str(tmp_path / "a.db"), Ed25519PrivateKey.generate(), MemorySink()


def events(store, name: str) -> list[AuditRecord]:
    return [a for a in (AuditRecord.model_validate(b) for _, b, _, _ in store.audit_chain()) if a.event == name]


def job(world, now=at(23, 8), sink=None, key=None):
    from argus.infrastructure.audit_digest import AuditDigestJob
    store, _, k, s = world
    return AuditDigestJob(store, key if key is not None else k, sink if sink is not None else s, clock=lambda: now)


def test_the_job_ships_each_closed_day_once(world):
    store, _, key, sink = world
    assert job(world).run_once().startswith("shipped 3 digest(s)")
    assert sorted(sink.objects) == [object_name(date(2026, 10, n)) for n in (20, 21, 22)]
    assert job(world).run_once().startswith("shipped 0 digest(s)")        # the same bytes again: nothing new
    shipped = events(store, "security.audit_digest_shipped")
    assert [e.detail["day"] for e in shipped] == ["2026-10-20", "2026-10-21", "2026-10-22"]
    assert all(e.detail["off_host"] is True and e.actor == "scheduler" and e.category == "security" for e in shipped)


def test_every_shipped_digest_verifies_and_matches_the_chain(world):
    store, _, key, sink = world
    job(world).run_once()
    for name, data in sink.objects.items():
        signed = json.loads(data)
        assert verify_signed(signed, key.public_key()), name
        assert check_against_chain(signed, store.audit_chain()) == [], name


def test_the_next_day_adds_one_more_and_the_old_ones_stay_valid(world):
    store, _, key, sink = world
    job(world).run_once()
    before = dict(sink.objects)
    assert job(world, now=at(24, 8)).run_once().startswith("shipped 1 digest(s)")
    assert {n: d for n, d in sink.objects.items() if n in before} == before
    assert object_name(date(2026, 10, 23)) in sink.objects            # it counts the rows the job itself wrote on the 23rd


def test_a_broken_chain_signs_nothing(world):
    store, path, key, sink = world
    c = sqlite3.connect(path, isolation_level=None)
    c.execute("DROP TRIGGER audit_no_update")
    c.execute("UPDATE audit SET body = replace(body, 'user1', 'mallory') WHERE audit_id = 'aud_0001'")
    summary = job(world).run_once()
    assert summary.startswith("skipped") and sink.objects == {}
    (e,) = events(store, "security.audit_digest_skipped")
    assert e.detail["reason"] == "chain_broken" and e.detail["problems"] == 1


def test_a_sink_failure_is_recorded_and_the_next_run_catches_up(world):
    store, _, key, sink = world
    sink.fail = OSError("connection refused")
    assert job(world).run_once().startswith("failed")                  # it does not raise
    (e,) = events(store, "security.audit_digest_failed")
    assert e.detail == {"day": "2026-10-20", "error": "OSError", "off_host": True}
    assert sink.objects == {}
    sink.fail = None
    assert job(world).run_once().startswith("shipped 3 digest(s)")


def test_a_different_object_under_the_same_name_is_reported_and_never_overwritten(world):
    store, _, key, sink = world
    name = object_name(date(2026, 10, 21))
    sink.objects[name] = b"someone else's bytes"
    summary = job(world).run_once()
    assert "1 conflict(s)" in summary and sink.objects[name] == b"someone else's bytes"
    (e,) = events(store, "security.audit_digest_conflict")
    assert e.detail["day"] == "2026-10-21"
    assert len(sink.objects) == 3                                      # the other two days were shipped


def test_without_a_key_or_a_sink_the_job_says_so_and_ships_nothing(world):
    from argus.infrastructure.audit_digest import AuditDigestJob
    store, _, key, sink = world
    assert AuditDigestJob(store, None, sink, clock=lambda: at(23)).run_once().startswith("unconfigured")
    assert AuditDigestJob(store, key, None, clock=lambda: at(23)).run_once().startswith("unconfigured")
    reasons = [e.detail["missing"] for e in events(store, "security.audit_digest_unconfigured")]
    assert reasons == ["key", "sink"] and sink.objects == {}


# --- the local sink -----------------------------------------------------------------------------------------------------
def test_the_local_sink_creates_once_and_says_it_is_not_off_host(tmp_path):
    from argus.adapters.outbound.digest_sinks import LocalDirSink
    sink = LocalDirSink(tmp_path / "out")
    assert sink.off_host is False
    assert sink.put_once("audit-digest/2026/2026-10-20.json", b"one") == "stored"
    assert sink.put_once("audit-digest/2026/2026-10-20.json", b"one") == "exists_same"
    assert sink.put_once("audit-digest/2026/2026-10-20.json", b"two") == "exists_different"
    assert (tmp_path / "out" / "audit-digest" / "2026" / "2026-10-20.json").read_bytes() == b"one"
    for bad in ("../escape.json", "/abs.json", "a/../../b.json"):
        with pytest.raises(ValueError):
            sink.put_once(bad, b"x")


def test_a_local_sink_marks_the_event_not_off_host(world, tmp_path):
    from argus.adapters.outbound.digest_sinks import LocalDirSink
    store, *_ = world
    job(world, sink=LocalDirSink(tmp_path / "out")).run_once()
    assert {e.detail["off_host"] for e in events(store, "security.audit_digest_shipped")} == {False}


# --- the schedule and the wiring --------------------------------------------------------------------------------------------
def test_the_schedule_section_is_off_by_default_and_bounded():
    from argus.infrastructure.scheduler import load_audit_digest
    assert load_audit_digest("schedules: []\n") is None
    assert load_audit_digest("audit_digest:\n  enabled: false\n") is None
    assert load_audit_digest("audit_digest:\n  enabled: true\n") == 86400
    assert load_audit_digest("audit_digest:\n  enabled: true\n  every_s: 7200\n") == 7200
    with pytest.raises(ValueError, match="below the minimum"):
        load_audit_digest("audit_digest:\n  enabled: true\n  every_s: 60\n")
    with pytest.raises(ValueError, match="unknown field"):
        load_audit_digest("audit_digest:\n  enabled: true\n  bucket: x\n")


def test_the_shipped_schedule_file_keeps_the_digest_off():
    from pathlib import Path

    from argus.infrastructure.scheduler import load_audit_digest
    text = (Path(__file__).resolve().parents[1] / "deploy" / "scheduler" / "schedules.yaml").read_text(encoding="utf-8")
    assert load_audit_digest(text) is None and "audit_digest:" in text


def test_the_scheduler_loop_runs_the_digest_job():
    from argus.infrastructure.scheduler import Scheduler
    stop, calls = threading.Event(), []

    class Stub:
        def run_once(self):
            calls.append(1)
            stop.set()
            return "stub"

    class Store:
        def active_incident(self, target):
            return None

    Scheduler(Store(), [], digest_job=Stub(), digest_every_s=3600).run_forever(stop, every_s=0.01)
    assert calls == [1]


def test_the_digest_key_is_an_ed25519_pem_named_for_what_it_signs():
    from cryptography.hazmat.primitives import serialization

    from argus.infrastructure.wiring import ed25519_signing_key
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    assert ed25519_signing_key(pem, name="audit_digest_ed25519_key").public_key() == key.public_key()
    assert ed25519_signing_key(None, name="audit_digest_ed25519_key") is None
    with pytest.raises(SystemExit, match="audit_digest_ed25519_key is not a PEM private key"):
        ed25519_signing_key("not a key", name="audit_digest_ed25519_key")


def test_the_sink_comes_from_one_setting(monkeypatch, tmp_path):
    from argus.adapters.outbound.digest_sinks import LocalDirSink
    from argus.infrastructure.wiring import Settings, make_digest_sink
    monkeypatch.delenv("ARGUS_AUDIT_DIGEST_SINK", raising=False)
    assert make_digest_sink(Settings()) is None
    monkeypatch.setenv("ARGUS_AUDIT_DIGEST_SINK", f"dir:{tmp_path}")
    assert isinstance(make_digest_sink(Settings()), LocalDirSink)
    monkeypatch.setenv("ARGUS_AUDIT_DIGEST_SINK", "ftp://nowhere")
    with pytest.raises(SystemExit, match="ARGUS_AUDIT_DIGEST_SINK"):
        make_digest_sink(Settings())
