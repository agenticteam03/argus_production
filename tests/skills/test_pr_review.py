"""Exercise read-only review helpers on small local Git histories and recorded API data."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / ".claude" / "skills" / "pr-review" / "scripts"


def git(repo, *args, check=True):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                            encoding="utf-8", check=False, timeout=30)
    if check:
        assert result.returncode == 0, result.stderr
    return result.stdout.strip() if check else result


def commit(repo, path, content, message):
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content.encode("utf-8"))
    git(repo, "add", "--", path)
    git(repo, "commit", "-qm", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def history(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "Review fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    git(repo, "config", "commit.gpgsign", "false")
    git(repo, "config", "core.autocrlf", "false")
    brain = repo / "brain" / "tools" / "brain.py"
    brain.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "brain" / "tools" / "brain.py", brain)
    git(repo, "add", "--", "brain/tools/brain.py")
    main = commit(repo, "app.py", "mode = 'base'\n", "base")
    git(repo, "update-ref", "refs/remotes/origin/main", main)
    git(repo, "checkout", "-qb", "task/example")
    head = commit(repo, "app.py", "mode = 'approved'\n", "feature")
    return {"repo": repo, "main": main, "head": head}


def run_helper(name, repo, *args):
    result = subprocess.run([sys.executable, str(SCRIPTS / name), "--repo", str(repo), *map(str, args)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, timeout=30)
    assert result.stderr == "", result.stderr
    return result.returncode, json.loads(result.stdout)


def snapshot(history):
    head, main = history["head"], history["main"]
    return {
        "complete": True,
        "pr": {"number": 7, "state": "open", "draft": False, "user": {"login": "author"},
               "head": {"sha": head, "ref": "task/example"}, "base": {"sha": main, "ref": "main"}},
        "main_sha": main, "branch_exists": True,
        "files": [{"filename": "app.py", "status": "modified"}],
        "checks": [{"id": i, "name": name, "head_sha": head, "status": "completed", "conclusion": "success"}
                   for i, name in enumerate(("test", "frontend"), 1)],
        "main_checks": [{"id": 3, "name": "main-guard", "head_sha": main,
                         "status": "completed", "conclusion": "success"}],
        "reviews": [], "comments": [], "review_comments": [],
    }


def ready(history, tmp_path, data=None, *, read=True, keep=True, findings=True):
    data = snapshot(history) if data is None else data
    source = tmp_path / "snapshot.json"
    source.write_bytes(json.dumps(data).encode("utf-8"))
    args = ["--snapshot", source]
    if keep:
        args.append("--keep-branch")
    if findings:
        args.append("--findings-clear")
    if read:
        _, preview = run_helper("merge_ready.py", history["repo"], *args)
        args.extend(["--discussions-read", preview["discussion_digest"]])
    return run_helper("merge_ready.py", history["repo"], *args)


def test_clean_pr_is_ready_without_executing_an_action(history, tmp_path):
    repo = history["repo"]
    before = (git(repo, "rev-parse", "HEAD"), git(repo, "status", "--porcelain"),
              git(repo, "for-each-ref", "--format=%(refname) %(objectname)"))
    code, report = ready(history, tmp_path)
    assert code == 0
    assert report["ready"] is True
    assert report["merge_method"] == "merge" and report["keep_branch"] is True
    assert before == (git(repo, "rev-parse", "HEAD"), git(repo, "status", "--porcelain"),
                      git(repo, "for-each-ref", "--format=%(refname) %(objectname)"))


def test_clean_github_merge_state_does_not_hide_a_head_behind_main(history, tmp_path):
    repo = history["repo"]
    git(repo, "checkout", "-q", "main")
    history["main"] = commit(repo, "main-only.txt", "new main\n", "advance main")
    git(repo, "update-ref", "refs/remotes/origin/main", history["main"])
    git(repo, "checkout", "-q", "task/example")
    data = snapshot(history)
    data["pr"]["mergeStateStatus"] = "CLEAN"
    code, report = ready(history, tmp_path, data)
    assert code == 1
    assert any(reason["kind"] == "ancestry" for reason in report["reasons"])


@pytest.mark.parametrize("setting", ["read", "keep", "findings"])
def test_readiness_requires_discussion_receipt_branch_retention_and_clear_findings(history, tmp_path, setting):
    code, report = ready(history, tmp_path, **{setting: False})
    assert code == 1 and report["ready"] is False


def test_every_review_and_comment_is_returned_before_acknowledgement(history, tmp_path):
    data = snapshot(history)
    data["comments"] = [{"id": i, "body": f"comment {i}"} for i in range(205)]
    data["review_comments"] = [{"id": 999, "body": "inline concern", "path": "app.py"}]
    code, report = ready(history, tmp_path, data, read=False)
    assert code == 1
    assert len(report["discussion"]["comments"]) == 205
    assert report["discussion"]["review_comments"][0]["body"] == "inline concern"


def test_receipt_is_invalidated_by_a_new_comment(history, tmp_path):
    data = snapshot(history)
    source = tmp_path / "snapshot.json"
    source.write_bytes(json.dumps(data).encode("utf-8"))
    _, first = run_helper("merge_ready.py", history["repo"], "--snapshot", source)
    data["comments"].append({"id": 1, "body": "a new concern"})
    source.write_bytes(json.dumps(data).encode("utf-8"))
    code, report = run_helper("merge_ready.py", history["repo"], "--snapshot", source,
                              "--keep-branch", "--findings-clear", "--discussions-read", first["discussion_digest"])
    assert code == 1
    assert any(reason["kind"] == "discussion" for reason in report["reasons"])


@pytest.mark.parametrize("bad", ["incomplete", "missing-comments", "stale-main", "missing-head"])
def test_missing_or_stale_data_refuses_readiness(history, tmp_path, bad):
    data = snapshot(history)
    if bad == "incomplete":
        data["complete"] = False
    elif bad == "missing-comments":
        del data["review_comments"]
    elif bad == "stale-main":
        data["main_sha"] = "a" * 40
    else:
        data["pr"]["head"]["sha"] = "b" * 40
    code, report = ready(history, tmp_path, data, read=False)
    assert code != 0 and report["ready"] is False


@pytest.mark.parametrize("category", ["code", "infrastructure", "unknown"])
def test_failed_check_explains_its_category_and_never_becomes_a_pass(history, tmp_path, category):
    data = snapshot(history)
    data["checks"][0]["conclusion"] = "failure"
    data["check_diagnoses"] = {"1": {"category": category, "evidence": "recorded runner log evidence"}}
    code, report = ready(history, tmp_path, data)
    assert code == 1
    failure = next(reason for reason in report["reasons"] if reason["kind"] == "check")
    assert failure["category"] == category
    assert "recorded runner log evidence" in failure["detail"]


def test_only_a_completed_exact_head_rerun_can_replace_a_failed_check(history, tmp_path):
    data = snapshot(history)
    old = data["checks"][0]
    old["conclusion"] = "failure"
    data["checks"].append({**old, "id": 10, "conclusion": "success", "head_sha": history["main"]})
    assert ready(history, tmp_path, data)[0] == 1
    data["checks"][-1]["head_sha"] = history["head"]
    assert ready(history, tmp_path, data)[0] == 0


def test_red_main_guard_blocks_otherwise_green_pr(history, tmp_path):
    data = snapshot(history)
    data["main_checks"][0]["conclusion"] = "failure"
    assert ready(history, tmp_path, data)[0] == 1


def test_renaming_a_protected_path_still_needs_a_teammates_current_approval(history, tmp_path):
    data = snapshot(history)
    data["files"] = [{"filename": "ordinary.py", "previous_filename": "ops/deploy.sh", "status": "renamed"}]
    code, report = ready(history, tmp_path, data)
    assert code == 1 and "ops/deploy.sh" in report["protected_paths"]
    data["reviews"] = [{"id": 1, "user": {"login": "author"}, "state": "APPROVED",
                        "commit_id": history["head"]}]
    assert ready(history, tmp_path, data)[0] == 1
    data["reviews"][0]["user"]["login"] = "teammate"
    assert ready(history, tmp_path, data)[0] == 0


def test_a_later_changes_request_or_dismissal_cannot_leave_an_old_approval_active(history, tmp_path):
    data = snapshot(history)
    data["files"] = [{"filename": "ops/deploy.sh"}]
    data["reviews"] = [{"id": 1, "user": {"login": "teammate"}, "state": "APPROVED",
                        "commit_id": history["head"]}]
    for state in ("CHANGES_REQUESTED", "DISMISSED"):
        data["reviews"] = data["reviews"][:1] + [{"id": 2, "user": {"login": "teammate"},
                                                 "state": state, "commit_id": history["head"]}]
        assert ready(history, tmp_path, data)[0] == 1


@pytest.mark.parametrize("approved", [False, True])
def test_large_unprotected_pr_requires_a_teammate_instead_of_self_merge(history, tmp_path, approved):
    data = snapshot(history)
    data["files"] = [{"filename": f"ordinary/file-{index}.py"} for index in range(100)]
    if approved:
        data["reviews"] = [{"id": 1, "user": {"login": "teammate"}, "state": "APPROVED",
                            "commit_id": history["head"]}]
    code, report = ready(history, tmp_path, data)
    assert code == (0 if approved else 1)
    assert report["protected_paths"] == []


def advance_main(history):
    repo = history["repo"]
    git(repo, "checkout", "-q", "main")
    history["main"] = commit(repo, "main-only.txt", "new main\n", "advance main")
    git(repo, "update-ref", "refs/remotes/origin/main", history["main"])
    git(repo, "checkout", "-q", "task/example")
    git(repo, "merge", "--no-edit", "main")
    return git(repo, "rev-parse", "HEAD")


def test_an_automatic_main_only_merge_keeps_approval_and_reports_the_merge(history):
    approved = history["head"]
    head = advance_main(history)
    code, report = run_helper("since_approval.py", history["repo"], "--approved", approved, "--head", head)
    assert code == 0 and report["approval_retained"] is True
    assert len(report["commits"]) == 1
    assert report["commits"][0]["main_only"] is True
    assert report["commits"][0]["remerge_diff"] == ""


def test_a_new_authored_commit_after_approval_needs_rereview(history):
    approved = history["head"]
    head = commit(history["repo"], "new.txt", "authored change\n", "new work")
    code, report = run_helper("since_approval.py", history["repo"], "--approved", approved, "--head", head)
    assert code == 1 and report["approval_retained"] is False
    assert len(report["commits"]) == 1


def test_a_conflict_resolution_hiding_behavior_needs_rereview(history):
    repo, approved = history["repo"], history["head"]
    git(repo, "checkout", "-q", "main")
    main = commit(repo, "app.py", "mode = 'main'\n", "main conflict")
    git(repo, "update-ref", "refs/remotes/origin/main", main)
    git(repo, "checkout", "-q", "task/example")
    assert git(repo, "merge", "--no-edit", "main", check=False).returncode != 0
    head = commit(repo, "app.py", "mode = 'hidden change'\n", "resolve conflict")
    code, report = run_helper("since_approval.py", repo, "--approved", approved, "--head", head)
    assert code == 1 and report["approval_retained"] is False
    assert "hidden change" in report["commits"][0]["remerge_diff"]


def test_a_protected_pr_keeps_approval_after_only_an_automatic_main_merge(history, tmp_path):
    approved = history["head"]
    history["head"] = advance_main(history)
    data = snapshot(history)
    data["files"] = [{"filename": "ops/deploy.sh"}]
    data["reviews"] = [{"id": 1, "user": {"login": "teammate"}, "state": "APPROVED", "commit_id": approved}]
    assert ready(history, tmp_path, data)[0] == 0


ENTRY = "brain/journal/entries/2026-10-22-T-fixture.md"
JOURNAL = "## 2026-10-22 — fixture\n\nType: test\nWho: fixture\nContext: preserved\n\nUnique evidence line.\n"


@pytest.mark.parametrize("keep_line", [True, False])
def test_rollup_preserves_every_removed_entry_payload(history, keep_line):
    repo = history["repo"]
    entry = JOURNAL + "\n### Test state\n\nGreen fixture.\n\n### Next step\n\nAwait review.\n"
    base = commit(repo, ENTRY, entry, "entry")
    commit(repo, "brain/journal/logbook.md", JOURNAL if keep_line else JOURNAL.replace("Unique evidence line.\n", ""),
           "roll up journal")
    commit(repo, "brain/tdd/CURRENT_TEST_STATE.md", "# Test state\n\nGreen fixture.\n", "roll up test state")
    commit(repo, "brain/NEXT_STEP.md", "# Next\n\nAwait review.\n", "roll up next step")
    git(repo, "rm", "--", ENTRY)
    git(repo, "commit", "-qm", "remove archived entry")
    code, report = run_helper("rollup_check.py", repo, "--base", base)
    assert code == (0 if keep_line else 1)
    assert report["ready"] is keep_line


def test_missing_input_has_a_sanitized_refusal(history, tmp_path):
    code, report = run_helper("merge_ready.py", history["repo"], "--snapshot", tmp_path / "absent.json")
    assert code == 2 and report["ready"] is False
    assert "Traceback" not in json.dumps(report)


def test_an_absent_source_branch_refuses_readiness(history, tmp_path):
    data = snapshot(history)
    data["branch_exists"] = False
    code, report = ready(history, tmp_path, data)
    assert code == 1
    assert any(reason["kind"] == "branch" for reason in report["reasons"])


def test_non_author_local_ci_evidence_only_replaces_absent_required_ci(history, tmp_path):
    data = snapshot(history)
    data["checks"] = []
    data["comments"] = [{"id": 1, "user": {"login": "teammate"},
                         "body": "LOCAL CI PASS report\ncommit " + history["head"]}]
    assert ready(history, tmp_path, data)[0] == 0
    data["comments"][0]["user"]["login"] = "author"
    assert ready(history, tmp_path, data)[0] == 1


def test_malformed_nested_evidence_has_no_traceback(history, tmp_path):
    data = snapshot(history)
    data["files"] = [42]
    code, report = ready(history, tmp_path, data, read=False)
    assert code == 2 and report["ready"] is False


@pytest.fixture
def common():
    spec = importlib.util.spec_from_file_location("review_common_fixture", SCRIPTS / "review_common.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def api(common, monkeypatch, tmp_path):
    head, main = "a" * 40, "b" * 40
    pr = {"head": {"sha": head, "ref": "task/example", "repo": {"full_name": "fixture/project"}},
          "updated_at": "captured", "changed_files": 1, "comments": 205, "review_comments": 0}
    comments = [{"id": i, "body": f"comment {i}"} for i in range(205)]
    prefix = "repos/fixture/project"
    replies = {
        f"{prefix}/pulls/7": pr,
        f"{prefix}/git/ref/heads/main": {"object": {"sha": main}},
        f"{prefix}/git/ref/heads/task%2Fexample": {"object": {"sha": head}},
        f"{prefix}/pulls/7/files?per_page=100": [[{"filename": "app.py"}]],
        f"{prefix}/pulls/7/reviews?per_page=100": [[]],
        f"{prefix}/issues/7/comments?per_page=100": [comments[:100], comments[100:200], comments[200:]],
        f"{prefix}/pulls/7/comments?per_page=100": [[]],
        f"{prefix}/commits/{head}/check-runs?per_page=100": [{"total_count": 0, "check_runs": []}],
        f"{prefix}/commits/{main}/check-runs?per_page=100": [{"total_count": 0, "check_runs": []}],
    }
    calls = []

    def fake_run(command, **kwargs):
        assert command[:4] == ["gh", "api", "--method", "GET"]
        calls.append(command)
        payload = replies[command[-1]]
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    monkeypatch.setattr(common.subprocess, "run", fake_run)
    return {"module": common, "repo": tmp_path, "replies": replies, "calls": calls}


def test_live_reader_uses_only_gets_and_reads_every_page(api):
    data = api["module"].live_snapshot(api["repo"], 7, "fixture/project")
    assert data["complete"] is True and len(data["comments"]) == 205
    for call in api["calls"]:
        if "?per_page=" in call[-1]:
            assert "--paginate" in call and "--slurp" in call


@pytest.mark.parametrize("bad", ["files", "checks"])
def test_live_reader_refuses_incomplete_pages(api, bad):
    if bad == "files":
        api["replies"]["repos/fixture/project/pulls/7"]["changed_files"] = 2
    else:
        api["replies"]["repos/fixture/project/commits/" + "a" * 40 + "/check-runs?per_page=100"][0]["total_count"] = 1
    with pytest.raises(api["module"].ReviewError, match="incomplete"):
        api["module"].live_snapshot(api["repo"], 7, "fixture/project")


def test_an_unparseable_removed_journal_refuses_with_a_diagnostic(history):
    repo = history["repo"]
    base = commit(repo, ENTRY, "This entry has no required date heading.\n", "malformed entry")
    git(repo, "rm", "--", ENTRY)
    git(repo, "commit", "-qm", "remove malformed entry")
    code, report = run_helper("rollup_check.py", repo, "--base", base)
    assert code == 2 and report["ready"] is False
