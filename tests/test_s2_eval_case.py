"""TASK-60 (scenario 2): the `link_ok` verify signal, the injection scripts and the dep-api-moved-network case."""
from __future__ import annotations

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
def test_scripts_use_lab_names_only_and_refuse_vm_095(script):
    text = script.read_text(encoding="utf-8")
    assert "vm-095" in text and "exit" in text            # the refusal
    assert "/opt/argus" not in text.replace("/opt/argus-lab", "")
    for forbidden in ("wg0", "labmvp", "reboot", "docker rm", "docker stop"):
        assert forbidden not in text


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
