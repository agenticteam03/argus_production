## 2026-10-22 — T-0047 H5 step 2 B: `analysis.anomaly_summary` offered to the dependency and restart classes

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
Consequences: the offer stays only if the model batch (12 cases of the two classes, `--strategy model_loop`, 5 trials,
before/after) keeps accuracy and hard 0; both runs need an image with H5 (the deployed 6c83da3 predates it). A
class-registry change: `conantkd` reviews.
References: [T-0047](../../tasks/current/T-0047-hypotheses-cause-ranking.md), ACR-0024 §3.7.

### Test state

T-0047 H5 step 2 B: `tests/test_t0047_h5_anomaly_summary.py` 23 passed (red seen); offline evaluation 32/61 registered, 57/61 baseline, hard 0.

### Next step

T-0047 H5 step 2 B: the model batch on vm-095 (before/after, 5 trials) once an image with H5 is available; keep or remove the tag by its result.
