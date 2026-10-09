# OP-011 step 02 — evidence: correlation deployed; SC-03 still gave two incidents (2026-10-09, conantkd, session 75c48aa9bfad)

Mutating (vm-095: backup, migration 004, agent image; vm-166: checkout; the lab), run by the agent over SSH
(`code.bash` in this folder). Sanitized: no addresses, no secrets.

| Check | Result |
|---|---|
| State probe | both VMs on `task/T-0024-sc05-disk` `b049086`, LAB BASELINE OK, NO INTERFERENCE |
| vm-095 | `BACKUP OK` (`argus-20261009T131715Z.dump`); `DEPLOY OK: ca7977c8e294 (task/OP-011-correlation)`; `schema: 001_init, 002_checkpoints, 003_worker_lease, 004_alert_occurrence`; agent, worker, scheduler recreated; `argus.application.correlation` present (window 0:30:00); reconcile every 60 s, no alert |
| vm-166 | `DEPLOY OK: ca7977c8e294` (checkout only) |
| SC-03 start | `argus-lab-cache` stopped 13:19:30 UTC |
| Alerts (vm-166 Alertmanager) | `DependencyProbeFailed` startsAt 13:21:01; `ContainerUnhealthy` startsAt **13:21:31** |
| Pass 13:21:09 | `{'vm-166': {'started': 1}}` → `inc_67a608e63ce5` (occurrence `DependencyProbeFailed started`); DIAGNOSED `dependency_unavailable`, root cause `argus-lab-cache`, **closed 13:21:40** |
| Pass 13:22:09 | `{'started': 1, 'duplicate': 1}` → `inc_e74b841c66f9` (occurrence `ContainerUnhealthy started`); DIAGNOSED, same class and root cause, closed 13:22:26 |
| Pass 13:23:09 | `{'duplicate': 1}`: no third incident |
| Reset | cache started; 0 active alerts 13:23:19; LAB BASELINE OK and NO INTERFERENCE on both VMs |
| Note | the first `docker compose` call read the rest of the `bash -s` script from stdin; the block was re-run with `</dev/null` (no effect on the result) |

**Finding.** The code does what §6.4 says: it attaches only to an **open** incident. The two alerts arrived one pass
apart (the second started 30 s after the first), and the first incident was diagnosed and closed in 31 s, before the
second alert was pulled. So one failure still gave two incidents. The second alert **started (13:21:31) before the
first incident closed (13:21:40)**: it belongs to the same episode. Decided by `conantkd`: ACR-0004 (an alert that
started before the latest incident of its target and class closed is attached to it), step 03.
