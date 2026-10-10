# T-0030 step 02 — evidence: Postgres restarted and stopped under load on vm-095 (2026-10-10, conantkd, session d550d6afba41)

Run by the agent over SSH (`code.bash` in this folder). Sanitized: no addresses, no secrets.

| Check | Result |
|---|---|
| Setup | `BACKUP OK` (`argus-20261010T023316Z.dump`); `DEPLOY OK: a56f01455b5a (task/T-0030-vm-proof)`; agent, worker, scheduler recreated, **restarts=0**; Postgres up since 2026-10-06 |
| Run 1: restart mid-run | SC-03 (cache stopped 02:34:39) → `inc_32394f84942c` `running` 02:36:26 (the model investigating) → `docker restart argus-v18-postgres` at 02:36:26 (under a second) → the incident **DIAGNOSED** `dependency_unavailable` at 02:36:45. No error logged: the run was in its model call and the pool's connection check reconnected. Restarts still 0 |
| Run 2: 30 s outage | Postgres stopped 02:37:08 – started 02:37:39. **Worker:** `database call failed; retry in 5 s` at 02:37:39 (the claim's pool wait ended in an error), then on; **restarts=0** (before the fix that error ended `run_forever` and the container). **Scheduler:** no pass during the outage (it waited for a connection), the next at 02:37:52 `{'attached': 1, 'duplicate': 1}`, no error. **api:** `/healthz` 200 during and after; it reads incidents again after |
| Reset | cache started 02:39:10; no active alert 02:39:50; both occurrences of `inc_32394f84942c` (`started`, `attached`) resolved |
| Baseline | vm-095 on `a56f014`, vm-166 on `eebfa72` (unchanged by this task); LAB BASELINE OK, **NO INTERFERENCE** on both |

**Result:** a database restart and a 30-second outage are pauses: no Argus container restarted, the run in progress
was diagnosed, the worker retried and went on, the scheduler resumed its passes, the api kept answering.
