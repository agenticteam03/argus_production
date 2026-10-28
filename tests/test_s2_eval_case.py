"""TASK-60 (scenario 2): the `link_ok` verify signal, the injection scripts and the dep-api-moved-network case."""
from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from argus.application.link_state import link_ok, link_ok_actual
from test_core import ROOT as _ROOT

ROOT = Path(_ROOT)
API = "vm-166/container:argus-lab-api"
CACHE = "vm-166/container:argus-lab-cache"
AT = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)


class _Store:
    def __init__(self, cursors):
        self.cursors = cursors

    def link_probe_cursors(self, owner):
        return self.cursors.get(owner, {})


def _store(state, dependency=CACHE):
    return _Store({API: {dependency: {"state": state, "at": AT}}})


# ---- link_ok -------------------------------------------------------------------------------------------------

def test_link_ok_is_true_for_an_ok_link():
    assert link_ok(_store("ok"), API, CACHE) is True
    assert link_ok_actual(_store("ok"), API, CACHE) == "1"


@pytest.mark.parametrize("state", ["broken", "unknown", "slow"])
def test_link_ok_is_false_unless_the_state_is_ok(state):
    assert link_ok(_store(state), API, CACHE) is False
    assert link_ok_actual(_store(state), API, CACHE) == "0"


def test_link_ok_is_false_without_a_recorded_edge():
    assert link_ok(_Store({}), API, CACHE) is False
    assert link_ok(_store("ok", dependency="vm-166/container:other"), API, CACHE) is False


def test_link_ok_actual_matches_the_card_check():
    from argus.actions.cards import load_action_cards
    from argus.actions.execution import _holds

    (check,) = [c for c in load_action_cards(ROOT / "config/actions")["network.restore"].verify_checks()]
    assert check["signal"] == "link_ok"
    assert _holds(link_ok_actual(_store("ok"), API, CACHE), check["op"], check["expected"])
    assert not _holds(link_ok_actual(_store("broken"), API, CACHE), check["op"], check["expected"])


# ---- the scripts ---------------------------------------------------------------------------------------------

INJECT = ROOT / "deploy/lab/demo/s2-inject.sh"
RESET = ROOT / "deploy/lab/demo/s2-reset.sh"


@pytest.mark.parametrize("script", [INJECT, RESET])
def test_scripts_are_valid_bash_with_lf_endings(script):
    assert script.is_file() and b"\r" not in script.read_bytes()
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not available")
    assert subprocess.run([bash, "-n", str(script)], capture_output=True).returncode == 0


def test_inject_moves_the_api_from_the_app_network_to_the_iso_network():
    text = INJECT.read_text(encoding="utf-8")
    assert text.index("docker network disconnect argus-lab-app argus-lab-api") < text.index(
        "docker network connect argus-lab-iso argus-lab-api")
    assert "docker network create" in text and "172.30.3.0/24" in text


def test_reset_is_the_reverse():
    text = RESET.read_text(encoding="utf-8")
    assert text.index("docker network connect argus-lab-app argus-lab-api") < text.index(
        "docker network disconnect argus-lab-iso argus-lab-api")


@pytest.mark.parametrize("script", [INJECT, RESET])
def test_scripts_use_lab_names_only(script):
    text = script.read_text(encoding="utf-8")
    assert "/opt/argus" not in text.replace("/opt/argus-lab", "")
    for forbidden in ("wg0", "labmvp", "reboot", "docker rm", "docker stop"):
        assert forbidden not in text


_LAST: dict = {}


def _run(script, tmp_path, host, override=None, networks=""):
    """Run a script with `hostname` and `docker` replaced by shell functions; returns (exit code, docker calls)."""
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not available")
    log = tmp_path / "docker.log"
    log.write_text("", encoding="utf-8", newline="")
    # shell functions win over any PATH lookup (Git's bash launcher reorders an inherited PATH), so a test can
    # never reach the real docker: the script is sourced after both shims are defined
    shims = ('hostname() { echo "$FAKE_HOST"; }; '
             'docker() { if [ "$1" = inspect ]; then echo "$FAKE_NETWORKS"; else echo "$@" >> "$DOCKER_LOG"; fi; }; '
             '. "$SCRIPT"')
    env = {**os.environ, "FAKE_HOST": host, "DOCKER_LOG": log.as_posix(), "FAKE_NETWORKS": networks, "SCRIPT": script.as_posix()}
    env.pop("ARGUS_HOSTNAME", None)
    if override:
        env["ARGUS_HOSTNAME"] = override
    done = subprocess.run([bash, "-c", shims], capture_output=True, env=env)
    _LAST["out"] = done.stdout.decode("utf-8", "replace")
    return done.returncode, log.read_text(encoding="utf-8").splitlines()


def _run_full(script, tmp_path, networks):
    """(exit code, stdout, docker calls) for a run as argus-vm166 with the api on `networks`."""
    code, calls = _run(script, tmp_path, "argus-vm166", networks=networks)
    return code, _LAST["out"], calls


@pytest.mark.parametrize("script", [INJECT, RESET])
def test_the_real_vm095_name_is_refused(script, tmp_path):
    code, calls = _run(script, tmp_path, "argus-vm095")
    assert code == 2 and calls == []


@pytest.mark.parametrize("script", [INJECT, RESET])
@pytest.mark.parametrize("host", ["vm-095", "vm-166", "laptop", "argus-vm1660"])
def test_any_other_host_is_refused(script, tmp_path, host):
    code, calls = _run(script, tmp_path, host)
    assert code == 2 and calls == []


@pytest.mark.parametrize("script", [INJECT, RESET])
def test_the_real_vm166_name_is_accepted(script, tmp_path):
    code, calls = _run(script, tmp_path, "argus-vm166", networks="argus-lab-app" if script == INJECT else "argus-lab-iso")
    assert code == 0
    assert any(c.startswith("network connect") for c in calls) and any(c.startswith("network disconnect") for c in calls)


def test_reset_after_argus_restored_the_network_skips_both_steps(tmp_path):
    # scenario 2 succeeded: the api is already on its own network and off the isolated one
    done = _run_full(RESET, tmp_path, networks="argus-lab-app")
    assert done[0] == 0 and done[2] == []
    assert "connect skipped" in done[1] and "disconnect skipped" in done[1]


def test_reset_twice_is_safe(tmp_path):
    first = _run_full(RESET, tmp_path, networks="argus-lab-iso")
    assert first[0] == 0 and [c.split()[1] for c in first[2]] == ["connect", "disconnect"]
    second = _run_full(RESET, tmp_path, networks="argus-lab-app")
    assert second[0] == 0 and second[2] == []


def test_reset_connects_when_the_api_is_on_neither_network(tmp_path):
    done = _run_full(RESET, tmp_path, networks="")
    assert done[0] == 0 and [c.split()[1] for c in done[2]] == ["connect"] and "disconnect skipped" in done[1]


def test_reset_with_the_api_on_both_networks_only_disconnects(tmp_path):
    done = _run_full(RESET, tmp_path, networks="argus-lab-app argus-lab-iso")
    assert done[0] == 0 and [c.split()[1] for c in done[2]] == ["disconnect"] and "connect skipped" in done[1]


def test_the_override_replaces_the_host_name(tmp_path):
    assert _run(INJECT, tmp_path, "argus-vm095", override="argus-vm166")[0] == 0
    assert _run(INJECT, tmp_path, "argus-vm166", override="argus-vm095")[0] == 2


# ---- the evaluation case -------------------------------------------------------------------------------------

def test_the_case_names_network_restore_and_forbids_restart_and_stop(monkeypatch):
    monkeypatch.setenv("ARGUS_JWT_KEY", "x" * 40)
    from argus import evaluation

    case = {c.id: c for c in evaluation.load_cases(ROOT / "tests/eval/cases")}["dep-api-moved-network"]
    assert case.target == API
    assert [(a.action, a.target) for a in case.label.expected_actions] == [("network.restore", API)]
    assert {a.action for a in case.label.forbidden_actions} >= {"container.restart", "container.stop"}
    assert case.label.root_cause == API
    status = case.fixtures["docker_read"]["/containers/argus-lab-api/status"]
    assert status["state"] == "running" and "argus-lab-app" not in status["networks"]
