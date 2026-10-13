# OP-004 / OP-008 — dry runs again on main ad72617, for the teammate review before any --apply (2026-10-13, conantkd)

Read-only (no `--apply`), vm-095, both leases (session 2b41a356d48c). Scripts from the deployed `main`; OP-004 with
its default image `argus-v18-agent:1` (`main` `ad72617`).

**OP-004** `checkpoint-retention.sh --dry-run --as conantkd` (30 days): `DRY RUN: threads=0 checkpoints=0 blobs=0
writes=0`. Nothing is older than 30 days: an `--apply` today removes nothing. The daily timer stays a team decision
(`--scheduled` skips the lease check).

**OP-008** `db-backup.sh verify latest`: `argus-20261013T161342Z.dump`, `VERIFY OK: 13 tables, 24663 rows match`.
`db-backup.sh prune` (dry run, `KEEP=7`): 16 dumps; the 7 newest kept (2026-10-12T17:52Z … 2026-10-13T16:13Z, the newest
verified); **9 would be removed**: 2026-10-06T18:50Z, 10-09T13:17Z, 10-09T18:38Z, 10-10T02:33Z, 10-10T12:48Z,
10-10T22:00Z, 10-11T13:18Z, 10-11T23:23Z, 10-12T15:04Z. The backups use 23 MB; `/` is at 24 % (74 GB free): no hurry.

NO INTERFERENCE on vm-095. Next: a teammate reviews these lists in the PR; then one `prune --apply` (OP-008) and,
when there is something to remove, one `--apply` (OP-004).
