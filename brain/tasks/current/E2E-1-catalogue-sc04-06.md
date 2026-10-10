# E2E-1 — SC-04, SC-05 and SC-06 in the scenario runner's catalogue

| Field | Value |
|---|---|
| Status | `in progress` — step 1 (the catalogue entries) and step 2 (batch 1 on vm-166: 17/20) done 2026-10-10; step 3 (read the three misses, batch 2 of SC-07 and SC-05) next |
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

## Step 2 (vm-166's lease, done 2026-10-10)

Both VMs on `main` `ebbe9c9`. An SC-04 trial passed, then batch 1 (`--runs 5 SC-07 SC-04 SC-06 SC-05`, 13:23-16:12
UTC; [evidence](../../execution/history/E2E-1/step-02/evidence.md)):

| Scenario | Pass | Misses |
|---|---|---|
| SC-04 | 5/5 | — |
| SC-06 | 5/5 | — |
| SC-07 | 4/5 | run 4: root cause the client, not the backend (a wrong conclusion) |
| SC-05 | 3/5 | runs 1, 3: escalated without naming the filler (a safe abstention) |

0 errors; every reset clean, NO INTERFERENCE after every run. Detection, class and first runbook right in all 20
runs: the misses are in the model's conclusion.

## Step 3 (next)

1. Read the evidence of the three missed incidents on vm-095 (`inc_e7e415955549`, `inc_3e6af419ab13`,
   `inc_c18ea3c6bcf3`): what the model read and why it concluded or abstained. No change before that.
2. Batch 2: `--runs 5 SC-07 SC-05` (vm-166's lease), to tell variance from a systematic gap.
3. SC-02 × 5 when vm-095's lease is free (its failure runs on vm-095's lab).
