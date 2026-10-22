# OP-008 step 05 — evidence: the approved `prune --apply` (2026-10-22 UTC, conantkd)

The second `prune --apply` with `KEEP=7` on vm-095, approved by juanbetancurm in #247 and re-previewed right before
the apply, as step 04 asked. Run by conantkd after DEPLOY-afb72e8 (whose backup, 12:56Z, is the newest set).
Commands: `db-backup.sh prune --as conantkd`, then the same with `--apply`. Sanitized: no addresses, no secrets.

| Check | Observed | Result |
|---|---|---|
| Before | `nonint-check before` saved (54 lines) | OK |
| Dry run (`KEEP=7`) | **`PRUNE DRY RUN: 18 backup sets would be removed`**, oldest `argus-20261013T034636Z.dump` | preview |
| Apply | **`PRUNE OK: 18 backup sets removed`** | OK |
| After | `NO INTERFERENCE: non-Argus objects unchanged` | OK |

## Notes

1. **18, not the 16 of the approval:** two more sets aged out of the newest 7 since step 04 (the backups taken after
   it, today's included), as in step 03 (the approved 9 plus 3). The rule approved was `KEEP=7`, not a fixed list.
2. **Open, next vm-095 session:** list `backups/` (expect 7 sets, the 2026-10-21T20:18Z verified one among them) and
   `sha256sum -c` the newest verified dump. The preview was read through `tail`, so the kept list was not printed.
