# EVAL-4 — A health-check diagnosis may name the failing check in other words; re-grade stored results offline

| Field | Value |
|---|---|
| Status | `done` 2026-10-12 — offline (re-graded EVAL-3 step 2's 275 runs, no model call); PR #100 merged. Follow-up: EVAL-6 (#129, in review) |
| Phase | evaluation (§21.2) — [`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md) |
| Found by | EVAL-3 step 2 (#99, `conantkd`): `health_check_failed` 0.72 strict; 6 of its 8 misses were the wording check only |
| Architecture | no change (no ACR): five evaluation labels and an offline grading tool |
| Branch | `task/EVAL-4-health-wording` (from `main`) |
| Owner | `conantkd` (+ agent); decision by `conantkd` 2026-10-12 |
| Needs the VM lease | no (the results file was read from vm-095 once) |

## Goal (plain language)

The five `health_check_failed` cases wanted the diagnosis to contain the literal words "health check". In EVAL-3 step
2 the model named the right root cause and class in 6 of the 8 misses, but wrote "failed health probes", "health probe
timed out" or "Docker marks the container unhealthy". The words check is there to see that the diagnosis names the
symptom, not a spelling; the core accuracy, which leaves the words out, was already 0.99.

## Change

- `diagnosis_any` of `health-api-vm095-01`, `-vm095-02`, `-vm166-01`, `-vm166-02` and `health-db-vm166-01`:
  `health check`, `healthcheck`, `health probe`, `unhealthy` (was `health check` only). Outcomes, classes, root causes
  and fixtures unchanged; `ambiguous-health-no-cause` (abstain) unchanged.
- `argus/evaluation/regrade.py` (`python -m argus.evaluation.regrade <results.jsonl>`): grades a stored results file
  again with the current labels, without a model call. Hard counts stay the recorded ones (model requests are not
  stored).

**Disclosure:** the labels changed after seeing the model's answers. The justification is the rubric's intent (name
the failing check); the answers that motivated it are quoted in `tests/test_eval4_health_wording.py`. A diagnosis that
names no health check at all still fails.

## Result (re-grade of `eval-20261012-182757.jsonl`, EVAL-3 step 2, 275 runs)

| Labels | Passed | Accuracy (core) | Abstention | health | nginx |
|---|---|---|---|---|---|
| before (`main`) | 265 | 0.96 (0.99) | 0.98 | 0.72 (worst trial 0.40) | 0.92 |
| **EVAL-4** | **271** | **0.99 (0.99)** | 0.98 | **0.96** (worst trial 0.80) | 0.92 |

The re-grade with the old labels reproduces the run's own summary exactly (265, 0.96, 0.72): the tool is faithful.
Real misses left: `health-api-vm166-01` trial 1 escalated although the logs showed `KeyError: 'FEATURE_FLAGS'`;
`ambiguous-health-no-cause` trial 4 named the api with no cause (an abstain miss); `nginx-slow-half` trial 2 named no
root cause; `nginx-slow-partial` trial 2 escalated.

## Tests

`tests/test_eval4_health_wording.py`, 4 tests, red seen 3/4 with the old labels (the labels; the six answers; the
re-grade of a stored file).
