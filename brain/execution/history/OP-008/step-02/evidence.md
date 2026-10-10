# OP-008 step 02 — evidence: verify and prune dry run on vm-095 (2026-10-10, conantkd, session 0583614fc355)

Run by the agent over SSH (`code.bash` in this folder, shared by the OP-004 and OP-008 dry runs). Sanitized: no
addresses, no secrets. The branch sources were copied to `/tmp/argus-dryrun` with `git archive`; the deployed
checkout (`task/T-0030-vm-proof` `a56f014`) and the running agent were not changed.

| Check | Result |
|---|---|
| Before | `LAB BASELINE OK`; four backup sets in `/opt/argus-v18/backups` (2026-10-06 to 2026-10-10), none with a `.verified` marker yet |
| Verify | branch `2fbc07a`: `verify latest` restored `argus-20261010T023316Z.dump` into the throwaway `argus-lab-pgrestore`: **`VERIFY OK: 12 tables, 12225 rows match`**; the marker was written; no restore container left |
| Prune, default `KEEP=7` | `newest verified (kept): argus-20261010T023316Z.dump`; **`PRUNE DRY RUN: 0 backup sets would be removed`** |
| Prune, `KEEP=2` (preview only) | would remove `argus-20261009T131715Z` and `argus-20261006T185011Z`; the newest verified set kept; 13 files still present (12 + the new marker) |
| After | no file deleted; **NO INTERFERENCE** (`nonint-check after`), `LAB BASELINE OK` |

**Result:** the snapshot backup is restorable, the marker is written only after a matching restore, and the preview
names exactly what a bounded `--apply` would remove. No `--apply` was run: that needs a teammate's review of this list.
