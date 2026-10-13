# E2E-8 — Close Phase 12: every scenario through the runner, five runs each

| Field | Value |
|---|---|
| Status | `in progress` — written 2026-10-12 by `conantkd` for `juanbetancurm`; step 1 (catalogue, offline) done 2026-10-13 by `conantkd` (`task/E2E-8-catalogue`); step 2 (the runs) next |
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
   `ops/e2e/run.py SC-10 SC-12 ID-1 --runs 5`. Read every miss.
3. **Record:** evidence per step, the task file, a journal entry; Phase 12's row of `IMPLEMENTATION_PLAN.md` (in the
   next roll-up) to 100 % when every line is 5/5.

## Step 1 — done 2026-10-13 (`conantkd` + agent, offline)

- **Runner** (`ops/e2e/run.py`): a command may run on another host (`{host: vm-095, run: ...}`; not `on:`, which
  YAML 1.1 reads as `true`); a gate may name its `host`, and `pre_gate` / `gate` may be lists; `investigations` (a
  list of `{request, expect}`) are all sent before the first is polled, each is graded, and the run passes only when
  all pass (a problem names its target). Every host a command, gate or request touches must be in `hosts` (session
  marker, NO INTERFERENCE), checked when the catalogue loads. Results keep one line per investigation.
- **Catalogue** (`ops/e2e/scenarios.yaml`):
  - **SC-10** stops vm-095's **`argus-v18-node-exporter`**, not the gate exporter `argus-v18-exporter` of the LGS run:
    since T-0027 a host that lost a scrape target is the class `monitoring_blind_spot` (`no_action_escalated`,
    RB-014, no model), while the gate exporter down still ends `undiagnosable` before any class (that path stays
    covered by its unit tests and the LGS run). Gate `up{job="argus-v18-node-exporter"} == 0` on vm-095; a check of
    `vm-095/host:vm-095` plus a check of vm-166's api (`no_incident`, reads on vm-166 only).
  - **SC-12**: SC-01's OOM loop on vm-166, then `argus-v18-read-gateway` stopped (gate: the restarts on Prometheus, which
    the exporter counts with its own Docker socket, and the gateway not running); the report on the worker must end
    `no_action_escalated` or `undiagnosable`, never `diagnosed`; a check of vm-095's api in the same run.
  - **ID-1** (identity proof): SC-01 and SC-02 together, with their own commands, gates and expectations (YAML anchors,
    so they cannot drift from SC-01 / SC-02).
  - The reset of SC-10 and SC-12 **starts the stopped Argus service first** (`docker start` also succeeds when it is
    running); a test holds every scenario that stops an `argus-v18-*` service to that.
- **Tests:** `tests/test_e2e8_catalogue.py` (11; red seen: `investigations` an unknown key, no SC-10 / SC-12 / ID-1, no
  host check); the 39 tests of `tests/test_e2e_runner.py` unchanged and green.

## Not in this task

The Prometheus-down alarm (Phase 13, T-0032's "not covered") and the §12.7 combined capabilities stay their own tasks.
