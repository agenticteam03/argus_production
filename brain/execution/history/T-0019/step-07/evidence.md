# T-0019 step 07 — batch 3c on the VMs (2026-10-12, conantkd, both leases, session 66378486227b)

Branch `task/T-0019-batch3c-network-verbs` `030690a` on both VMs (before the merge, as batch 2 was verified).

## Deploy (C.1)

| Check | vm-166 | vm-095 |
|---|---|---|
| session, before | SESSION OK; NO INTERFERENCE | SESSION OK; NO INTERFERENCE |
| deploy | `DEPLOY OK: 030690a64203` | backup `argus-20261012T192443Z.dump`; `DEPLOY OK: 030690a64203` |
| services | target services up: 5 | target services up: 4; agent, worker, scheduler recreated, one image `8f4869a9a440`, running, restarts 0; health 200 |
| checks | — | 20/20 database checks; `phase3_check` 55/55; WRITE GATE CLOSED |
| after | `ref=task/T-0019-batch3c-network-verbs`, LAB BASELINE OK, NO INTERFERENCE | same |

## The routes from vm-166 (C.2, loopback ports)

| Request | Answer |
|---|---|
| `/connectivity?from=argus-lab-api&to=argus-lab-cache` | 200: both running on `argus-lab-app`; shared `[argus-lab-app]` |
| `/connectivity?from=argus-lab-api&to=argus-lab-db` | 200: shared `[argus-lab-app]` |
| `/connectivity?…&to=argus-lab-nope` | 404 "not in this host's allowlist" |
| `/connectivity?from=argus-lab-api&to=argus-lab-api` | 400 "from and to are the same container" |
| `/tcp?host=argus-lab-cache&port=6379&attempts=3` | 200: ok True, succeeded 3 |
| `/tcp?host=argus-lab-cache&port=6379` | 200: ok True, succeeded 1 (the old request) |
| `/tcp?…&attempts=6` | 400 "attempts must be 1-5" |

No address in any answer (network names only).

## The agent's code path (C.3, vm-095 tools process, no model)

- `check_connectivity ok | connectivity vm-166: argus-lab-api (running) on argus-lab-app -> argus-lab-cache (running) on argus-lab-app; shared networks: argus-lab-app`
- `check_tcp_connection ok | tcp argus-lab-cache:6379 from vm-166 app network: 3/3 connected (ok 0.5 ms, ok 0.5 ms, ok 0.6 ms)`

## The model on the 55 cases, 5 trials (C.4)

`eval-20261012-195620.jsonl` (kept on vm-095), started 19:56 UTC; NO INTERFERENCE after.

| Run | Accuracy (core) | Abstention | dependency | health | nginx | reads/run (dependency) | hard |
|---|---|---|---|---|---|---|---|
| EVAL-3 step 2 (`main` `244453b`) | 0.96 (0.99) | 0.98 | 1.00 | 0.72 | 0.92 | 4.16 | 0 0 0 |
| **batch 3c** (`030690a`) | 0.96 (0.99) | 0.98 | 0.96 | 0.76 | 0.96 | **3.40** | **0 0 0** |
| batch 3c, re-graded with EVAL-4's labels (#100) | 0.98 (0.99) | 0.98 | 0.96 | 0.92 | 0.96 | | |

- `check_connectivity` was used in 25 runs, all `ok`. In `dep-backend-wrong-network` (SC-07's story) all 5 runs read
  DNS and connectivity only (2 reads) and wrote the cause: "no shared Docker network: the client is attached to
  argus-lab-app while the backend is attached to argus-lab-iso. DNS resolution itself succeeds". Trial 4 fails only
  because it left `root_cause_target` empty (the text names the backend's network).
- The other misses are the known ones: health (wording, see EVAL-4; two escalation/abstain misses) and one nginx
  escalation.
