"""The vm-deploy skill's checklist: order, what each change needs, and that the helper never reaches a VM."""

from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".claude" / "skills" / "vm-deploy"
SCRIPT = SKILL / "scripts" / "deploy_checklist.py"


def load():
    spec = importlib.util.spec_from_file_location("deploy_checklist", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def steps(changed, target="vm-095", new_env=(), new_secrets=()):
    return load().checklist(target, "afb72e8", changed, new_env, new_secrets)


def index(lines, text):
    return next(i for i, line in enumerate(lines) if text in line)


def test_agent_change_on_vm095_needs_both_leases_and_keeps_the_order():
    lines = steps(["argus/detectors/classes.py"])
    assert "both leases" in lines[0]
    order = ["SESSION", "deploy.sh status", "nonint-check.sh before", "db-backup.sh backup", "deploy.sh afb72e8",
             "up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler", "argus deploy record",
             "argus db check", "nonint-check.sh after", "release"]
    positions = [index(lines, text) for text in order]
    assert positions == sorted(positions)


def test_a_migration_runs_after_the_backup_and_before_the_new_image():
    lines = steps(["deploy/migrations/013_webauthn.sql", "argus/application/second_factor.py"])
    backup, migrate, image = (index(lines, t) for t in ("db-backup.sh backup", "db-migrate.sh", "up -d --build"))
    assert backup < migrate < image
    assert "013_webauthn.sql" in lines[migrate]


def test_no_migration_step_without_a_migration():
    assert not any("db-migrate.sh" in line for line in steps(["argus/api.py"]))


def test_ui_change_rebuilds_only_the_ui():
    lines = steps(["frontend/src/App.tsx"])
    assert any("compose.ui.yml" in line for line in lines)
    assert not any("argus-v18-worker" in line for line in lines)


def test_new_compose_variables_must_be_in_hosts_env_before_up():
    lines = steps(["deploy/vm-095/compose.core.yml"], new_env=["ARGUS_WEBAUTHN_RP_ID"])
    env, image = index(lines, "ARGUS_WEBAUTHN_RP_ID"), index(lines, "up -d --build")
    assert "hosts.env" in lines[env] and env < image


def test_a_new_secret_mount_must_exist_before_any_up():
    key = "/opt/argus-v18/secrets/agent/jwt_ed25519_key"
    lines = steps(["deploy/vm-095/compose.core.yml"], new_secrets=[("deploy/vm-095/compose.core.yml", key)])
    secret, deploy, image = index(lines, key), index(lines, "deploy.sh afb72e8"), index(lines, "up -d --build")
    assert deploy < secret < image and "never printed" in lines[secret]


def test_a_secret_mount_counts_only_on_the_vm_that_brings_its_file_up():
    key = "/opt/argus-v18/secrets/agent/jwt_ed25519_key"
    lines = steps(["deploy/vm-095/compose.core.yml"], target="vm-166",
                  new_secrets=[("deploy/vm-095/compose.core.yml", key)])
    assert len(lines) == 1 and "nothing to deploy" in lines[0]


def test_the_diff_reader_finds_the_real_ed25519_mount():
    _, _, secrets = load().changed_paths("6c83da3", "afb72e8")
    assert ("deploy/vm-095/compose.core.yml", "/opt/argus-v18/secrets/agent/jwt_ed25519_key") in secrets


@pytest.mark.parametrize("target, overlay", [("vm-095", "compose.core-join.yml"), ("vm-166", "compose.loopback.yml")])
def test_target_and_monitoring_run_on_both_vms_with_that_hosts_overlay(target, overlay):
    lines = steps(["deploy/monitoring/alerts.yml"], target=target)
    up = index(lines, "compose.monitoring.yml")
    assert overlay in lines[up] and f"--env-file {target}.env" in lines[up]


def test_unmapped_deploy_paths_are_reported_not_dropped():
    lines = steps(["deploy/langfuse/compose.yml"])
    assert "nothing to deploy" in lines[0] and "not covered" in lines[-1] and "deploy/langfuse/compose.yml" in lines[-1]


def test_docs_only_change_needs_no_deploy():
    lines = steps(["brain/journal/entries/x.md", "docs/INCIDENTS.md"])
    assert len(lines) == 1 and "nothing to deploy" in lines[0]


def test_vm166_change_needs_only_its_own_lease_and_no_agent_rebuild():
    lines = steps(["deploy/lab/compose.lab.yml"], target="vm-166")
    assert "vm-166's lease" in lines[0] and "both" not in lines[0]
    assert not any("argus-v18-agent" in line for line in lines)


def test_unknown_target_is_refused():
    with pytest.raises(ValueError, match="vm-095 or vm-166"):
        steps(["argus/x.py"], target="prod")


@pytest.mark.parametrize("commit", ["", "main; rm -rf /", "AFB72E8"])
def test_commit_must_be_a_sha(commit):
    with pytest.raises(ValueError, match="commit"):
        load().checklist("vm-095", commit, ["argus/x.py"], ())


def test_the_helper_never_connects_to_a_vm_or_runs_docker():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and node.func.attr in {"run", "check_output", "Popen", "call"}]
    for call in calls:
        first = call.args[0]
        assert isinstance(first, (ast.List, ast.Tuple)), "a subprocess call must have a literal argument list"
        assert isinstance(first.elts[0], ast.Constant) and first.elts[0].value == "git"
    text = SCRIPT.read_text(encoding="utf-8")
    assert "import paramiko" not in text and "os.system" not in text


def test_skill_is_manual_only():
    head = (SKILL / "SKILL.md").read_text(encoding="utf-8").split("---")[1]
    assert "disable-model-invocation: true" in head


def test_cli_prints_a_checklist_from_the_repository(tmp_path):
    result = subprocess.run([sys.executable, str(SCRIPT), "--target", "vm-095", "--from", "HEAD~1", "--to", "HEAD"],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 0, result.stderr
    assert "CHECKLIST" in result.stdout
