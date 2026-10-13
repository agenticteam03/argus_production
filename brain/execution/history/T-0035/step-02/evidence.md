# T-0035 step 2 — evidence (2026-10-13 UTC, run by conantkd's agent over ssh; both leases, session 4f8a9d4f8dc1)

Goal: the heartbeat rule on both hosts' Prometheus, the real renewal measured on Alertmanager 0.34.0 (`juanbetancurm`'s
note 1 of #108), then migration 006 and vm-095's agent, worker and scheduler from the branch with the check on.

| Block | Expected | Observed | Result |
|---|---|---|---|
| B.1 vm-166 (`dfb135f`) | DEPLOY OK; rule in `alerts.yml`; Prometheus recreated, rule loaded and firing; LAB BASELINE OK; NO INTERFERENCE | `DEPLOY OK: dfb135ff1a6e (task/T-0035-monitoring-heartbeat)`; `heartbeat rule in alerts.yml: 1`; `prometheus running`; `rule loaded: True state: firing`; `LAB BASELINE OK`; `NO INTERFERENCE` | OK |
| B.1 vm-095 (`dfb135f`) | as above | the same lines | OK |
| Measurement (8 min, every 30 s, both Alertmanagers from vm-095's scheduler container, read-only) | the renewal period and `endsAt` | `updatedAt` renewed every 60–75 s on both hosts (largest age seen 64 s); `endsAt` = `updatedAt` + 240 s; `argus_host` = the host read | OK |
| B.2 vm-095 (`800a9df`, the check on) | BACKUP OK; DEPLOY OK; schema with 006; one image, restarts 0; health 200; 20/20; 55/55; WRITE GATE CLOSED; the scheduler logs the check; LAB BASELINE OK; NO INTERFERENCE | `BACKUP OK` (1879667 bytes); `DEPLOY OK: 800a9df1547c`; `schema: … 005_alert_resolution, 006_monitoring_state`; agent, worker, scheduler on `c65852339eb7`, `running restarts=0`; `health 200`; `20/20`; `55/55`; `WRITE GATE CLOSED`; `monitoring heartbeat: stale after 180 s, grace 300 s`; `LAB BASELINE OK`; `NO INTERFERENCE` | OK |
| vm-166 checkout (`800a9df`) | DEPLOY OK; NO INTERFERENCE | `DEPLOY OK: 800a9df1547c`; `LAB BASELINE OK`; `NO INTERFERENCE` | OK |
| B.2 again (`239e1d6`, 2026-10-13 06:04 UTC: the loss notification) | as B.2 | `BACKUP OK`; `DEPLOY OK: 239e1d6a1492`; one image `244249401450`, restarts 0; health 200; 20/20; 55/55; `WRITE GATE CLOSED`; the check logged; `LAB BASELINE OK`; `NO INTERFERENCE`; vm-166 checkout `239e1d6`, `NO INTERFERENCE` | OK |
| State after one minute | both hosts `alive` after two fresh ticks; the heartbeat ignored by intake | `vm-095 state=alive fresh_ticks=2`, `vm-166 state=alive fresh_ticks=2`; reconcile `{'vm-095': {'ignored': 1}, 'vm-166': {'ignored': 1}}` | OK |

**Decision from the measurement:** `stale_after` 180 s and `grace` 300 s stay. 180 s tolerates one missed renewal
(2 × 75 s = 150 s) and declares a loss before the host's other alerts expire (their `endsAt` is also `updatedAt` +
240 s), so no alert is falsely resolved in between.

**Slip (recorded):** the rule was loaded (B.1, 04:58 UTC) while vm-095 still ran `main`'s scheduler, which does not
filter the heartbeat. It opened one incident per host at 04:59 UTC (`inc_37f342b585bb` on vm-166, `inc_e1bcaffa0d3f`
on vm-095), both closed `unsupported_escalated` in about 5 s ("evidence pack collected; no diagnosis is claimed"),
never repeated (the alert keeps its identity). The new scheduler (B.2, 05:09 UTC) ignores it. The task file now states
the order: the scheduler that filters the heartbeat first, then the rule.

Step 3 (stopping vm-166's Prometheus, then its Alertmanager, with a queued application incident) was not run by the
agent: it stops workloads, which needs the developer. The block is in `brain/execution/current/code.bash`.
