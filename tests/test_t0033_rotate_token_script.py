"""T-0033 follow-up (review of #94): `ops/rotate-token.sh` keeps the live token's mode on a rollback, and a failed
service recreate is reported as a failure, not as "recreated".

Before: `--rollback` copied `<token>.prev` with `cp -p` and its mode (0400) onto the live file, so a token the service
read through its group became unreadable; and `docker compose ... | grep ... || true` hid a failed recreate, after
which the script still printed "recreated". The script runs against a fake /opt/argus-v18 (ARGUS_DEPLOY_HOME), a fake
`docker` (ARGUS_DOCKER) and a fixed host name (ARGUS_HOSTNAME), like tests/test_deploy.py.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "rotate-token.sh"
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(BASH is None, reason="bash not available")
POSIX_MODES = os.name != "nt"                   # NTFS has no POSIX modes: the mode check runs on Linux (CI)
OLD = "old-token-value-0123456789abcdefghijklmnopq"


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "argus"
    (h / "secrets").mkdir(parents=True)
    (h / "app" / "deploy" / "target").mkdir(parents=True)
    tok = h / "secrets" / "host_probe_token"
    tok.write_text(OLD, encoding="utf-8")
    if POSIX_MODES:
        tok.chmod(0o640)
    return h


def _docker(tmp_path, exit_code=0):
    log = tmp_path / "docker.log"
    d = tmp_path / "fake-docker"
    d.write_text(f'#!/bin/sh\necho "$@" >> "{log.as_posix()}"\n'
                 f'[ {exit_code} -eq 0 ] && echo " Container argus-v18-host-probe Recreated" || echo "Error response from daemon: boom"\n'
                 f'exit {exit_code}\n', encoding="utf-8")
    d.chmod(0o755)
    return d, log


def run(home, docker, *args):
    env = dict(os.environ, ARGUS_DEPLOY_HOME=home.as_posix(), ARGUS_DOCKER=docker.as_posix(), ARGUS_HOSTNAME="argus-vm166")
    return subprocess.run([BASH, SCRIPT.as_posix(), *args], env=env, capture_output=True, text=True)


def test_rotate_writes_a_new_token_keeps_the_old_one_and_never_prints_either(home, tmp_path):
    docker, log = _docker(tmp_path)
    r = run(home, docker, "host_probe", "--as", "alice")
    assert r.returncode == 0, r.stdout + r.stderr
    new = (home / "secrets" / "host_probe_token").read_text(encoding="utf-8")
    assert len(new) == 43 and new != OLD
    assert (home / "secrets" / "host_probe_token.prev").read_text(encoding="utf-8") == OLD
    assert new not in r.stdout + r.stderr and OLD not in r.stdout + r.stderr
    assert "TOKEN ROTATE host_probe on vm-166 by alice: argus-v18-host-probe recreated" in r.stdout
    assert "--force-recreate --no-deps argus-v18-host-probe" in log.read_text(encoding="utf-8")


def test_rollback_restores_the_old_token_with_the_live_files_mode(home, tmp_path):
    docker, _ = _docker(tmp_path)
    assert run(home, docker, "host_probe", "--as", "alice").returncode == 0
    r = run(home, docker, "host_probe", "--rollback", "--as", "alice")
    assert r.returncode == 0, r.stdout + r.stderr
    live = home / "secrets" / "host_probe_token"
    assert live.read_text(encoding="utf-8") == OLD
    if POSIX_MODES:
        assert stat.S_IMODE(live.stat().st_mode) == 0o640           # not the 0400 of `.prev`
        assert stat.S_IMODE((home / "secrets" / "host_probe_token.prev").stat().st_mode) == 0o400


def test_a_failed_recreate_is_a_failure_not_recreated(home, tmp_path):
    docker, _ = _docker(tmp_path, exit_code=1)
    r = run(home, docker, "host_probe", "--as", "alice")
    assert r.returncode != 0
    assert "recreated;" not in r.stdout and "FAILED" in r.stdout
    assert "--rollback" in r.stdout                                    # it says how to go back
    assert OLD not in r.stdout + r.stderr


def test_arguments_are_still_guarded(home, tmp_path):
    docker, log = _docker(tmp_path)
    assert run(home, docker, "bogus_probe", "--as", "alice").returncode == 2
    assert run(home, docker, "host_probe").returncode == 2
    assert not log.exists()


# --- T-0041: db_probe, whose token this host's Prometheus also sends (its scrape `credentials_file`) ----------------
def _db_home(home, with_prometheus_copy=True):
    (home / "secrets" / "db_probe_token").write_text(OLD, encoding="utf-8")
    if with_prometheus_copy:
        (home / "secrets" / "prometheus").mkdir()
        (home / "secrets" / "prometheus" / "db_probe_token").write_text(OLD, encoding="utf-8")
        if POSIX_MODES:
            (home / "secrets" / "prometheus" / "db_probe_token").chmod(0o400)
    return home


def test_db_probe_rotation_writes_the_service_and_the_prometheus_copy(home, tmp_path):
    _db_home(home)
    docker, log = _docker(tmp_path)
    r = run(home, docker, "db_probe", "--as", "alice")
    assert r.returncode == 0, r.stdout + r.stderr
    new = (home / "secrets" / "db_probe_token").read_text(encoding="utf-8")
    assert len(new) == 43 and new != OLD
    assert (home / "secrets" / "prometheus" / "db_probe_token").read_text(encoding="utf-8") == new
    assert (home / "secrets" / "db_probe_token.prev").read_text(encoding="utf-8") == OLD
    if POSIX_MODES:
        assert stat.S_IMODE((home / "secrets" / "prometheus" / "db_probe_token").stat().st_mode) == 0o400
    assert "--force-recreate --no-deps argus-v18-db-probe" in log.read_text(encoding="utf-8")
    assert "Prometheus reads it at its next scrape" in r.stdout and new not in r.stdout + r.stderr


def test_db_probe_without_the_prometheus_copy_changes_nothing(home, tmp_path):
    _db_home(home, with_prometheus_copy=False)
    docker, log = _docker(tmp_path)
    r = run(home, docker, "db_probe", "--as", "alice")
    assert r.returncode == 1 and "prometheus" in r.stdout
    assert (home / "secrets" / "db_probe_token").read_text(encoding="utf-8") == OLD and not log.exists()


def test_db_probe_rollback_restores_both_copies(home, tmp_path):
    _db_home(home)
    docker, _ = _docker(tmp_path)
    assert run(home, docker, "db_probe", "--as", "alice").returncode == 0
    r = run(home, docker, "db_probe", "--rollback", "--as", "alice")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (home / "secrets" / "db_probe_token").read_text(encoding="utf-8") == OLD
    assert (home / "secrets" / "prometheus" / "db_probe_token").read_text(encoding="utf-8") == OLD
