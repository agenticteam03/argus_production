# T-0013 step 05 — evidence (2026-10-04, juanbetancurm)

Key output lines from output.bash, sanitized (no addresses, no secrets, no personal names).

| Check | Expected | Observed |
|---|---|---|
| S5.1 lease + marker | branch pushed, lease yours, marker on both VMs | `VERDICT S5.1 OK` |
| S5.2 vm-166 `deploy.sh init main` | DEPLOY OK, clean checkout | `DEPLOY OK: 8eff9943bb17 (main)`, `VERDICT S5.2 OK` |
| S5.3 vm-095 `deploy.sh init task/T-0013-langgraph-skeleton` | DEPLOY OK, 002 present | `DEPLOY OK: c87d76c5e0a3 (task/T-0013-langgraph-skeleton)`, `VERDICT S5.3 OK` |
| S5.4 migration + rebuild | 002 applied, runner langgraph, 15/15 | `= 001_init (already applied)`, `+ 002_checkpoints applied`, `agent runner: langgraph`, `PASS DELETE checkpoint refused (permission denied for table checkpoints)`, `15/15 database checks passed`, `VERDICT S5.4 OK` |
| S5.5 H-1 + SC-09 | HEALTHY, UNSUPPORTED, both checkpointed | `outcome: HEALTHY`, `outcome: UNSUPPORTED → escalated to a human with evidence`, `checkpointed investigations: 0 -> 2`, `VERDICT S5.5 OK` |
| S5.6 + S5.7, first attempt | SC-01 diagnosed | **STOP**: the wait used Docker's counter (`restarts=3`) but Prometheus had `restarts_10m=1`, so detection matched no class: `outcome: UNSUPPORTED`, evidence pack, no invented diagnosis (correct behaviour); checkpointed (2 -> 3) |
| Fix | gate on what Argus reads | S5.6 now waits until vm-166's Prometheus shows `restarts_10m ≥ 3`; S5.7 is self-contained |
| S5.6 second attempt | Prometheus ≥ 3 | `docker restarts=11  prometheus restarts_10m=9`, `VERDICT S5.6 OK` |
| S5.7 SC-01 on LangGraph | DIAGNOSED, RB-001, checkpointed | `outcome: DIAGNOSED · class container_restart_loop`, RB-001 recalled, `checkpointed investigations: 3 -> 4`, `VERDICT S5.7 OK` |
| S5.8 reset SC-01 (vm-166) | NO INTERFERENCE | worker stopped and removed; `NO INTERFERENCE: non-Argus objects unchanged` |
| S5.9 vm-095 | all Up, NO INTERFERENCE | `NO INTERFERENCE: non-Argus objects unchanged` |
| S5.10 release | lease released | `Lease released.` |

nonint-check: NO INTERFERENCE on both VMs (yes).

Learned: a readiness gate must wait on the data the agent reads (Prometheus), not on the source it is derived from
(Docker) — Prometheus samples every 15 s, so it trails Docker by a few samples.
