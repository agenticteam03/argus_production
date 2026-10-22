"""Compose reviewed architecture version metadata from two branch snapshots.

This prints replacement metadata for a human to inspect. It never edits an
architecture document or changes an ACR's decision status.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


VERSION = re.compile(r"\d+\.\d+\.\d+")
ENTRY_BREAK = re.compile(r";\s+(?=(?:\d+\.\d+\.\d+|base \d+\.\d+\.\d+)\b)")
ACR_LINK = re.compile(r"\[ACR-(\d{4})\]\(changes/ACR-\1-[^)]+\.md\)")
PROBLEM_LINK = re.compile(r"\[OP-\d{3}\]\(\.\./OPEN_PROBLEMS\.md\)")


def _key(version: str) -> tuple[int, int, int]:
    if not VERSION.fullmatch(version):
        raise ValueError(f"invalid version: {version}")
    return tuple(int(part) for part in version.split("."))


def _parse(document: str) -> tuple[dict[str, str], dict[str, str]]:
    match = re.search(r"\*\*Version:\*\*\s+(.+?)\s+·\s+\*\*Audience:\*\*", document, re.S)
    if not match:
        raise ValueError("missing architecture version line")
    value = match.group(1).strip()
    first = re.fullmatch(r"(\d+\.\d+\.\d+) \((.+)\)", value, re.S)
    if not first:
        raise ValueError("invalid architecture version line")
    pieces = ENTRY_BREAK.split(first.group(1) + " " + first.group(2))
    header: dict[str, str] = {}
    for piece in pieces:
        if piece.startswith("base "):
            version_match = re.match(r"base (\d+\.\d+\.\d+)\b", piece)
            if version_match is None:
                raise ValueError("invalid base version entry")
            version = version_match.group(1)
        else:
            version_match = re.match(r"(\d+\.\d+\.\d+)\b", piece)
            if version_match is None:
                raise ValueError(f"invalid version entry: {piece}")
            version = version_match.group(1)
        _key(version)
        if version in header:
            raise ValueError(f"duplicate version in header: {version}")
        header[version] = piece

    changelog = re.search(r"^## Changelog\s*\n(.*?)(?=^## |\Z)", document, re.M | re.S)
    if changelog is None:
        raise ValueError("missing changelog")
    rows: dict[str, str] = {}
    for line in changelog.group(1).splitlines():
        if not re.match(r"^\|\s*\d+\.\d+\.\d+\s*\|", line):
            continue
        # The real changelog contains an unescaped pipe in a prose cell.
        # Anchor the fixed outer cells and preserve the entire middle cell.
        cells = re.fullmatch(r"\|\s*([^|]+)\|\s*([^|]+)\|(.+)\|\s*([^|]+)\|", line)
        legacy = None if cells else re.fullmatch(r"\|\s*([^|]+)\|\s*([^|]+)\|(.+)\|", line)
        if cells is None and legacy is None:
            raise ValueError(f"invalid changelog row: {line}")
        if cells is not None:
            version, _date, _change, link = (cell.strip() for cell in cells.groups())
        else:
            assert legacy is not None
            version, _date, link = (cell.strip() for cell in legacy.groups())
        _key(version)
        if version in rows:
            raise ValueError(f"duplicate version in changelog: {version}")
        if header.get(version, "").startswith("base "):
            if link != "—":
                raise ValueError(f"invalid base link for {version}")
        elif ACR_LINK.search(link) is None and PROBLEM_LINK.search(link) is None:
            raise ValueError(f"missing or invalid ACR/problem link for {version}")
        rows[version] = line
    missing = set(header) - set(rows)
    if missing:
        raise ValueError(f"missing changelog row for {min(missing, key=_key)}")
    extra = set(rows) - set(header)
    if extra:
        raise ValueError(f"missing header entry for {min(extra, key=_key)}")
    return header, rows


def compose_documents(current: str, incoming: str) -> tuple[str, tuple[str, ...]]:
    """Reconcile two branch snapshots without dropping any represented version.

    The header sorts high to low; the changelog sorts low to high. Entries of
    the same version must be byte-identical in both snapshots.
    """
    headers: dict[str, str] = {}
    rows: dict[str, str] = {}
    for document in (current, incoming):
        document_header, document_rows = _parse(document)
        for version, entry in document_header.items():
            if version in headers and headers[version] != entry:
                raise ValueError(f"conflicting header for {version}")
            headers[version] = entry
        for version, row in document_rows.items():
            if version in rows and rows[version] != row:
                raise ValueError(f"conflicting changelog row for {version}")
            rows[version] = row
    if set(headers) != set(rows):
        raise ValueError("version header and changelog do not cover the same versions")
    base_versions = [version for version, entry in headers.items() if entry.startswith("base ")]
    if len(base_versions) != 1 or _key(base_versions[0]) != min(map(_key, headers)):
        raise ValueError("expected one lowest base version")
    ordered = sorted(headers, key=_key, reverse=True)
    first = headers[ordered[0]].replace(ordered[0] + " ", ordered[0] + " (", 1)
    value = "; ".join([first, *(headers[version] for version in ordered[1:])]) + ")"
    return value, tuple(rows[version] for version in sorted(rows, key=_key))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", type=Path, required=True, help="reviewed current ARCHITECTURE.md")
    parser.add_argument("--incoming", type=Path, required=True, help="other branch's ARCHITECTURE.md")
    args = parser.parse_args()
    try:
        current = args.current.read_bytes().decode("utf-8-sig")
        incoming = args.incoming.read_bytes().decode("utf-8-sig")
        value, rows = compose_documents(current, incoming)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.error(str(exc))
    output = (
        "Version value (between **Version:** and · **Audience:**):\n"
        + value
        + "\n\nChangelog rows (replace the rows under ## Changelog):\n"
        + "\n".join(rows)
        + "\n"
    )
    sys.stdout.buffer.write(output.encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
