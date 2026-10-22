"""Check an Argus journal entry and its task status before review.

This is a read-only format check. Brain lint and human review remain authoritative.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


SECTION_NAMES = ("### Test state", "### Next step")
STATUS_ROW = re.compile(r"(?m)^\| Status \|\s*(.*?)\s*\|\s*$")
INLINE_STATUS = re.compile(r"(?m)^.*\*\*Status:\*\*\s*.+$")
PLAIN_STATUS = re.compile(r"(?m)^Status:\s*.+$")
MARKDOWN_LINK = re.compile(r"\[[^]\n]+\]\([^)\n]+\)")
PR_REFERENCE = re.compile(r"(?<!\w)#[1-9][0-9]*\b|https://github\.com/[^/\s)]+/[^/\s)]+/pull/[1-9][0-9]*\b")


def check(entry: str, task: str) -> list[str]:
    errors: list[str] = []
    if not re.match(r"\A## \d{4}-\d{2}-\d{2} (?:—|-) \S", entry):
        errors.append("journal entry must start with '## YYYY-MM-DD — title' or a hyphenated title")

    for heading in SECTION_NAMES:
        matches = list(re.finditer(rf"(?m)^{re.escape(heading)}[ \t]*$", entry))
        if len(matches) != 1:
            errors.append(f"journal entry needs exactly one {heading} section")
            continue
        next_heading = re.search(r"(?m)^#{2,3} ", entry[matches[0].end() :])
        body = entry[matches[0].end() :]
        if next_heading:
            body = body[: next_heading.start()]
        if not body.strip():
            errors.append(f"{heading} section is empty")

    rows = STATUS_ROW.findall(task)
    inline = INLINE_STATUS.findall(task)
    plain = PLAIN_STATUS.findall(task) if not rows and not inline else []
    if len(rows) + len(inline) + len(plain) != 1:
        errors.append("task needs one '| Status | ... |', '**Status:** ...', or 'Status: ...' line")
        return errors
    status = rows[0] if rows else inline[0] if inline else plain[0]
    state = re.match(r"`([^`]+)`", status) if rows else re.search(r"(?:\*\*Status:\*\*|^Status:)\s*([^·\n]+)", status)
    if rows and not state:
        errors.append("task status must begin with a backticked state")
    if not MARKDOWN_LINK.search(status) and not PR_REFERENCE.search(status):
        errors.append("task status needs a link or #PR reference to evidence")
    if state and re.match(r"(?i)^done\b", state.group(1).strip().lstrip("`*_")) and not PR_REFERENCE.search(status):
        errors.append("done task status needs its PR reference")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry", type=Path, required=True)
    parser.add_argument("--task", type=Path, required=True)
    args = parser.parse_args()
    try:
        entry = args.entry.read_text(encoding="utf-8")
        task = args.task.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        print(f"ERROR: cannot read input: {exc}", file=sys.stderr)
        return 2
    errors = check(entry, task)
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    if errors:
        return 1
    print("PASS: journal sections and task status are ready for review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
