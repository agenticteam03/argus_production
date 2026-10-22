"""Check removed journal payloads against the Brain's official roll-up transformation."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from review_common import ReviewError, emit, git, load_brain, refusal, resolve


def report(repo: Path, base: str, head: str) -> dict:
    base, head = resolve(repo, base), resolve(repo, head)
    brain = load_brain(repo)
    folder = "brain/journal/entries"
    before = set(git(repo, "ls-tree", "-r", "--name-only", base, "--", folder).splitlines())
    after = set(git(repo, "ls-tree", "-r", "--name-only", head, "--", folder).splitlines())
    removed = sorted(path for path in before - after if path.endswith(".md"))
    summaries = {}
    problems = []
    for path in removed:
        try:
            journal, sections = brain.split_entry(Path(path).name, git(repo, "show", base + ":" + path))
        except brain.BrainError as error:
            raise ReviewError("Removed entry has an invalid Brain format: " + path) from error
        expected = {brain.LOGBOOK: journal, **sections}
        for target, body in expected.items():
            name = target.as_posix()
            if name not in summaries:
                summaries[name] = git(repo, "show", head + ":" + name)
            rebased = brain.rebase_links(body, folder, target.parent.as_posix()).strip()
            if rebased not in summaries[name]:
                missing = [index for index, line in enumerate(rebased.splitlines(), 1)
                           if line.strip() and line not in summaries[name].splitlines()]
                problems.append({"entry": path, "summary": name, "missing_lines": missing,
                                 "detail": "Payload missing, changed or reordered after roll-up"})
    return {"ready": not problems, "removed_entries": removed, "problems": problems, "base": base, "head": head}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()
    try:
        result = report(args.repo, args.base, args.head)
        emit(result)
        return 0 if result["ready"] else 1
    except (ReviewError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        return refusal(error)


if __name__ == "__main__":
    raise SystemExit(main())
