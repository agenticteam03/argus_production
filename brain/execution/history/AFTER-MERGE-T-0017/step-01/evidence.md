# AFTER-MERGE (T-0017) step 01 — evidence (2026-10-06, run by conantkd, session 796fd4f3bf61)

Goal: put vm-095's checkout back on `main` (`f126272`, after PR #25) without restarting or rebuilding anything.

Key output lines from output.bash, SANITIZED (no addresses, no secrets, no personal names).

| Block | Expected | Observed | Result |
|---|---|---|---|
| M.0 session marker | `holder=conantkd session=796fd4f3bf61` | the same line | OK |
| M.1 probe (read-only) | `SESSION OK`; `aba61c1…` on `task/T-0017-pg-backup-drill`; `LAB BASELINE OK`; health 200; the dump root-only | `SESSION OK`; `commit=aba61c1cc098…`, `ref=task/T-0017-pg-backup-drill`; `LAB BASELINE OK`; 8 `argus-v18-*` Up (postgres healthy); `health 200`; `argus-20261006T185011Z.dump` (+ `.sha256`, `.fingerprint`), all `-rw------- root` | OK |
| M.2 checkout to main | `DEPLOY OK: f126272… (main)`; rebuild hint = agent (not run); `ref=main`; `LAB BASELINE OK`; same uptime; NO INTERFERENCE | `saved /opt/argus-v18/baseline/before.txt (69 lines)`; rebuild hint names only the agent; `DEPLOY OK: f126272d9f97 (main)`; `commit=f126272d9f97…`, `ref=main`; `LAB BASELINE OK`; `argus-v18-agent Up 18 hours`, `argus-v18-postgres Up 24 hours (healthy)` (same as M.1); `NO INTERFERENCE: non-Argus objects unchanged`; `AFTER-MERGE T-0017 DONE` | OK |

nonint-check: NO INTERFERENCE on vm-095 (yes).

**Result:** vm-095 is on `main` `f126272`. Nothing was restarted. The running agent image is still the one built at
`2097eb1`: `main` now also holds T-0015 (`argus/adapters/inbound/http.py`, `argus/infrastructure/wiring.py`), so
the image will match the deployed commit after the agent rebuild of T-0015 step 6. vm-166 was not touched (on
`main`; its services' code is unchanged).
