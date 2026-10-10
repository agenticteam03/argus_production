# E2E-1 — SC-04, SC-05 and SC-06 in the scenario runner's catalogue

| Field | Value |
|---|---|
| Status | `in progress` — step 1 (the catalogue entries, offline) done 2026-10-10; step 2 (a batch on vm-166) needs its lease |
| Phase | 12 (end-to-end tests) — [`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md) |
| Architecture | no change (no ACR) |
| Branch | `task/E2E-1-catalogue-sc04-06` (from `main`) |
| Owner | `juanbetancurm` (+ agent), quality lane ([`../../policies/PARALLEL_LANES.md`](../../policies/PARALLEL_LANES.md)) |
| Needs the VM lease | step 2 only (vm-166) |

## Goal (plain language)

SC-04 (database sessions leaked), SC-05 (disk almost full) and SC-06 (CPU quota) were each proven once by hand on
vm-166 (T-0020, T-0024, T-0028). Phase 12 asks for repeated runs: the runner (`ops/e2e/run.py`, T-0023) can repeat
them only when they are in its catalogue.

## Step 1 (offline, done)

`ops/e2e/scenarios.yaml`:
- **commands:** start and reset are those of the VM proofs (the evidence files in
  `execution/history/T-0020`, `T-0024`, `T-0028`); the resets remove only what the scenario started, `rm -f`
  (idempotent), never `compose down`;
- **gates:** the detector's own signal and threshold (`db_connection_usage` ≥ 0.9; `host_disk_used_ratio_5m` ≥ 0.9
  over `/` and the lab filesystem; `container_cpu_throttled_ratio_5m` ≥ 0.5 and quota used ≥ 0.8), so the request
  finds the failure the detector needs;
- **pre-gates:** the signal back under its threshold (SC-04, SC-05), or no burner samples in the last 5 minutes
  (SC-06), so run N never sees run N-1's failure;
- **expected:** diagnosed, the class, the root cause (the leaker, the filler, the burner itself), the class's first
  runbook (RB-004, RB-005, RB-006), every read on vm-166.

SC-05 needs the lab filesystem `/srv/argus-lab-fill` (T-0024, kept mounted on vm-166).

Tests: `tests/test_e2e_runner.py` (red seen: the 3 scenarios were missing; 36 pass), including a check that each
gate holds the detector's signal expression exactly as the agent fills it. `run.py --dry-run SC-05` prints the steps
and executes nothing.

## Step 2 (needs vm-166's lease)

`ops/e2e/run.py --runs 5 SC-04 SC-05 SC-06` from the laptop, as a background batch, once the VMs run a commit with
`cpu_saturation` (`main` since #59) and the holder of vm-166's lease agrees. Record the per-scenario result in
`execution/history/E2E-1/` and the phase-12 line in the next roll-up.
