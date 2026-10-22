## 2026-10-21 — OP-013: a held-out set for the two classes under the baseline; the baseline scores 0.50 on it

Type: work
Who: juanbetancurm (+ agent)
Context: D-003 put `dependency_unavailable` and `nginx_upstream_failure` on the baseline (1.00 vs the model's 0.90 and
0.92), but the baseline's rules were written from those cases (OP-013).
Decision / result:
- 12 new cases in `tests/eval/heldout/cases/`, six per class (one ambiguous each), mechanisms the main set lacks
  (OOM-killed cache, wrong listen port, database shutdown, overload, client limit; upstream crash, CPU-starved and
  restarting upstream, and two causes in the proxy itself). Labels from RB-003/RB-015, written without reading the
  baseline's rules.
- A separate folder, so CI's evaluation and the D-003 test never load them; `tests/test_op013_heldout_cases.py`
  checks the structure only (red seen: 0 cases).
- Baseline, offline, 1 deterministic trial: 3/6 per class (0.50), hard 0. Labels unchanged after the run.
Consequences: the model's runs (`model_loop`, `plan_then_reason`, 5 trials each) on vm-095 decide each class by §21.2;
the labels are reviewed first. Plan: [OP-013 task](../../tasks/current/OP-013-held-out-set.md).
References: [OP-013](../../OPEN_PROBLEMS.md), D-003.

### Test state

OP-013: `tests/test_op013_heldout_cases.py` 4 passed; full offline suite 1475 passed, 62 skipped (main `9d65e1e`); baseline on the held-out set 6/12 (dep 3/6, nginx 3/6), hard 0.

### Next step

OP-013: review the held-out labels, then the two model runs on vm-095 (5 trials each) and the re-decision per class.
