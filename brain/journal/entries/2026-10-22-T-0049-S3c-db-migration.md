## 2026-10-22 - T-0049 S3c: the db-migration skill

Type: implementation
Who: juanbetancurm (+ agent)
Context: T-0049 step S3, the third P1 skill (`db-migration`), taken over from S2's plan. Worktree `w-s3c`, branch
`task/T-0049-s3c-db-migration` from main `6a72339`. The pattern comes from migrations 007 to 012.
Decision / result:
- `.claude/skills/db-migration/SKILL.md`: a table or column change. Test first (SQLite store test and
  `tests/test_postgres.py` on a throwaway Postgres). The next-numbered SQL file with least-privilege grants (and the
  sequence grant for a `bigserial`); never edit an applied one. The SQLite mirror (SCHEMA, insert-only triggers, the
  column added to an older file at start). Both stores and `import_sqlite`. `argus db check` with **the insert first**,
  then the refusals (the #181 lesson). The deploy order: backup, `ops/db-migrate.sh`, then the new image, then
  `argus db check`.
- `scripts/check_migration.py NNN_name.sql` (read-only, static: files read as text, `SCHEMA` and `CHECKS_SQL` read with
  `ast`, no database). Every run fails when a table or column the SQLite store creates comes from no migration. For the
  named migration, it fails on:
  - the name or the next number;
  - a new table without a grant to `argus_runtime`, or a `bigserial` column without its sequence grant;
  - the SQLite store not creating the table, or either store never inserting into it;
  - `argus db check` without a succeeding insert, or with a refusal before it;
  - an insert-only table without its UPDATE and DELETE refusals and SQLite triggers;
  - a new column not handled by both stores.
- Migrations 003, 004, 005 and 007 to 012 pass. **Found on the way:** 006 (`monitoring_state`) has no insert in
  `argus db check`, so its grants are not proven on the live database. Recorded here, not fixed: it is runtime
  code, outside this skill's PR.
Consequences: `.claude/skills/` is protected: conantkd reviews. No runtime change.
References: [T-0049](../../tasks/current/T-0049-agent-skills.md), #181.

### Test state

- **RED seen:** against a naive checker that only looked for the file, **16 failed, 8 passed**: a store table with no
  migration, a store column with no migration, a missing table and sequence grant, a missing SQLite table, either store
  never inserting, no db-check insert, a refusal before the insert, missing UPDATE/DELETE refusals and triggers, a wrong
  number or name, a new column the SQLite store ignores, and the CLI.
- GREEN: `tests/skills/test_db_migration.py` **24 passed**: committed migrations 007 to 012 pass; a complete new
  `widget` table passes; the CLI gives the same answer twice and leaves the fixture tree byte-identical. Ruff clean.
- Full offline suite on `6a72339` plus this change: 1656 passed, 62 skipped, 1 deselected, exit 0. After the
  fast-forward to main `95e67a7` (#282): **1662 passed, 62 skipped, 1 deselected in 973 s**, exit 0 (the known
  detached-CI Brain test). Brain lint clean.

### Next step

S1 pre-reviews; conantkd reviews the PR (protected path). A small follow-up for 006's missing db-check insert.
