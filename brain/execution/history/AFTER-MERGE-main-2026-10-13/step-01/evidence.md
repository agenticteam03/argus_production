# AFTER-MERGE (main) 2026-10-13 step 01 — evidence (run by conantkd, session 38abbb604d92)

Goal: both VMs from `task/T-0035-monitoring-heartbeat` (`239e1d6`, T-0035 step 3) to `main` (`ad72617`) after PRs
#113–#131 (#123 merged while A.1 ran on vm-166, so the deployment includes it). The agent ran the blocks of
[`code.bash`](code.bash) over ssh, in order, inside the lease (both VMs, until 19:17 UTC after a renewal).

| Block | Expected | Observed | Result |
|---|---|---|---|
| M.1 markers | the same marker on both VMs | both `holder=conantkd session=38abbb604d92` | OK |
| A.1 vm-166 → main | SESSION OK; DEPLOY OK (main); target services up; LAB BASELINE OK; NO INTERFERENCE | `SESSION OK`; baseline saved (63 lines); `DEPLOY OK: ad72617a596c (main)`; `target services up: 5`; `commit=ad72617…`, `ref=main`; `LAB BASELINE OK`; `NO INTERFERENCE: non-Argus objects unchanged` | OK |
| A.1 vm-095 → main + agent | as above + BACKUP OK; migrations 001–006 (006 already applied); one image, restarts 0, health 200, 20/20, 55/55, WRITE GATE CLOSED | `SESSION OK`; baseline saved (54 lines); `BACKUP OK` (1881050 bytes); `DEPLOY OK: ad72617a596c (main)`; `target services up: 4`; 001–006 `already applied`; agent, worker, scheduler recreated together, all on image `0206f4339441`, `running restarts=0`; `health 200`; `worker: no startup errors`; `20/20 database checks passed`; `55/55 checks passed`; `WRITE GATE CLOSED`; `commit=ad72617…`, `ref=main`; `LAB BASELINE OK`; `NO INTERFERENCE` | OK |
| P.1 vm-166 Prometheus | recreated; heartbeat rule loaded; every target up; NO INTERFERENCE | `Started`; `10 rules; heartbeat: True`; cadvisor, db-probe, exporter, node-exporter `up`; `ArgusMonitoringHeartbeat/firing`; `NO INTERFERENCE` | OK |
| P.1 vm-095 Prometheus | as above | `Started`; `10 rules; heartbeat: True`; cadvisor, exporter, node-exporter `up`; heartbeat firing after ~10 s; `NO INTERFERENCE` | OK |
| Heartbeat after both | `monitoring_state` alive on both hosts; no incident opened | scheduler `monitoring heartbeat: stale after 180 s, grace 300 s`; `vm-095` and `vm-166` `alive`, 3 fresh ticks each; 0 incidents opened in the last 30 minutes | OK |

Notes:
- On vm-095 the last two lines of A.1 (`deploy.sh status`, `nonint-check after`) did not run when the block went
  through `ssh … bash -s`: a command in the block read the rest of stdin. They were run right after on their own.
  Blocks sent this way need `</dev/null` on every command inside them.
- 10 rules on both hosts: the 9 of T-0035's deployment plus T-0043's `ArgusScrapeTargetMissing`.

State after this step: **both VMs on `main` `ad72617`** (vm-095's agent, worker and scheduler on one image built from
it; both Prometheus with T-0035's heartbeat rule and T-0043's config). No model call.
