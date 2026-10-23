"""Measure review readiness from exact Git ancestry and complete read-only evidence."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from review_common import (
    ReviewError,
    ancestor,
    discussion,
    emit,
    git,
    in_repo,
    live_snapshot,
    load_brain,
    read_json,
    refusal,
    resolve,
)


def latest_checks(checks: list[dict]) -> dict[str, dict]:
    result = {}
    for check in checks:
        name = check["name"]
        if name not in result or int(check["id"]) > int(result[name]["id"]):
            result[name] = check
    return result


def report(repo: Path, data: dict, receipt: str | None, keep_branch: bool, findings_clear: bool) -> dict:
    required = ("pr", "main_sha", "branch_exists", "files", "checks", "main_checks",
                "reviews", "comments", "review_comments")
    if data.get("complete") is not True or any(key not in data for key in required):
        raise ReviewError("Complete PR, check, file and discussion evidence is required")
    if not all(isinstance(data[key], list) and all(isinstance(item, dict) for item in data[key])
               for key in required[3:]):
        raise ReviewError("Evidence lists have an invalid shape")
    pr = data["pr"]
    head = resolve(repo, pr["head"]["sha"])
    main = resolve(repo, data["main_sha"])
    local_main = resolve(repo, "origin/main")
    brain = load_brain(repo, local_main)
    items, digest = discussion(data)
    reasons = []

    def refuse(kind: str, detail: str, category: str = "unknown") -> None:
        reasons.append({"kind": kind, "category": category, "detail": detail})

    if main != local_main or pr["base"]["ref"] != "main" or pr["base"]["sha"] != main:
        refuse("ancestry", "Recorded remote main differs from fetched origin/main; refresh and recheck")
    up_to_date = ancestor(repo, main, head)
    if not up_to_date:
        refuse("ancestry", "PR head does not contain main; GitHub CLEAN is not an ancestry check", "code")
    if pr["state"] != "open" or pr["draft"] is not False:
        refuse("pr", "PR must be open and ready for review")
    if data["branch_exists"] is not True:
        refuse("branch", "The PR source branch is missing or moved")
    if not keep_branch:
        refuse("branch", "Retain the source branch after a merge; never use --delete-branch")
    if receipt != digest:
        refuse("discussion", "Read every review, conversation comment and inline comment, then acknowledge this digest")
    if not findings_clear:
        refuse("findings", "The reviewer has not marked the findings clear")

    selected = latest_checks(data["checks"])
    required_checks = {name: selected[name] for name in brain.SELF_MERGE_CHECKS if name in selected}
    # Delegate the policy's non-author LOCAL CI exception; protected paths are checked separately below.
    local_ci = False
    if not required_checks:
        local_ci = brain.self_merge_problem(pr, [], [], data["comments"]) is None
    diagnoses = data.get("check_diagnoses", {})
    for name in brain.SELF_MERGE_CHECKS:
        check = required_checks.get(name)
        if check is None:
            if not local_ci:
                refuse("check", name + " missing on the exact head; CI or authorized local-CI evidence is required")
            continue
        if (check.get("head_sha") == head and check.get("status") == "completed"
                and check.get("conclusion") == "success"):
            continue
        if not isinstance(diagnoses, dict):
            raise ReviewError("Check diagnoses must be an object")
        diagnosis = diagnoses.get(str(check["id"]), {})
        if not isinstance(diagnosis, dict):
            raise ReviewError("Every check diagnosis must be an object")
        category = diagnosis.get("category", "unknown")
        evidence = diagnosis.get("evidence", "")
        if category not in ("code", "infrastructure", "unknown") or not isinstance(evidence, str) or not evidence.strip():
            category, evidence = "unknown", "inspect the exact run's logs; no cause has been established"
        detail = name + " is not green on the exact head (" + str(check.get("conclusion")) + "): " + evidence
        refuse("check", detail, category)
    guard = latest_checks(data["main_checks"]).get("main-guard")
    if not (guard and guard.get("head_sha") == main and guard.get("status") == "completed"
            and guard.get("conclusion") == "success"):
        refuse("main-guard", "Current main-guard is missing or not green; stop merge advice")

    paths = brain.changed_paths(data["files"])
    if any(not isinstance(item.get("filename"), str) for item in data["files"]):
        raise ReviewError("Every changed file must name its path")
    if any(not isinstance(path, str) for path in paths):
        raise ReviewError("Every rename source must name its path")
    protected = sorted({path for path in paths if brain.is_protected(path)})
    active = {}
    for review in sorted(data["reviews"], key=lambda value: int(value["id"])):
        if review["state"] in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            active[review["user"]["login"]] = review
    author = pr["user"]["login"]
    if any(review["state"] == "CHANGES_REQUESTED" for user, review in active.items() if user != author):
        refuse("approval", "A teammate's request for changes is still active")
    first_parents = set(git(repo, "rev-list", "--first-parent", head).splitlines())
    approved = False
    for user, review in active.items():
        if user == author or review["state"] != "APPROVED":
            continue
        commit = review.get("commit_id")
        if commit not in first_parents:
            continue
        with in_repo(repo):
            if brain.only_main_merged_since(commit, head, main):
                approved = True
    if not approved:
        why = brain.self_merge_problem(pr, list(selected.values()), paths, data["comments"],
                                       up_to_date=up_to_date, merge_commit=True,
                                       branch_kept=keep_branch and data["branch_exists"] is True)
        if why is not None:
            refuse("approval" if protected else "self-merge", "Self-merge refused: " + why)
    return {
        "ready": not reasons, "head": head, "main": main, "pr": pr["number"],
        "reasons": reasons, "protected_paths": protected, "discussion_digest": digest,
        "discussion": items if receipt != digest else {name: len(value) for name, value in items.items()},
        "merge_method": "merge", "keep_branch": keep_branch,
        "recommendation": "Ready for the developer's review decision" if not reasons else "Not ready",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--snapshot", type=Path)
    source.add_argument("--pr", type=int)
    parser.add_argument("--github-repo")
    parser.add_argument("--discussions-read", metavar="DIGEST")
    parser.add_argument("--keep-branch", action="store_true")
    parser.add_argument("--findings-clear", action="store_true")
    parser.add_argument("--check-diagnoses", type=Path)
    args = parser.parse_args()
    try:
        data = read_json(args.snapshot) if args.snapshot else live_snapshot(args.repo, args.pr, args.github_repo)
        if args.check_diagnoses:
            data["check_diagnoses"] = read_json(args.check_diagnoses)
        result = report(args.repo, data, args.discussions_read, args.keep_branch, args.findings_clear)
        emit(result)
        return 0 if result["ready"] else 1
    except (ReviewError, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        return refusal(error)


if __name__ == "__main__":
    raise SystemExit(main())
