## 2026-10-13 — AFTER-MERGE: both VMs on main ad72617 (#113-#131)

Type: deployment
Who: conantkd (+ agent)
Context: E2E-8 step 2 must run on `main`. Both VMs ran `task/T-0035-monitoring-heartbeat` `239e1d6` (T-0035 step 3),
with migration 006 applied and the heartbeat rule loaded.
Decision / result: both VMs on `main` `ad72617`: target services rebuilt; on vm-095 a backup, migrations (001–006,
nothing new) and agent, worker and scheduler recreated together (20/20, 55/55, WRITE GATE CLOSED); then both
Prometheus recreated (10 rules, heartbeat loaded, every target up). `monitoring_state` alive on both hosts, no
incident opened. LAB BASELINE OK and NO INTERFERENCE on both.
Consequences: blocks sent over `ssh … bash -s` need `</dev/null` on each command (one read the rest of the block).
References: [evidence](../../execution/history/AFTER-MERGE-main-2026-10-13/step-01/evidence.md).

### Test state

No code change. Local CI unchanged.

### Next step

E2E-8 step 2 on both VMs: `ops/e2e/run.py H-1 H-2 SC-09 SC-11 --runs 5`, then `SC-10 SC-12 ID-1 --runs 5`.
