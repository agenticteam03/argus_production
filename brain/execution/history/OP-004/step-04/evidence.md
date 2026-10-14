# OP-004 step 04 — evidence: the approved `--apply` on vm-095 (2026-10-14, conantkd)

Run by conantkd on vm-095 ([`code.bash`](code.bash), shared with OP-008 step 03). Approved by juanbetancurm in PR
#138: one `--apply` at 30 days, the daily timer stays off. Sanitized: no addresses, no secrets.

| Check | Expected | Observed |
|---|---|---|
| Before | `LAB BASELINE OK` | `LAB BASELINE OK` (`argus-lab-api` healthy) |
| Backup before the apply | `BACKUP OK`, `VERIFY OK` | `argus-20261014T162458Z.dump`: `VERIFY OK: 13 tables, 29001 rows match` |
| Dry run (30 days) | counts | `DRY RUN: threads=0 checkpoints=0 blobs=0 writes=0` |
| Apply (30 days) | the same counts | `PRUNED: threads=0 checkpoints=0 blobs=0 writes=0` |
| After | `NO INTERFERENCE` | `NO INTERFERENCE: non-Argus objects unchanged` |

**Result:** the apply ran as `argus_owner` and removed nothing, as the dry runs of 2026-10-10 and 2026-10-13 said:
the checkpoints start with T-0013 (2026-10-06), so no final incident is 30 days old yet; the first become eligible
around 2026-11-05. The apply also appends one `maintenance.checkpoints_pruned` audit record with zero counts (not
read back in this run).

**Deviation:** no Brain lease was claimed for this run (the lease of AFTER-MERGE-main was released at 06:59Z); the
scripts passed their check because `/opt/argus-v18/SESSION` still named conantkd. Nobody else held a lease at the time.

Open: the daily timer (`--scheduled` skips the lease check) stays a team decision.
