## 2026-10-22 — T-0047: a read step's hypotheses get the structural checks only

Type: implementation
Who: juanbetancurm (+ agent)
Context: the [analysis](2026-10-22-T-0047-evidence-support-analysis.md) of #274's batch found a false positive in
the §3.2 checks. A read step's `state_hypotheses` list is checked before that step's reads run. So a cause marked
`supported` while its own read was requested in the same step was flagged, although the `conclude` after it was clean
(`dep-cache-paused` trial 3, `dep-cache-restarting` trial 2). The decision was to fix the checker first, then the
prompt as its own change.
Decision / result:
- `argus/tooling/model_harness.py`: `check_hypotheses(..., deciding=False)` for a read step's list.
  - It keeps the structural rows: evidence ids not stored or both for and against, a missing or out-of-scope target,
    the same id twice, a schema failure, more than five.
  - The evidence rows (a `supported` hypothesis's own-target observation, a `ruled_out` one's `against`, an
    `external` one's in-scope observation) apply on `conclude` / `escalate` only.
  - The checks stay log-only.
- `argus/evaluation/replay.py`: each problem in the row reads `step <n> <decision>: <problem>`, from the
  `hypothesis.invalid` audit, so a batch can tell a read step's problems from the decision's.
  `hypothesis_problem_rate` is unchanged (a run with any problem).
- `tests/test_t0047_hypothesis_check_steps.py` (red first: 4 failed):
  - a `supported` cause whose own read is requested in the same step is not flagged on the read step, and the same
    list on `conclude` without that read still is;
  - the other evidence rows also wait for the decision;
  - a read step keeps each structural row;
  - two replays of `dep-cache-paused` in #274's shape: one reads the cache and has no problem, the other never reads
    it and names `step 2 conclude` in its problem.
- `tests/test_t0047_h2_ranking_and_storage.py`: the read-step test now expects a structural problem (an unknown id)
  instead of `ruled_out` without `against`.
- ARCHITECTURE 1.8.33 (§11.3) and ACR-0024's "as built" note record the rule (`conantkd` reviews).
Consequences: older result files keep problems without the step prefix, and a read step's evidence problems are no
longer counted. So `problems` in a new batch is not comparable with #274's 0.45. The prompt change comes next, after
this is reviewed.
References: [T-0047](../../tasks/current/T-0047-hypotheses-cause-ranking.md), ACR-0024 §3.2, ARCHITECTURE §11.3.

### Test state

T-0047 hypothesis check steps: `tests/test_t0047_hypothesis_check_steps.py` 13 passed (red seen: 4 failed); the
T-0047 H1, H2 and H4 test files pass with it (54 passed). Full offline suite, with Git Bash first on PATH, on
`b22c669` plus this change: **1849 passed, 34 skipped, 1 deselected** (the known detached-CI Brain test), exit 0.

### Next step

T-0047: `conantkd` reviews the read-step check fix; then the prompt change (a target for every non-external
hypothesis, `supported` needs a read of that target, ids copied exactly), with a model batch.
