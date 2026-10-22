# OP-008 step 04 — evidence: a fresh verify, the prune preview, the sha256 after-check (2026-10-21, conantkd)

Run on vm-095 by conantkd's agent (S.0, S.2) and by conantkd (S.1, the dry run: the agent's permission check refused
a prune, even a preview). Commands: [`code.bash`](code.bash). Sanitized: no addresses, no secrets.

| Check | Observed | Result |
|---|---|---|
| Before | `nonint-check before` saved (54 lines); disk 32 % used (66 GB free); `backups/` 52 MB | OK |
| Dry run (`KEEP=7`) | `newest verified (kept): argus-20261014T162458Z.dump`; **`PRUNE DRY RUN: 16 backup sets would be removed`** (2026-10-13T03:46Z to 2026-10-20T05:20Z) | preview only |
| **Verify the newest** | `argus-20261021T201818Z.dump` (the H2 deploy's backup, migration 012): **`VERIFY OK: 17 tables, 32759 rows match`**; marker written | OK |
| sha256 after-check (open since step 03) | `argus-20261014T162458Z.dump: OK`, `argus-20261021T201818Z.dump: OK`; both `.verified` present; 24 dumps in the folder | OK |
| After | `NO INTERFERENCE: non-Argus objects unchanged`; lease released | OK |

## Notes

1. **No backup had been verified since 2026-10-14**: the deploys back up (`BACKUP OK`) but do not run `verify`. With
   today's verify, the prune keeps a restore point from today instead of a week-old one. Proposal: every deploy's
   code.bash runs `verify` on the backup it just took (about 1 minute).
2. **Approval asked:** one `prune --apply` with `KEEP=7` on vm-095. With today's verified set it removes the sets
   from 2026-10-13 to 2026-10-20 (the 2026-10-14 verified one included, superseded) and keeps the 7 newest
   (2026-10-20T13:08Z to 2026-10-21T20:18Z, the newest verified among them). The list is re-previewed right before the
   apply; space is not pressing (52 MB).
