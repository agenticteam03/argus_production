"""T-0021 step 3: credential isolation (ARCHITECTURE §12.6).

The worker runs as `argus` and cannot read an executor token; the tools process runs as `argus-tools` and is the only
reader. The worker may start exactly one program as `argus-tools` (sudoers: the fixed tools-server launcher, no
arguments). `python -m argus.tooling.isolation_check` proves it inside the worker container (step 5 on vm-095).
The real image check runs with ARGUS_TEST_DOCKER=1 (needs the Docker CLI).
"""
from __future__ import annotations

import os
import shutil
import subprocess

import pytest

from argus.infrastructure.wiring import Settings, build
from test_core import ROOT, RUNBOOKS, FakeMetrics

SUDOERS = ROOT / "deploy" / "agent" / "argus-tools.sudoers"
LAUNCHER = ROOT / "deploy" / "agent" / "argus-tools-server"


def test_in_mcp_mode_the_worker_needs_no_executor_token(tmp_path, monkeypatch):
    monkeypatch.setenv("ARGUS_JWT_KEY", "x" * 40)
    s = Settings(config_dir=ROOT / "config", secrets_dir=tmp_path / "no-secrets", runbooks_dir=RUNBOOKS,
                 db_path=str(tmp_path / "t.db"), tool_catalogue="mcp")
    app = build(s, metrics=FakeMetrics(), require_credentials=True)       # no token anywhere: still starts
    assert app.catalogue.dispatcher.credentials == {}
    with pytest.raises(SystemExit, match="missing credential"):           # direct mode still needs them
        build(Settings(config_dir=ROOT / "config", secrets_dir=tmp_path / "no-secrets", runbooks_dir=RUNBOOKS,
                       db_path=str(tmp_path / "t2.db")), metrics=FakeMetrics(), require_credentials=True)


def test_the_api_reads_no_executor_token_even_when_one_is_readable(tmp_path, monkeypatch):
    """T-0021 step 4: the api never investigates, so it loads no executor token in either catalogue mode."""
    monkeypatch.setenv("ARGUS_JWT_KEY", "x" * 40)
    secrets = tmp_path / "secrets"
    (secrets / "vm-095").mkdir(parents=True)
    (secrets / "vm-095" / "docker_read_token").write_text("tok", encoding="utf-8")
    s = Settings(config_dir=ROOT / "config", secrets_dir=secrets, runbooks_dir=RUNBOOKS, db_path=str(tmp_path / "t.db"))
    app = build(s, metrics=FakeMetrics(), require_credentials=False, load_credentials=False)
    assert app.catalogue.dispatcher.credentials == {}


def test_the_tools_command_is_the_whole_command(monkeypatch):
    from argus.tooling.mcp.client import child_client
    launcher = "sudo -n -u argus-tools /usr/local/bin/argus-tools-server"
    monkeypatch.setenv("ARGUS_TOOLS_COMMAND", launcher)
    params = child_client({}, Settings().tools_command)._server
    assert [params.command, *params.args] == launcher.split()             # nothing appended: no arguments to sudo
    default = child_client({}, None)._server
    assert default.args[-2:] == ["-m", "argus.tooling.mcp.tools_server"]


def test_sudoers_allows_only_the_launcher_without_arguments():
    rules = [ln.strip() for ln in SUDOERS.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")]
    grants = [r for r in rules if not r.startswith("Defaults")]
    assert grants == ['argus ALL=(argus-tools) NOPASSWD: /usr/local/bin/argus-tools-server ""']
    text = LAUNCHER.read_text(encoding="utf-8")
    assert '"$@"' not in text
    # Review of PR #36: sudo keeps the caller's working folder and `python -m` would put it first on sys.path, so a
    # worker could plant its own `argus` package there. The launcher leaves that folder and runs Python isolated.
    assert "cd / || exit 1" in text.splitlines()
    assert "exec /usr/local/bin/python -I -u -m argus.tooling.mcp.tools_server" in text
    assert "ARGUS_SECRETS_DIR=/run/argus-secrets" in text and "ARGUS_CONFIG_DIR=/app/config" in text


def test_isolation_check_says_stop_when_the_worker_can_read_a_token(tmp_path, monkeypatch, capsys):
    from argus.tooling import isolation_check
    (tmp_path / "vm-166").mkdir()
    (tmp_path / "vm-166" / "docker_read_token").write_text("t")
    monkeypatch.setenv("ARGUS_SECRETS_DIR", str(tmp_path))
    monkeypatch.setenv("ARGUS_TOOLS_COMMAND", "")
    assert isolation_check.main() == 1
    out = capsys.readouterr().out.splitlines()
    assert out[-1] == "TOOLS ISOLATION STOP"
    assert any(ln.startswith("FAIL") and "cannot read" in ln for ln in out)


def test_isolation_check_takes_the_token_list_from_the_inventory(tmp_path, monkeypatch, capsys):
    """T-0021 step 5: on vm-095 the token folders belong to argus-tools, so the worker cannot even list them. The
    check must not mistake "cannot see" for "missing": the expected tokens come from the inventory, and their presence
    is proved by the tools process starting (it refuses to start without every token)."""
    from argus.tooling import isolation_check
    monkeypatch.setenv("ARGUS_SECRETS_DIR", str(tmp_path / "unlistable"))
    monkeypatch.setenv("ARGUS_CONFIG_DIR", str(ROOT / "config"))
    monkeypatch.setenv("ARGUS_TOOLS_COMMAND", "")
    isolation_check.main()
    out = capsys.readouterr().out.splitlines()
    assert not any(ln.startswith("FAIL") and "token" in ln for ln in out), out
    assert any(ln.startswith("ok") and "cannot read any executor token" in ln and "expected by the inventory" in ln
               for ln in out), out


@pytest.mark.skipif(os.getenv("ARGUS_TEST_DOCKER") != "1" or shutil.which("docker") is None,
                    reason="ARGUS_TEST_DOCKER=1 not set (needs Docker)")
def test_the_agent_image_isolates_the_tokens():
    tag = "argus-v18-agent:t0021-test"
    subprocess.run(["docker", "build", "-q", "-t", tag, str(ROOT)], check=True, capture_output=True)
    r = subprocess.run(["docker", "run", "--rm", "--user", "root", "-v", f"{ROOT / 'config'}:/app/config:ro",
                        "-v", f"{ROOT / 'deploy' / 'agent' / 'isolation-test-setup.sh'}:/setup.sh:ro",
                        tag, "sh", "/setup.sh"], capture_output=True, text=True, timeout=300)
    assert "TOOLS ISOLATION OK" in r.stdout.splitlines()[-1], r.stdout + r.stderr
