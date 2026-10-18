# DEPLOY-161 step 01 — evidence: vm-095 to `main` 0b3b4e8 (#160, #161, ACR-0017) (2026-10-16, juanbetancurm)

Goal: vm-095 on `main` after #160 (`GET /api/v1/incidents/{id}/metrics`) and #161 (`GET /api/v1/topology`), the two
routes of ACR-0017 for the UI. Run after the class demo. Before: vm-095 on `main` `f9a4a06` (#158's UI). Leases: vm-095
(session `19195da3fd04`) and vm-166 (session `bd7100416e18`), both released at the end. Commands:
[`code.bash`](code.bash). The public address is not written here (`policies/SECURITY.md` rule 4).

| Block | Observed | Result |
|---|---|---|
| P.1 vm-095 (read-only) | `commit=f9a4a06…` `ref=main` (the rollback); checkout clean (0); agent, worker, scheduler, ui `running restarts=0`; `health 200`; tracing off (0); its lab `LAB BASELINE OK` | OK |
| P.1 vm-166 (read-only) | `LAB BASELINE NOT OK: argus-lab-worker`: `Restarting (137)`, SC-01's out-of-memory worker left by the demo's real run | restored in S.2 |
| D.1 laptop | vm-095 lease claimed (`DEPLOY-161`); brain.py: an agent deploy needs **both** leases | S.1 |
| S.1 laptop | vm-166 lease claimed; vm-095 renewed; vm-166 marker written. vm-095's marker found **empty** (0 bytes, written 18:47 UTC), so the first D.2/D.3 attempts skipped themselves (nothing ran) | S.3 |
| S.2 vm-166 | `service=argus-lab-worker-oom oom=true restarts=356`; removed with the catalogue's reset (`--profile sc01 rm -sf`); `LAB BASELINE OK`; `NO INTERFERENCE` | OK |
| S.3 laptop | vm-095 marker written again: `holder=juanbetancurm session=19195da3fd04`, 42 bytes | OK |
| D.2 vm-095 → `main` + agent | `SESSION OK`; baseline saved (54 lines); `BACKUP OK` (2318802 bytes); `DEPLOY OK: 0b3b4e8e0f7a (main)`; migrations 001–006 already applied; agent, worker, scheduler recreated together on image `795790c3ca57`, `running restarts=0`; `health 200`; no startup errors (agent, worker); `ARGUS_HOME_HOST` `vm-095`; `20/20`; `55/55`; `WRITE GATE CLOSED` | OK |
| D.3 vm-095 UI (public mode) | `argus-v18-ui` recreated: `running health=healthy restarts=0`, ports 80 and 443 only; through the edge without a login: `GET /api/v1/topology` 401, `/api/v1/incidents/inc_smoke/metrics` 401 (the new routes exist and need a login), `/targets` 401, `/me` 401, `/docs` 404; the map read inside the agent: 15 nodes (the inventory's 15 targets), 6 edges, status `running`/`unknown`, Argus host `vm-095`, no address in the answer; `commit=0b3b4e8…` `ref=main`; `LAB BASELINE OK`; `NO INTERFERENCE` | OK |
| D.4 vm-095, logged in through the edge | `me 200 operator`; `incidents 200` (30); `topology 200` (15 nodes, 6 edges); `metrics 200` for `inc_e3267aa223c3` (`container_restart_loop`: `restarts_10m`, `container_memory_bytes`, `oom_killed`, `container_cpu_cores`, 67 points); overlay `200` (no broken link); no address in any answer | OK |
| D.5 laptop | leases released on vm-095 and vm-166 | OK |

Before S.3, a D.4 run against the old version answered `me 200` and `incidents 200`, then 404 on `/api/v1/topology`:
the old edge did not know the route (expected).

## Found on the way

- **Both leases.** A change to the agent on vm-095 needs vm-166's lease too (`PARALLEL_LANES.md`); the first plan
  claimed only vm-095. brain.py said so at the claim.
- **The demo left the lab changed.** SC-01's worker (`argus-lab-worker-oom`) was still in its restart loop on vm-166
  (356 restarts): the demo's real run had no reset. Earlier, on 2026-10-14 at 22:07 UTC, the demo's `break-cache` had
  left `argus-lab-cache` stopped (restored 2026-10-16 03:15 UTC, `DEMO-READY`). A pre-check of both labs before a
  deploy catches this.
- **An empty marker.** vm-095's `/opt/argus-v18/SESSION` was empty at 18:47 UTC (most likely a partial re-run of D.1's
  marker line). The blocks now check the marker with `if … fi` instead of `exit 1`, which closed the SSH shell; a
  wrong or empty marker skips the block and changes nothing.

## Not done here

- The browser check (log in, the incident list and one incident; the Map and Metrics tabs stay hidden until the
  frontend's `VITE_ARGUS_INSIGHTS=1` build) is not recorded in this file.
- `/opt/argus-v18/demo` on vm-095 (conantkd's demo files) was left as found.
