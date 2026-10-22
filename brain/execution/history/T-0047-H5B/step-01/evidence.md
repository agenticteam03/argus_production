# T-0047 H5B step 01 — evidence: the #274 model batch before the merge, vm-095 (2026-10-22, juanbetancurm)

Goal: decide whether `analysis.anomaly_summary` stays offered to `dependency_unavailable` and `container_restart_loop`
(ACR-0024 §3.8). Before = main's code (the read registered, offered to no class), after = this branch. Both arms use
the 12 cases of the two classes, `--strategy model_loop`, 5 trials and `--model configured`, in the deployed image
(afb72e8) with a read-only `git archive` of `argus/` bound over `/app/argus`; no build, no deploy. The developer ran
the blocks from the coordinator's run file. Commands: [`code.bash`](code.bash) (H5B.2-H5B.5). The coordinator wrote
the re-run's H5B.2b-H5B.4c from them, with two guards: H5B.3b refuses while any `argus-v18-eval-h5b-*` container
exists, and each arm writes `h5b-<arm>-<UTC stamp>.jsonl` with no `rm`. No key, address or token is written here.

| Block | Observed | Result |
|---|---|---|
| H5B.2 | lease claimed on vm-095 (task T-0047-H5B), renewed to 120 min | PASS (2 of 2) |
| H5B.3 | `SESSION OK`; `ref=afb72e8`; `LAB BASELINE OK`; branch `b3cc16c`; code diff only `classes.py`; 12 cases; 6 per-target series; offers `[]` before and the two classes after; both arms `Up`, errors `0 0` | started |
| H5B.4 (early) | both arms still `Up` (nothing removed); before: dependency 5 of 8 so far, `dep-backend-stopped` trial 2 **HARD** `unsupported_root_cause=1` on main's code; after: 4 of 4 | partial |
| H5B.4 (final) | no containers and no result files: a block had been pasted twice, deleting the files | **lost** |
| H5B.5 | lease released | PASS (1 of 1) |
| H5B.2b | a new lease on vm-095 | PASS |
| H5B.3b | run stamp `20261022T174900`; 0 old containers; main `95e67a7`, branch `b3cc16c`; code diff only `classes.py`; 12 cases; offers `[]` then the two classes; both `Up`, errors `0 0` | started |
| H5B.4b | both arms `Exited (1)` (the CLI's status when a case fails), then removed; the summaries below; `NO INTERFERENCE: non-Argus objects unchanged` | summaries |
| H5B.4c | the one hard row, read-only (below); lease released afterwards | read |

| Arm | All 60 runs | top-1 / top-3 | `container_restart_loop` (30) | `dependency_unavailable` (25) | hard (outside policy, secrets, forbidden reads, unsupported root cause) |
|---|---|---|---|---|---|
| before (main `95e67a7`) | 47, 0.76 | 0.86 / 0.94 | 0.97 (worst trial 0.83) | 0.52 (worst trial 0.40) | 0 0 0 0 |
| after (`b3cc16c`) | 56, 0.93 | 0.96 / 1.00 | 1.00 (worst trial 1.00) | 0.84 (worst trial 0.60) | 0 0 0 **1** |

The 25 dependency runs are the five `dep-*` cases; `ambiguous-dep-all-running` (5 runs) escalated in every trial of
both arms. Other figures, before → after:
- reads per incident 2.9 → 3.6;
- p50 10 959 → 12 717 ms;
- ruled-out recall 0.52 → 0.60;
- problems 0.45 → 0.45.

The read `analysis.anomaly_summary` was called in 0 before-runs and 3 after-runs (2 dependency, 1 restart).

Failing runs (of 5):
- **before:** `dep-cache-paused` 4, `dep-cache-restarting` 3, `dep-backend-wrong-network` 2, `dep-cache-stopped` 2,
  `dep-backend-stopped` 1, `restart-exit0-job-01` 1;
- **after:** `dep-backend-wrong-network` 2, `dep-cache-restarting` 2, `dep-backend-stopped` 1.

The hard row (H5B.4c): `dep-backend-stopped`, trial 1, verdict FAIL.
- **What the model named:** root cause `vm-166/container:argus-lab-backend`, class `dependency_unavailable`: the
  right target and class.
- **What it cited:** h1 and h2 are both on the backend and both `supported`, with the problem "supported without
  an observation or metric snapshot of its own target".
- **Why it counts:** the model named the right cause but cited no read of that container, so the grader counts it
  as unsupported.
- **The same case on main's code:** the lost first batch had this hard on main's code too (trial 2, above).

## Notes

- **Decision rule** (task file, H5 step 2 B): accuracy per class not lower and hard 0, or the tag is removed.
  - `container_restart_loop` meets it.
  - `dependency_unavailable` is not lower (0.52 → 0.84) but has hard 1, so its tag is removed (the review of
    #274); it can be measured again after the support-evidence fix.
- **What the batch cannot attribute:** with 3 calls in 60 runs, the gain cannot be put down to the read's output
  alone. The offer also changes the tool list the model sees, and 25 runs per class leave room for variance.
- **Production effect:** `dependency_unavailable` runs `baseline` (D-003), so its offer reaches the model only if
  OP-013's proposal gives the class a model strategy again.
