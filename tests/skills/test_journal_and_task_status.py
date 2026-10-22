"""Behavior checks for the journal-and-task-status handoff validator."""

from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / ".claude/skills/journal-and-task-status/scripts/check_status.py"
)


def check(tmp_path: Path, entry: str, status: str) -> subprocess.CompletedProcess[str]:
    task = tmp_path / "brain/tasks/current/T-0049.md"
    journal = tmp_path / "brain/journal/entries/2026-10-22-T-0049.md"
    task.parent.mkdir(parents=True)
    journal.parent.mkdir(parents=True)
    task.write_text("# T-0049\n\n| Field | Value |\n|---|---|\n" + status + "\n", encoding="utf-8")
    journal.write_text(entry, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--task", str(task), "--entry", str(journal)],
        text=True,
        capture_output=True,
        check=False,
    )


ENTRY = """## 2026-10-22 — T-0049 S4: journal skill

Type: implementation
Who: juanbetancurm (+ agent)
Decision / result: validated the handoff format.

### Test state

RED seen: missing sections were rejected. Focused suite passed.

### Next step

Request review of the [task](../../tasks/current/T-0049.md).
"""


def test_valid_in_progress_handoff(tmp_path: Path) -> None:
    result = check(tmp_path, ENTRY, "| Status | `in progress` — [skill](../../.claude/skills/journal-and-task-status/SKILL.md) |")
    assert result.returncode == 0, result.stderr
    assert "PASS" in result.stdout


@pytest.mark.parametrize("heading", ["### Test state", "### Next step"])
def test_missing_rollup_sections_are_rejected(tmp_path: Path, heading: str) -> None:
    result = check(tmp_path, ENTRY.replace(heading, "### Other"), "| Status | `proposed` — [plan](../T-0049.md) |")
    assert result.returncode == 1
    assert heading in result.stderr


def test_empty_rollup_section_is_rejected(tmp_path: Path) -> None:
    result = check(tmp_path, ENTRY.replace("RED seen: missing sections were rejected. Focused suite passed.", ""), "| Status | `proposed` — [plan](../T-0049.md) |")
    assert result.returncode == 1
    assert "empty" in result.stderr


def test_done_without_pr_is_rejected(tmp_path: Path) -> None:
    result = check(tmp_path, ENTRY, "| Status | `done` — [skill](../../.claude/skills/journal-and-task-status/SKILL.md) |")
    assert result.returncode == 1
    assert "PR" in result.stderr


def test_done_with_pr_is_accepted(tmp_path: Path) -> None:
    result = check(tmp_path, ENTRY, "| Status | `done` — [PR #269](https://github.com/agenticteam03/argus_production/pull/269) |")
    assert result.returncode == 0, result.stderr


def test_unlinked_status_is_rejected(tmp_path: Path) -> None:
    result = check(tmp_path, ENTRY, "| Status | `in progress` — draft written |")
    assert result.returncode == 1
    assert "link" in result.stderr.lower()


def test_status_row_has_to_exist(tmp_path: Path) -> None:
    result = check(tmp_path, ENTRY, "| Phase | 24 |")
    assert result.returncode == 1
    assert "Status" in result.stderr


def test_real_merged_task_shape_with_plain_pr_number(tmp_path: Path) -> None:
    status = "| Status | `done` — catalogue merged (#131); [evidence](../../execution/history/E2E-8/step-02/evidence.md) |"
    result = check(tmp_path, ENTRY, status)
    assert result.returncode == 0, result.stderr


def test_real_inline_status_and_hyphen_title(tmp_path: Path) -> None:
    status = "**Owner:** `conantkd` · **Branch:** `task/OP-004-checkpoint-cleanup` · **PR:** #42 (merged) · **Status:** offline implementation merged"
    result = check(tmp_path, ENTRY.replace("2026-10-22 —", "2026-10-22 -"), status)
    assert result.returncode == 0, result.stderr


def test_legacy_plain_status_with_pr_reference(tmp_path: Path) -> None:
    result = check(tmp_path, ENTRY, "Status: proposed in PR #150. Owner: conantkd.")
    assert result.returncode == 0, result.stderr


def test_plain_done_status_requires_its_pr(tmp_path: Path) -> None:
    result = check(tmp_path, ENTRY, "Status: done — [evidence](../../execution/history/T-0049/evidence.md)")
    assert result.returncode == 1
    assert "PR" in result.stderr


@pytest.mark.parametrize(
    "status",
    [
        "Status: `done` — [evidence](x.md)",
        "**Status:** `done` · [evidence](x.md)",
        "**Status:** **done** [evidence](x.md)",
        "Status: *done* [evidence](x.md)",
    ],
)
def test_marked_up_done_status_requires_its_pr(tmp_path: Path, status: str) -> None:
    result = check(tmp_path, ENTRY, status)
    assert result.returncode == 1
    assert "PR" in result.stderr


def test_marked_up_done_status_with_pr_is_accepted(tmp_path: Path) -> None:
    result = check(tmp_path, ENTRY, "Status: `done` — merged in #12")
    assert result.returncode == 0, result.stderr
