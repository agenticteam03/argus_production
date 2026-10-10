"""OP-004: owner-only retention of LangGraph checkpoints, with a safe dry run."""
from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


OWNER_DSN = os.getenv("ARGUS_TEST_PG_OWNER_DSN")
pytestmark = pytest.mark.skipif(not OWNER_DSN, reason="needs a throwaway Postgres")
ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)


@pytest.fixture()
def database():
    import psycopg

    with psycopg.connect(OWNER_DSN, autocommit=True) as c:
        c.execute("DROP SCHEMA public CASCADE")
        c.execute("CREATE SCHEMA public")
        for migration in sorted((ROOT / "deploy/migrations").glob("*.sql")):
            c.execute(migration.read_text(encoding="utf-8"))
    yield OWNER_DSN


def _thread(c, name: str, status: str, closed_at: datetime | None):
    from psycopg.types.json import Jsonb

    body = {"closed_at": closed_at.isoformat() if closed_at else None}
    c.execute("INSERT INTO incident (id,target,status,opened_at,body) VALUES (%s,%s,%s,%s,%s)",
              (name, "vm-095/container:argus-lab-api", status, NOW - timedelta(days=45), Jsonb(body)))
    c.execute("INSERT INTO checkpoints (thread_id,checkpoint_id,checkpoint) VALUES (%s,'cp1','{}')", (name,))
    c.execute("INSERT INTO checkpoint_blobs (thread_id,channel,version,type,blob) "
              "VALUES (%s,'channel','v1','bytes',%s)", (name, b"blob"))
    c.execute("INSERT INTO checkpoint_writes (thread_id,checkpoint_id,task_id,idx,channel,blob) "
              "VALUES (%s,'cp1','task',0,'channel',%s)", (name, b"write"))
    c.execute("INSERT INTO run_event (incident_id,seq,at,node,phase,data) "
              "VALUES (%s,1,%s,'detect','exit','{}')", (name, NOW))


def test_dry_run_and_apply_only_prune_old_final_threads(database):
    import psycopg
    from argus.infrastructure.checkpoint_retention import prune_checkpoints

    with psycopg.connect(database) as c:
        _thread(c, "old_closed", "closed", NOW - timedelta(days=31))
        _thread(c, "old_escalated", "escalated", NOW - timedelta(days=40))
        _thread(c, "recent_closed", "closed", NOW - timedelta(days=29))
        _thread(c, "old_running", "running", NOW - timedelta(days=40))
        _thread(c, "no_end_time", "closed", None)
        c.execute("INSERT INTO audit (audit_id,incident_id,at,body) VALUES "
                  "('audit_before',NULL,%s,'{}')", (NOW,))

    preview = prune_checkpoints(database, days=30, now=NOW)
    assert preview == {"dry_run": True, "threads": 2, "checkpoints": 2, "blobs": 2, "writes": 2}
    with psycopg.connect(database) as c:
        assert c.execute("SELECT count(*) FROM checkpoints").fetchone()[0] == 5
        assert c.execute("SELECT count(*) FROM audit").fetchone()[0] == 1

    done = prune_checkpoints(database, days=30, now=NOW, dry_run=False)
    assert done == {"dry_run": False, "threads": 2, "checkpoints": 2, "blobs": 2, "writes": 2}
    with psycopg.connect(database) as c:
        expected = {"recent_closed", "old_running", "no_end_time"}
        for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            assert {r[0] for r in c.execute(f"SELECT thread_id FROM {table}")} == expected
        assert c.execute("SELECT count(*) FROM incident").fetchone()[0] == 5
        assert c.execute("SELECT count(*) FROM run_event").fetchone()[0] == 5
        audit = c.execute("SELECT body FROM audit WHERE audit_id <> 'audit_before'").fetchone()[0]
        assert audit["event"] == "maintenance.checkpoints_pruned"
        assert audit["category"] == "decision" and audit["actor"] == "system"
        assert audit["detail"]["threads_removed"] == 2
        assert c.execute("SELECT count(*) FROM audit").fetchone()[0] == 2

    again = prune_checkpoints(database, days=30, now=NOW, dry_run=False)
    assert again["threads"] == again["checkpoints"] == again["blobs"] == again["writes"] == 0


def test_runtime_role_cannot_prune(database):
    import psycopg
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    from argus.infrastructure.checkpoint_retention import prune_checkpoints

    with psycopg.connect(database) as c:
        c.execute("ALTER ROLE argus_runtime PASSWORD 'throwaway-test-password'")
    dsn = make_conninfo(**{**conninfo_to_dict(database), "user": "argus_runtime",
                           "password": "throwaway-test-password"})
    with pytest.raises(PermissionError, match="argus_owner"):
        prune_checkpoints(dsn, days=30, now=NOW, dry_run=False)


def test_audit_failure_rolls_back_every_checkpoint_delete(database, monkeypatch):
    import psycopg
    from argus.infrastructure import checkpoint_retention as retention

    with psycopg.connect(database) as c:
        _thread(c, "old_final", "closed", NOW - timedelta(days=31))
        c.execute("INSERT INTO audit (audit_id,incident_id,at,body) VALUES "
                  "('aud_collision',NULL,%s,'{}')", (NOW,))
    monkeypatch.setattr(retention.secrets, "token_hex", lambda length: "collision")
    with pytest.raises(psycopg.errors.UniqueViolation):
        retention.prune_checkpoints(database, days=30, now=NOW, dry_run=False)
    with psycopg.connect(database) as c:
        for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            assert c.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 1
        assert c.execute("SELECT count(*) FROM audit").fetchone()[0] == 1


def test_invalid_retention_window_is_refused_before_connecting():
    from argus.infrastructure.checkpoint_retention import prune_checkpoints

    with pytest.raises(ValueError, match="positive"):
        prune_checkpoints("unused", days=0)


def test_cli_and_timer_keep_preview_as_the_manual_default():
    from argus.__main__ import build_parser

    parser = build_parser()
    preview = parser.parse_args(["db", "prune-checkpoints"])
    assert preview.days == 30 and preview.apply is False
    apply = parser.parse_args(["db", "prune-checkpoints", "--days", "45", "--apply"])
    assert apply.days == 45 and apply.apply is True

    wrapper = (ROOT / "ops/checkpoint-retention.sh").read_text(encoding="utf-8")
    service = (ROOT / "deploy/vm-095/systemd/argus-v18-checkpoint-retention.service").read_text(encoding="utf-8")
    timer = (ROOT / "deploy/vm-095/systemd/argus-v18-checkpoint-retention.timer").read_text(encoding="utf-8")
    assert "MODE=--dry-run" in wrapper and "NOT YOUR SESSION" in wrapper
    assert "source=$SECRET,target=/run/argus-secrets/db_password,readonly" in wrapper
    assert "--apply --scheduled" in service and "OnCalendar=daily" in timer


def test_wrapper_requires_the_lease_for_manual_runs_and_never_passes_the_secret(tmp_path):
    bash = (str(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git/bin/bash.exe")
            if os.name == "nt" else shutil.which("bash"))
    if not bash or not Path(bash).is_file():
        pytest.skip("bash unavailable")
    home = tmp_path / "argus-v18"
    secret = home / "secrets/postgres/owner_password"
    secret.parent.mkdir(parents=True)
    secret.write_bytes(b"test-secret-never-print")
    (home / "SESSION").write_bytes(b"holder=tester session=abc\n")
    fake_docker = tmp_path / "docker.sh"
    fake_docker.write_bytes(b'#!/usr/bin/env bash\nprintf "%s\\n" "$@"\n')
    fake_docker.chmod(0o755)
    env = {**os.environ, "ARGUS_DEPLOY_HOME": home.as_posix(), "ARGUS_DOCKER": fake_docker.as_posix()}
    script = (ROOT / "ops/checkpoint-retention.sh").as_posix()

    preview = subprocess.run([bash, script, "--dry-run", "--as", "tester"], env=env,
                             capture_output=True, text=True)
    assert preview.returncode == 0, preview.stderr + preview.stdout
    assert "prune-checkpoints" in preview.stdout and "--apply" not in preview.stdout
    assert "test-secret-never-print" not in preview.stdout
    assert "--network\nargus-v18-core" in preview.stdout
    # The secret is 0400 and owned by the Postgres image's user (uid 70 on vm-095); with --cap-drop ALL only that
    # owner can read it, so the container runs as the file's owner, never as a fixed user.
    owner = subprocess.run([bash, "-c", 'stat -c %u:%g "$1"', "_", secret.as_posix()],
                           capture_output=True, text=True).stdout.strip()
    assert f"--user\n{owner}\n" in preview.stdout
    refused = subprocess.run([bash, script, "--apply", "--as", "other"], env=env,
                             capture_output=True, text=True)
    assert refused.returncode != 0 and "NOT YOUR SESSION" in refused.stdout
    scheduled = subprocess.run([bash, script, "--apply", "--scheduled"], env=env,
                               capture_output=True, text=True)
    assert scheduled.returncode == 0 and "--apply" in scheduled.stdout
