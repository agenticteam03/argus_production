"""brain/tools/brain.py: the session lease on the `session` branch, audit, lint and archive-step.

Each test builds a throwaway "GitHub" (a bare repository) and two developer clones, alice and bob.
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "brain" / "tools"))
import brain  # noqa: E402

T0 = dt.datetime(2026, 10, 2, 12, 0, tzinfo=dt.timezone.utc)


def run(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture()
def repos(tmp_path, monkeypatch):
    cfg = tmp_path / "gitconfig"
    cfg.write_bytes(b"[init]\n\tdefaultBranch = main\n[core]\n\tautocrlf = false\n")
    for k, v in {"GIT_CONFIG_GLOBAL": str(cfg), "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t",
                 "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
                 "GIT_COMMITTER_EMAIL": "t@example.invalid", "BRAIN_NO_GH": "1"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("ARGUS_DEVELOPER", raising=False)
    origin = tmp_path / "origin.git"
    run(tmp_path, "init", "--bare", str(origin))
    seed = tmp_path / "seed"
    run(tmp_path, "clone", str(origin), str(seed))
    (seed / "README.md").write_bytes(b"argus\n")
    (seed / ".gitignore").write_bytes(b"output*.bash\n")
    run(seed, "add", "-A")
    run(seed, "commit", "-m", "init")
    run(seed, "push", "origin", "HEAD:main")
    clones = {}
    for who in ("alice", "bob"):
        c = tmp_path / who
        run(tmp_path, "clone", str(origin), str(c))
        run(c, "config", "argus.developer", who)
        clones[who] = c
    return clones


def as_(monkeypatch, repo: Path, at: dt.datetime = T0):
    monkeypatch.chdir(repo)
    monkeypatch.setenv("BRAIN_NOW", at.isoformat())


def lease_of(repo: Path) -> dict:
    run(repo, "fetch", "origin", "+refs/heads/session:refs/remotes/origin/session")
    return json.loads(run(repo, "show", "origin/session:session.json"))


def test_claim_then_another_developer_is_refused(repos, monkeypatch, capsys):
    as_(monkeypatch, repos["alice"])
    assert brain.main(["start", "--task", "T-0013"]) == 0
    assert lease_of(repos["alice"])["holder"] == "alice"
    as_(monkeypatch, repos["bob"], T0 + dt.timedelta(minutes=10))
    assert brain.main(["start"]) == 2
    assert "in use by alice" in capsys.readouterr().err
    assert lease_of(repos["bob"])["holder"] == "alice"


def test_code_only_start_does_not_claim(repos, monkeypatch):
    as_(monkeypatch, repos["alice"])
    assert brain.main(["start", "--no-claim"]) == 0
    assert run(repos["alice"], "ls-remote", "origin", "session") == ""


def test_simultaneous_claims_only_one_wins(repos, monkeypatch):
    """bob read 'no lease' before alice pushed her claim: his push is not a fast-forward and is refused."""
    as_(monkeypatch, repos["alice"])
    assert brain.main(["start"]) == 0
    as_(monkeypatch, repos["bob"])
    with pytest.raises(brain.BrainError, match="someone else was faster"):
        brain.write_lease({"holder": "bob", "expires_at": T0.isoformat(), "released": False}, None, "claim: bob")
    assert lease_of(repos["bob"])["holder"] == "alice"


def test_expired_lease_can_be_taken_over_and_is_recorded(repos, monkeypatch):
    as_(monkeypatch, repos["alice"])
    assert brain.main(["start", "--task", "T-0013"]) == 0
    as_(monkeypatch, repos["bob"], T0 + dt.timedelta(minutes=61))
    assert brain.main(["start"]) == 0
    lease = lease_of(repos["bob"])
    assert lease["holder"] == "bob"
    assert lease["took_over_from"]["holder"] == "alice"
    assert lease["task"] == "T-0013"


def test_renew_extends_and_only_the_holder_may_renew(repos, monkeypatch):
    as_(monkeypatch, repos["alice"])
    assert brain.main(["start"]) == 0
    as_(monkeypatch, repos["alice"], T0 + dt.timedelta(minutes=50))
    assert brain.main(["renew", "--minutes", "120"]) == 0
    assert lease_of(repos["alice"])["expires_at"] == (T0 + dt.timedelta(minutes=170)).isoformat()
    as_(monkeypatch, repos["bob"], T0 + dt.timedelta(minutes=55))
    assert brain.main(["renew"]) == 2
    assert brain.main(["release"]) == 2


def test_handoff_releases_and_the_next_developer_sees_the_note(repos, monkeypatch, capsys):
    as_(monkeypatch, repos["alice"])
    assert brain.main(["start", "--task", "T-0013"]) == 0
    assert brain.main(["handoff", "done: step 2; next: step 3 (red test written)"]) == 0
    capsys.readouterr()
    as_(monkeypatch, repos["bob"], T0 + dt.timedelta(minutes=5))
    assert brain.main(["start"]) == 0
    out = capsys.readouterr().out
    assert "next: step 3" in out
    assert lease_of(repos["bob"])["holder"] == "bob"


def test_release_lets_the_next_developer_claim(repos, monkeypatch):
    as_(monkeypatch, repos["alice"])
    assert brain.main(["start"]) == 0
    assert brain.main(["release"]) == 0
    as_(monkeypatch, repos["bob"], T0 + dt.timedelta(minutes=1))
    assert brain.main(["start"]) == 0


def test_start_refuses_a_dirty_working_tree(repos, monkeypatch, capsys):
    as_(monkeypatch, repos["alice"])
    (repos["alice"] / "wip.py").write_bytes(b"x = 1\n")
    assert brain.main(["start"]) == 2
    assert "uncommitted changes" in capsys.readouterr().err


def test_start_needs_a_developer_identity(repos, monkeypatch, capsys):
    as_(monkeypatch, repos["alice"])
    run(repos["alice"], "config", "--unset", "argus.developer")
    assert brain.main(["start"]) == 2
    assert "git config argus.developer" in capsys.readouterr().err


def test_audit_blocks_planted_secrets_addresses_and_files(repos, monkeypatch, capsys):
    """Fakes are built at runtime so this file itself never contains them."""
    repo = repos["alice"]
    as_(monkeypatch, repo)
    fake_key = "sk-" + "A1b2C3d4" * 4
    public = ".".join(["8", "8", "8", "8"])
    private_host = ".".join(["10", "1", "2", "3"])
    path = "C:" + "\\" + "Users" + "\\" + "someone"
    pem = "-----BEGIN " + "OPENSSH PRIVATE KEY-----"
    (repo / "notes.md").write_bytes("\n".join([fake_key, public, private_host, path, pem,
                                               "subnet 10.0.0.0/24 and 172.30.0.1 and 127.0.0.1 are fine",
                                               f"{public} allowed here  # brain-audit: allow"]).encode())
    (repo / "secrets").mkdir()
    (repo / "secrets" / "token").write_bytes(b"x\n")
    (repo / "output.bash").write_bytes(b"ignored by .gitignore\n")
    assert brain.main(["audit"]) == 1
    out = capsys.readouterr().out
    assert "notes.md:1: API key" in out
    assert "notes.md:2: public IP address" in out
    assert "notes.md:3: private host address" in out
    assert "notes.md:4: Windows user-profile path" in out
    assert "notes.md:5: private key" in out
    assert "notes.md:6" not in out and "notes.md:7" not in out
    assert "secrets/token: forbidden file" in out
    assert "output.bash" not in out


def test_audit_staged_checks_only_what_will_be_committed(repos, monkeypatch, capsys):
    repo = repos["alice"]
    as_(monkeypatch, repo)
    (repo / "clean.py").write_bytes(b"x = 1\n")
    (repo / "dirty.md").write_bytes(("token " + "sk-" + "Z" * 30 + "\n").encode())
    run(repo, "add", "clean.py")
    assert brain.main(["audit", "--staged"]) == 0
    run(repo, "add", "dirty.md")
    assert brain.main(["audit", "--staged"]) == 1


def test_lint_reports_crlf_broken_links_and_missing_files(repos, monkeypatch, capsys):
    repo = repos["alice"]
    as_(monkeypatch, repo)
    (repo / "brain").mkdir()
    (repo / "brain" / "README.md").write_bytes(b"see [state](CURRENT_STATE.md) and [web](https://example.com)\r\n")
    assert brain.main(["lint"]) == 1
    out = capsys.readouterr().out
    assert "brain/README.md: Windows line endings" in out
    assert "broken link CURRENT_STATE.md" in out
    assert "brain/NEXT_STEP.md: missing" in out
    assert "example.com" not in out


def test_archive_step_moves_the_commands_and_resets_current(repos, monkeypatch):
    repo = repos["alice"]
    as_(monkeypatch, repo)
    cur = repo / "brain" / "execution" / "current"
    cur.mkdir(parents=True)
    (cur / "code.bash").write_bytes(brain.CODE_BASH_HEADER.encode())
    assert brain.main(["archive-step", "T-0013", "1"]) == 2          # nothing to archive yet
    (cur / "code.bash").write_bytes((brain.CODE_BASH_HEADER + "echo hi\n").encode())
    assert brain.main(["archive-step", "T-0013", "1"]) == 0
    step = repo / "brain" / "execution" / "history" / "T-0013" / "step-01"
    assert (step / "code.bash").read_bytes().endswith(b"echo hi\n")
    assert (step / "evidence.md").is_file()
    assert (cur / "code.bash").read_bytes() == brain.CODE_BASH_HEADER.encode()
    assert brain.main(["archive-step", "T-0013", "1"]) == 2          # never overwrites


def test_checkpoint_refuses_main(repos, monkeypatch, capsys):
    as_(monkeypatch, repos["alice"])
    assert brain.main(["checkpoint", "T-0013: x", "--no-tests"]) == 2
    assert "task branch" in capsys.readouterr().err


def test_checkpoint_commits_pushes_and_blocks_a_secret(repos, monkeypatch, capsys):
    repo = repos["alice"]
    as_(monkeypatch, repo)
    run(repo, "checkout", "-b", "task/T-0013-x")
    (repo / "a.py").write_bytes(b"x = 1\n")
    assert brain.main(["checkpoint", "T-0013: add a", "--no-tests"]) == 0
    assert "task/T-0013-x" in run(repo, "ls-remote", "origin", "task/T-0013-x")
    (repo / "b.md").write_bytes(("key " + "sk-" + "Q" * 30 + "\n").encode())
    assert brain.main(["checkpoint", "T-0013: add b", "--no-tests"]) == 2
    assert run(repo, "log", "-1", "--format=%s") == "T-0013: add a"
