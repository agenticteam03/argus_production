## 2026-10-23 — T-0050: Cards, closed catalogue, risk table and suggestions (Phase 17)

Type: task
Who: conantkd (+ agent)
Context: Phase 17 of NEXT-PHASE (Cards, catalogue and suggestions) moves remediation candidates to reviewed,
data-grounded definitions (service cards, action cards, closed catalogue, risk table, runbooks). The write gate
stays strictly closed; no write capability is released. Candidate evaluation and suggestions are read-only.
Decision / result:
- Precondition interpreter without `eval` (`argus/actions/preconditions.py`): evaluates expression ASTs over
  observation state using safe recursive AST evaluation. Supports comparisons (`==`, `!=`, `<`, `<=`, `>`, `>=`),
  membership (`in`, `not in`), and boolean logic (`and`, `or`, `not`). Disallows dynamic code primitives (`eval`, `exec`,
  `compile`), private dunder attributes, function calls, and statement mutations. Missing attributes resolve safely
  without raising unhandled exceptions.
- Risk table and level elevation (`config/risk.yaml`, `argus/actions/risk.py`): maps `(action, target_kind) -> RiskColor`
  (`green`, `amber`, `red`, `forbidden`). The model never rates risk. The color can only go up: `criticality: high`
  raises one level, judge `disagree` or `doubt` raises one level. Database restart is strictly `forbidden` and cannot be lowered.
- Closed catalogue & cards (`config/actions/*.yaml`, `argus/actions/catalog.py`, `argus/actions/cards.py`):
  closed catalogue of typed actions organized by intent (`container.start`, `container.restart`, `container.stop`, etc.)
  with canonical and model names. Actions in `NEVER_OFFERED_ACTIONS` cannot be registered. Service cards declared in
  `config/inventory.yaml` and loaded onto `TargetInfo.service_card()`. Initial action cards for Docker lab targets
  (`container.start.yaml`, `container.restart.yaml`, `container.stop.yaml`).
- Action suggestions & basis computation (`argus/actions/suggestions.py`): basis (`runbook`, `memory`, `reference`,
  `operator`) is computed strictly by code from cited grounds; model-only ideas downgrade to suggestions. Suggestions
  are read-only text hints (`is_executable=False`).
- SC-03 exit proof verified: on `argus-lab-cache` (the root cause), `container.start` passes preconditions and service
  card checks (`green` risk, `runbook` basis). On `argus-lab-api` (the victim), restarting the victim instead of the cause
  is strictly forbidden (RB-002, RB-003).
- Review corrections on local commit `e5cd3d7`: moved `ServiceCard` to the domain layer to satisfy the import boundary;
  require exact catalogue/card names, verified card sources and a non-forbidden resolved risk; preserve unknown through
  negated preconditions and reject object-property access. Inventory and action-card loaders reject incomplete or
  unreviewed entries. RB-003 v1.0.1 declares a guarded cache-start action. The incident read route and evaluation
  replay derive `next_actions` from a recalled runbook and a recent, timestamped status of the root cause. SC-03 now
  has an expected action and a forbidden victim-restart trap in its evaluation label.

Consequences:
- Candidate actions remain read-only suggestions; the write gate stays closed.
- An absent, stale or untimestamped observation yields no candidate. The current runbook action is limited to a
  stopped cache, while other catalogue entries remain unavailable until their cards and runbook grounds are reviewed.

References: [T-0050](../../tasks/current/T-0050-cards-and-catalogue.md),
[ACR-0019](../../architecture/changes/ACR-0019-human-approved-remediation.md), RB-003 v1.0.1.

### Test state

- RED seen:
  - `tests/test_action_preconditions.py`: `ModuleNotFoundError: No module named 'argus.actions'`
  - `tests/test_action_risk.py`: `ModuleNotFoundError: No module named 'argus.actions.risk'`
  - `tests/test_action_cards.py`: `ModuleNotFoundError: No module named 'argus.actions.cards'`
  - `tests/test_action_suggestions.py`: `ModuleNotFoundError: No module named 'argus.actions.suggestions'`
- GREEN:
  - `tests/test_action_preconditions.py`: 34 passed
  - `tests/test_action_risk.py`: 6 passed
  - `tests/test_action_cards.py`: 6 passed
  - `tests/test_action_suggestions.py`: 3 passed
  - `tests/test_write_gate_standing.py`: 10 passed (write gate remains strictly closed)
  - `tests/test_e2e2_evidence_gaps.py`: 12 passed
  - Total focused suite: 49 passed. Ruff clean, `brain.py lint` clean.
- Review corrections: regression tests were red for a missing-field negation, object-property access, an ungrounded
  candidate and the domain import boundary. The final selected suite passed **138 tests** (action modules, write-gate
  standing, evidence gaps, import boundaries, all baseline case labels and UI contract). Ruff passed on changed code;
  `brain.py lint` passed.
- C5 incident integration verification: focused action, incident, evaluation, write-gate and UI-contract suite passed
  **177 tests**; Ruff, `git diff --check` and `brain.py lint` passed. Evidence is archived at
  [`execution/history/T-0050/step-05/`](../../execution/history/T-0050/step-05/). The local test run used the installed
  Python 3.12 runtime because the repository virtual environment points to a removed interpreter. A full suite run
  completed with **1,934 passed, 10 failed, 7 errors, 7 skipped**. All 17 failures/errors were subprocess tests whose
  uv-managed interpreter lacked dependencies available only in `.venv/Lib/site-packages` (`pywintypes`, `yaml`).
- Final line-by-line review caught and fixed 8 issues: viewer-visible candidates, weak lab target identity, incorrect
  `status` keys in action guards (the observation field is `state`), incomplete action-card validation, incomplete
  inventory catalogue validation, incomplete service-card parsing, and arbitrary Python comparison methods reachable
  from precondition context. Focused regressions passed.
- `brain.py lint` is clean. `brain.py audit` reports an unrelated Windows-profile-path finding in
  `.review-pr297/review.txt`; that untracked review artifact was left untouched.
- PR #316 is open as a draft on `e5cd3d7`. Its description explicitly says not to review or approve. The C5 local
  changes are not yet part of the remote head; CI is pending for their push. `brain/execution/current/code.bash`
  contains unrelated edits and is excluded from this task commit.

### Next step

Commit and push the verified C5 incident integration to draft PR #316. Keep it as a draft and do not review or approve
it until explicitly requested. CI will run on the push. After the task is ready for review and merge, proceed to Phase
18 offline simulation machinery (§14 tables, proposals with grounds/predictions/alternatives against a fake gateway,
judge integration), preserving the closed write gate.
