# E2E-8 — Close Phase 12: every scenario through the runner, five runs each

| Field | Value |
|---|---|
| Status | `planned` — written 2026-10-12 by `conantkd` for `juanbetancurm` |
| Phase | 12 (end-to-end tests) — [`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md) |
| Architecture | no change expected (no ACR): runner catalogue entries and VM runs |
| Branch | `task/E2E-8-phase12-close` (this file); the work on its own branches from `main` |
| Owner | `juanbetancurm` (+ agent), quality lane |
| Needs the VM lease | both (SC-10 and the identity proof use vm-095; SC-12 and SC-01 vm-166) |

## Goal (plain language)

Phase 12 asks for **five runs of every scenario** through the CLI path (`ops/e2e/run.py`). Today (2026-10-12):

| Scenario | In the runner catalogue | Runs on the VMs |
|---|---|---|
| SC-01 … SC-08 | yes | **5/5 each** (SC-02 E2E-6, SC-05 E2E-5) |
| H-1, H-2, SC-09, SC-11 | yes | 1/1 each (LangGraph, 2026-10-06/09) |
| SC-10 (vm-095 exporter stopped: `monitoring_blind_spot`, RB-014) | **no** | 1/1 (LGS) |
| SC-12 (vm-166 read gateway stopped: vm-166 escalates, vm-095 continues) | **no** | 1/1 (LGS) |
| identity proof (SC-01 on vm-166 + SC-02 on vm-095 at once: same container name, two hosts) | **no** | 1/1 (LGS) |

Phase 12 is done when each line is 5/5 (or every miss is read and explained), as SC-01 … SC-08 are.

## Before starting (prerequisites)

1. **Merges, in this order** (all from 2026-10-12, waiting for your review): #98 (3a) → #103 (3b, stacked on #98;
   GitHub retargets it to `main`) and #101 (3c) in any order; #97 (roll-up), #99 (EVAL-3 step 2), #100 (EVAL-4),
   #102 (`rotate-token.sh`) are independent.
2. **AFTER-MERGE of both VMs to `main`.** Both VMs run `task/T-0019-batch3b-host-verbs` `9ac49ec` (3a + 3b), verified in
   T-0019 step 08. On `main` after the merges: `deploy.sh main`, the target services rebuilt (read gateway, host probe,
   network probe changed), on vm-095 a backup and agent, worker and scheduler recreated together; 20/20,
   `phase3_check` 55/55, WRITE GATE CLOSED, LAB BASELINE OK, NO INTERFERENCE. Blocks to copy: T-0019 step 07 `C.1`
   and step 08 `B.1` (`brain/execution/history/T-0019/`), with `BR=main`.
3. `brain.py rollup` on a `task/rollup-<date>` branch once the PRs are in (the roll-up #97 covers up to #96).

## Steps

1. **Catalogue (offline, tests first):** add to `ops/e2e/scenarios.yaml`
   - **SC-10:** stop vm-095's exporter (the T-0027 / LGS commands), gate on the scrape target being down, expect
     `monitoring_blind_spot` / RB-014 escalated **with no model call** and every read on vm-095; reset = start it,
     pre-gate = target up again. The file's header says "Not here yet: SC-10 and SC-12 (they stop Argus's own
     services)": write the reset so a failed run never leaves the exporter stopped.
   - **SC-12:** stop vm-166's read gateway, a report on a vm-166 container escalates (no crash), and a report on vm-095
     still works in the same run; reset = start the gateway.
   - **identity proof:** SC-01 and SC-02 started together; two incidents, each with its own host's root cause, no read
     across hosts. The runner runs one scenario at a time today: this needs a small runner change (a `together:` list,
     or a scenario with two requests), with tests.
2. **Runs (both leases):** `ops/e2e/run.py H-1 H-2 SC-09 SC-11 --runs 5` (no failure is induced: minutes), then
   `SC-10 --runs 5`, `SC-12 --runs 5` and the identity proof × 5. Read every miss.
3. **Record:** evidence per step, the task file, a journal entry; Phase 12's row of `IMPLEMENTATION_PLAN.md` (in the
   next roll-up) to 100 % when every line is 5/5.

## Not in this task

The Prometheus-down alarm (Phase 13, T-0032's "not covered") and the §12.7 combined capabilities stay their own tasks.
