# T-0017 — Postgres backup/restore drill

| Field | Value |
|---|---|
| Status | `verified` on vm-095 (2026-10-06); merged by this pull request |
| Phase | 5 — Postgres ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md): "backup/restore drill") |
| Architecture | no change (operations script; the live database is only read) |
| Branch | `task/T-0017-pg-backup-drill` |
| Owner | `conantkd` (+ agent) |
| Needs the VM lease | steps 1 and 3 |

## Goal (plain language)

Postgres holds every incident, its evidence, the audit trail and the LangGraph checkpoints. A backup nobody has
restored is only a hope. This task adds one script that takes a backup **and proves it can be restored**, without
ever writing to the live database, and runs it once on vm-095.

## Design

`ops/db-backup.sh` (refuses unless `/opt/argus-v18/SESSION` is yours):

- `backup --as <handle>`: `pg_dump -Fc` of `argus-v18-postgres` into `/opt/argus-v18/backups/argus-<UTC>.dump`
  (+ `.sha256`, + `.fingerprint`). The fingerprint is, per table, the row count and an md5 of every row as text,
  taken **before and after** the dump; if they differ (an investigation wrote meanwhile) the dump is discarded and
  the script says so (`BACKUP STOP`). Folder `700`, files `600`: a dump holds password hashes (`principal`), so it
  never leaves the VM.
- `verify <dump> --as <handle>`: checks the sha256, restores into a throwaway `argus-lab-pgrestore`
  (`postgres:16-alpine`, `--network none`, no port, data in `tmpfs`, 384 MB / 0.4 CPU), compares its fingerprint
  with the stored one (`VERIFY OK` / `VERIFY MISMATCH`), and always removes the container. It never touches
  `argus-v18-postgres`.

Not in scope: scheduling (cron) and retention of old dumps; copying dumps off the VM (needs an encryption decision).

## Steps

1. State probe on vm-095 (read-only): database size, free disk and memory, the image present.
2. Script, tests first (`tests/test_db_backup.py`): 6 offline tests with a fake `docker`, plus one against a real
   throwaway Postgres (`ARGUS_TEST_DOCKER=1`). **Red seen:** all 6 offline tests failed against a stub script
   (`assert 1 == 0`, missing `BACKUP OK` / `VERIFY OK`). Green: 6 passed; the real-Docker test passed on the laptop
   (Docker Desktop 29.8.1).
3. Deploy the branch on vm-095, run `backup` then `verify`, `nonint-check` before/after, archive the evidence.
   **Done:** `BACKUP OK` (11 tables, 4603 rows, 363 KB, root-only files); the first `verify` never ran because the
   block expanded `backups/argus-*.dump` in the operator's shell, which cannot list the 700 folder, so we added
   `verify latest` (red seen: `VERIFY STOP: no such dump: latest`); re-run: **`VERIFY OK: 11 tables, 4603 rows
   match`**, restore container removed, postgres never restarted, NO INTERFERENCE.
   Evidence: [`../../execution/history/T-0017/step-03/evidence.md`](../../execution/history/T-0017/step-03/evidence.md).
4. Brain: phase 5 to 100 %, `CURRENT_STATE.md`, `NEXT_STEP.md`, journal; pull request. **Done.**

## Follow-ups (not in this task)

- Run the backup on a schedule (cron or the T-0014 scheduler) and keep the last N dumps.
- A copy off the VM (today the only copy sits on the same disk as the database): needs an encryption decision first.
