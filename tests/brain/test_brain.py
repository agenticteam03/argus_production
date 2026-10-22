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
    monkeypatch.delenv("GITHUB_HEAD_REF", raising=False)    # set by CI on pull_request runs: the PR's branch, not ours
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


# --- the review rule on main (free plan: verify-main instead of branch protection) -----------------------------------
def _pr(n, author, head):
    return {"number": n, "user": {"login": author}, "head": {"sha": head}}


def _review(who, state, commit):
    return {"user": {"login": who}, "state": state, "commit_id": commit}


def test_check_main_accepts_initial_commit_and_approved_prs():
    commits = [("m2" * 20, 2), ("m1" * 20, 2), ("root" * 10, 0)]
    prs = {"m2" * 20: _pr(3, "alice", "h3"), "m1" * 20: _pr(2, "bob", "h2")}
    reviews = {3: [_review("bob", "APPROVED", "h3")], 2: [_review("alice", "APPROVED", "h2")]}
    assert brain.check_main(commits, prs.get, reviews.get, set()) == []


def test_check_main_flags_direct_push_self_approval_and_stale_approval():
    commits = [("d" * 40, 1), ("s" * 40, 2), ("o" * 40, 2), ("root" * 10, 0)]
    prs = {"s" * 40: _pr(5, "alice", "h5"), "o" * 40: _pr(4, "bob", "h4-new")}
    reviews = {5: [_review("alice", "APPROVED", "h5")],                    # approved by its own author
               4: [_review("alice", "APPROVED", "h4-old")]}                # approval predates the last push
    problems = brain.check_main(commits, prs.get, reviews.get, set())
    assert len(problems) == 3
    assert "pushed directly to main" in problems[0]
    assert "PR #5 by alice" in problems[1]
    assert "PR #4 by bob" in problems[2]


def test_check_main_honours_recorded_exceptions(tmp_path):
    p = tmp_path / "brain" / "policies"
    p.mkdir(parents=True)
    (p / "main-exceptions.txt").write_bytes(b"# comment\npr 1  2026-10-02  someone  bootstrap\n")
    allowed = brain.read_exceptions(tmp_path)
    assert allowed == {1}
    commits = [("x" * 40, 2), ("root" * 10, 0)]
    assert brain.check_main(commits, {"x" * 40: _pr(1, "alice", "h1")}.get, lambda n: [], allowed) == []


# --- self-merge (REVIEW_PROTOCOL.md "Self-merge"): green required checks, no protected path ---------------------------
def _run(name, conclusion="success"):
    return {"name": name, "status": "completed", "conclusion": conclusion}


GREEN = [_run("test"), _run("frontend"), _run("main-guard", "skipped")]


def test_a_self_merge_with_green_checks_and_ordinary_files_is_accepted():
    pr = _pr(7, "alice", "h7")
    assert brain.self_merge_problem(pr, GREEN, ["argus/application/topology.py", "tests/test_x.py"], []) is None
    commits = [("x" * 40, 2), ("root" * 10, 0)]
    assert brain.check_main(commits, {"x" * 40: pr}.get, lambda n: [], set(),
                            lambda p, *_: brain.self_merge_problem(p, GREEN, ["frontend/src/App.jsx"], [])) == []


@pytest.mark.parametrize("checks, why", [
    ([_run("test"), _run("frontend", "failure")], "frontend not success"),
    ([_run("test")], "frontend missing"),
    ([_run("test", "cancelled"), _run("frontend")], "test not success"),
    ([], "test missing"),
])
def test_a_self_merge_needs_every_required_check_green_on_its_last_push(checks, why):
    assert why in brain.self_merge_problem(_pr(7, "alice", "h7"), checks, ["argus/x.py"], [])


@pytest.mark.parametrize("path", ["brain/architecture/changes/ACR-0099-x.md", "brain/policies/SECURITY.md",
                                  "brain/agents/REVIEW_PROTOCOL.md", "brain/tools/brain.py", ".github/workflows/ci.yml",
                                  "config/policy.yaml", "config/inventory.yaml", "deploy/ui/nginx/locations.conf",
                                  "contracts/ui-api.json", "ops/local_ci.py", "brain/policies/main-exceptions.txt",
                                  # SELF-MERGE-2 (the #165 review): rails, root scripts, compose files, rail tests
                                  "brain/agents/AGENT_PROTOCOL.md", "brain/policies/PARALLEL_LANES.md",
                                  "ops/deploy.sh", "ops/nonint-check.sh", "ops/write-gate-check.sh",
                                  "deploy/vm-095/compose.core.yml", "deploy/target/compose.target.yml",
                                  "deploy/migrations/007_x.sql", "argus/policy/engine.py",
                                  "argus/application/invoke_capability.py", "argus/infrastructure/gate_report.py",
                                  "argus/tooling/isolation_check.py", "tests/brain/test_brain.py",
                                  "tests/test_write_gate_standing.py", "tests/test_op014_prompt_injection.py",
                                  # phase 15: the action path, before it exists
                                  "config/actions/container.start.yaml", "config/risk.yaml", "config/ranking.yaml",
                                  "argus/capabilities/write_contract.py", "argus/actions/dispatch.py",
                                  "services/action-gateway/service.py",
                                  # T-0049 S0: skills are agent procedures, including their executable helpers.
                                  ".claude/skills/code-bash-step/SKILL.md",
                                  ".claude/skills/code-bash-step/scripts/check_block.py",
                                  ".claude/skills/code-bash-step/templates/comment.ps1"])
def test_a_self_merge_never_covers_a_protected_path(path):
    why = brain.self_merge_problem(_pr(7, "alice", "h7"), GREEN, ["argus/x.py", path], [])
    assert why and path in why and "teammate" in why


@pytest.mark.parametrize("path", ["argus/application/topology.py", "frontend/src/App.jsx", "deploy/ui/Dockerfile",
                                  "tests/test_core.py", "brain/journal/entries/2026-10-18-x.md", "docs/INCIDENTS.md"])
def test_ordinary_paths_stay_self_mergeable(path):
    assert brain.self_merge_problem(_pr(7, "alice", "h7"), GREEN, [path], []) is None


def test_a_renamed_protected_file_counts_under_its_old_name_too():
    files = brain.changed_paths([{"filename": "docs/ARCHITECTURE.md",
                                  "previous_filename": "brain/architecture/ARCHITECTURE.md"},
                                 {"filename": "argus/x.py"}])
    assert files == ["docs/ARCHITECTURE.md", "brain/architecture/ARCHITECTURE.md", "argus/x.py"]
    why = brain.self_merge_problem(_pr(7, "alice", "h7"), GREEN, files, [])
    assert why and "brain/architecture/ARCHITECTURE.md" in why


def test_a_self_merge_with_too_many_files_to_check_is_refused():
    files = [f"argus/f{i}.py" for i in range(brain.FILES_PAGE)]
    assert "too many" in brain.self_merge_problem(_pr(7, "alice", "h7"), GREEN, files, [])


def test_a_local_ci_pass_for_the_last_push_by_another_developer_replaces_the_github_checks():
    pr = _pr(7, "alice", "abc123")
    good = [{"user": {"login": "bob"}, "body": "LOCAL CI PASS abc123 (laptop, commit abc123)\n\nall steps pass"}]
    assert brain.self_merge_problem(pr, [], ["argus/x.py"], good) is None
    own = [{"user": {"login": "alice"}, "body": "LOCAL CI PASS abc123 (laptop, commit abc123)"}]   # the author's
    old = [{"user": {"login": "bob"}, "body": "LOCAL CI PASS 999999 (laptop, commit 999999)"}]     # an earlier push
    failed = [{"user": {"login": "bob"}, "body": "LOCAL CI FAIL abc123 (laptop, commit abc123)"}]
    for comments in (own, old, failed):
        assert brain.self_merge_problem(pr, [], ["argus/x.py"], comments) is not None


@pytest.mark.parametrize("kw, why", [
    ({"merge_commit": False}, "merge commit"),
    ({"up_to_date": False}, "up to date"),
    ({"branch_kept": False}, "deleted"),
])
def test_a_self_merge_must_be_up_to_date_a_merge_commit_and_keep_its_branch(kw, why):
    assert why in brain.self_merge_problem(_pr(7, "alice", "h7"), GREEN, ["argus/x.py"], [], **kw)


def test_check_main_reports_why_a_self_merge_was_not_valid():
    commits = [("x" * 40, 2), ("root" * 10, 0)]
    seen = []
    problems = brain.check_main(commits, {"x" * 40: _pr(8, "bob", "h8")}.get, lambda n: [], set(),
                                lambda p, sha, parents: seen.append((sha, parents)) or
                                brain.self_merge_problem(p, GREEN, ["config/policy.yaml"], []))
    assert len(problems) == 1 and "PR #8 by bob" in problems[0] and "config/policy.yaml" in problems[0]
    assert seen == [("x" * 40, 2)]                       # the merge commit and its parent count reach the check


# --- an update that only brings in main keeps the approval (REVIEW_PROTOCOL.md) ----------------------------------------
def test_check_main_keeps_an_approval_when_only_main_was_merged_in_after_it():
    commits = [("o" * 40, 2), ("root" * 10, 0)]
    prs = {"o" * 40: _pr(4, "bob", "h4-new")}
    reviews = {4: [_review("alice", "APPROVED", "h4-old")]}
    asked = []
    keeps = lambda approved, pr, sha: asked.append((approved, pr["number"], sha)) or approved == "h4-old"  # noqa: E731
    assert brain.check_main(commits, prs.get, reviews.get, set(), keeps_approval=keeps) == []
    assert asked == [("h4-old", 4, "o" * 40)]
    assert len(brain.check_main(commits, prs.get, reviews.get, set(), keeps_approval=lambda *_: False)) == 1
    reviews[4] = [_review("bob", "APPROVED", "h4-old")]                 # still never the author's own approval
    assert len(brain.check_main(commits, prs.get, reviews.get, set(), keeps_approval=keeps)) == 1


def _commit(repo: Path, name: str, text: str, msg: str) -> str:
    (repo / name).write_bytes(text.encode())
    run(repo, "add", name)
    run(repo, "commit", "-q", "-m", msg)
    return run(repo, "rev-parse", "HEAD")


@pytest.fixture()
def pr_branch(repos):
    """bob's task branch with one approved commit; main has moved on since (a.md on the branch, m.md on main)."""
    repo = repos["bob"]
    run(repo, "checkout", "-q", "-b", "task/T-1")
    approved = _commit(repo, "a.md", "one\ntwo\nthree\n", "the approved work")
    run(repo, "checkout", "-q", "main")
    _commit(repo, "m.md", "main moved on\n", "someone else's merge")
    run(repo, "checkout", "-q", "task/T-1")
    return repo, approved


def test_a_clean_merge_of_main_keeps_the_approval(pr_branch, monkeypatch):
    repo, approved = pr_branch
    monkeypatch.chdir(repo)
    run(repo, "merge", "-q", "--no-edit", "main")                       # what "Update branch" does
    head = run(repo, "rev-parse", "HEAD")
    assert brain.only_main_merged_since(approved, head, run(repo, "rev-parse", "main"))
    assert brain.only_main_merged_since(approved, approved, run(repo, "rev-parse", "main"))


def test_a_new_commit_after_the_approval_needs_a_new_one(pr_branch, monkeypatch):
    repo, approved = pr_branch
    monkeypatch.chdir(repo)
    run(repo, "merge", "-q", "--no-edit", "main")
    head = _commit(repo, "a.md", "one\ntwo\nfour\n", "a change after the approval")
    assert not brain.only_main_merged_since(approved, head, run(repo, "rev-parse", "main"))


def test_a_merge_with_an_extra_edit_needs_a_new_approval(pr_branch, monkeypatch):
    repo, approved = pr_branch
    monkeypatch.chdir(repo)
    run(repo, "merge", "-q", "--no-commit", "main")
    (repo / "a.md").write_bytes(b"one\ntwo\nchanged inside the merge\n")
    run(repo, "add", "a.md")
    run(repo, "commit", "-q", "--no-edit")
    head = run(repo, "rev-parse", "HEAD")
    assert not brain.only_main_merged_since(approved, head, run(repo, "rev-parse", "main"))


def test_a_resolved_conflict_needs_a_new_approval(pr_branch, monkeypatch):
    repo, approved = pr_branch
    monkeypatch.chdir(repo)
    run(repo, "checkout", "-q", "main")
    _commit(repo, "a.md", "one\ntwo\nmain's three\n", "main edits the same lines")
    run(repo, "checkout", "-q", "task/T-1")
    subprocess.run(["git", "merge", "--no-edit", "main"], cwd=repo, capture_output=True)    # conflicts
    (repo / "a.md").write_bytes(b"one\ntwo\nthree\n")                  # resolved by keeping the branch's side
    run(repo, "add", "a.md")
    run(repo, "commit", "-q", "--no-edit")
    head = run(repo, "rev-parse", "HEAD")
    assert not brain.only_main_merged_since(approved, head, run(repo, "rev-parse", "main"))


def test_a_rewritten_branch_needs_a_new_approval(pr_branch, monkeypatch):
    repo, approved = pr_branch
    monkeypatch.chdir(repo)
    run(repo, "reset", "-q", "--hard", "main")
    head = _commit(repo, "a.md", "one\ntwo\nthree\n", "the same text, a new history")
    assert not brain.only_main_merged_since(approved, head, run(repo, "rev-parse", "main"))
    assert not brain.only_main_merged_since("0" * 40, head, run(repo, "rev-parse", "main"))


def test_a_clean_merge_of_another_branch_needs_a_new_approval(pr_branch, monkeypatch):
    """Only a merge with main keeps the approval: a branch that is not main brings code nobody approved, even when git
    merges it without a conflict (#183's open case)."""
    repo, approved = pr_branch
    monkeypatch.chdir(repo)
    run(repo, "checkout", "-q", "-b", "side", "main")
    _commit(repo, "s.md", "never reviewed\n", "work on another branch")
    run(repo, "checkout", "-q", "task/T-1")
    run(repo, "merge", "-q", "--no-edit", "side")                       # clean: s.md is new
    head = run(repo, "rev-parse", "HEAD")
    assert not brain.only_main_merged_since(approved, head, run(repo, "rev-parse", "main"))


def test_main_merged_into_another_branch_first_still_needs_a_new_approval(pr_branch, monkeypatch):
    """The same code through a branch that merged main first: every merge after the approval must take main itself."""
    repo, approved = pr_branch
    monkeypatch.chdir(repo)
    run(repo, "checkout", "-q", "-b", "side", approved)
    _commit(repo, "s.md", "never reviewed\n", "work on another branch")
    run(repo, "merge", "-q", "--no-edit", "main")
    run(repo, "checkout", "-q", "task/T-1")
    run(repo, "merge", "-q", "--no-edit", "side")                       # a fast-forward
    head = run(repo, "rev-parse", "HEAD")
    assert not brain.only_main_merged_since(approved, head, run(repo, "rev-parse", "main"))


# --- gh_json: one retry for a short or failed `gh api` answer (main-guard's "unexpected end of JSON input") ----------
class _Done:
    def __init__(self, code: int, out: str, err: str = ""):
        self.returncode, self.stdout, self.stderr = code, out, err


def test_gh_json_retries_a_truncated_answer(monkeypatch):
    answers = [_Done(0, '[{"number": 1'), _Done(0, '[{"number": 1}]')]
    monkeypatch.setattr(brain.subprocess, "run", lambda *a, **k: answers.pop(0))
    monkeypatch.setattr(brain.time, "sleep", lambda s: None)
    assert brain.gh_json("repos/o/r/pulls") == [{"number": 1}]
    assert answers == []


def test_gh_json_retries_a_failed_call_then_gives_up(monkeypatch):
    calls = []
    monkeypatch.setattr(brain.subprocess, "run", lambda *a, **k: calls.append(a) or _Done(1, "", "HTTP 502"))
    monkeypatch.setattr(brain.time, "sleep", lambda s: None)
    with pytest.raises(brain.BrainError, match="HTTP 502"):
        brain.gh_json("repos/o/r/pulls")
    assert len(calls) == brain.GH_TRIES


def test_gh_json_does_not_retry_a_good_answer(monkeypatch):
    calls = []
    monkeypatch.setattr(brain.subprocess, "run", lambda *a, **k: calls.append(a) or _Done(0, "null"))
    assert brain.gh_json("repos/o/r/pulls") is None
    assert len(calls) == 1


# --- open pull requests in `brain.py start`: drafts are tasks in progress, not review requests -----------------------
def _open_pr(n, draft):
    return {"number": n, "title": f"T-{n}", "author": {"login": "alice"}, "headRefName": f"task/T-{n}", "isDraft": draft}


def test_draft_pull_requests_are_listed_as_work_in_progress_not_for_review():
    lines = brain.format_prs([_open_pr(1, False), _open_pr(2, True)])
    review = lines.index(next(ln for ln in lines if ln.startswith("Pull requests waiting for review")))
    drafts = lines.index(next(ln for ln in lines if ln.startswith("Tasks in progress")))
    assert "#1 " in lines[review + 1] and drafts > review + 1 and "#2 " in lines[drafts + 1]
    only_drafts = brain.format_prs([_open_pr(2, True)])
    assert only_drafts[0] == "Pull requests waiting for review: none" and "#2 " in only_drafts[-1]
    assert brain.format_prs([]) == ["Pull requests waiting for review: none"]


def test_guard_push_refuses_main_only(monkeypatch, capsys):
    monkeypatch.setenv("PRE_COMMIT_REMOTE_BRANCH", "refs/heads/main")
    assert brain.main(["guard-push"]) == 1
    assert "pull request" in capsys.readouterr().err
    monkeypatch.setenv("PRE_COMMIT_REMOTE_BRANCH", "refs/heads/task/T-0013-x")
    assert brain.main(["guard-push"]) == 0


# --- one lease per VM (PARALLEL_LANES change 1, LANES-1) ------------------------------------------------------------

def vm_lease(repo: Path, vm: str) -> dict:
    return lease_of(repo)["vms"][vm]


def test_two_developers_hold_one_vm_each(repos, monkeypatch, capsys):
    as_(monkeypatch, repos["alice"])
    assert brain.main(["start", "--vm", "vm-166", "--task", "T-0029"]) == 0
    as_(monkeypatch, repos["bob"], T0 + dt.timedelta(minutes=5))
    assert brain.main(["start", "--vm", "vm-095", "--task", "T-0025"]) == 0
    assert vm_lease(repos["bob"], "vm-166")["holder"] == "alice"
    assert vm_lease(repos["bob"], "vm-095")["holder"] == "bob"
    capsys.readouterr()
    assert brain.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "vm-095: ACTIVE: bob" in out and "vm-166: ACTIVE: alice" in out
    as_(monkeypatch, repos["alice"], T0 + dt.timedelta(minutes=10))
    assert brain.main(["start", "--vm", "vm-095"]) == 2
    assert "vm-095 is in use by bob" in capsys.readouterr().err


def test_claiming_both_vms_is_refused_while_one_is_held(repos, monkeypatch, capsys):
    as_(monkeypatch, repos["alice"])
    assert brain.main(["start", "--vm", "vm-166"]) == 0
    as_(monkeypatch, repos["bob"], T0 + dt.timedelta(minutes=5))
    assert brain.main(["start"]) == 2                       # the default is both VMs, as before
    assert "vm-166 is in use by alice" in capsys.readouterr().err
    assert vm_lease(repos["bob"], "vm-095") is None         # nothing claimed: all or nothing


def test_the_summary_keeps_an_older_brain_py_out_of_a_busy_lab(repos, monkeypatch):
    """Branches made before LANES-1 run the old brain.py, which reads only the top-level fields."""
    as_(monkeypatch, repos["alice"])
    assert brain.main(["start", "--vm", "vm-166"]) == 0
    as_(monkeypatch, repos["bob"], T0 + dt.timedelta(minutes=5))
    assert brain.main(["start", "--vm", "vm-095"]) == 0
    top = lease_of(repos["bob"])
    assert top["holder"] == "alice+bob" and top["released"] is False   # an old start refuses: not its own holder
    assert top["expires_at"] == (T0 + dt.timedelta(minutes=65)).isoformat()
    assert brain.main(["release"]) == 0
    top = lease_of(repos["bob"])
    assert top["holder"] == "alice" and top["released"] is False


def test_a_lease_in_the_old_format_holds_both_vms(repos, monkeypatch, capsys):
    as_(monkeypatch, repos["alice"])
    old = {"holder": "alice", "session_id": "s1", "task": "T-0028", "branch": "task/T-0028-x", "base_commit": "x",
           "started_at": T0.isoformat(), "expires_at": (T0 + dt.timedelta(minutes=60)).isoformat(),
           "released": False, "handoff": None}
    brain.write_lease(old, None, "claim: alice (T-0028)")
    as_(monkeypatch, repos["bob"], T0 + dt.timedelta(minutes=5))
    assert brain.main(["start", "--vm", "vm-095"]) == 2
    assert "vm-095 is in use by alice" in capsys.readouterr().err
    as_(monkeypatch, repos["bob"], T0 + dt.timedelta(minutes=61))
    assert brain.main(["start", "--vm", "vm-095"]) == 0
    assert vm_lease(repos["bob"], "vm-095")["took_over_from"]["holder"] == "alice"
    assert vm_lease(repos["bob"], "vm-166")["holder"] == "alice"       # still hers (expired), not taken


def test_an_older_brain_py_renew_and_release_of_the_summary_are_honoured(repos, monkeypatch):
    as_(monkeypatch, repos["alice"])
    assert brain.main(["start"]) == 0
    raw, sha = brain.read_lease()
    raw["expires_at"] = (T0 + dt.timedelta(minutes=180)).isoformat()     # what the old `renew` writes
    sha = brain.write_lease(raw, sha, "renew: alice")
    vms, _, _ = brain.read_leases()
    assert all(v["expires_at"] == raw["expires_at"] for v in vms.values())
    raw["released"] = True                                                 # what the old `release` writes
    brain.write_lease(raw, sha, "release: alice")
    as_(monkeypatch, repos["bob"], T0 + dt.timedelta(minutes=5))
    assert brain.main(["start", "--vm", "vm-095"]) == 0


def test_renew_and_release_touch_only_my_own_vm(repos, monkeypatch):
    as_(monkeypatch, repos["alice"])
    assert brain.main(["start", "--vm", "vm-166"]) == 0
    as_(monkeypatch, repos["bob"], T0 + dt.timedelta(minutes=5))
    assert brain.main(["start", "--vm", "vm-095"]) == 0
    as_(monkeypatch, repos["bob"], T0 + dt.timedelta(minutes=30))
    assert brain.main(["renew", "--minutes", "120"]) == 0
    assert vm_lease(repos["bob"], "vm-095")["expires_at"] == (T0 + dt.timedelta(minutes=150)).isoformat()
    assert vm_lease(repos["bob"], "vm-166")["expires_at"] == (T0 + dt.timedelta(minutes=60)).isoformat()
    assert brain.main(["handoff", "evaluation running; results in eval-results"]) == 0
    assert vm_lease(repos["bob"], "vm-095")["released"] is True
    assert vm_lease(repos["bob"], "vm-166")["released"] is False


def test_renewing_one_vm_does_not_renew_the_other(repos, monkeypatch):
    """The summary then carries the later expiry; that is not an old brain.py's renew."""
    as_(monkeypatch, repos["alice"])
    assert brain.main(["start"]) == 0
    assert brain.main(["renew", "--vm", "vm-166", "--minutes", "120"]) == 0
    vms, _, _ = brain.read_leases()
    assert vms["vm-166"]["expires_at"] == (T0 + dt.timedelta(minutes=120)).isoformat()
    assert vms["vm-095"]["expires_at"] == (T0 + dt.timedelta(minutes=60)).isoformat()


def test_vm095_alone_reminds_that_an_agent_change_needs_both(repos, monkeypatch, capsys):
    as_(monkeypatch, repos["alice"])
    assert brain.main(["start", "--vm", "vm-095"]) == 0
    out = capsys.readouterr().out
    assert "needs BOTH leases" in out
    assert "[VM vm-095 · bash]" in out and "[VM vm-166 · bash]" not in out


# --- journal entries as files and the roll-up (PARALLEL_LANES change 2, LANES-2) ----------------------------------

ENTRY_A = """## 2026-10-10 — T-0040: first thing (T-0040)

Type: implementation
Who: alice (+ agent)
Decision / result: done; see [the task](../../tasks/current/T-0040.md).
References: [`../../tasks/current/T-0040.md`](../../tasks/current/T-0040.md), [web](https://example.com/a).

### Test state

**T-0040, 2026-10-10:** 3 tests, red seen ([task](../../tasks/current/T-0040.md)).

### Next step

**T-0040 (2026-10-10, `alice`):** merged; next T-0041 ([task](../../tasks/current/T-0040.md)).
"""

ENTRY_B = """## 2026-10-11 — T-0041: second thing (T-0041)

Type: verification
Who: bob (+ agent)
Decision / result: verified on vm-166.
"""


def brain_tree(repo: Path) -> Path:
    b = repo / "brain"
    for d in ("journal/entries", "tdd", "tasks/current"):
        (b / d).mkdir(parents=True, exist_ok=True)
    (b / "journal" / "logbook.md").write_bytes(b"# Logbook\n\n## 2026-10-09 \xe2\x80\x94 old entry\n\nType: x\n")
    (b / "tdd" / "CURRENT_TEST_STATE.md").write_bytes(
        b"# Current test state\n\n**Last updated:** 2026-10-09\n\n**OLD, 2026-10-09:** old line.\n")
    (b / "NEXT_STEP.md").write_bytes(b"# Next step\n\n**OLD (2026-10-09):** old next step.\n")
    (b / "tasks" / "current" / "T-0040.md").write_bytes(b"# T-0040\n")
    return b


def test_rollup_folds_entries_into_the_summaries_and_removes_them(repos, monkeypatch, capsys):
    repo = repos["alice"]
    as_(monkeypatch, repo)
    b = brain_tree(repo)
    (b / "journal" / "entries" / "2026-10-11-T-0041.md").write_bytes(ENTRY_B.encode())
    (b / "journal" / "entries" / "2026-10-10-T-0040.md").write_bytes(ENTRY_A.encode())
    assert brain.main(["rollup"]) == 0
    log = (b / "journal" / "logbook.md").read_text(encoding="utf-8")
    assert log.index("old entry") < log.index("T-0040: first thing") < log.index("T-0041: second thing")
    assert "### Test state" not in log and "### Next step" not in log      # only the journal part goes to the log
    assert "](../tasks/current/T-0040.md)" in log                         # links rebased from entries/ to journal/
    assert "[`../tasks/current/T-0040.md`](../tasks/current/T-0040.md)" in log   # a shown path moves with its link
    assert "[web](https://example.com/a)" in log                           # absolute links untouched
    tests = (b / "tdd" / "CURRENT_TEST_STATE.md").read_text(encoding="utf-8")
    assert tests.index("**Last updated:**") < tests.index("**T-0040, 2026-10-10:**") < tests.index("**OLD")
    assert "](../tasks/current/T-0040.md)" in tests
    nxt = (b / "NEXT_STEP.md").read_text(encoding="utf-8")
    assert nxt.index("# Next step") < nxt.index("**T-0040 (2026-10-10") < nxt.index("**OLD")
    assert "](tasks/current/T-0040.md)" in nxt
    assert list((b / "journal" / "entries").glob("*.md")) == []
    assert "2 journal entries rolled up" in capsys.readouterr().out
    assert brain.main(["lint"]) in (0, 1)                                  # the tree is readable by lint
    assert "broken link" not in capsys.readouterr().out


def test_rollup_with_nothing_to_do_changes_nothing(repos, monkeypatch, capsys):
    repo = repos["alice"]
    as_(monkeypatch, repo)
    b = brain_tree(repo)
    before = (b / "journal" / "logbook.md").read_bytes()
    assert brain.main(["rollup"]) == 0
    assert "nothing to roll up" in capsys.readouterr().out
    assert (b / "journal" / "logbook.md").read_bytes() == before


def test_rollup_refuses_an_entry_without_its_heading(repos, monkeypatch, capsys):
    repo = repos["alice"]
    as_(monkeypatch, repo)
    b = brain_tree(repo)
    (b / "journal" / "entries" / "2026-10-10-T-0040.md").write_bytes(b"Type: no heading\n")
    assert brain.main(["rollup"]) == 2
    assert "must start with '## <date>" in capsys.readouterr().err
    assert (b / "journal" / "entries" / "2026-10-10-T-0040.md").exists()  # nothing half-done


def _rule_on_main(repo: Path) -> None:
    """main gets brain.py with the roll-up (the rule applies to branches created from it)."""
    (repo / "brain" / "tools").mkdir(parents=True, exist_ok=True)
    (repo / "brain" / "tools" / "brain.py").write_bytes(b"def cmd_rollup(args):\n    pass\n")
    brain_tree(repo)
    run(repo, "add", "-A")
    run(repo, "commit", "-m", "main with the roll-up")
    run(repo, "push", "origin", "HEAD:main")
    run(repo, "fetch", "origin")


def test_lint_refuses_a_task_branch_that_edits_a_shared_summary(repos, monkeypatch, capsys):
    repo = repos["alice"]
    as_(monkeypatch, repo)
    _rule_on_main(repo)
    run(repo, "checkout", "-b", "task/T-0042-x")
    (repo / "brain" / "NEXT_STEP.md").write_bytes(b"# Next step\n\nedited on a task branch\n")
    capsys.readouterr()
    assert brain.main(["lint"]) == 1
    out = capsys.readouterr().out
    assert "brain/NEXT_STEP.md: a task branch does not edit the shared summaries" in out
    assert "journal/entries/" in out


def test_lint_lets_a_rollup_branch_and_main_edit_the_summaries(repos, monkeypatch, capsys):
    repo = repos["alice"]
    as_(monkeypatch, repo)
    _rule_on_main(repo)
    (repo / "brain" / "NEXT_STEP.md").write_bytes(b"# Next step\n\nedited on main\n")
    capsys.readouterr()
    brain.main(["lint"])
    assert "shared summaries" not in capsys.readouterr().out
    run(repo, "checkout", "-b", "task/rollup-2026-10-10")
    brain.main(["lint"])
    assert "shared summaries" not in capsys.readouterr().out


def test_lint_reads_the_pr_branch_from_ci_when_head_is_detached(repos, monkeypatch, capsys):
    """On a pull_request run CI checks out a detached merge commit; GITHUB_HEAD_REF names the PR's branch."""
    repo = repos["alice"]
    as_(monkeypatch, repo)
    _rule_on_main(repo)
    run(repo, "checkout", "--detach")
    (repo / "brain" / "NEXT_STEP.md").write_bytes(b"# Next step\n\nedited by a task PR\n")
    capsys.readouterr()
    brain.main(["lint"])
    assert "shared summaries" not in capsys.readouterr().out             # detached, no PR: nothing to check
    monkeypatch.setenv("GITHUB_HEAD_REF", "task/T-0043-x")
    assert brain.main(["lint"]) == 1
    assert "brain/NEXT_STEP.md: a task branch does not edit the shared summaries" in capsys.readouterr().out


def test_lint_keeps_branches_made_before_the_rule(repos, monkeypatch, capsys):
    """PARALLEL_LANES transition: a branch whose base has no roll-up keeps its summary edits."""
    repo = repos["alice"]
    as_(monkeypatch, repo)
    run(repo, "checkout", "-b", "task/T-0039-old")
    brain_tree(repo)
    (repo / "brain" / "NEXT_STEP.md").write_bytes(b"# Next step\n\nedited before the rule\n")
    capsys.readouterr()
    brain.main(["lint"])
    assert "shared summaries" not in capsys.readouterr().out


def test_rollup_orders_same_day_entries_by_when_they_reached_the_branch(repos, monkeypatch):
    """Same date, merged Z first then A: the logbook follows the merge order, not the file names (LANES-2 follow-up,
    found in the first roll-up, PR #73)."""
    repo = repos["alice"]
    as_(monkeypatch, repo)
    b = brain_tree(repo)
    run(repo, "add", "-A")
    run(repo, "commit", "-m", "brain")
    entries = b / "journal" / "entries"
    for name, title in (("2026-10-10-Z.md", "Z merged first"), ("2026-10-10-A.md", "A merged second")):
        (entries / name).write_bytes(f"## 2026-10-10 — {title}\n\nType: x\n".encode())
        run(repo, "add", "-A")
        run(repo, "commit", "-m", f"merge {name}")
    (entries / "2026-10-09-M.md").write_bytes(b"## 2026-10-09 \xe2\x80\x94 M, an older day, not committed yet\n\nType: x\n")
    assert brain.main(["rollup"]) == 0
    log = (b / "journal" / "logbook.md").read_text(encoding="utf-8")
    assert log.index("M, an older day") < log.index("Z merged first") < log.index("A merged second")


def _branch_then_rollup_on_main(repo: Path) -> None:
    """A task branch with its own commit, then main moves on with a roll-up (summaries edited on main)."""
    run(repo, "checkout", "-b", "task/T-0044-x")
    (repo / "brain" / "journal" / "entries").mkdir(parents=True, exist_ok=True)
    (repo / "brain" / "journal" / "entries" / "2026-10-12-T-0044.md").write_bytes(b"## 2026-10-12 - x (T-0044)\n")
    run(repo, "add", "-A")
    run(repo, "commit", "-m", "task work")
    run(repo, "checkout", "main")
    (repo / "brain" / "NEXT_STEP.md").write_bytes(b"# Next step\n\nrolled up on main\n")
    run(repo, "add", "-A")
    run(repo, "commit", "-m", "roll-up on main")
    run(repo, "push", "origin", "HEAD:main")
    run(repo, "fetch", "origin")
    run(repo, "checkout", "task/T-0044-x")


def test_lint_lets_a_task_branch_merge_main_after_a_rollup(repos, monkeypatch, capsys):
    """LINT-merge-base: during `git merge origin/main` HEAD is still the branch's old tip, so the summaries changed by
    main's roll-up looked like the branch's own edits and the merge commit was refused (PRs #101, #103)."""
    repo = repos["alice"]
    as_(monkeypatch, repo)
    _rule_on_main(repo)
    _branch_then_rollup_on_main(repo)
    run(repo, "merge", "--no-ff", "--no-commit", "origin/main")
    capsys.readouterr()
    brain.main(["lint"])
    assert "shared summaries" not in capsys.readouterr().out
    run(repo, "commit", "-m", "merge main")                               # after the merge commit: still clean
    brain.main(["lint"])
    assert "shared summaries" not in capsys.readouterr().out


def test_lint_still_refuses_a_summary_edit_made_during_a_merge_of_main(repos, monkeypatch, capsys):
    repo = repos["alice"]
    as_(monkeypatch, repo)
    _rule_on_main(repo)
    _branch_then_rollup_on_main(repo)
    run(repo, "merge", "--no-ff", "--no-commit", "origin/main")
    (repo / "brain" / "NEXT_STEP.md").write_bytes(b"# Next step\n\nrolled up on main\n\nand edited by the branch\n")
    capsys.readouterr()
    assert brain.main(["lint"]) == 1
    assert "brain/NEXT_STEP.md: a task branch does not edit the shared summaries" in capsys.readouterr().out


def test_gh_json_raises_a_404_at_once(monkeypatch):
    calls = []
    monkeypatch.setattr(brain.subprocess, "run",
                        lambda *a, **k: calls.append(a) or _Done(1, "", "gh: Branch not found (HTTP 404)"))
    with pytest.raises(brain.BrainError, match="HTTP 404"):
        brain.gh_json("repos/o/r/branches/gone")
    assert len(calls) == 1
