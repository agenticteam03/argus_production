"""Check that an Argus database migration has its other pieces before review.

Read-only and static: it reads deploy/migrations/*.sql, the SQLite store's SCHEMA and the Postgres store's CHECKS_SQL
(`argus db check`) as text; it never connects to a database. Run from the repository root:

    python .claude/skills/db-migration/scripts/check_migration.py NNN_name.sql [--root DIR]

Every run also checks that each table and column the SQLite store creates comes from a migration.
Tests, `argus db check` on a real Postgres, Brain lint and human review remain authoritative.
"""
from __future__ import annotations

import argparse
import ast
from pathlib import Path
import re
import sys

MIGRATIONS = Path("deploy/migrations")
SQLITE = Path("argus/adapters/outbound/sqlite_store.py")
POSTGRES = Path("argus/adapters/outbound/postgres_store.py")
# LangGraph's own checkpoint saver tables (002): Postgres only; the SQLite runs use LangGraph's SQLite saver
POSTGRES_ONLY = {"checkpoint_migrations", "checkpoints", "checkpoint_blobs", "checkpoint_writes"}
NAME = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")
CREATE = re.compile(r"(?is)CREATE TABLE (?:IF NOT EXISTS )?(\w+)\s*\((.*?)\);")
ALTER = re.compile(r"(?i)ALTER TABLE (\w+) ADD COLUMN (?:IF NOT EXISTS )?(\w+)")
GRANT = re.compile(r"(?is)GRANT\s+(.+?)\s+ON\s+(?!SEQUENCE\b|SCHEMA\b)(?:TABLE\s+)?([\w,\s]+?)\s+TO\s+argus_runtime")
SERIAL = re.compile(r"(?im)^\s*(\w+)\s+(?:big|small)?serial\b")


def _sql(text: str) -> str:
    return re.sub(r"--[^\n]*", "", text)


def _constant(path: Path, name: str):
    """A module-level constant (SCHEMA, CHECKS_SQL) read with `ast`, without importing the module, and the module's
    text without that assignment."""
    text = path.read_text(encoding="utf-8")
    for node in ast.parse(text).body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if any(isinstance(t, ast.Name) and t.id == name for t in targets) and node.value is not None:
            lines = text.splitlines(keepends=True)
            return ast.literal_eval(node.value), "".join(lines[:node.lineno - 1] + lines[node.end_lineno:])
    raise ValueError(f"{path}: no {name}")


def _columns(body: str) -> set[str]:
    return {m.group(1).lower() for m in re.finditer(r"(?m)^\s*(\w+)\s+\w", body)}


def check(root: Path | str, migration: str) -> list[str]:
    root = Path(root)
    files = sorted(p.name for p in (root / MIGRATIONS).glob("*.sql"))
    texts = {n: _sql((root / MIGRATIONS / n).read_text(encoding="utf-8")) for n in files}
    sqlite_py = (root / SQLITE).read_text(encoding="utf-8")
    schema, _ = _constant(root / SQLITE, "SCHEMA")
    checks, postgres_py = _constant(root / POSTGRES, "CHECKS_SQL")   # the store's own code, not its db check
    errors: list[str] = []

    created = {t.lower(): body for text in texts.values() for t, body in CREATE.findall(text)}
    columns = {t: _columns(body) for t, body in created.items()}
    for text in texts.values():
        for t, c in ALTER.findall(text):
            columns.setdefault(t.lower(), set()).add(c.lower())
    privileges: dict[str, set[str]] = {}
    for text in texts.values():
        for privs, tables in GRANT.findall(text):
            words = set(re.sub(r"\([^)]*\)", "", privs).upper().replace(",", " ").split())
            for t in tables.replace(",", " ").split():
                privileges.setdefault(t.lower(), set()).update(words)

    # every run: what the SQLite store creates or adds comes from a migration (a missing migration fails here)
    for t in re.findall(r"(?i)CREATE TABLE IF NOT EXISTS (\w+)", schema):
        if t.lower() not in created:
            errors.append(f"{t}: the SQLite store creates it but no migration creates it")
    for t, c in ALTER.findall(sqlite_py):
        if c.lower() not in columns.get(t.lower(), set()):
            errors.append(f"{t}.{c}: the SQLite store adds it but no migration adds it")

    if migration not in files:
        return errors + [f"{migration}: no such migration in {MIGRATIONS.as_posix()}"]
    m = NAME.match(migration)
    if not m:
        return errors + [f"{migration}: a migration is named NNN_name.sql (three digits, lower case)"]
    n = int(m.group(1))
    others = [int(NAME.match(f).group(1)) for f in files if f != migration and NAME.match(f)]
    if n in others or n != 1 + max([o for o in others if o < n], default=0):
        errors.append(f"{migration}: {n:03d} is not the next number after {max(others, default=0):03d} "
                      "(each number once, no gap)")
    text = texts[migration]

    for t, body in CREATE.findall(text):
        t = t.lower()
        if t in POSTGRES_ONLY:
            continue
        if t not in privileges:
            errors.append(f"{t}: no grant to argus_runtime (the runtime role could not use it)")
        for col in SERIAL.findall(body):
            seq = f"{t}_{col.lower()}_seq"
            if not re.search(rf"(?i)GRANT\s+USAGE\s+ON\s+SEQUENCE\s+{seq}\s+TO\s+argus_runtime", text):
                errors.append(f"{t}: no usage grant on its sequence {seq} (the runtime role's insert would fail)")
        if not re.search(rf"(?i)CREATE TABLE IF NOT EXISTS {t}\b", schema):
            errors.append(f"{t}: the SQLite store does not create it (SCHEMA in {SQLITE.as_posix()})")
        if not re.search(rf"(?i)\bINTO {t}\b", sqlite_py):
            errors.append(f"{t}: the SQLite store never inserts into it")
        if not re.search(rf"(?i)\bINTO {t}\b", postgres_py):
            errors.append(f"{t}: the Postgres store never inserts into it")

        def on(verb: str, sql: str) -> bool:
            return bool(re.match(rf"(?is)\s*{verb}\s+(?:FROM\s+)?{t}\b", sql))
        insert = next((i for i, (_, sql, ok) in enumerate(checks) if ok and on("INSERT INTO", sql)), None)
        if insert is None:
            errors.append(f"{t}: argus db check has no insert into it that must succeed (CHECKS_SQL)")
        refusals = [(i, sql) for i, (_, sql, ok) in enumerate(checks)
                    if not ok and any(on(v, sql) for v in ("UPDATE", "DELETE", "TRUNCATE"))]
        if insert is not None and any(i < insert for i, _ in refusals):
            errors.append(f"{t}: argus db check tests a refusal before its insert (with no row it passes whatever "
                          "the grants are: the #181 lesson)")
        if privileges.get(t, set()) <= {"SELECT", "INSERT"}:       # insert-only, as evidence, audit and the events
            for verb in ("UPDATE", "DELETE"):
                if not any(on(verb, sql) for _, sql in refusals):
                    errors.append(f"{t}: insert-only but argus db check has no {verb} refusal")
                if not re.search(rf"(?i)BEFORE {verb} ON {t}\b", schema):
                    errors.append(f"{t}: insert-only but there is no SQLite {verb} trigger refusing it")

    for t, c in ALTER.findall(text):
        if not re.search(rf"\b{c}\b", sqlite_py):
            errors.append(f"{t}.{c}: the SQLite store does not add it (an older file gains it at start)")
        if not re.search(rf"\b{c}\b", postgres_py):
            errors.append(f"{t}.{c}: the Postgres store never uses it")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("migration", help="the file name, e.g. 013_widget.sql")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        errors = check(args.root, Path(args.migration).name)
    except (OSError, UnicodeError, SyntaxError, ValueError) as exc:
        print(f"ERROR: cannot read the repository: {exc}", file=sys.stderr)
        return 2
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    if errors:
        return 1
    print(f"PASS: {Path(args.migration).name} has the pieces this checker knows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
