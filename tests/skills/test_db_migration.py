"""T-0049 S3c: the `db-migration` checker. A missing migration, grant, store or db check makes it FAIL, not pass.

Each fixture is a copy of the committed migrations and the two stores in a temporary folder, with one new table
(`widget`, migration 013) added completely and then one piece taken out. The checker only reads files.
"""
from __future__ import annotations

import hashlib
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".claude" / "skills" / "db-migration" / "scripts" / "check_migration.py"
_spec = importlib.util.spec_from_file_location("check_migration", SCRIPT)
cm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cm)

SQLITE = Path("argus/adapters/outbound/sqlite_store.py")
POSTGRES = Path("argus/adapters/outbound/postgres_store.py")
MIGRATIONS = Path("deploy/migrations")

WIDGET_SQL = """-- 013: a test table.
CREATE TABLE widget (
  id    bigserial PRIMARY KEY,
  name  text NOT NULL,
  at    timestamptz NOT NULL);

GRANT SELECT, INSERT ON widget TO argus_runtime;
GRANT USAGE ON SEQUENCE widget_id_seq TO argus_runtime;
"""
WIDGET_SQLITE = """CREATE TABLE IF NOT EXISTS widget (id INTEGER PRIMARY KEY, name TEXT NOT NULL, at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS widget_no_update BEFORE UPDATE ON widget
  BEGIN SELECT RAISE(ABORT, 'widget is insert-only'); END;
CREATE TRIGGER IF NOT EXISTS widget_no_delete BEFORE DELETE ON widget
  BEGIN SELECT RAISE(ABORT, 'widget is insert-only'); END;
"""
CHECK_INSERT = ('    ("insert widget (migration 013)", "INSERT INTO widget (name, at) VALUES (\'dbcheck\', now())", '
                'True),\n')
CHECK_REFUSALS = ('    ("widget is insert-only (UPDATE refused)", "UPDATE widget SET name = \'x\' WHERE name = '
                  '\'dbcheck\'", False),\n'
                  '    ("widget is insert-only (DELETE refused)", "DELETE FROM widget WHERE name = \'dbcheck\'", '
                  'False),\n')


def repo(tmp_path: Path, *, sql=WIDGET_SQL, name="013_widget.sql", sqlite=WIDGET_SQLITE, sqlite_insert=True,
         pg_insert=True, checks=CHECK_INSERT + CHECK_REFUSALS) -> Path:
    """The committed files plus `widget`; an argument set to "" (or False) leaves that piece out."""
    for rel in (SQLITE, POSTGRES):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, tmp_path / rel)
    shutil.copytree(ROOT / MIGRATIONS, tmp_path / MIGRATIONS)
    if sql:
        (tmp_path / MIGRATIONS / name).write_text(sql, encoding="utf-8")
    s = (tmp_path / SQLITE).read_text(encoding="utf-8")
    s = s.replace('SCHEMA = """\n', 'SCHEMA = """\n' + sqlite, 1)
    if sqlite_insert:
        s += '\n_WIDGET = "INSERT INTO widget (name, at) VALUES (?, ?)"\n'
    (tmp_path / SQLITE).write_text(s, encoding="utf-8")
    p = (tmp_path / POSTGRES).read_text(encoding="utf-8")
    p = p.replace("CHECKS_SQL: list[tuple[str, str, bool]] = [\n",
                  "CHECKS_SQL: list[tuple[str, str, bool]] = [\n" + checks, 1)
    if pg_insert:
        p += '\n_WIDGET = "INSERT INTO widget (name, at) VALUES (%s, %s)"\n'
    (tmp_path / POSTGRES).write_text(p, encoding="utf-8")
    return tmp_path


def problems(root: Path, migration="013_widget.sql") -> list[str]:
    return cm.check(root, migration)


@pytest.mark.parametrize("migration", ["007_incident_parent.sql", "008_deploy_event.sql", "009_link_event.sql",
                                       "010_session_login.sql", "011_audit_chain.sql",
                                       "012_incident_hypothesis.sql"])
def test_the_committed_migrations_of_the_current_pattern_pass(migration):
    assert cm.check(ROOT, migration) == []


def test_a_complete_new_table_passes(tmp_path):
    assert problems(repo(tmp_path)) == []


def test_a_table_the_sqlite_store_creates_without_a_migration_fails(tmp_path):
    root = repo(tmp_path, sql="")                                    # the store has it, deploy/migrations does not
    assert any("no migration creates" in p and "widget" in p for p in cm.check(root, "012_incident_hypothesis.sql"))


def test_a_sqlite_column_without_a_migration_fails(tmp_path):
    root = repo(tmp_path)
    s = (root / SQLITE).read_text(encoding="utf-8")
    (root / SQLITE).write_text(s + '\n_X = "ALTER TABLE incident ADD COLUMN owner_x TEXT"\n', encoding="utf-8")
    assert any("no migration adds" in p and "incident.owner_x" in p for p in problems(root))


@pytest.mark.parametrize("change, why", [
    (("GRANT SELECT, INSERT ON widget TO argus_runtime;\n", ""), "no grant"),
    (("GRANT USAGE ON SEQUENCE widget_id_seq TO argus_runtime;\n", ""), "sequence"),
])
def test_a_missing_grant_fails(tmp_path, change, why):
    root = repo(tmp_path, sql=WIDGET_SQL.replace(*change))
    assert any(why in p for p in problems(root))


def test_a_table_the_sqlite_store_does_not_create_fails(tmp_path):
    assert any("SQLite store does not create" in p for p in problems(repo(tmp_path, sqlite="")))


@pytest.mark.parametrize("store, why", [("sqlite_insert", "SQLite store never inserts"),
                                        ("pg_insert", "Postgres store never inserts")])
def test_a_store_that_never_writes_the_table_fails(tmp_path, store, why):
    assert any(why in p for p in problems(repo(tmp_path, **{store: False})))


def test_no_insert_in_db_check_fails(tmp_path):
    assert any("argus db check has no insert" in p for p in problems(repo(tmp_path, checks=CHECK_REFUSALS)))


def test_a_refusal_checked_before_the_insert_fails(tmp_path):
    # the #181 lesson: a refusal with no row yet passes whatever the grants are
    root = repo(tmp_path, checks=CHECK_REFUSALS + CHECK_INSERT)
    assert any("before its insert" in p for p in problems(root))


@pytest.mark.parametrize("verb", ["UPDATE", "DELETE"])
def test_an_insert_only_table_needs_its_refusal_and_its_sqlite_trigger(tmp_path, verb):
    no_check = "".join(line for line in CHECK_REFUSALS.splitlines(keepends=True) if f"({verb} refused)" not in line)
    assert any(f"no {verb} refusal" in p for p in problems(repo(tmp_path / "a", checks=CHECK_INSERT + no_check)))
    lines = WIDGET_SQLITE.splitlines(keepends=True)
    i = lines.index(f"CREATE TRIGGER IF NOT EXISTS widget_no_{verb.lower()} BEFORE {verb} ON widget\n")
    sqlite = "".join(lines[:i] + lines[i + 2:])                     # the trigger and its BEGIN ... END line
    assert any(f"no SQLite {verb} trigger" in p for p in problems(repo(tmp_path / "b", sqlite=sqlite)))


@pytest.mark.parametrize("name, why", [("015_widget.sql", "not the next number"),
                                       ("012_widget.sql", "not the next number"),
                                       ("13_widget.sql", "NNN_name.sql")])
def test_a_wrong_migration_number_or_name_fails(tmp_path, name, why):
    assert any(why in p for p in problems(repo(tmp_path, name=name), name))


def test_a_new_column_the_sqlite_store_does_not_add_fails(tmp_path):
    root = repo(tmp_path, sql="-- 013\nALTER TABLE incident ADD COLUMN owner_x text;\n", sqlite="",
                sqlite_insert=False, pg_insert=False, checks="")
    assert any("incident.owner_x" in p and "SQLite" in p for p in problems(root))


def test_an_unknown_migration_fails(tmp_path):
    assert any("no such migration" in p for p in problems(repo(tmp_path), "013_nothing.sql"))


def tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode() + p.read_bytes())
    return h.hexdigest()


def test_the_cli_is_read_only_and_gives_the_same_answer_twice(tmp_path):
    root = repo(tmp_path)
    before = tree_hash(root)
    runs = [subprocess.run([sys.executable, str(SCRIPT), "013_widget.sql", "--root", str(root)],
                           capture_output=True, text=True, encoding="utf-8") for _ in range(2)]
    assert runs[0].returncode == 0, runs[0].stderr
    assert (runs[0].stdout, runs[0].stderr) == (runs[1].stdout, runs[1].stderr)
    assert tree_hash(root) == before
    bad = subprocess.run([sys.executable, str(SCRIPT), "013_widget.sql", "--root", str(repo(tmp_path / "x",
                         checks=CHECK_INSERT))], capture_output=True, text=True, encoding="utf-8")
    assert bad.returncode == 1 and "FAIL" in bad.stderr
