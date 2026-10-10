# OP-004 step 02 — evidence: checkpoint retention dry run on vm-095 (2026-10-10, conantkd, session 0583614fc355)

Run by the agent over SSH (`code.bash` in this folder, shared by the OP-004 and OP-008 dry runs). Sanitized: no
addresses, no secrets. The branch sources were copied to `/tmp/argus-dryrun` with `git archive`; the deployed
checkout (`task/T-0030-vm-proof` `a56f014`) and the running agent were not changed.

| Check | Result |
|---|---|
| Backup evidence | `argus-20261010T023316Z.dump` restored by OP-008's `verify latest` in the same session: `VERIFY OK: 12 tables, 12225 rows match` |
| First dry run (`106b568`) | **stopped:** `missing credential /run/argus-secrets/db_password`. On vm-095 the owner secret is `0400` and owned by uid 70 (the Postgres image's user), not root; with `--cap-drop ALL` the container's root cannot read it. Nothing ran against the database; the image and `/tmp` were removed, `NO INTERFERENCE` |
| Fix (`123f1e3`) | the wrapper runs the container as the secret's owner (`stat -c %u:%g`), every other restriction unchanged; test red with `0:0`, green after |
| Dry run, 30 days (default) | **`DRY RUN: threads=0 checkpoints=0 blobs=0 writes=0`** (no final incident is older than 30 days yet) |
| Dry run, 1 day (preview only) | `DRY RUN: threads=88 checkpoints=783 blobs=1825 writes=3900` (proves the query sees the eligible rows) |
| After | temporary image `argus-v18-maint:op004` and `/tmp` removed; no row deleted; `LAB BASELINE OK`, **NO INTERFERENCE** |

**Result:** the command runs on vm-095 as `argus_owner` in a read-only transaction and reports counts. With the
default 30-day window an `--apply` would delete nothing today. No `--apply` was run and the timer is not installed.
