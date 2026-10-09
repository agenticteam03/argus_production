"""ops/db-backup.sh (T-0017, OP-008): restorable snapshot backups and bounded retention.

`backup` fingerprints and dumps one read-only PostgreSQL snapshot. `verify` restores into a throwaway, network-less,
tmpfs-backed `argus-lab-pgrestore`; `prune` previews old backup sets unless `--apply` is explicit. Offline tests use
a fake `docker` (ARGUS_DOCKER), and the last two tests use real Docker only with ARGUS_TEST_DOCKER=1.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "db-backup.sh"


def _bash() -> str | None:
    if os.name == "nt":                       # never WSL's bash.exe: use Git for Windows' bash
        git_bash = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "bash.exe"
        return str(git_bash) if git_bash.is_file() else None
    return shutil.which("bash")


BASH = _bash()
pytestmark = pytest.mark.skipif(BASH is None, reason="bash not available")

# A stand-in for docker. It logs calls, answers the table list and each fingerprint query from fixture files,
# "dumps" fixed text and accepts a restore.
FAKE_DOCKER = r'''#!/usr/bin/env bash
echo "$*" >> "$FAKE_DIR/calls.log"
answer_sql() {
  case "$1" in
    *pg_export_snapshot*) echo '00000003-0000001B-1' ;;
    *pg_tables*) cat "$FAKE_DIR/$c.tables" ;;
    *__ARGUS_TABLES_DONE__*) echo '__ARGUS_TABLES_DONE__' ;;
    *md5*)
      case "$1" in
        *'public."audit"'*) sed -n '1p' "$FAKE_DIR/$c.fp.1" ;;
        *'public."evidence"'*) sed -n '2p' "$FAKE_DIR/$c.fp.1" ;;
        *'public."incident"'*) sed -n '3p' "$FAKE_DIR/$c.fp.1" ;;
      esac ;;
    *) : ;;
  esac
}
cmd=$1; shift
case "$cmd" in
  exec)
    while [ "${1#-}" != "$1" ]; do case "$1" in -e) shift 2 ;; *) shift ;; esac; done
    c=$1; shift
    case "$1" in
      pg_dump) printf 'PGDMP fake dump of %s\n' "$c" ;;
      pg_restore) cat > "$FAKE_DIR/restored.bin" ;;
      pg_isready) exit 0 ;;
      psql)
        if [[ " $* " == *" -c "* ]]; then
          answer_sql "$*"
        else
          while IFS= read -r sql; do answer_sql "$sql"; done
        fi ;;
    esac ;;
  logs) echo "PostgreSQL init process complete; ready for start up." ;;
  run) echo "fakecontainerid" ;;
  rm|inspect) : ;;
esac
'''

LIVE, RESTORE = "argus-v18-postgres", "argus-lab-pgrestore"
FP = "audit 3 aaa\nevidence 2 bbb\nincident 1 ccc\n"


@pytest.fixture()
def env(tmp_path):
    fake = tmp_path / "fake"
    fake.mkdir()
    (fake / "docker.sh").write_bytes(FAKE_DOCKER.encode())
    for c in (LIVE, RESTORE):
        (fake / f"{c}.tables").write_bytes(b"audit\nevidence\nincident\n")
        (fake / f"{c}.fp.1").write_bytes(FP.encode())
    home = tmp_path / "opt"
    home.mkdir()
    (home / "SESSION").write_bytes(b"holder=alice session=abc\n")
    return {"fake": fake, "home": home}


def run(env, *args: str, who: str = "alice") -> subprocess.CompletedProcess:
    e = dict(os.environ, ARGUS_DEPLOY_HOME=env["home"].as_posix(), FAKE_DIR=env["fake"].as_posix(),
             ARGUS_DOCKER=f"bash {(env['fake'] / 'docker.sh').as_posix()}")
    return subprocess.run([BASH, SCRIPT.as_posix(), *args, "--as", who], env=e, capture_output=True, text=True)


def calls(env) -> str:
    log = env["fake"] / "calls.log"
    return log.read_text(encoding="utf-8") if log.exists() else ""


def dumps(env) -> list[Path]:
    return sorted((env["home"] / "backups").glob("argus-*.dump")) if (env["home"] / "backups").exists() else []


def test_backup_refuses_when_the_session_is_not_yours(env):
    r = run(env, "backup", who="bob")
    assert r.returncode != 0
    assert "NOT YOUR SESSION" in r.stdout + r.stderr
    assert dumps(env) == [] and "pg_dump" not in calls(env)


def test_backup_writes_the_dump_its_checksum_and_its_fingerprint(env):
    r = run(env, "backup")
    assert r.returncode == 0, r.stdout + r.stderr
    [dump] = dumps(env)
    assert "BACKUP OK" in r.stdout and dump.name in r.stdout
    assert dump.read_bytes().startswith(b"PGDMP")
    assert dump.with_name(dump.name + ".sha256").read_text(encoding="utf-8").split()[0]
    assert dump.with_suffix(".fingerprint").read_text(encoding="utf-8") == FP
    assert not list((env["home"] / "backups").glob("*.part"))
    assert f"exec {LIVE} pg_dump" in calls(env) or f"{LIVE} pg_dump" in calls(env)
    if os.name != "nt":                           # POSIX modes: only root may read a dump (it holds password hashes)
        assert (env["home"] / "backups").stat().st_mode & 0o077 == 0
        assert dump.stat().st_mode & 0o077 == 0


def test_backup_uses_one_snapshot_even_if_database_changes(env):
    (env["fake"] / f"{LIVE}.fp.2").write_bytes(b"audit 4 zzz\nevidence 2 bbb\nincident 1 ccc\n")
    r = run(env, "backup")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "BACKUP OK" in r.stdout
    assert "--snapshot=" in calls(env)
    assert len(dumps(env)) == 1


def backup_ok(env) -> Path:
    r = run(env, "backup")
    assert r.returncode == 0, r.stdout + r.stderr
    (env["fake"] / "calls.log").unlink()
    return dumps(env)[-1]                             # names carry the UTC time: the last one is the newest


def test_verify_restores_into_an_isolated_throwaway_container_and_reports_ok(env):
    dump = backup_ok(env)
    r = run(env, "verify", dump.as_posix())
    assert r.returncode == 0, r.stdout + r.stderr
    assert "VERIFY OK: 3 tables, 6 rows match" in r.stdout
    log = calls(env)
    started = next(line for line in log.splitlines() if line.startswith("run "))
    assert f"--name {RESTORE}" in started and "--network none" in started and "--tmpfs" in started
    assert "-p " not in started and "--publish" not in started and "-v " not in started
    assert (env["fake"] / "restored.bin").read_bytes() == dump.read_bytes()
    assert log.splitlines()[-1].startswith(f"rm -f {RESTORE}")          # always removed at the end
    assert LIVE not in log                                            # verify never touches the live database


def test_verify_latest_picks_the_newest_dump_itself(env):
    # Step T-0017.3 on vm-095: `sudo ls backups/argus-*.dump` found nothing because the operator's own shell expands
    # the glob before sudo, and the folder is root-only (700). The script, running as root, must find the dump.
    first = backup_ok(env)
    old = first.with_name("argus-20000101T000000Z.dump")              # make the first dump an old one
    sha = first.with_name(first.name + ".sha256").read_text(encoding="utf-8").replace(first.name, old.name)
    first.rename(old)
    first.with_name(first.name + ".sha256").unlink()
    old.with_name(old.name + ".sha256").write_text(sha, encoding="utf-8")
    first.with_suffix(".fingerprint").rename(old.with_suffix(".fingerprint"))
    newest = backup_ok(env)
    r = run(env, "verify", "latest")
    assert r.returncode == 0, r.stdout + r.stderr
    assert newest.name in r.stdout and old.name not in r.stdout
    assert "VERIFY OK" in r.stdout


def test_verify_latest_without_any_dump_says_so(env):
    r = run(env, "verify", "latest")
    assert r.returncode != 0
    assert "VERIFY STOP" in r.stdout and "no dump" in r.stdout


def test_verify_reports_a_mismatch_and_still_removes_the_container(env):
    dump = backup_ok(env)
    (env["fake"] / f"{RESTORE}.fp.1").write_bytes(b"audit 3 aaa\nevidence 1 bbb\nincident 1 ccc\n")
    r = run(env, "verify", dump.as_posix())
    assert r.returncode != 0
    assert "VERIFY MISMATCH" in r.stdout and "evidence" in r.stdout
    assert calls(env).splitlines()[-1].startswith(f"rm -f {RESTORE}")


def test_verify_refuses_a_dump_whose_checksum_does_not_match(env):
    dump = backup_ok(env)
    dump.write_bytes(b"PGDMP tampered\n")
    r = run(env, "verify", dump.as_posix())
    assert r.returncode != 0
    assert "VERIFY STOP" in r.stdout and "checksum" in r.stdout
    assert "run " not in calls(env)                                    # no container started


def test_verify_marks_only_a_successfully_restored_dump(env):
    dump = backup_ok(env)
    marker = dump.with_suffix(".verified")
    assert not marker.exists()
    ok = run(env, "verify", dump.as_posix())
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert marker.is_file()

    marker.unlink()
    (env["fake"] / f"{RESTORE}.fp.1").write_bytes(b"audit 4 changed\n")
    failed = run(env, "verify", dump.as_posix())
    assert failed.returncode != 0 and "VERIFY MISMATCH" in failed.stdout
    assert not marker.exists()


def test_prune_previews_then_removes_complete_old_backup_sets(env, monkeypatch):
    monkeypatch.setenv("ARGUS_BACKUP_KEEP", "2")
    folder = env["home"] / "backups"
    folder.mkdir()
    names = [f"argus-2026100{day}T000000Z" for day in range(1, 5)]
    for name in names:
        for suffix in (".dump", ".dump.sha256", ".fingerprint"):
            (folder / f"{name}{suffix}").write_bytes(b"test\n")
    (folder / f"{names[0]}.verified").write_bytes(b"verified\n")
    (folder / f"{names[1]}.verified").write_bytes(b"verified\n")

    preview = run(env, "prune")
    assert preview.returncode == 0, preview.stdout + preview.stderr
    assert "PRUNE DRY RUN" in preview.stdout and names[0] in preview.stdout
    assert all((folder / f"{name}.dump").exists() for name in names)
    assert calls(env) == ""                   # pruning is a local file operation

    applied = run(env, "prune", "--apply")
    assert applied.returncode == 0, applied.stdout + applied.stderr
    assert "PRUNE OK" in applied.stdout
    for name in (names[1], names[2], names[3]):
        assert (folder / f"{name}.dump").exists()
    for suffix in (".dump", ".dump.sha256", ".fingerprint", ".verified"):
        assert not (folder / f"{names[0]}{suffix}").exists()


def test_prune_preserves_the_only_verified_backup_even_beyond_keep(env, monkeypatch):
    monkeypatch.setenv("ARGUS_BACKUP_KEEP", "2")
    folder = env["home"] / "backups"
    folder.mkdir()
    names = [f"argus-2026100{day}T000000Z" for day in range(1, 5)]
    for name in names:
        (folder / f"{name}.dump").write_bytes(b"test\n")
    (folder / f"{names[0]}.verified").write_bytes(b"verified\n")
    applied = run(env, "prune", "--apply")
    assert applied.returncode == 0, applied.stdout + applied.stderr
    assert (folder / f"{names[0]}.dump").exists()
    assert not (folder / f"{names[1]}.dump").exists()


def test_prune_apply_refuses_a_different_lease_holder(env):
    folder = env["home"] / "backups"
    folder.mkdir()
    dump = folder / "argus-20261001T000000Z.dump"
    dump.write_bytes(b"test\n")
    refused = run(env, "prune", "--apply", who="bob")
    assert refused.returncode != 0 and "NOT YOUR SESSION" in refused.stdout
    assert dump.is_file()


def test_prune_apply_rejects_an_invalid_keep_count(env, monkeypatch):
    monkeypatch.setenv("ARGUS_BACKUP_KEEP", "0")
    folder = env["home"] / "backups"
    folder.mkdir()
    dump = folder / "argus-20261001T000000Z.dump"
    dump.write_bytes(b"test\n")
    refused = run(env, "prune", "--apply")
    assert refused.returncode != 0 and "positive integer" in refused.stdout
    assert dump.is_file()


# --- real Docker (laptop with Docker Desktop): ARGUS_TEST_DOCKER=1 -----------------------------------------------

@pytest.mark.skipif(os.getenv("ARGUS_TEST_DOCKER") != "1", reason="ARGUS_TEST_DOCKER=1 not set (needs Docker)")
def test_real_backup_and_verify_against_a_throwaway_postgres(tmp_path):
    src = f"argus-pgtest-src-{uuid.uuid4().hex[:8]}"
    restore = f"argus-pgtest-restore-{uuid.uuid4().hex[:8]}"
    home = tmp_path / "opt"
    home.mkdir()
    (home / "SESSION").write_bytes(b"holder=alice session=abc\n")
    e = dict(os.environ, ARGUS_DEPLOY_HOME=home.as_posix(), ARGUS_PG_CONTAINER=src, ARGUS_RESTORE_CONTAINER=restore)
    sql = ((ROOT / "deploy" / "migrations" / "001_init.sql").read_text(encoding="utf-8")
           + (ROOT / "deploy" / "migrations" / "002_checkpoints.sql").read_text(encoding="utf-8")
           + "INSERT INTO principal (id, kind, role, scopes, password_hash) VALUES ('t', 'user', 'operator', '[]', 'x');\n")
    subprocess.run(["docker", "run", "-d", "--rm", "--name", src, "--network", "none", "-e", "POSTGRES_USER=argus_owner",
                    "-e", "POSTGRES_DB=argus", "-e", "POSTGRES_HOST_AUTH_METHOD=trust", "postgres:16-alpine"],
                   check=True, capture_output=True)
    try:
        for _ in range(60):
            logs = subprocess.run(["docker", "logs", src], capture_output=True, text=True)
            if "init process complete" in logs.stdout + logs.stderr and subprocess.run(
                    ["docker", "exec", src, "pg_isready", "-U", "argus_owner", "-d", "argus"],
                    capture_output=True).returncode == 0:
                break
            subprocess.run(["docker", "exec", src, "sleep", "1"], capture_output=True)
        subprocess.run(["docker", "exec", "-i", src, "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-U", "argus_owner",
                        "-d", "argus"], input=sql, text=True, check=True, capture_output=True)
        b = subprocess.run([BASH, SCRIPT.as_posix(), "backup", "--as", "alice"], env=e, capture_output=True, text=True)
        assert b.returncode == 0, b.stdout + b.stderr
        dump = sorted((home / "backups").glob("argus-*.dump"))[0]
        v = subprocess.run([BASH, SCRIPT.as_posix(), "verify", dump.as_posix(), "--as", "alice"], env=e,
                           capture_output=True, text=True)
        assert v.returncode == 0, v.stdout + v.stderr
        assert "VERIFY OK" in v.stdout
        gone = subprocess.run(["docker", "ps", "-a", "-q", "--filter", f"name=^{restore}$"], capture_output=True, text=True)
        assert gone.stdout.strip() == ""
    finally:
        subprocess.run(["docker", "rm", "-f", src, restore], capture_output=True)


@pytest.mark.skipif(os.getenv("ARGUS_TEST_DOCKER") != "1", reason="ARGUS_TEST_DOCKER=1 not set (needs Docker)")
def test_real_snapshot_stays_consistent_when_the_live_database_writes_during_dump(tmp_path):
    src = f"argus-pgtest-src-{uuid.uuid4().hex[:8]}"
    restore = f"argus-pgtest-restore-{uuid.uuid4().hex[:8]}"
    home = tmp_path / "opt"
    home.mkdir()
    (home / "SESSION").write_bytes(b"holder=alice session=abc\n")
    shim = tmp_path / "docker-write-during-dump.sh"
    shim.write_bytes(b'''#!/usr/bin/env bash
set -euo pipefail
if [[ " $* " == *" pg_dump "* ]]; then
  docker exec "$ARGUS_PG_CONTAINER" psql -X -q -v ON_ERROR_STOP=1 -U argus_owner -d argus -c \
    "INSERT INTO principal (id,kind,role,scopes,password_hash) VALUES ('during','user','operator','[]','x')"
fi
exec docker "$@"
''')
    e = dict(os.environ, ARGUS_DEPLOY_HOME=home.as_posix(), ARGUS_PG_CONTAINER=src,
             ARGUS_RESTORE_CONTAINER=restore, ARGUS_DOCKER=f"bash {shim.as_posix()}")
    sql = ((ROOT / "deploy/migrations/001_init.sql").read_text(encoding="utf-8")
           + (ROOT / "deploy/migrations/002_checkpoints.sql").read_text(encoding="utf-8")
           + "INSERT INTO principal (id,kind,role,scopes,password_hash) VALUES ('before','user','operator','[]','x');\n")
    subprocess.run(["docker", "run", "-d", "--rm", "--name", src, "--network", "none", "-e",
                    "POSTGRES_USER=argus_owner", "-e", "POSTGRES_DB=argus", "-e",
                    "POSTGRES_HOST_AUTH_METHOD=trust", "postgres:16-alpine"], check=True, capture_output=True)
    try:
        for _ in range(60):
            logs = subprocess.run(["docker", "logs", src], capture_output=True, text=True)
            if "init process complete" in logs.stdout + logs.stderr and subprocess.run(
                    ["docker", "exec", src, "pg_isready", "-U", "argus_owner", "-d", "argus"],
                    capture_output=True).returncode == 0:
                break
            subprocess.run(["docker", "exec", src, "sleep", "1"], capture_output=True)
        subprocess.run(["docker", "exec", "-i", src, "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-U", "argus_owner",
                        "-d", "argus"], input=sql, text=True, check=True, capture_output=True)
        b = subprocess.run([BASH, SCRIPT.as_posix(), "backup", "--as", "alice"], env=e, capture_output=True, text=True)
        assert b.returncode == 0, b.stdout + b.stderr
        live = subprocess.run(["docker", "exec", src, "psql", "-X", "-At", "-U", "argus_owner", "-d", "argus",
                               "-c", "SELECT count(*) FROM principal"], capture_output=True, text=True, check=True)
        assert live.stdout.strip() == "2"               # the writer ran after the snapshot was exported
        dump = sorted((home / "backups").glob("argus-*.dump"))[0]
        v = subprocess.run([BASH, SCRIPT.as_posix(), "verify", dump.as_posix(), "--as", "alice"], env=e,
                           capture_output=True, text=True)
        assert v.returncode == 0, v.stdout + v.stderr
        assert "VERIFY OK" in v.stdout
    finally:
        subprocess.run(["docker", "rm", "-f", src, restore], capture_output=True)
