"""ops/db-backup.sh (T-0017): a Postgres backup that is proved restorable, without touching the live database.

`backup` dumps argus-v18-postgres (read-only toward it) and stores a per-table fingerprint taken in the same quiet
window; `verify` restores the dump into a throwaway, network-less, tmpfs-backed `argus-lab-pgrestore` and compares
the fingerprints. The offline tests drive the script with a fake `docker` (ARGUS_DOCKER); the last test uses the real
Docker and runs only with ARGUS_TEST_DOCKER=1.
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

# A stand-in for docker. It logs every call, answers the table list from <container>.tables and each fingerprint
# query from the next <container>.fp.<n> file (the last one repeats), "dumps" a fixed text and accepts a restore.
FAKE_DOCKER = r'''#!/usr/bin/env bash
echo "$*" >> "$FAKE_DIR/calls.log"
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
        sql="$*"; [ -t 0 ] || sql="$sql $(cat)"
        case "$sql" in
          *pg_tables*) cat "$FAKE_DIR/$c.tables" ;;
          *md5*)
            n=$(cat "$FAKE_DIR/$c.n" 2>/dev/null || echo 0); n=$((n + 1))
            [ -f "$FAKE_DIR/$c.fp.$n" ] && echo "$n" > "$FAKE_DIR/$c.n" || n=$((n - 1))
            cat "$FAKE_DIR/$c.fp.$n" ;;
          *) : ;;
        esac ;;
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


def test_backup_stops_when_the_database_changed_during_the_dump(env):
    (env["fake"] / f"{LIVE}.fp.2").write_bytes(b"audit 4 zzz\nevidence 2 bbb\nincident 1 ccc\n")
    r = run(env, "backup")
    assert r.returncode != 0
    assert "BACKUP STOP" in r.stdout and "changed during the dump" in r.stdout
    assert dumps(env) == [] and not list((env["home"] / "backups").glob("*.part"))


def backup_ok(env) -> Path:
    r = run(env, "backup")
    assert r.returncode == 0, r.stdout + r.stderr
    (env["fake"] / "calls.log").unlink()
    return dumps(env)[0]


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
