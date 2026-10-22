"""Behavioral cases for composing parallel architecture version updates."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / ".claude/skills/acr-and-version-line/scripts/version_line.py"
)
SPEC = importlib.util.spec_from_file_location("version_line", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
VERSION_LINE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERSION_LINE)


def document(*, version: str, rows: tuple[str, ...]) -> str:
    return (
        "# Architecture\n\n"
        f"**Version:** {version} · **Audience:** engineers\n\n"
        "## Changelog\n\n"
        "| Version | Date | Change | ACR |\n"
        "|---|---|---|---|\n"
        + "\n".join(rows)
        + "\n"
    )


BASE_ROW = "| 1.8.0 | 2026-10-02 | base | — |"
ROW_ONE = "| 1.8.1 | 2026-10-06 | first | [ACR-0001](changes/ACR-0001-first.md) |"
ROW_TWO = "| 1.8.2 | 2026-10-07 | second | [ACR-0002](changes/ACR-0002-second.md) |"


def test_parallel_versions_are_reconciled_in_numeric_order() -> None:
    current = document(
        version="1.8.1 (2026-10-06, first; base 1.8.0 of 2026-10-02)",
        rows=(ROW_ONE, BASE_ROW),
    )
    incoming = document(
        version="1.8.2 (2026-10-07, second; base 1.8.0 of 2026-10-02)",
        rows=(BASE_ROW, ROW_TWO),
    )
    value, rows = VERSION_LINE.compose_documents(current, incoming)
    assert value == (
        "1.8.2 (2026-10-07, second; 1.8.1 2026-10-06, first; "
        "base 1.8.0 of 2026-10-02)"
    )
    assert rows == (BASE_ROW, ROW_ONE, ROW_TWO)
    assert VERSION_LINE.compose_documents(current, incoming) == (value, rows)


def test_shuffled_rows_are_sorted_without_changing_payloads() -> None:
    doc = document(
        version="1.8.2 (2026-10-07, second; 1.8.1 2026-10-06, first; base 1.8.0 of 2026-10-02)",
        rows=(ROW_TWO, BASE_ROW, ROW_ONE),
    )
    assert VERSION_LINE.compose_documents(doc, doc)[1] == (BASE_ROW, ROW_ONE, ROW_TWO)


def test_reconciled_metadata_is_idempotent_when_used_again() -> None:
    current = document(
        version="1.8.1 (2026-10-06, first; base 1.8.0 of 2026-10-02)",
        rows=(BASE_ROW, ROW_ONE),
    )
    incoming = document(
        version="1.8.2 (2026-10-07, second; base 1.8.0 of 2026-10-02)",
        rows=(BASE_ROW, ROW_TWO),
    )
    value, rows = VERSION_LINE.compose_documents(current, incoming)
    reconciled = document(version=value, rows=rows)
    assert VERSION_LINE.compose_documents(reconciled, reconciled) == (value, rows)


def test_same_version_with_conflicting_descriptions_fails() -> None:
    first = document(version="1.8.1 (2026-10-06, first; base 1.8.0 of 2026-10-02)", rows=(BASE_ROW, ROW_ONE))
    second = document(
        version="1.8.1 (2026-10-06, changed; base 1.8.0 of 2026-10-02)",
        rows=(BASE_ROW, ROW_ONE),
    )
    with pytest.raises(ValueError, match="conflicting.*1.8.1"):
        VERSION_LINE.compose_documents(first, second)


def test_same_version_with_conflicting_changelog_rows_fails() -> None:
    first = document(version="1.8.1 (2026-10-06, first; base 1.8.0 of 2026-10-02)", rows=(BASE_ROW, ROW_ONE))
    second = document(
        version="1.8.1 (2026-10-06, first; base 1.8.0 of 2026-10-02)",
        rows=(BASE_ROW, ROW_ONE.replace("| first |", "| changed |")),
    )
    with pytest.raises(ValueError, match="conflicting changelog row for 1.8.1"):
        VERSION_LINE.compose_documents(first, second)


def test_missing_changelog_row_fails() -> None:
    doc = document(version="1.8.1 (2026-10-06, first; base 1.8.0 of 2026-10-02)", rows=(BASE_ROW,))
    with pytest.raises(ValueError, match="missing.*1.8.1"):
        VERSION_LINE.compose_documents(doc, doc)


def test_changelog_entry_needs_valid_acr_or_problem_link() -> None:
    doc = document(
        version="1.8.1 (2026-10-06, first; base 1.8.0 of 2026-10-02)",
        rows=(BASE_ROW, "| 1.8.1 | 2026-10-06 | first | ACR-0001 |"),
    )
    with pytest.raises(ValueError, match="link.*1.8.1"):
        VERSION_LINE.compose_documents(doc, doc)


def test_pipe_inside_inline_code_is_kept_in_changelog_payload() -> None:
    row = "| 1.8.1 | 2026-10-06 | `lab` | `production` | [ACR-0001](changes/ACR-0001-first.md) |"
    doc = document(
        version="1.8.1 (2026-10-06, first; base 1.8.0 of 2026-10-02)",
        rows=(BASE_ROW, row),
    )
    assert VERSION_LINE.compose_documents(doc, doc)[1] == (BASE_ROW, row)


def test_existing_legacy_row_with_link_in_change_cell_is_preserved() -> None:
    row = "| 1.8.1 | 2026-10-06 | first ([ACR-0001](changes/ACR-0001-first.md)) |"
    doc = document(
        version="1.8.1 (2026-10-06, first; base 1.8.0 of 2026-10-02)",
        rows=(BASE_ROW, row),
    )
    assert VERSION_LINE.compose_documents(doc, doc)[1] == (BASE_ROW, row)


def test_composition_never_approves_a_proposed_acr(tmp_path: Path) -> None:
    proposal = tmp_path / "ACR-0001-first.md"
    proposal.write_bytes(b"| Status | `proposed` |\n")
    doc = document(
        version="1.8.1 (2026-10-06, first; base 1.8.0 of 2026-10-02)",
        rows=(BASE_ROW, ROW_ONE),
    )
    VERSION_LINE.compose_documents(doc, doc)
    assert proposal.read_bytes() == b"| Status | `proposed` |\n"


def test_cli_emits_unicode_metadata_as_utf8(tmp_path: Path) -> None:
    row = "| 1.8.1 | 2026-10-06 | limit ≤ 10 | [ACR-0001](changes/ACR-0001-first.md) |"
    doc = document(
        version="1.8.1 (2026-10-06, limit ≤ 10; base 1.8.0 of 2026-10-02)",
        rows=(BASE_ROW, row),
    )
    path = tmp_path / "ARCHITECTURE.md"
    path.write_bytes(doc.encode("utf-8"))
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--current", str(path), "--incoming", str(path)],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert "limit ≤ 10" in result.stdout.decode("utf-8")
