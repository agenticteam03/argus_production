import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy" / "lab" / "demo" / "s4-inject.sh"


def _bash():
    for candidate in (shutil.which("bash"), r"C:\Program Files\Git\bin\bash.exe"):
        if candidate and Path(candidate).exists():
            result = subprocess.run([candidate, "-c", "exit 0"], capture_output=True, check=False, timeout=5)
            if result.returncode == 0:
                return candidate
    pytest.skip("a working POSIX shell is required")


def _run(tmp_path, args, hostname="argus-vm166", docker_status=0):
    shims = ('hostname() { printf "%s\n" "$S4_TEST_HOST"; }; '
             'docker() { printf "%s\n" "$*" >> docker.calls; return "$S4_DOCKER_STATUS"; }; '
             'source "$1" "${@:2}"')
    env = {**os.environ, "S4_TEST_HOST": hostname, "S4_DOCKER_STATUS": str(docker_status)}
    return subprocess.run([_bash(), "-c", shims, "s4-test", str(SCRIPT), *args], cwd=tmp_path, env=env,
                          capture_output=True, text=True, check=False, timeout=10)


def _calls(tmp_path):
    path = tmp_path / "docker.calls"
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def test_script_has_valid_posix_shell_syntax():
    result = subprocess.run([_bash(), "-n", str(SCRIPT)], capture_output=True, text=True, check=False, timeout=5)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("action,endpoint", [("freeze", "/fault/freeze"), ("unfreeze", "/fault/unfreeze")])
def test_the_worker_is_frozen_through_its_http_fault_endpoint_not_a_file(tmp_path, action, endpoint):
    result = _run(tmp_path, [action])

    assert result.returncode == 0, result.stderr
    calls = _calls(tmp_path)
    assert len(calls) == 1 and calls[0].startswith("exec argus-lab-jobworker ")
    assert endpoint in calls[0]
    assert "touch" not in calls[0] and "/tmp/freeze" not in calls[0]


def test_unfreeze_is_repeatable_and_tolerates_a_worker_that_is_already_unfrozen(tmp_path):
    for _ in range(2):
        assert _run(tmp_path, ["unfreeze"]).returncode == 0
    assert len(_calls(tmp_path)) == 2
    assert all("/fault/unfreeze" in call for call in _calls(tmp_path))


def test_freeze_reports_a_refusal_instead_of_pretending_it_worked(tmp_path):
    result = _run(tmp_path, ["freeze"], docker_status=1)

    assert result.returncode != 0
    assert "FAULT_ENABLE" in result.stderr


def test_usage_line_and_exit_code_are_kept(tmp_path):
    for args in ([], ["thaw"]):
        result = _run(tmp_path, args)
        assert result.returncode == 2
        assert "freeze|unfreeze" in result.stderr
    assert not _calls(tmp_path)


@pytest.mark.parametrize("hostname", ["vm-095", "argus-vm095"])
def test_the_script_refuses_vm095_without_calling_docker(tmp_path, hostname):
    result = _run(tmp_path, ["freeze"], hostname=hostname)

    assert result.returncode == 1
    assert not _calls(tmp_path)
