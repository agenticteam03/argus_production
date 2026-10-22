# OP-008 — Snapshot-consistent backup and retention

**Owner:** `conantkd` · **Branch:** `task/OP-008-backup-retention` · **PR:** #51 (merged 2026-10-10) · **Status:** the approved first `prune --apply` ran on vm-095
on 2026-10-14 (12 sets removed, 7 kept); 2026-10-21 (step 04): the newest backup verified, the sha256 after-check done, a second `prune --apply` (16 sets) awaiting approval ([evidence](../../execution/history/OP-008/step-04/evidence.md)).

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
- Review notes of PR #51 (2026-10-10): a `.verified` marker protects a set only while its dump still passes
  `sha256sum -c`; the dry run names the protected set (`newest verified (kept): …`, or `none`) and every verified set
  whose checksum no longer matches. Leftovers (`.dump.part`, and `.sha256`/`.fingerprint`/`.verified` without their
  dump) are listed as `leftover (not removed)` in both modes; removing them stays a manual, reviewed step.

## Verification and remaining steps

1. **Offline, done:** red seen for marker/retention and concurrent-write expectations; 15 tests pass, including two
   against throwaway PostgreSQL 16 containers. The concurrent-write test inserts a row immediately before `pg_dump`
   and verifies the restored copy against the earlier fingerprint. The Windows full suite's only failure is the
   existing OD-3 timing benchmark; Linux CI is the full-suite gate. Review notes (2026-10-10): three new tests
   (checksum-gated protection, `none` reported, leftovers listed and kept) red seen, then green; 18 in the file.
2. **VM dry run, done 2026-10-10** ([evidence](../../execution/history/OP-008/step-02/evidence.md)): `VERIFY OK` on
   `argus-20261010T023316Z.dump` (marker written); default `KEEP=7`: 0 sets would be removed; `KEEP=2` preview: the
   two oldest sets, the verified one kept. NO INTERFERENCE.
3. **Apply, done 2026-10-14** ([evidence](../../execution/history/OP-008/step-03/evidence.md)): approved by
   juanbetancurm in PR #138 (`KEEP=7`). A fresh backup first (`VERIFY OK: 13 tables, 29001 rows`); the dry run and
   the apply named the same 12 sets (the approved 9 plus 3 that aged out since); 7 sets kept, the newest verified
   among them; NO INTERFERENCE. Run without a Brain lease (journal). **Open:** `sha256sum -c` on the newest verified
   dump after the prune, at the next VM session; then set OP-008 to fixed.

Backup/verify scheduling remains a separate team decision; this branch installs no timer and touches no VM.
