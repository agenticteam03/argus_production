"""Shared Git/GitHub readers; never checkout, fetch, review, push or merge."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
import types
from pathlib import Path
from urllib.parse import quote


class ReviewError(Exception):
    """Missing or incomplete evidence must refuse readiness."""


def git_result(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "--no-pager", "-C", str(repo), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", check=False, timeout=30)


def git(repo: Path, *args: str) -> str:
    result = git_result(repo, *args)
    if result.returncode != 0:
        raise ReviewError("Required local Git evidence is unavailable")
    return result.stdout.rstrip("\n")


def resolve(repo: Path, ref: str) -> str:
    return git(repo, "rev-parse", "--verify", "--end-of-options", ref + "^{commit}")


def ancestor(repo: Path, before: str, after: str) -> bool:
    result = git_result(repo, "merge-base", "--is-ancestor", before, after)
    if result.returncode not in (0, 1):
        raise ReviewError("Ancestry could not be measured")
    return result.returncode == 0


@contextlib.contextmanager
def in_repo(repo: Path):
    previous = Path.cwd()
    os.chdir(repo)
    try:
        yield
    finally:
        os.chdir(previous)


def load_brain(repo: Path, policy_ref: str = "origin/main"):
    """Use fetched main's Brain, never a PR's replacement protection list."""
    source = git(repo, "show", policy_ref + ":brain/tools/brain.py")
    module = types.ModuleType("_argus_review_brain")
    module.__file__ = str(repo / "brain" / "tools" / "brain.py")
    sys.modules[module.__name__] = module
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    for name in ("is_protected", "changed_paths", "only_main_merged_since", "self_merge_problem",
                 "split_entry", "rebase_links"):
        if not callable(getattr(module, name, None)):
            raise ReviewError("Fetched main lacks the required Brain review API")
    return module


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReviewError("Cannot read the recorded evidence as UTF-8 JSON") from error
    if not isinstance(data, dict):
        raise ReviewError("Recorded evidence must be a JSON object")
    return data


def emit(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=True, indent=2))


def refusal(error: Exception) -> int:
    emit({"ready": False, "error": str(error) if isinstance(error, ReviewError) else "Evidence could not be checked"})
    return 2


def discussion(data: dict) -> tuple[dict, str]:
    try:
        items = {name: data[name] for name in ("reviews", "comments", "review_comments")}
        if not all(isinstance(value, list) for value in items.values()):
            raise ReviewError("All discussion lists are required")
        payload = {"head": data["pr"]["head"]["sha"], **items}
    except (KeyError, TypeError) as error:
        raise ReviewError("Complete discussion and head data are required") from error
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()
    return items, digest


def gh_json(repo: Path, endpoint: str, *, pages: bool = False):
    command = ["gh", "api", "--method", "GET"]
    if pages:
        command.extend(["--paginate", "--slurp"])
    result = subprocess.run([*command, endpoint], cwd=repo, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", check=False, timeout=30)
    if result.returncode != 0:
        raise ReviewError("A required GitHub GET failed; retry or inspect the infrastructure")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ReviewError("GitHub returned incomplete JSON evidence") from error


def gh_pages(repo: Path, endpoint: str, key: str | None = None) -> list[dict]:
    pages = gh_json(repo, endpoint, pages=True)
    if not isinstance(pages, list):
        raise ReviewError("GitHub pagination did not return all pages")
    result = []
    for page in pages:
        items = page.get(key) if key and isinstance(page, dict) else page
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise ReviewError("A GitHub page has an invalid shape")
        result.extend(items)
    if key and pages and len(result) != pages[0].get("total_count"):
        raise ReviewError("GitHub check-run pages are incomplete")
    return result


def live_snapshot(repo: Path, number: int, repository: str | None = None) -> dict:
    if repository is None:
        result = subprocess.run(["gh", "repo", "view", "--json", "nameWithOwner"], cwd=repo,
                                capture_output=True, text=True, encoding="utf-8", check=False, timeout=30)
        if result.returncode != 0:
            raise ReviewError("Cannot identify the GitHub repository")
        repository = json.loads(result.stdout)["nameWithOwner"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or number < 1:
        raise ReviewError("Invalid repository or PR number")
    prefix = "repos/" + repository
    pr = gh_json(repo, f"{prefix}/pulls/{number}")
    head = pr["head"]["sha"]
    main = gh_json(repo, prefix + "/git/ref/heads/main")["object"]["sha"]
    head_repo = pr["head"]["repo"]["full_name"]
    branch = gh_json(repo, "repos/" + head_repo + "/git/ref/heads/" + quote(pr["head"]["ref"], safe=""))
    files = gh_pages(repo, f"{prefix}/pulls/{number}/files?per_page=100")
    reviews = gh_pages(repo, f"{prefix}/pulls/{number}/reviews?per_page=100")
    comments = gh_pages(repo, f"{prefix}/issues/{number}/comments?per_page=100")
    inline = gh_pages(repo, f"{prefix}/pulls/{number}/comments?per_page=100")
    checks = gh_pages(repo, f"{prefix}/commits/{head}/check-runs?per_page=100", "check_runs")
    main_checks = gh_pages(repo, f"{prefix}/commits/{main}/check-runs?per_page=100", "check_runs")
    again = gh_json(repo, f"{prefix}/pulls/{number}")
    main_again = gh_json(repo, prefix + "/git/ref/heads/main")["object"]["sha"]
    if (again["head"]["sha"] != head or again.get("updated_at") != pr.get("updated_at") or main_again != main):
        raise ReviewError("PR or main changed while collecting evidence; read it again")
    if (len(files) != pr["changed_files"] or len(comments) != pr["comments"]
            or len(inline) != pr["review_comments"]):
        raise ReviewError("The PR's file or discussion pages are incomplete")
    return {"complete": True, "pr": pr, "main_sha": main, "branch_exists": branch["object"]["sha"] == head,
            "files": files, "reviews": reviews, "comments": comments, "review_comments": inline,
            "checks": checks, "main_checks": main_checks}
