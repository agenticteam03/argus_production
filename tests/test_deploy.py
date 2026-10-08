"""ops/deploy.sh: the VMs check out an exact commit of this repository (shared-Brain plan, deploy method B).

Each test builds a throwaway "GitHub" (a bare repository) and a fake /opt/argus-v18 (ARGUS_DEPLOY_HOME).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "deploy.sh"


def _bash() -> str | None:
    if os.name == "nt":                       # never WSL's bash.exe: use Git for Windows' bash
        git_bash = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "bash.exe"
        return str(git_bash) if git_bash.is_file() else None
    return shutil.which("bash")


BASH = _bash()
pytestmark = pytest.mark.skipif(BASH is None, reason="bash not available")


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture()
def env(tmp_path, monkeypatch):
    cfg = tmp_path / "gitconfig"
    cfg.write_bytes(b"[init]\n\tdefaultBranch = main\n[core]\n\tautocrlf = false\n")
    for k, v in {"GIT_CONFIG_GLOBAL": str(cfg), "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t",
                 "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
                 "GIT_COMMITTER_EMAIL": "t@example.invalid"}.items():
        monkeypatch.setenv(k, v)
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "--bare", str(origin))
    work = tmp_path / "work"
    git(tmp_path, "clone", str(origin), str(work))
    (work / "README.md").write_bytes(b"argus\n")
    git(work, "add", "-A")
    git(work, "commit", "-m", "first")
    git(work, "push", "origin", "HEAD:main")
    home = tmp_path / "opt"
    (home / "app").mkdir(parents=True)
    (home / "app" / "old-tarball-file.txt").write_bytes(b"from the laptop tarball\n")
    (home / "SESSION").write_bytes(b"holder=alice session=abc\n")
    return {"origin": origin, "work": work, "home": home, "tmp": tmp_path}


def deploy(env, *args: str, who: str = "alice") -> subprocess.CompletedProcess:
    e = dict(os.environ, ARGUS_DEPLOY_HOME=env["home"].as_posix(), ARGUS_DEPLOY_REPO=env["origin"].as_posix())
    return subprocess.run([BASH, SCRIPT.as_posix(), *args, "--as", who], env=e, capture_output=True, text=True)


def deployed(env) -> dict:
    text = (env["home"] / "DEPLOYED").read_text(encoding="utf-8")
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


def test_init_clones_the_exact_commit_and_keeps_the_old_folder(env):
    sha = git(env["work"], "rev-parse", "HEAD")
    r = deploy(env, "init", "main")
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"DEPLOY OK: {sha[:12]}" in r.stdout
    app = env["home"] / "app"
    assert git(app, "rev-parse", "HEAD") == sha
    assert (app / "README.md").is_file() and not (app / "old-tarball-file.txt").exists()
    kept = [p for p in env["home"].iterdir() if p.name.startswith("app.pre-git-")]
    assert len(kept) == 1 and (kept[0] / "old-tarball-file.txt").is_file()
    d = deployed(env)
    assert d["commit"] == sha and d["ref"] == "main" and d["developer"] == "alice"


def test_refuses_when_the_session_is_not_yours(env):
    r = deploy(env, "init", "main", who="bob")
    assert r.returncode != 0
    assert "NOT YOUR SESSION" in r.stdout + r.stderr
    assert not (env["home"] / "DEPLOYED").exists()


def test_deploy_moves_to_a_newer_commit_and_hints_what_to_rebuild(env):
    assert deploy(env, "init", "main").returncode == 0
    first = deployed(env)["commit"]
    (env["work"] / "argus").mkdir()
    (env["work"] / "argus" / "x.py").write_bytes(b"x = 1\n")
    git(env["work"], "add", "-A")
    git(env["work"], "commit", "-m", "second")
    git(env["work"], "push", "origin", "HEAD:main")
    sha = git(env["work"], "rev-parse", "HEAD")
    r = deploy(env, "main")
    assert r.returncode == 0, r.stdout + r.stderr
    assert git(env["home"] / "app", "rev-parse", "HEAD") == sha
    d = deployed(env)
    assert d["commit"] == sha and d["previous"] == first
    assert "argus-v18-agent" in r.stdout                     # argus/ changed -> rebuild the agent (printed, not run)


def test_refuses_local_modifications_on_the_vm(env):
    assert deploy(env, "init", "main").returncode == 0
    (env["home"] / "app" / "README.md").write_bytes(b"edited on the VM\n")
    r = deploy(env, "main")
    assert r.returncode != 0
    assert "DEPLOY STOP" in r.stdout and "local modifications" in r.stdout


def test_unknown_ref_is_refused(env):
    assert deploy(env, "init", "main").returncode == 0
    r = deploy(env, "no-such-branch")
    assert r.returncode != 0
    assert "DEPLOY STOP" in r.stdout and "unknown" in r.stdout


def test_status_needs_no_session(env):
    assert deploy(env, "init", "main").returncode == 0
    r = deploy(env, "status", who="bob")
    assert r.returncode == 0
    assert "commit=" in r.stdout


# --- status also reports whether the lab is at its baseline (DEPLOY-MAIN found argus-lab-cache stopped for ~7 h) ---

def fake_docker(env, lines: str) -> str:
    """A stand-in for `docker ps` that prints the given '<name> <state> <status>' lines."""
    script = env["tmp"] / "fake-docker.sh"
    script.write_bytes(b"#!/usr/bin/env bash\ncat <<'OUT'\n" + lines.encode() + b"OUT\n")
    return f"bash {script.as_posix()}"


def status(env, docker: str) -> subprocess.CompletedProcess:
    e = dict(os.environ, ARGUS_DEPLOY_HOME=env["home"].as_posix(), ARGUS_DEPLOY_REPO=env["origin"].as_posix(),
             ARGUS_DOCKER=docker)
    return subprocess.run([BASH, SCRIPT.as_posix(), "status"], env=e, capture_output=True, text=True)


def test_status_says_the_lab_is_at_baseline_when_every_lab_container_runs_healthy(env):
    r = status(env, fake_docker(env, "argus-lab-api running Up 3 hours (healthy)\n"
                                     "argus-lab-cache running Up 3 hours\n"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "LAB BASELINE OK" in r.stdout


def test_status_flags_a_stopped_or_unhealthy_lab_container(env):
    r = status(env, fake_docker(env, "argus-lab-cache exited Exited (0) 7 hours ago\n"
                                     "argus-lab-api running Up 31 minutes (unhealthy)\n"))
    assert r.returncode == 0                                  # status stays read-only and informative
    assert "LAB BASELINE NOT OK" in r.stdout
    assert "argus-lab-cache" in r.stdout and "argus-lab-api" in r.stdout.split("LAB BASELINE NOT OK")[1]


def test_status_lists_the_argus_programs_and_the_command_each_runs(env):
    """T-0014: one image, three programs on vm-095; status shows which command each container runs."""
    r = status(env, fake_docker(env, 'argus-v18-agent running "python -m argus api"\n'
                                     'argus-v18-worker running "python -m argus worker"\n'
                                     'argus-v18-scheduler running "python -m argus scheduler"\n'
                                     "argus-v18-postgres running Up 3 hours (healthy)\n"
                                     "argus-lab-api running Up 3 hours (healthy)\n"))
    assert r.returncode == 0, r.stdout + r.stderr
    argus = [ln for ln in r.stdout.splitlines() if ln.startswith("argus: ")]
    assert [ln.split()[1] for ln in argus] == ["argus-v18-agent", "argus-v18-worker", "argus-v18-scheduler"]
    assert "argus api" in argus[0] and "argus worker" in argus[1]


def test_status_without_docker_says_so_instead_of_claiming_ok(env):
    r = status(env, "no-such-docker-binary")
    assert r.returncode == 0
    assert "LAB BASELINE OK" not in r.stdout
    assert "lab: docker not available" in r.stdout
