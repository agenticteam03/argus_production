# OP-008 — Snapshot-consistent backup and retention

**Owner:** `conantkd` · **Branch:** `task/OP-008-backup-retention` · **Status:** offline implementation verified; VM
dry run pending.

## Goal

Keep backups consistent while the database is writing and bound backup-folder growth without deleting the last
verified restore point.

## Accepted design and implementation

- `backup` starts a read-only, repeatable-read PostgreSQL transaction, exports a snapshot, fingerprints all public
  tables within that session, and passes its ID to `pg_dump --snapshot`. A concurrent write cannot make the
  fingerprint disagree with the dump. The session stays open until the dump completes.
- `verify` restores into the existing isolated, temporary PostgreSQL container. Only a matching restore writes a
  root-only `<base>.verified` marker.
- `prune --as <holder>` is a dry run by default. `--apply` removes complete backup sets older than the newest
  `ARGUS_BACKUP_KEEP` (default seven), while always keeping the newest verified set. The command refuses a wrong VM
  session marker or invalid keep count. No scheduler mode is included.

## Verification and remaining steps

1. **Offline, done:** red seen for marker/retention and concurrent-write expectations; 15 tests pass, including two
   against throwaway PostgreSQL 16 containers. The concurrent-write test inserts a row immediately before `pg_dump`
   and verifies the restored copy against the earlier fingerprint. The Windows full suite's only failure is the
   existing OD-3 timing benchmark; Linux CI is the full-suite gate.
2. **VM dry run, pending:** obtain the VM lease; probe state and `NO INTERFERENCE`; check restorable backup evidence;
   deploy the script; run `prune --as <holder>` without `--apply`; record exact candidate sets and preserved sets.
3. **Apply, pending teammate review:** backup deletion is a stop condition. Have a teammate review the dry-run list
   and restorable backup evidence before one bounded `prune --apply`. Verify retained dumps, markers, and
   `NO INTERFERENCE`. Set OP-008 to fixed only then.

Backup/verify scheduling remains a separate team decision; this branch installs no timer and touches no VM.
