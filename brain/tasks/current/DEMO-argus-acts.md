# DEMO-ARGUS-ACTS — Argus acting in three staged scenarios (shared coordination file)

| Field | Value |
|---|---|
| Status | in progress; deadline 2026-10-28 (fast track) |
| Architecture | [ACR-0019](../../architecture/changes/ACR-0019-human-approved-remediation.md) (accepted); a new action family needs ACR-0035 (reserved here, task S2-1) |
| Branch | none: this file only coordinates; each piece has its own branch and PR |
| Owners | `juanbetancurm` and `conantkd`, each with their own agents; this file is what both read |
| Needs the VM lease | yes for the deploy window and the live runs (`conantkd` holds the leases) |

## Goal (plain language)

We present Argus resolving three staged faults end to end: detect, investigate, propose a fix, get a human approval, act, verify. The faults are staged; the
investigation is real. Scenario 1: the cache stops and, later, the API's CPU spikes (a red herring); the cache must rank first. Scenario 2: the API is moved to
the wrong network while everything stays healthy; Argus reconnects it (a new action). Scenario 4: the worker freezes while healthy and the queue grows; Argus restarts it
and verifies throughput and the queue.

## How we coordinate (read this first)

1. **This file is the contract.** Names in the "Contracts" section are fixed: change one only by a PR to this file that the other owner approves, never silently in code.
2. **Status lives in the table below, one row per piece, one line each.** Edit only your own rows (so edits from two people never touch the same line). Update `State`
   when you open a PR, when it merges and when you are blocked; put the PR number in the row.
3. **One PR per piece**, opened ready (no drafts), containing current `main` (merge it in; never rebase). A merge of `main` keeps an approval; a new commit does not.
4. **Approvals:** one approval of the last push from someone other than the author (`juanbetancurm` or `conantkd`). A PR that opens a write pair (a release PR) needs both.
   An ACR needs one approval that also counts as the second approval (AGENT_PROTOCOL §4). Non-protected PRs may be self-merged by their author under REVIEW_PROTOCOL.
5. **Nothing is deployed without the leases.** One deploy window for everything merged by then; the owner of the leases runs it.
6. **Do not edit the other owner's files** without a message here or in the PR. If a piece needs a file the other owner is changing, say so in your row.
7. **Cut line:** at the end of integration the owners decide together which scenarios act and which are shown as detection plus a proposal (the pair stays closed).

## Pieces

State values: `ready` (not started), `building`, `PR #n`, `merged`, `blocked: <why>`. Owner `J` = juanbetancurm's agents, `C` = conantkd's.

| Id | Piece | Owner | State | PR |
|---|---|---|---|---|
| X-1 | Rebuild phase 20 candidate on current `main` (draft #326 is far behind and conflicts) | C | merged | #354 |
| X-2 | Deploy phase 19 (#324, #347) and corpus (#349, #351, #352), migrations, one window | C | second window deployed `9798950` on 2026-10-28: tunnel, worker, agent, scheduler and vm-166 target; gate closed, checks pass | |
| X-3 | Gateway and socket-proxy services in the lab, action token (never in the repo), credential isolation on real images | C | building (stacked on #355; defined, not started: X-5's window starts them with the token) | |
| X-4 | Wire frozen-row execution to the gateway client with fresh precheck and verify | C | PR #355 (#354 merged; also needs the target redeployed on vm-166) | #355 |
| X-5 | Release PR, pair 1: `container.start` on the cache (both approve) | C | ready | |
| X-6 | Release PR, pair 2: `container.restart` on the job worker (both approve) | C | ready | |
| X-7 | Release PR, pair 3: `network.restore` on the API (both approve) | C | ready | |
| X-8 | ARCHITECTURE.md update and version bump for `network.restore`, in the PR that implements it (AGENT_PROTOCOL section 4; ACR-0035 itself may merge as `proposed`) | C | ready | |
| S1-1 | Ranking: a cause whose anomaly started after its dependency's is demoted; `analysis.anomaly_summary` offered to the dependency classes | J | ready | |
| S1-2 | Lab API CPU-spike fault and injection scripts | J | ready | |
| S1-3 | Evaluation case: cache first, API CPU after | J | ready | |
| S1-4 | "Approval waiting" notice to the team's Telegram route | J | ready | |
| S4-1 | Lab job worker, producer, queue, freeze fault (profile `sc10`) | J | ready | |
| S4-2 | Signals, alert, class `worker_stalled`, runbook RB-022 | J | ready | |
| S4-3 | Verification with several checks; stalled-worker evaluation case | J | ready | |
| S2-1 | ACR-0035 `network.restore` | J | ready | |
| S2-2 | Action card, catalogue entry, risk row, preconditions, API expected networks | J | ready | |
| S2-3 | Read of network connect/disconnect events (`services/target`) | J | ready | |
| S2-4 | Gateway: exact-body network connect/disconnect routes (either owner; say who takes it) | open | ready | |
| S2-5 | `link_ok` verify check, injection scripts, evaluation case | J | ready | |

## Contracts (names both owners build against)

**Releases (`write_gate.open`, one PR each, all on vm-166, lab scope):**
`container.start` on `vm-166/container:argus-lab-cache`; `container.restart` on `vm-166/container:argus-lab-jobworker`; `network.restore` on `vm-166/container:argus-lab-api`.

**Scenario 1.** API fault: environment flag `FAULT_ENABLE=1`, `GET /fault/cpu?s=N` (N at most 120); `/health` keeps answering. Scripts in `deploy/lab/demo/`: `s1-inject.sh`, `s1-reset.sh`.
The action is `container.start` (the cache is stopped), not restart. The evaluation case is `dep-cache-stopped-api-cpu-after`.

**Scenario 4.** Containers `argus-lab-jobworker` and `argus-lab-jobproducer`, compose profile `sc10`, queue = the Redis list `lab:jobs` on `argus-lab-cache`. Worker port serves `/health` (stays 200 when frozen),
`/metrics`, `/fault/freeze`, `/fault/unfreeze`. Metrics: `argus_lab_jobs_processed_total`, `argus_lab_queue_depth`, `argus_lab_last_processed_timestamp_seconds`. Signals: `jobs_processed_rate`,
`queue_depth`, `worker_last_processed_age_s`. Incident class `worker_stalled`, runbook RB-022. Inventory: the job worker depends on the cache and the lab database; role worker, stateless,
safe action `container.restart`, never `container.stop`. The evaluation case is `worker-stalled`.

**Scenario 2.** Action `network.restore` (ACR-0035): ONE worker call; the gateway then does connect, then disconnect (no new ledger state, no migration). Parameters `connect_network` and `disconnect_network`
(strings). Both must be lab networks (`argus-lab-[A-Za-z0-9_.-]+`): connect a declared network the target is not on; disconnect a network it is on that is not declared for it; never the default bridge, `host` or
`none`; vm-166 lab containers only. Expected network of the lab containers: `argus-lab-app`; the wrong one used in the demo: `argus-lab-iso`. Worker route: `POST /containers/{name}/network-restore`; the gateway
calls Docker's `POST /networks/{name}/connect` and `/disconnect` with the single body `{"Container": "<id>"}` (the configured network name, not the id). Verify check `link_ok` (the link recorder's latest state of
the edge dependent to target). Risk row: stateless amber, stateful red, proxy red, database forbidden. Rollback: NONE automatic; a person restores the old state by hand, and the approver card shows
`reversible: no` (ACR-0035 section 3.4). Scripts: `s2-inject.sh`, `s2-reset.sh`. Evaluation case `dep-api-moved-network`.

**Verification** may list several checks, all of which must hold within the window; the single-check form keeps working. Used by `container.restart` for worker targets and by `network.restore`.

**Reserved numbers:** ACR-0035 (network.restore). No new migration is expected; if one is needed it is 018 and must be announced in a row above.

## Out of scope

Anything on vm-095 as an action target; any pair not listed under Releases; changing the judge, the risk colours of existing actions, or the approval flow; the operator terminal (phase 21) and phases 22-23.
