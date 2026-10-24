# T-0050 — Cards, closed catalogue, risk table and suggestions (Phase 17)

| Field | Value |
|---|---|
| Status | `in progress` — Phase 17 is in PR [#316](https://github.com/agenticteam03/argus_production/pull/316); branch is aligned with `main` at `c8d8594` (`13a54ae`); 116 post-alignment tests and GitHub test/frontend checks passed ([evidence](../../journal/entries/2026-10-23-T-0050-phase17-cards-and-catalogue.md)) |
| Phase | 17 of [NEXT-PHASE](NEXT-PHASE-supervised-remediation.md) ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md)) |
| Architecture | [ACR-0019](../../architecture/changes/ACR-0019-human-approved-remediation.md) (`accepted`, PR #302) |
| Branch | `task/T-0050-cards-and-catalogue` |
| Owner | `conantkd` (+ agent) |
| Needs the VM lease | no (pure offline domain code, configuration data and unit tests; write gate stays closed) |

## Goal (plain language)

Define **what Argus is allowed to propose**, on **which targets**, under **which fresh observations**, and at **what risk level**, completely grounded in reviewed data (service cards, action cards, risk table, runbooks) rather than model discretion.

No write capability is released in this phase; the write gate stays closed. All evaluation of candidate actions and preconditions is read-only, serving `suggest_action` (text for operators) and `next_actions` (candidate actions evaluated against cards and observation state).

## Steps (each TDD, red tests first)

### C1 — Precondition interpreter without `eval`
- AST-based expression parser and evaluator (`argus/actions/preconditions.py`).
- Supported operations:
  - comparisons (`==`, `!=`, `<`, `<=`, `>`, `>=`)
  - membership (`in`, `not in`)
  - boolean logic (`and`, `or`, `not`)
  - safe attribute / dictionary path resolution over observation dictionaries.
- Strictly forbidden: `eval`, `exec`, `compile`, attribute mutation, function calls, arbitrary builtins.
- **Tests:** `tests/test_action_preconditions.py` (red seen first).

### C2 — Risk table and color resolution
- `config/risk.yaml` declaring base risk colors (`green`, `amber`, `red`, `forbidden`) per `(action, target_kind)`.
- Enforces:
  - restarting cache is `green`;
  - restarting database is `forbidden`;
  - risk color can only go up (e.g. `criticality: high` raises color one level; judge `disagree` raises color one level).
- `argus/actions/risk.py`: parser and risk resolution helper.
- **Tests:** `tests/test_action_risk.py` (red seen first).

### C3 — Action cards and service cards schema and catalogue
- Closed catalogue definition (`argus/actions/catalog.py`) with canonical names (`container.start`), model names (`start_container`), and enforcement of the "never offered" list.
- Action cards in `config/actions/`:
  - `container.start.yaml`, `container.restart.yaml`, `container.stop.yaml`.
- Service cards model and parsing in `argus/actions/cards.py`.
- **Tests:** `tests/test_action_cards.py` (red seen first).

### C4 — Basis resolution and action suggestions
- `argus/actions/suggestions.py`:
  - Code-computed basis: `runbook`, `memory`, `reference`, `operator`. Downgrades model-only ideas to text suggestions.
  - `suggest_action(text, closest_capability?)`: text output for operator, never executable.
  - `evaluate_next_actions(target, service_card, action_cards, observations)`: candidate actions that pass preconditions and service card safe_actions.
- SC-03 exit proof verification: suggests starting `argus-lab-cache`, forbids restarting `argus-lab-api`.
- **Tests:** `tests/test_action_suggestions.py` (red seen first).

### C5 — Review corrections and incident integration
- Service card data lives in the domain layer; inventory validates required fields and catalogue names at load time.
- Candidate evaluation requires a reviewed action name, matching card, verified ground and fresh source timestamp;
  missing observations cannot satisfy negated guards. Risk escalation to `forbidden` removes the candidate.
- RB-003 v1.0.1 declares the cache-start action and its guard. The incident read view and offline replay compute
  `next_actions` only from that declaration, a recalled runbook and stored root-cause evidence. The output is text
  for operators and cannot execute a write.
- The SC-03 evaluation key requires `container.start` on the cache and rejects `container.restart` on the API.
- **Tests:** `tests/test_action_incident.py`, the SC-03 baseline replay, UI contract and write-gate standing tests.
