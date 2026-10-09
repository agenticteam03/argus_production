# T-0023 — Phase 12: run the synthetic incidents end to end, repeatedly, and grade every run

| Field | Value |
|---|---|
| Status | `in progress` — steps 1-2 `verified` 2026-10-09 (SC-01 and SC-03 5/5 each on the VMs); step 3 `planned` |
| Phase | 12 — end-to-end tests ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md): "scripted e2e suite; ≥ 5 runs per scenario") |
| Architecture | no change (no ACR): a client of the HTTP API (§7.1) and of the lab; feeds the §21.2 evaluation later |
| Branch | `task/T-0023-e2e-runner` (from `main`) |
| Owner | `juanbetancurm` (+ agent) |
| Needs the VM lease | step 2 only (the first real batch) |

## Goal (plain language)

Today every scenario run is a set of manual blocks: start the failure on a VM, wait, ask Argus from vm-095, read the
answer, reset, check for interference. Quality claims need **at least 5 runs per scenario** (IMPLEMENTATION_PLAN
§7, §9), which is too slow by hand. A runner on the laptop does the same steps from a reviewed catalogue, the same
way every time, grades each result against the expected one and writes one line per run.

## Design

- **Where it runs:** the laptop. `python ops/e2e/run.py SC-01 SC-03 --runs 5 --as <you>`.
  - VM commands go through `ssh argus-vm095` / `ssh argus-vm166` (the developers' aliases), and only the commands
    written in the catalogue run there.
  - The investigation goes through the Argus HTTP API on the usual SSH tunnel (`127.0.0.1:18000`), as Swagger does.
    Nothing new is deployed on the VMs.
- **The catalogue** `ops/e2e/scenarios.yaml`, reviewed like code. Each scenario has: its host; `start` commands; a
  **readiness gate** (a command polled until its last line matches, with a timeout: never a fixed sleep; the
  Prometheus gate queries the host's own Prometheus on `127.0.0.1:18090`); the request (target, reason, kind); the
  expected result; `reset` commands.
- **One run:** the session marker on each touched host must be the runner's user → `nonint-check before` → start
  → gate → investigate → poll until `closed`/`escalated` → grade → **reset, always** (also after an error) →
  `nonint-check after`.
- **Stop rules:** a host that does not say `NO INTERFERENCE`, or a failed reset, stops the whole batch at once. A
  wrong diagnosis is a FAIL for that run; the batch goes on.
- **Grading** (from `GET /api/v1/incidents/{id}`, operator view): outcome; class; root-cause target; the first
  recalled runbook (audit `recall.passages`); whether a model call is allowed (`model: none` = no evidence with
  caller `model` and a strategy other than `model_loop`); every read on the expected host (host isolation).
- **Output:** `SC-01 run 3/5 PASS (inc_…, 94 s)`, a summary table, and a JSON-lines file **outside the repo**
  (default `~/argus-e2e/`), one record per run (the input of the §21.2 evaluation later).
- **Password:** `ARGUS_PASSWORD` from the environment, or a hidden prompt. Never written, never passed to ssh.
- `--dry-run` prints every command and request and touches nothing; `--list` lists the catalogue.

## Steps

1. **Runner + catalogue, offline tests (no VM).** `tests/test_e2e_runner.py` with a fake ssh and a fake API: the
   catalogue validates (every scenario has a host, a request, an expectation; unknown keys refused); the gate times
   out; reset runs after an error; interference stops the batch; the grader catches a wrong host, a wrong class, a
   wrong outcome, a wrong first runbook, a model call where none is allowed; the dry run executes nothing.
   Catalogue: H-1, H-2, SC-01, SC-02, SC-03, SC-07, SC-09, SC-11 (verified by hand before). SC-10/SC-12 (they stop
   Argus's own services) and SC-04 (after PR #38) come later.
2. **First real batch (vm-095 + vm-166, lease).** H-1, H-2, SC-09, SC-11 once (nothing induced); then SC-01 and
   SC-03, 5 runs each. NO INTERFERENCE after every run. Results recorded in `execution/history/T-0023/`.
3. **The rest:** SC-02, SC-07 × 5; then the next scenarios as they land (SC-04, SC-05, SC-06, SC-08).

## Done when

- The suite of step 1 is green with red seen, and the runner's dry run lists every catalogued scenario.
- At least SC-01 and SC-03 have 5 graded runs each on the real VMs, NO INTERFERENCE after every run.

## Red seen / evidence

- **Step 1 (2026-10-09): runner + catalogue.** `tests/test_e2e_runner.py` (22 tests). Red seen: collection error,
  `ops/e2e/run.py` did not exist. Then 22 passed; full suite **206 passed**, 2 skipped (Postgres tests included).
  `python ops/e2e/run.py --list` lists the 8 catalogued scenarios; `--dry-run` prints every step and runs nothing.
  Design choices: a **pre-gate** waits until the signal is clean before a run (the restart signal looks back 10
  minutes, so run N must not see run N-1's restarts); a gate is a comparison (`>=3`, `==0`) or a regular expression;
  a run that stops the batch is still written to the results file.
- **Step 2, first part (2026-10-09, vm-095 + vm-166).** H-1, H-2, SC-09, SC-11: 4/4 PASS. SC-03 × 5: **5/5 PASS**
  (`dependency_unavailable`, root cause `argus-lab-cache`, RB-003 first, every read on vm-166). SC-01: runs 1-2 PASS
  (`container_restart_loop`, RB-001 first; run 2 waited ~10 min in the pre-gate, as designed), run 3 ERROR: the
  laptop's API tunnel dropped (`ConnectionRefusedError`), its reset and NO INTERFERENCE check still passed; then ssh
  to vm-166 timed out in run 4's session check and the batch stopped before run 4 started anything.
- **Fix (2026-10-09): a dropped connection.** Red seen: 4 new tests failed. The runner now opens its own tunnel to
  vm-095 (local port 18001, keepalives, `ExitOnForwardFailure`) and reopens it when the API cannot be reached; an API
  call retries for about 2 minutes; ssh gets `ConnectTimeout`/`ServerAliveInterval` and retries a connection failure
  (rc 255) or a timeout, never a command that failed on the VM. 27 tests in `test_e2e_runner.py`.
- **Step 2, second part (2026-10-09).** With `4f8ae43`: SC-01 three more runs, 3/3 PASS. **Step 2 done: SC-01 5/5,
  SC-03 5/5**, H-1, H-2, SC-09, SC-11 1/1 each, NO INTERFERENCE after every run. Evidence:
  [`../../execution/history/T-0023/step-02/evidence.md`](../../execution/history/T-0023/step-02/evidence.md).
- **Review of PR #40 (2026-10-09, `conantkd`, fixes on this branch):** two holes, tests first (6 new tests, red seen
  6/6). (1) The API returns `evidence` and `audit` only to operators and approvers; without them the model and host
  checks passed on nothing. Now such a view is a problem in `grade` and the run is an ERROR, never a PASS. (2) The
  reset ran even when nothing was started (a pre-gate that never clears), and SC-07's `docker network rm` fails on an
  absent network, which would stop the batch with a misleading "fix by hand". Now the reset runs only once a start
  was attempted, and SC-07's reset succeeds when the network is already gone. 33 passed in `test_e2e_runner.py`.
