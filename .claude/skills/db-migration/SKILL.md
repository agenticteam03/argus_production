---
name: db-migration
description: >-
  Add an Argus database change: a deploy/migrations SQL file, the matching
  SQLite store, the runtime role's grants, both stores' code, the `argus db
  check` statements and the deploy order. Use when a table or column is
  added; not for queries on existing tables.
---

# Add an Argus database migration

Read `brain/architecture/ARCHITECTURE.md` (the storage and least-privilege
sections) and the task's own file first; they win over this skill. A new table
usually comes from an accepted ACR. This skill grants no permission to run
a migration, deploy, or touch a VM.

The pattern follows migrations 007 to 012 (`incident.parent_id`,
`deploy_event`, `link_event`, `auth_session`/`login_failure`, the audit chain,
`incident_hypothesis`).

1. **Test first.**
   - Write the store test that inserts a row and reads it back on SQLite (the
     offline suite).
   - Write `test_<table>_migration_NNN` in `tests/test_postgres.py`. It runs
     on a throwaway Postgres (`ARGUS_TEST_PG_OWNER_DSN`), and CI runs it.
   - Show both failing.
2. **SQL.** Add `deploy/migrations/NNN_<name>.sql` with the next free number.
   - Start with a header comment: what the change is for, and what the
     runtime role may do with it.
   - Give the runtime role only what it needs. An append-only record is
     `GRANT SELECT, INSERT ... TO argus_runtime`. A `bigserial` column also
     needs `GRANT USAGE ON SEQUENCE <table>_<col>_seq`.
   - **Never edit an applied migration.** `ops/db-migrate.sh` refuses a file
     whose hash changed after it was applied; make a new number instead.
3. **SQLite.** Mirror the change in `argus/adapters/outbound/sqlite_store.py`:
   - a new table goes in `SCHEMA` (`CREATE TABLE IF NOT EXISTS`);
   - an insert-only table gets `BEFORE UPDATE` and `BEFORE DELETE` triggers
     that `RAISE(ABORT, ...)`;
   - a new column is added at start to an older file (`ALTER TABLE ... ADD
     COLUMN`), as `claimed_by` and `resolved_at` are.
4. **Both stores.**
   - Add the methods to the port and to both `SqliteStore` and
     `PostgresStore`.
   - If an old SQLite file can hold the data, `import_sqlite` copies it.
5. **`argus db check`.** Add to `CHECKS_SQL` in
   `argus/adapters/outbound/postgres_store.py`:
   - **first, an insert that must succeed**;
   - then the refusals that must fail (UPDATE, DELETE, or a changed identity
     column).

   Order matters: the #181 lesson. A refusal checked before any row exists
   passes whatever the grants are, so it proves nothing.
6. **Check.** From the repository root, run:
   `python .claude/skills/db-migration/scripts/check_migration.py NNN_<name>.sql`

   Status 0 means none of the listed problems was found. Then run the focused
   tests, the full offline suite, Brain lint, a journal entry, and the commit
   block (`code-bash-step`).
7. **Deploy order** (the deploy task, with the leases; not this skill):
   1. take a backup;
   2. run `sudo bash ops/db-migrate.sh` on vm-095;
   3. then deploy the new image;
   4. then run `argus db check`.

   The old image keeps working on the new schema because changes are
   additive. The new image does not work without the migration. Say this in
   the journal entry's Consequences.

The checker is read-only and static: it reads the files as text and never
connects to a database. On every run it fails if:

- a table or column the SQLite store creates or adds comes from no migration
  (a missing migration).

For the named migration, it fails if:

- the name is not `NNN_name.sql` or the number is not the next one;
- a new table has no grant to `argus_runtime`, or a `bigserial` column has no
  sequence grant;
- the SQLite store does not create the table, or a store never inserts into it;
- `argus db check` has no insert that must succeed, or tests a refusal before
  it;
- an insert-only table (only SELECT and INSERT granted) lacks an UPDATE or
  DELETE refusal, or the matching SQLite trigger;
- a new column is not handled by either store.

It cannot prove the grants on a live database: `argus db check` and the
Postgres tests do that. LangGraph's checkpoint tables (002) are Postgres only.
