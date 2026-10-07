# T-0017 step 03 — evidence (2026-10-06, run by conantkd, session 06cb9843af9b)

Goal: a real backup of the Argus database on vm-095, proved restorable in a throwaway container.

Key output lines from output.bash, SANITIZED (no addresses, no secrets, no personal names).

## First run (blocks 3.1–3.6 of `code.bash` in this folder)

| Block | Expected | Observed | Result |
|---|---|---|---|
| 3.1 session + before | `SESSION OK`, snapshot saved | `SESSION OK`; `saved /opt/argus-v18/baseline/before.txt (69 lines)` | OK |
| 3.2 checkout | `DEPLOY OK (task/T-0017-pg-backup-drill)`, nothing to rebuild | `DEPLOY OK: cf36bb1bae76 (task/T-0017-pg-backup-drill)`; empty rebuild list | OK |
| 3.3 backup | `BACKUP OK`, root-only files | `11 tables, 4603 rows`; `BACKUP OK: /opt/argus-v18/backups/argus-20261006T185011Z.dump (363199 bytes)`; folder `drwx------ root`, `.dump` / `.dump.sha256` / `.fingerprint` all `-rw------- root` | OK |
| 3.4 verify | `VERIFY OK: 11 tables, 4603 rows match` | `ls: cannot access '/opt/argus-v18/backups/argus-*.dump'` then `VERIFY STOP: no such dump:` | **failed (our block, not the script)** |
| 3.5 leftovers / live DB | no restore container; postgres not restarted | `restore container removed`; `argus-v18-postgres Up 14 hours (healthy)` (same uptime as the probe); `argus-v18-agent Up 8 hours`; `ref=task/T-0017-pg-backup-drill`; `LAB BASELINE OK` | OK |
| 3.6 after | `NO INTERFERENCE` | `NO INTERFERENCE: non-Argus objects unchanged`; `T-0017.3 DRILL DONE` | OK |

**Why 3.4 failed:** `DUMP=$(sudo ls -1t /opt/argus-v18/backups/argus-*.dump | head -1)` — the operator's own shell
expands the glob **before** `sudo`, and it cannot list the root-only (700) folder, so `ls` got the literal pattern.
The folder protection worked; the block was wrong. **Fix:** `db-backup.sh verify latest` finds the newest dump itself,
as root (test `test_verify_latest_picks_the_newest_dump_itself`, red seen: `VERIFY STOP: no such dump: latest`).

## Re-run of the verification (block 3b, `code-3b.bash` in this folder)

| Block | Expected | Observed | Result |
|---|---|---|---|
| 3b.1 session + before | `SESSION OK` | `SESSION OK`; snapshot saved | OK |
| 3b.2 checkout | `DEPLOY OK (task/T-0017-pg-backup-drill)`, nothing to rebuild | `DEPLOY OK: aba61c1cc098 (task/T-0017-pg-backup-drill)` | OK |
| 3b.3 verify latest | the 18:50 dump; `VERIFY OK: 11 tables, 4603 rows match` | `dump: /opt/argus-v18/backups/argus-20261006T185011Z.dump`; **`VERIFY OK: 11 tables, 4603 rows match`** | OK |
| 3b.4 leftovers / live DB | no restore container; postgres never restarted | `restore container removed`; `argus-v18-postgres Up 14 hours (healthy)`; `argus-v18-agent Up 8 hours`; `ref=task/T-0017-pg-backup-drill`; `LAB BASELINE OK` | OK |
| 3b.5 after | `NO INTERFERENCE` | `NO INTERFERENCE: non-Argus objects unchanged`; `T-0017.3b VERIFY DONE` | OK |

nonint-check: NO INTERFERENCE on vm-095 (yes, both runs).

**Result:** the backup of 2026-10-06 18:50 UTC restores into a clean Postgres 16 with every row of all 11 tables
identical (row count and content hash per table). The phase-5 backup/restore drill is done. State left on vm-095:
`/opt/argus-v18/backups/` (one dump, root-only); the checkout on `task/T-0017-pg-backup-drill` until the PR merges.
