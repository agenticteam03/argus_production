## 2026-10-22 — T-0047 H5 step 2 B: `analysis.anomaly_summary` offered to the restart class

Type: work
Who: juanbetancurm (+ agent)
Context: H5 step 1 built the read offered to no class (#252); part A gave the replay per-target series (#267), so a
dependency case can show which onset came first.
Decision / result:
- `argus/detectors/classes.py`: the `anomaly` tag on `dependency_unavailable` and `container_restart_loop`; the read
  stays at most once per incident (`config/policy.yaml`).
- `tests/test_t0047_h5_anomaly_summary.py`: the offer test now names exactly these two classes (red seen: offered to
  none).
- Offline evaluation unchanged (registered 32/61, baseline 57/61, hard 0).
- The model batch (vm-095, run stamp `20261022T174900`; before = main `95e67a7`, after = `b3cc16c`; the 12 cases,
  `--strategy model_loop`, 5 trials, 60 runs per arm). `container_restart_loop` 0.97 → 1.00, hard 0 → 0.
  `dependency_unavailable` 0.52 → 0.84, hard 0 → 1. All 60 runs: 0.76 → 0.93 (top-1 0.86 → 0.96).
  - The read was called in 3 of the 60 after-runs.
  - The hard is `dep-backend-stopped` trial 1: the right root cause and class, but no observation of the backend
    cited. It is the evidence gap `problems 0.45` shows in both arms. A lost first batch had the same hard on main's
    code (trial 2).
  - Restart meets the rule. Dependency is not lower but has hard 1.
- The tag decision (the rule, as `conantkd`'s review asked): `anomaly` stays on `container_restart_loop` and is removed
  from `dependency_unavailable`. That class can be measured again after the support-evidence fix (the gap behind the
  hard). The restart arm's numbers stand: its offer is the same with or without the other class's tag.
  `tests/test_t0047_h5_anomaly_summary.py` names only the restart class (red seen: it named both).
- A first batch was lost (a block pasted twice deleted its result files). The re-run refused to start while the
  batch containers existed, and wrote stamped files with no `rm`.
Consequences: the offer stays only if the model batch (12 cases of the two classes, `--strategy model_loop`, 5 trials,
before/after) keeps accuracy and hard 0, and it runs before the merge (ACR-0024 §3.8; `conantkd`'s review of #274).
No image is built: vm-095 runs afb72e8 with H5 registered, and each run binds a `git archive` of `argus/` (main's,
then this branch's) read-only over `/app/argus` in the deployed image; a deviation from `ops/eval-run.sh`, which takes
no extra mount. A class-registry change: `conantkd` reviews.
References: [T-0047](../../tasks/current/T-0047-hypotheses-cause-ranking.md), ACR-0024 §3.7,
[evidence](../../execution/history/T-0047-H5B/step-01/evidence.md).

### Test state

T-0047 H5 step 2 B: `tests/test_t0047_h5_anomaly_summary.py` 23 passed (red seen twice: offered to none, then to
both classes); offline evaluation 32/61 registered, 57/61 baseline, hard 0.

Model batch on vm-095 (run stamp `20261022T174900`): restart 0.97 → 1.00, dependency 0.52 → 0.84, hard after 1
(above). Full offline suite on the final tree (the tag on the restart class only, main `863dbf0` merged): **1701
passed, 63 skipped, 1 deselected**, exit 0.

### Next step

T-0047 H5 step 2 B: `conantkd` reviews #274 (the tag on `container_restart_loop` only). Then the support-evidence fix
(the gap behind the hard), after which `dependency_unavailable` can be measured again.
