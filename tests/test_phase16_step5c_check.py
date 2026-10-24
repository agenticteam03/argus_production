"""ACR-0018 / phase 16 step 5c: checking shipped digests against the audit chain, and the scheduler's secrets.

`argus audit check-digests <files or folders> --public-key <pem>` is what proves the digests did their job: each one is
signed by the audit digest key, names a row the chain still holds with the same hash and the same row count, and the days
form an unbroken series. It reads files, so it works on digests downloaded from the bucket by someone whose credential
can read them (the shipping credential cannot).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from argus.adapters.outbound.digest_sinks import LocalDirSink
from argus.adapters.outbound.sqlite_store import SqliteStore
from argus.domain.audit_chain import verify
from argus.domain.model import AuditRecord

UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[1]


def at(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 10, day, hour, tzinfo=UTC)


@pytest.fixture()
def shipped(tmp_path):
    """A store with rows on the 20th and 22nd, and the digests of the 20th to the 22nd shipped to a folder."""
    from argus.infrastructure.audit_digest import AuditDigestJob
    store = SqliteStore(str(tmp_path / "a.db"))
    for n, when in enumerate([at(20, 9), at(20, 17), at(22, 10)]):
        store.append(AuditRecord(audit_id=f"aud_{n:04d}", incident_id=None, at=when, category="access",
                                 event="access.login", actor=f"user{n}"))
    key = Ed25519PrivateKey.generate()
    out = tmp_path / "bucket"
    AuditDigestJob(store, key, LocalDirSink(out), clock=lambda: at(23, 8)).run_once()
    pem = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    return store, out, key, pem


def test_a_clean_series_checks_out(shipped):
    from argus.infrastructure.audit_digest import check_digest_files
    store, out, key, pem = shipped
    assert check_digest_files([out], store.audit_chain(), pem) == []


def test_a_single_file_and_a_folder_are_both_accepted(shipped):
    from argus.infrastructure.audit_digest import check_digest_files
    store, out, key, pem = shipped
    one = next(out.rglob("2026-10-20.json"))
    assert check_digest_files([one], store.audit_chain(), pem) == []


def test_an_edited_digest_no_longer_verifies(shipped):
    from argus.infrastructure.audit_digest import check_digest_files
    store, out, key, pem = shipped
    f = next(out.rglob("2026-10-21.json"))
    f.write_text(f.read_text(encoding="utf-8").replace('"chained_rows":2', '"chained_rows":3'), encoding="utf-8")
    assert check_digest_files([out], store.audit_chain(), pem) == ["2026-10-21: the signature does not verify"]


def test_another_key_is_named_and_refused(shipped):
    from argus.infrastructure.audit_digest import check_digest_files
    store, out, key, pem = shipped
    other = Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    problems = check_digest_files([out], store.audit_chain(), other)
    assert len(problems) == 3 and all("signature does not verify" in p for p in problems)


def test_a_missing_day_is_a_gap(shipped):
    from argus.infrastructure.audit_digest import check_digest_files
    store, out, key, pem = shipped
    next(out.rglob("2026-10-21.json")).unlink()
    assert check_digest_files([out], store.audit_chain(), pem) == ["2026-10-21: no digest for this day (a gap in the series)"]


def test_a_rewritten_chain_is_caught_by_the_digest_that_survived_off_host(shipped):
    from argus.infrastructure.audit_digest import check_digest_files
    store, out, key, pem = shipped
    rows = store.audit_chain()
    rewritten = [rows[0], (rows[1][0], rows[1][1], rows[1][2], "f" * 64), *rows[2:]]       # hashes recomputed by an intruder
    problems = check_digest_files([out], rewritten, pem)
    assert problems and all("different hash for aud_0001" in p for p in problems[:2])
    assert problems[0].startswith("2026-10-20:")


def test_a_body_tamper_with_the_stored_hash_is_rejected_even_when_the_digest_still_matches(shipped):
    from argus.infrastructure.audit_digest import check_digest_files
    store, out, key, pem = shipped
    rows = store.audit_chain()
    tampered = [(audit_id, dict(body), prev_hash, hash_)
                for audit_id, body, prev_hash, hash_ in rows]
    tampered[0][1]["event"] = "access.logout"

    assert verify(tampered)[2] == ["aud_0000: hash does not match its body (the row was edited)"]
    assert check_digest_files([out], tampered, pem) == [
        "audit chain: aud_0000: hash does not match its body (the row was edited)"]


def test_the_command_rejects_an_edited_body_without_printing_digests_ok(shipped, tmp_path, monkeypatch, capsys):
    import argus.__main__ as cli

    store, out, key, pem = shipped
    rows = [(audit_id, dict(body), prev_hash, hash_)
            for audit_id, body, prev_hash, hash_ in store.audit_chain()]
    rows[0][1]["event"] = "access.logout"
    monkeypatch.setattr(store, "audit_chain", lambda: rows)
    monkeypatch.setattr(cli, "make_store", lambda settings: store)
    public_key = tmp_path / "public.pem"
    public_key.write_bytes(pem)
    args = cli.build_parser().parse_args(["audit", "check-digests", str(out), "--public-key", str(public_key)])

    with pytest.raises(SystemExit, match="DIGESTS DO NOT MATCH THE CHAIN: 1 problem"):
        cli.audit(args)

    output = capsys.readouterr().out
    assert "PROBLEM  audit chain: aud_0000: hash does not match its body" in output
    assert "DIGESTS OK" not in output and "access.logout" not in output


def test_a_file_that_is_not_a_digest_is_reported_not_skipped(shipped):
    from argus.infrastructure.audit_digest import check_digest_files
    store, out, key, pem = shipped
    (out / "audit-digest" / "2026" / "notes.json").write_text("not json at all", encoding="utf-8")
    assert "notes.json: not a signed digest" in check_digest_files([out], store.audit_chain(), pem)[0]


def test_nothing_to_check_is_a_problem_not_a_pass(tmp_path, shipped):
    from argus.infrastructure.audit_digest import check_digest_files
    store, out, key, pem = shipped
    empty = tmp_path / "empty"
    empty.mkdir()
    assert check_digest_files([empty], store.audit_chain(), pem) == ["no digest files found"]


# --- the compose file -------------------------------------------------------------------------------------------------------
CORE = yaml.safe_load((ROOT / "deploy" / "vm-095" / "compose.core.yml").read_text(encoding="utf-8"))["services"]


def test_only_the_scheduler_mounts_the_digest_secrets():
    for name, svc in CORE.items():
        mounted = [v for v in svc.get("volumes", []) if "secrets/digest" in str(v)]
        assert bool(mounted) == (name == "argus-v18-scheduler"), name


def test_the_scheduler_mounts_the_digest_key_and_the_oci_folder_read_only_from_their_own_folder():
    vols = CORE["argus-v18-scheduler"]["volumes"]
    assert "/opt/argus-v18/secrets/digest/audit_digest_ed25519_key:/run/argus-secrets/audit_digest_ed25519_key:ro" in vols
    assert "/opt/argus-v18/secrets/digest/oci_digest:/run/argus-secrets/oci_digest:ro" in vols
    assert not any("secrets/agent" in v and "db_password" not in v for v in vols)      # never the whole agent folder


def test_the_digest_sink_is_set_from_the_environment_and_empty_by_default():
    assert CORE["argus-v18-scheduler"]["environment"]["ARGUS_AUDIT_DIGEST_SINK"] == "${ARGUS_AUDIT_DIGEST_SINK:-}"


def test_the_scheduler_has_room_for_the_oci_sdk_and_the_chain():
    s = CORE["argus-v18-scheduler"]
    assert s["mem_limit"] == "256m" and s["memswap_limit"] == "256m"      # the SDK adds ~19 MB at start; 160m was the old limit
