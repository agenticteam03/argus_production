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

### Next step

Local checkpoint on `task/T-0050-cards-and-catalogue`. No PR opened per developer instructions. Next: Phase 18
offline simulation machinery (§14 tables, proposals with grounds/predictions/alternatives against a fake gateway,
judge integration), preserving closed write gate.
