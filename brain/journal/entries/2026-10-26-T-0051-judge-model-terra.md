## 2026-10-26 - T-0051: the phase 18 judge model set to gpt-5.6-terra (provisional)

Type: decision
Who: conantkd (+ agent)
Context: ACR-0019 §5 leaves the judge's model to phase 18: a model other than the deciding one (`gpt-5.6-luna`), from a
measured comparison, its cost recorded.
Decision / result:
- `gpt-5.6-terra` is the provisional judge, a team decision; the adapter's allowlist adds it, and the phase 18 tests
  use it.
- Measured once on vm-095 (18 labelled cases, two repetitions, the harness limited to this model): all 36 answers
  schema-valid, harmful false agree 0, good-agree 0.67 (4 `doubt`), bad 12/12 `disagree`, traps all `doubt` or
  `disagree`; 21,250 input and 6,436 output tokens.
Consequences: its per-token price is to be recorded from the API account; the other candidates are compared before
phase 20 releases an action. `ops/phase18_judge_eval.py` (protected) keeps its reference candidates.
References: [task](../../tasks/current/PHASE-18-supervised-actions.md), ACR-0019 §3.8 and §5.

### Test state

Phase 18, guards, graph and Postgres tests: 52 passed, 20 skipped (no local Docker); Ruff clean.

### Next step

Record the judge's per-token price; compare the other candidates before phase 20.
