"""T-0031, phase 8: the deployment half of the standing write-gate test (ARCHITECTURE §22.2).

`python -m argus.infrastructure.gate_report` reports what a running container really loaded (policy write gate, catalogue
safety classes, whether an action gateway name resolves); `ops/write-gate-check.sh` runs it in the agent, worker and
scheduler on vm-095 and adds what only the host sees (an action container, action mounts or environment). Read-only.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops/write-gate-check.sh"
CLOSED = "gate_open=0 write_capabilities=0 action_gateway_resolves=0"


def _report(config_dir: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "ARGUS_CONFIG_DIR": str(config_dir), "PYTHONPATH": str(ROOT)}
    return subprocess.run([sys.executable, "-m", "argus.infrastructure.gate_report"], env=env, capture_output=True, text=True)


def test_gate_report_of_this_repository_is_closed():
    result = _report(ROOT / "config")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith(CLOSED + " policy=")


def test_gate_report_flags_an_open_write_gate(tmp_path):
    shutil.copytree(ROOT / "config", tmp_path / "config")
    policy = tmp_path / "config/policy.yaml"
    text = policy.read_text(encoding="utf-8").replace("open: []", "open: [{capability: container.restart}]")
    policy.write_bytes(text.encode())
    result = _report(tmp_path / "config")
    assert result.returncode != 0 and result.stdout.startswith("gate_open=1 "), result.stdout + result.stderr


# --- the shell check, against a fake docker -------------------------------------------------------------------------
def _bash() -> str | None:
    if os.name == "nt":
        path = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git/bin/bash.exe"
        return str(path) if path.is_file() else None
    return shutil.which("bash")


FAKE_DOCKER = r"""#!/usr/bin/env bash
# ps -a: container names; exec -i <c> python - (the report's source on stdin): the report; inspect: mounts or env.
case "$1" in
  ps) printf '%s\n' argus-v18-agent argus-v18-worker argus-v18-scheduler argus-v18-postgres $FAKE_EXTRA_CONTAINER ;;
  exec) [ -n "$FAKE_NO_EXEC" ] && { echo "exec called in host-only mode" >&2; exit 3; }
        c=$3; grep -q "def report" || { echo "no report source on stdin" >&2; exit 2; }
        [ "$c" = "$FAKE_MISSING" ] && { echo "Error: No such container: $c" >&2; exit 1; }
        echo "${FAKE_REPORT:-gate_open=0 write_capabilities=0 action_gateway_resolves=0 policy=abc123def456}"
        case "$FAKE_REPORT" in gate_open=0*|"") exit 0 ;; *) exit 1 ;; esac ;;
  inspect) case "$*" in
             *Mounts*) echo "/opt/argus-v18/secrets/postgres/runtime_password /run/argus-secrets/db_password"
                       [ -n "$FAKE_ACTION_MOUNT" ] && echo "/opt/argus-v18/secrets/action/token /run/argus-secrets/action_token" ;;
             *Env*) echo "ARGUS_DB_BACKEND=postgres"; [ -n "$FAKE_ACTION_ENV" ] && echo "ARGUS_ACTION_TOKEN=s3cret-value" ;;
           esac ;;
esac
exit 0
"""


@pytest.fixture()
def check(tmp_path):
    bash = _bash()
    if not bash:
        pytest.skip("bash unavailable")
    fake = tmp_path / "docker.sh"
    fake.write_bytes(FAKE_DOCKER.encode())
    fake.chmod(0o755)

    home = tmp_path / "argus-v18"
    (home / "secrets/postgres").mkdir(parents=True)
    (home / "secrets/postgres/runtime_password").write_bytes(b"x")

    def run(*args: str, **fake_env: str) -> subprocess.CompletedProcess:
        env = {**os.environ, "ARGUS_DOCKER": fake.as_posix(), "ARGUS_DEPLOY_HOME": home.as_posix(),
               **{f"FAKE_{k.upper()}": v for k, v in fake_env.items()}}
        return subprocess.run([bash, SCRIPT.as_posix(), *args], env=env, capture_output=True, text=True)
    run.home = home
    return run


def test_check_reports_closed_when_every_service_is_read_only(check):
    result = check()
    assert result.returncode == 0, result.stdout + result.stderr
    for service in ("argus-v18-agent", "argus-v18-worker", "argus-v18-scheduler"):
        assert f"{service}: gate_open=0 write_capabilities=0 action_gateway_resolves=0" in result.stdout
    assert result.stdout.strip().splitlines()[-1].startswith("WRITE GATE CLOSED:")


@pytest.mark.parametrize("fake, reason", [
    ({"extra_container": "argus-v18-action-gateway"}, "action container present: argus-v18-action-gateway"),
    ({"report": "gate_open=1 write_capabilities=0 action_gateway_resolves=0 policy=abc"}, "argus-v18-agent: gate_open=1"),
    ({"report": "gate_open=0 write_capabilities=0 action_gateway_resolves=1 policy=abc"}, "action_gateway_resolves=1"),
    ({"action_mount": "1"}, "argus-v18-worker: action mount"),
    ({"action_env": "1"}, "argus-v18-worker: action environment ARGUS_ACTION_TOKEN"),
    ({"missing": "argus-v18-scheduler"}, "argus-v18-scheduler: no report"),
])
def test_check_stops_and_names_the_reason(check, fake, reason):
    result = check(**fake)
    last = result.stdout.strip().splitlines()[-1]
    assert result.returncode != 0 and last.startswith("WRITE GATE STOP:"), result.stdout + result.stderr
    assert reason in result.stdout
    assert "s3cret-value" not in result.stdout + result.stderr                   # names only, never values


def test_check_stops_on_an_action_credential_on_disk(check):
    (check.home / "secrets/action").mkdir()
    (check.home / "secrets/action/token").write_bytes(b"s3cret-value")
    result = check()
    assert result.returncode != 0 and "action credential on disk: secrets/action" in result.stdout
    assert "s3cret-value" not in result.stdout + result.stderr


# --- host-only mode: a Host T (vm-166) runs no Argus service, but ARCHITECTURE §2 would put the action gateway there --
def test_host_only_mode_checks_the_host_without_any_service_report(check):
    result = check("--host-only", no_exec="1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "gate_open=" not in result.stdout
    assert result.stdout.strip().splitlines()[-1].startswith("WRITE GATE CLOSED: host-only")


@pytest.mark.parametrize("fake, reason", [
    ({"extra_container": "argus-v18-action-gateway"}, "action container present: argus-v18-action-gateway"),
    ({"action_mount": "1"}, "argus-v18-postgres: action mount"),           # every argus-v18 container, not only services
    ({"action_env": "1"}, "argus-v18-postgres: action environment ARGUS_ACTION_TOKEN"),
])
def test_host_only_mode_stops_and_names_the_reason(check, fake, reason):
    result = check("--host-only", no_exec="1", **fake)
    assert result.returncode != 0 and result.stdout.strip().splitlines()[-1].startswith("WRITE GATE STOP:")
    assert reason in result.stdout
    assert "s3cret-value" not in result.stdout + result.stderr
