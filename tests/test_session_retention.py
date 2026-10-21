"""ACR-0018 (phase 16): owner-only retention of auth_session rows, with a safe dry run and a chained audit row."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


OWNER_DSN = os.getenv("ARGUS_TEST_PG_OWNER_DSN")
ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
needs_pg = pytest.mark.skipif(not OWNER_DSN, reason="needs a throwaway Postgres")


@pytest.fixture()
def database():
    import psycopg

    with psycopg.connect(OWNER_DSN, autocommit=True) as c:
        c.execute("DROP SCHEMA public CASCADE")
        c.execute("CREATE SCHEMA public")
        for migration in sorted((ROOT / "deploy/migrations").glob("*.sql")):
            c.execute(migration.read_text(encoding="utf-8"))
    yield OWNER_DSN


def _session(c, n: int, expired_days_ago: float, revoked: bool = False):
    expires = NOW - timedelta(days=expired_days_ago)
    c.execute("INSERT INTO auth_session (jti, principal, access, created_at, expires_at, revoked_at) "
              "VALUES (%s, 'u_alice', 'full', %s, %s, %s)",
              (f"{n:032x}", expires - timedelta(hours=8), expires, expires if revoked else None))


@needs_pg
def test_dry_run_and_apply_only_prune_long_expired_sessions(database):
    import psycopg
    from argus.domain.audit_chain import verify
    from argus.infrastructure.session_retention import prune_sessions

    with psycopg.connect(database) as c:
        _session(c, 1, 100)
        _session(c, 2, 91, revoked=True)
        _session(c, 3, 89)                  # expired, but inside the window
        _session(c, 4, -1)                  # live
        c.execute("INSERT INTO audit (audit_id,incident_id,at,body) VALUES ('audit_before',NULL,%s,'{}')", (NOW,))

    preview = prune_sessions(database, days=90, now=NOW)
    assert preview == {"dry_run": True, "sessions": 2, "revoked": 1}
    with psycopg.connect(database) as c:
        assert c.execute("SELECT count(*) FROM auth_session").fetchone()[0] == 4
        assert c.execute("SELECT count(*) FROM audit").fetchone()[0] == 1

    done = prune_sessions(database, days=90, now=NOW, dry_run=False)
    assert done == {"dry_run": False, "sessions": 2, "revoked": 1}
    with psycopg.connect(database) as c:
        assert {r[0] for r in c.execute("SELECT jti FROM auth_session")} == {f"{3:032x}", f"{4:032x}"}
        audit = c.execute("SELECT body FROM audit WHERE audit_id <> 'audit_before'").fetchone()[0]
        assert audit["event"] == "maintenance.sessions_pruned"
        assert audit["category"] == "access" and audit["actor"] == "system"
        assert audit["detail"] == {"sessions_removed": 2, "revoked_removed": 1, "retention_days": 90}
        rows = c.execute("SELECT audit_id, body, prev_hash, hash FROM audit ORDER BY seq").fetchall()
    assert verify(rows) == (1, 1, [])       # chained: `argus audit verify` stays clean

    again = prune_sessions(database, days=90, now=NOW, dry_run=False)
    assert again["sessions"] == 0


@needs_pg
def test_runtime_role_cannot_prune_sessions(database):
    import psycopg
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    from argus.infrastructure.session_retention import prune_sessions

    with psycopg.connect(database) as c:
        c.execute("ALTER ROLE argus_runtime PASSWORD 'throwaway-test-password'")
    dsn = make_conninfo(**{**conninfo_to_dict(database), "user": "argus_runtime",
                           "password": "throwaway-test-password"})
    with pytest.raises(PermissionError, match="argus_owner"):
        prune_sessions(dsn, days=90, now=NOW, dry_run=False)


@needs_pg
def test_audit_failure_rolls_back_every_session_delete(database, monkeypatch):
    import psycopg
    from argus.infrastructure import session_retention as retention

    with psycopg.connect(database) as c:
        _session(c, 1, 100)
        c.execute("INSERT INTO audit (audit_id,incident_id,at,body) VALUES ('aud_collision',NULL,%s,'{}')", (NOW,))
    monkeypatch.setattr(retention.secrets, "token_hex", lambda length: "collision")
    with pytest.raises(psycopg.errors.UniqueViolation):
        retention.prune_sessions(database, days=90, now=NOW, dry_run=False)
    with psycopg.connect(database) as c:
        assert c.execute("SELECT count(*) FROM auth_session").fetchone()[0] == 1
        assert c.execute("SELECT count(*) FROM audit").fetchone()[0] == 1


def test_invalid_retention_window_is_refused_before_connecting():
    from argus.infrastructure.session_retention import prune_sessions

    with pytest.raises(ValueError, match="positive"):
        prune_sessions("unused", days=0)


def test_cli_previews_by_default_with_each_action_s_own_window(monkeypatch):
    from argus.__main__ import build_parser, retention_days

    monkeypatch.delenv("ARGUS_SESSION_RETENTION_DAYS", raising=False)
    monkeypatch.delenv("ARGUS_CHECKPOINT_RETENTION_DAYS", raising=False)
    parser = build_parser()
    preview = parser.parse_args(["db", "prune-sessions"])
    assert retention_days(preview) == 90 and preview.apply is False
    assert retention_days(parser.parse_args(["db", "prune-checkpoints"])) == 30
    apply = parser.parse_args(["db", "prune-sessions", "--days", "120", "--apply"])
    assert retention_days(apply) == 120 and apply.apply is True
