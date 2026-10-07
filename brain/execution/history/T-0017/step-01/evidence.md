# T-0017 step 01 — evidence (2026-10-06, run by conantkd, session 06cb9843af9b)

Goal: read-only state probe of vm-095 before the Postgres backup/restore drill.

Key output lines from output.bash, SANITIZED (no addresses, no secrets, no personal names).

| Check | Expected | Observed |
|---|---|---|
| 1.1 session marker | `holder=conantkd session=06cb9843af9b` | `holder=conantkd session=06cb9843af9b` |
| 1.2 deployed code | `commit=2097eb1…`, `ref=main` | `commit=2097eb155cc8…` |
| 1.2 containers | `argus-v18-postgres` healthy, no `argus-lab-pgrestore` | `argus-v18-postgres Up 14 hours (healthy)`; no restore container |
| 1.3 database | Postgres 16, a few MB | `pg: 16.15 size: 12 MB`; 11 tables: audit 894, checkpoint_blobs 634, checkpoint_migrations 10, checkpoint_writes 1332, checkpoints 284, evidence 405, incident 79, notification 27, principal 4, run_event 932, schema_migrations 2 (live-tuple estimates) |
| 1.3 room for the drill | disk and memory well above the need | root filesystem 85 GB free (13 % used); 4383 MB memory available |
| 1.3 image | `postgres:16-alpine` present | `postgres:16-alpine 721873c34ceb` (no pull needed) |
| 1.3 backups folder | none yet | `backups: none yet` |

nonint-check: NO INTERFERENCE on vm-095 (yes) — `T-0017.1 PROBE DONE`.

Conclusion: the VM matches the Brain; the drill (≤ 384 MB, tmpfs ≤ 256 MB, a dump of a few MB) fits easily.
