"""Report first-parent changes after an approved head; never change the branch."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from review_common import ReviewError, ancestor, emit, git, in_repo, load_brain, refusal, resolve


def report(repo: Path, approved: str, head: str, main: str) -> dict:
    approved, head, main = (resolve(repo, ref) for ref in (approved, head, main))
    brain = load_brain(repo, main)
    on_path = approved in git(repo, "rev-list", "--first-parent", head).splitlines()
    commits = []
    if ancestor(repo, approved, head) and on_path:
        rows = git(repo, "rev-list", "--first-parent", "--reverse", "--parents", approved + ".." + head)
        for row in rows.splitlines():
            sha, *parents = row.split()
            remerge = ""
            main_only = False
            if len(parents) > 1:
                remerge = git(repo, "show", "--remerge-diff", "--format=", "--no-ext-diff", "--no-textconv", sha)
                with in_repo(repo):
                    main_only = len(parents) == 2 and brain.only_main_merged_since(parents[0], sha, main)
            commits.append({"sha": sha, "parents": parents, "main_only": main_only, "remerge_diff": remerge})
    with in_repo(repo):
        retained = on_path and brain.only_main_merged_since(approved, head, main)
    return {"ready": retained, "approval_retained": retained, "approved": approved, "head": head,
            "main": main, "commits": commits,
            "recommendation": "Approval retained; check current CI and discussion" if retained else "Re-review required"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--approved", required=True)
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--main", default="origin/main")
    args = parser.parse_args()
    try:
        result = report(args.repo, args.approved, args.head, args.main)
        emit(result)
        return 0 if result["approval_retained"] else 1
    except (ReviewError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        return refusal(error)


if __name__ == "__main__":
    raise SystemExit(main())
