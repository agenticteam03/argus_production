# E2E-1 — SC-04, SC-05 and SC-06 in the scenario runner's catalogue

| Field | Value |
|---|---|
| Status | `done` — steps 1-3 2026-10-10 (#63, #66, #69); the two evidence gaps it found were closed by [E2E-2](E2E-2-evidence-gaps.md) (SC-07 5/5) and E2E-3 / E2E-5 (SC-05 5/5 2026-10-12) |
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

## Step 3 (done 2026-10-10)

The three misses were read from the store on vm-095 (read-only), and batch 2 ran (`--runs 5 SC-07 SC-05`;
[evidence](../../execution/history/E2E-1/step-03/evidence.md)). Over both batches: **SC-07 6/10, SC-05 6/10**, 0 errors.

- **SC-05:** every `host.disk_usage` read hit `/` (28 %, its default mount) while the detector fired on the lab mount
  (92.6 %); the model saw a contradiction and escalated (or concluded with medium confidence).
- **SC-07:** the backend's assigned network exists only in comments; the model guessed which container was misplaced
  (the client 4 times, the host once). The label (the backend) is right.

## Step 4 (next)

1. E2E-2 (code, tests first): `host.disk_usage` without a mount reports every declared mount; the inventory declares
   each container's networks and `container.status` shows a container that is not on them.
2. After its merge: rebuild vm-095's agent (both leases), then `--runs 5 SC-05 SC-07` on vm-166.
3. SC-02 × 5 when vm-095's lease is free.
