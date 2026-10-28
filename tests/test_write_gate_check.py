"""T-0031, phase 8: the deployment half of the standing write-gate test (ARCHITECTURE §22.2).

`python -m argus.infrastructure.gate_report` reports what a running container really loaded (policy write gate, catalogue
safety classes, whether an action gateway name resolves); `ops/write-gate-check.sh` runs it in the agent, worker and
scheduler on vm-095 and adds what only the host sees (an action container, action mounts or environment). Read-only.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops/write-gate-check.sh"
RELEASE = ROOT / "deploy/action_gateway/first-lab-release.candidate.json"
CACHE = {"capability": "container.start", "target": "vm-166/container:argus-lab-cache"}
API = {"capability": "container.start", "target": "vm-166/container:argus-lab-api"}
RELEASED_LINE = "gate_open=2 write_capabilities=0 action_gateway_resolves=0 policy=abc123def456 released_ok=1"


def _report(config_dir: Path, **extra: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "ARGUS_CONFIG_DIR": str(config_dir), "PYTHONPATH": str(ROOT), **extra}
    return subprocess.run([sys.executable, "-m", "argus.infrastructure.gate_report"], env=env, capture_output=True, text=True)


def _setup(tmp_path: Path, policy_pairs: list, release_pairs: list) -> dict:
    """A copy of the config with this write gate, and the env that points the report at this release file."""
    shutil.copytree(ROOT / "config", tmp_path / "config")
    policy = tmp_path / "config/policy.yaml"
    data = yaml.safe_load(policy.read_text(encoding="utf-8"))
    data["write_gate"]["open"] = policy_pairs
    policy.write_bytes(yaml.safe_dump(data).encode())
    release = tmp_path / "release.json"
    release.write_bytes(json.dumps({"host": "vm-166", "released": release_pairs}).encode())
    return {"ARGUS_RELEASE_FILE": str(release)}


def _released(*pairs: dict) -> list:
    return [{**p, "route": "POST /containers/x/start"} for p in pairs]


def test_gate_report_of_this_repository_holds_exactly_the_released_pairs():
    result = _report(ROOT / "config")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith("gate_open=2 write_capabilities=0 action_gateway_resolves=0 policy=")
    assert result.stdout.strip().endswith("released_ok=1")


def test_gate_report_runs_from_stdin_inside_a_container_as_the_check_pipes_it(tmp_path):
    """ops/write-gate-check.sh runs `docker exec -i ... python - <gate_report.py` with ARGUS_RELEASE_JSON: __file__ is
    "<stdin>", so a module-level path built from it must not fail (found in the X-5 window: every report was missing)."""
    env = {**os.environ, "ARGUS_CONFIG_DIR": str(ROOT / "config"), "PYTHONPATH": str(ROOT),
           "ARGUS_RELEASE_JSON": RELEASE.read_text(encoding="utf-8")}
    source = (ROOT / "argus/infrastructure/gate_report.py").read_bytes()
    # from the filesystem root, as in a container whose working directory is shallow: "<stdin>" has one parent
    result = subprocess.run([sys.executable, "-"], input=source, env=env, cwd=tmp_path.anchor, capture_output=True)
    out = result.stdout.decode()
    assert result.returncode == 0, out + result.stderr.decode()
    assert out.startswith("gate_open=1 ") and out.strip().endswith("released_ok=1")


def test_equal_sets_pass(tmp_path):
    result = _report(tmp_path / "config", **_setup(tmp_path, [CACHE], _released(CACHE)))
    assert result.returncode == 0 and result.stdout.startswith("gate_open=1 ") and "released_ok=1" in result.stdout


def test_an_empty_policy_and_an_empty_release_pass(tmp_path):
    result = _report(tmp_path / "config", **_setup(tmp_path, [], []))
    assert result.returncode == 0 and result.stdout.startswith("gate_open=0 ") and "released_ok=1" in result.stdout


def test_an_extra_pair_in_the_policy_fails(tmp_path):
    result = _report(tmp_path / "config", **_setup(tmp_path, [CACHE, API], _released(CACHE)))
    assert result.returncode != 0 and result.stdout.startswith("gate_open=2 ") and "released_ok=0" in result.stdout


def test_a_pair_only_in_the_release_file_fails(tmp_path):
    result = _report(tmp_path / "config", **_setup(tmp_path, [CACHE], _released(CACHE, API)))
    assert result.returncode != 0 and "released_ok=0" in result.stdout


def test_a_release_file_with_a_pair_the_policy_lacks_fails_even_for_an_empty_policy(tmp_path):
    result = _report(tmp_path / "config", **_setup(tmp_path, [], _released(CACHE)))
    assert result.returncode != 0 and result.stdout.startswith("gate_open=0 ") and "released_ok=0" in result.stdout


def test_a_pair_that_breaks_the_lab_rule_fails_even_when_both_files_agree(tmp_path):
    bad = {"capability": "container.start", "target": "vm-095/container:argus-lab-cache"}
    result = _report(tmp_path / "config", **_setup(tmp_path, [bad], _released(bad)))
    assert result.returncode != 0 and "released_ok=0" in result.stdout


def test_a_policy_pair_without_any_release_file_fails(tmp_path):
    _setup(tmp_path, [CACHE], [])
    result = _report(tmp_path / "config", ARGUS_RELEASE_FILE=str(tmp_path / "missing.json"))
    assert result.returncode != 0 and "released_ok=0" in result.stdout        # no release file: nothing is released


def test_an_unreadable_release_fails(tmp_path):
    _setup(tmp_path, [], [])
    result = _report(tmp_path / "config", ARGUS_RELEASE_JSON="not json")
    assert result.returncode != 0 and "released_ok=0" in result.stdout


def test_the_release_json_in_the_environment_is_used(tmp_path):
    _setup(tmp_path, [CACHE], [])
    result = _report(tmp_path / "config", ARGUS_RELEASE_JSON=json.dumps({"released": _released(CACHE)}))
    assert result.returncode == 0 and "released_ok=1" in result.stdout


# --- the shell check, against a fake docker -------------------------------------------------------------------------
def _bash() -> str | None:
    if os.name == "nt":
        path = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git/bin/bash.exe"
        return str(path) if path.is_file() else None
    return shutil.which("bash")


FAKE_DOCKER = r"""#!/usr/bin/env bash
# ps -a: container names; exec -i [-e VAR=value] <c> python - (the report's source on stdin): the report; inspect: mounts or env.
case "$1" in
  ps) [ -n "$FAKE_PS_FAIL" ] && { echo "Cannot connect to the Docker daemon" >&2; exit 1; }
      printf '%s\n' argus-v18-agent argus-v18-worker argus-v18-scheduler argus-v18-postgres $FAKE_EXTRA_CONTAINER ;;
  exec) [ -n "$FAKE_NO_EXEC" ] && { echo "exec called in host-only mode" >&2; exit 3; }
        shift; c=""; release=""
        while [ $# -gt 0 ]; do
          case "$1" in -e) shift; case "$1" in ARGUS_RELEASE_JSON=*) release="${1#ARGUS_RELEASE_JSON=}" ;; esac ;;
                       -i) ;; *) c=$1; break ;; esac
          shift
        done
        grep -q "def report" || { echo "no report source on stdin" >&2; exit 2; }
        [ "$c" = "$FAKE_MISSING" ] && { echo "Error: No such container: $c" >&2; exit 1; }
        # the default report is what the real one prints for the reviewed pair when it was handed the release JSON
        ok=0; [ -n "$release" ] && ok=1
        echo "${FAKE_REPORT:-gate_open=${FAKE_RELEASED:-2} write_capabilities=0 action_gateway_resolves=0 policy=abc123def456 released_ok=$ok}"
        exit 0 ;;
  inspect) c="${@: -1}"
           case "$*" in
             *Mounts*) echo "/opt/argus-v18/secrets/postgres/runtime_password /run/argus-secrets/db_password"
                       [ -n "$FAKE_ACTION_MOUNT" ] && echo "/opt/argus-v18/secrets/action/token /run/argus-secrets/action_token"
                       case "$c" in argus-v18-action-*) echo "/opt/argus-v18/secrets/action/action_token /run/argus-v18/action_token" ;; esac ;;
             *Env*) echo "ARGUS_DB_BACKEND=postgres"; [ -n "$FAKE_ACTION_ENV" ] && echo "ARGUS_ACTION_TOKEN=s3cret-value"
                    case "$c" in argus-v18-action-*) echo "ARGUS_ACTION_ROLE=gateway" ;; esac
                    if [ "$c" = argus-v18-worker ]; then for kv in $FAKE_WORKER_ENV; do echo "$kv"; done; fi ;;
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

    def run(*args: str, release_file: str = "", **fake_env: str) -> subprocess.CompletedProcess:
        env = {**os.environ, "ARGUS_DOCKER": fake.as_posix(), "ARGUS_DEPLOY_HOME": home.as_posix(),
               **({"ARGUS_RELEASE_FILE": release_file} if release_file else {}),
               **{f"FAKE_{k.upper()}": v for k, v in fake_env.items()}}
        return subprocess.run([bash, SCRIPT.as_posix(), *args], env=env, capture_output=True, text=True)
    run.home = home
    return run


def test_check_reports_closed_when_every_service_holds_exactly_the_released_pair(check):
    result = check()
    assert result.returncode == 0, result.stdout + result.stderr
    for service in ("argus-v18-agent", "argus-v18-worker", "argus-v18-scheduler"):
        assert f"{service}: gate_open=2 write_capabilities=0 action_gateway_resolves=0" in result.stdout
        assert result.stdout.count("released_ok=1") == 3


def test_check_accepts_an_empty_release_with_an_empty_gate(check, tmp_path):
    empty = tmp_path / "empty-release.json"
    empty.write_bytes(b'{"host": "vm-166", "released": []}')
    result = check(report="gate_open=0 write_capabilities=0 action_gateway_resolves=0 policy=abc released_ok=1",
                   release_file=empty.as_posix())
    assert result.returncode == 0, result.stdout + result.stderr


def test_check_stops_when_the_gate_holds_a_pair_the_release_lacks(check, tmp_path):
    empty = tmp_path / "empty-release.json"
    empty.write_bytes(b'{"host": "vm-166", "released": []}')
    result = check(report="gate_open=1 write_capabilities=0 action_gateway_resolves=0 policy=abc released_ok=0",
                   release_file=empty.as_posix())
    assert result.returncode != 0 and "argus-v18-agent: gate_open=1" in result.stdout


def test_check_stops_on_a_count_that_is_not_the_released_count(check):
    result = check(released="1")                  # one pair in the gate, two in the release file
    assert result.returncode != 0 and result.stdout.strip().splitlines()[-1].startswith("WRITE GATE STOP:")


@pytest.mark.parametrize("fake, reason", [
    ({"extra_container": "argus-v18-action-gateway"}, "action container present: argus-v18-action-gateway"),
    ({"report": "gate_open=1 write_capabilities=0 action_gateway_resolves=0 policy=abc released_ok=0"}, "argus-v18-agent: gate_open=1"),
    ({"report": "gate_open=1 write_capabilities=0 action_gateway_resolves=0 policy=abc"}, "argus-v18-agent: gate_open=1"),
    ({"report": "gate_open=0 write_capabilities=0 action_gateway_resolves=1 policy=abc released_ok=0"}, "action_gateway_resolves=1"),
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
def test_host_only_mode_checks_the_host_without_any_service_report(check, tmp_path):
    result = check("--host-only", no_exec="1")                 # this repository releases two pairs
    assert result.returncode == 0, result.stdout + result.stderr
    assert "gate_open=" not in result.stdout
    assert result.stdout.strip().splitlines()[-1].startswith("WRITE GATE AS RELEASED: 2 reviewed pair(s); host-only")
    empty = tmp_path / "empty-release.json"
    empty.write_bytes(b'{"host": "vm-166", "released": []}')
    result = check("--host-only", no_exec="1", release_file=empty.as_posix())
    assert result.returncode == 0 and result.stdout.strip().splitlines()[-1].startswith("WRITE GATE CLOSED: host-only")


@pytest.mark.parametrize("fake, reason", [
    ({"extra_container": "argus-v18-action-shell"}, "action container present: argus-v18-action-shell"),   # not reviewed
    ({"action_mount": "1"}, "argus-v18-postgres: action mount"),           # every argus-v18 container, not only services
    ({"action_env": "1"}, "argus-v18-postgres: action environment ARGUS_ACTION_TOKEN"),
    ({"ps_fail": "1"}, "docker ps failed: containers not checked"),   # never CLOSED on what was not looked at
])
def test_host_only_mode_stops_and_names_the_reason(check, fake, reason):
    result = check("--host-only", no_exec="1", **fake)
    assert result.returncode != 0 and result.stdout.strip().splitlines()[-1].startswith("WRITE GATE STOP:")
    assert reason in result.stdout
    assert "s3cret-value" not in result.stdout + result.stderr


# --- once a pair is released: exactly the reviewed parts, nothing else (phase 20, X-5) ----------------------------------
GATEWAY = "argus-v18-action-proxy argus-v18-action-gateway"
WORKER_SETTINGS = ("ARGUS_ACTION_PATH=1 ARGUS_ACTION_GATEWAY_URL=http://argus-v18-action-gateway:18705 "
                   "ARGUS_ACTION_TOKEN_FILE=/run/argus-secrets/action_token ARGUS_ACTION_DAILY_HOST_CAP=2")


def _token(check, path: str) -> None:
    target = check.home / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"s3cret-value")


def test_the_action_host_accepts_exactly_the_released_gateway_its_mounts_role_and_token(check):
    _token(check, "secrets/action/action_token")
    result = check("--host-only", no_exec="1", extra_container=GATEWAY)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip().splitlines()[-1].startswith("WRITE GATE AS RELEASED: 2 reviewed pair(s); host-only")
    assert "s3cret-value" not in result.stdout + result.stderr


def test_with_nothing_released_the_gateway_is_refused_as_before(check, tmp_path):
    empty = tmp_path / "empty-release.json"
    empty.write_bytes(b'{"host": "vm-166", "released": []}')
    _token(check, "secrets/action/action_token")
    result = check("--host-only", no_exec="1", extra_container=GATEWAY, release_file=empty.as_posix())
    last = result.stdout.strip().splitlines()[-1]
    assert result.returncode != 0 and last.startswith("WRITE GATE STOP:")
    assert "action container present: argus-v18-action-proxy argus-v18-action-gateway" in result.stdout
    assert "argus-v18-action-gateway: action mount" in result.stdout
    assert "action credential on disk: secrets/action secrets/action/action_token" in result.stdout


def test_vm095_accepts_the_workers_settings_and_its_token_once_released(check):
    _token(check, "secrets/agent/action_token")
    result = check(worker_env=WORKER_SETTINGS)
    assert result.returncode == 0, result.stdout + result.stderr
    last = result.stdout.strip().splitlines()[-1]
    assert last.startswith("WRITE GATE AS RELEASED: 2 reviewed pair(s); argus-v18-agent,argus-v18-worker,argus-v18-scheduler")


@pytest.mark.parametrize("why, fake, token, reason", [
    ("a gateway on the agent host", {"extra_container": "argus-v18-action-gateway"}, None,
     "action container present: argus-v18-action-gateway"),
    ("a variable that was not reviewed", {"worker_env": WORKER_SETTINGS + " ARGUS_ACTION_SECRET=s3cret-value"}, None,
     "argus-v18-worker: action environment ARGUS_ACTION_SECRET"),
    ("the worker's settings on another service", {"action_env": "1"}, None,
     "argus-v18-agent: action environment ARGUS_ACTION_TOKEN"),
    ("the gateway's token on the agent host", {}, "secrets/action/action_token", "action credential on disk: secrets/action"),
])
def test_vm095_still_refuses_anything_but_the_reviewed_parts(check, why, fake, token, reason):
    if token:
        _token(check, token)
    result = check(**fake)
    assert result.returncode != 0 and result.stdout.strip().splitlines()[-1].startswith("WRITE GATE STOP:"), why
    assert reason in result.stdout, why
    assert "s3cret-value" not in result.stdout + result.stderr


def test_the_action_host_refuses_another_action_file_or_a_role_on_another_container(check):
    _token(check, "secrets/action/action_token")
    _token(check, "secrets/action/action_token.old")          # the check is by name: *action*
    result = check("--host-only", no_exec="1", extra_container=GATEWAY + " argus-v18-action-shell")
    assert result.returncode != 0
    assert "action credential on disk: secrets/action/action_token.old" in result.stdout
    assert "action container present: argus-v18-action-shell" in result.stdout

