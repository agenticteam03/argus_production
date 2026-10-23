## 2026-10-22 - Review of #266-#269; the open points they leave, with the night's carry-over

Type: review
Who: conantkd (+ agent)
Context: four teammate PRs reviewed, approved and merged: #268 (T-0049 S0, `.claude/skills/` protected), #267
(T-0047 H5 step 2 A, per-target range fixtures), #266 (OP-013 held-out set), #269 (ACR-0029 proposed). Each leaves
work that no PR tracks yet; this entry lists it so the next roll-up carries it into NEXT_STEP.
Decision / result - open points from these PRs:
- **OP-013 step 2 (owner: conantkd, review):** review the held-out labels against RB-003/RB-015 before the model runs
  count, first the four the task flags (`heldout-nginx-wrong-upstream-port`, `heldout-nginx-header-too-big`,
  `heldout-dep-backend-flap`, `heldout-nginx-errors-no-trace`). Approving #266 did not complete this step. Then
  step 3: `model_loop` and `plan_then_reason`, 5 trials each, on vm-095 (lease), and each class re-decided by §21.2
  in its own PR.
- **T-0047 H5 step 2 B (reviewer: conantkd):** the `anomaly` tag on `dependency_unavailable` and
  `container_restart_loop` (class registry) and its model batch (5 trials, accuracy not lower, hard 0;
  `dependency_unavailable` through `--strategy model_loop`). Known limit from part A: `range_earlier` is one series
  per signal, so a dependency's baseline window in the replay is the case target's.
- **ACR-0029 acceptance:** the six decisions of its §5 (who may label, step-up scope, confirmation and stability
  windows, retention, similarity weights and prior cap, application slices). It stays `proposed`; implementation
  also waits for ACR-0018's deployment gates (WebAuthn, step-up, private path, off-host audit).
- **T-0049:** the `code-bash-step` skill PR is now unblocked; under `.claude/skills/` it needs a teammate's review.
Carried over from the night of 2026-10-21 (still open):
- DEPLOY-afb72e8 (`brain/execution/current/code.bash`, #258): for the developer to run; EdDSA forces a new login.
- OP-008 `prune --apply` (KEEP=7, approved in #247): preview again first; the developer runs it.
- D2 (#243): the WebAuthn domain.
- T-0046 L6: whether `link_event.at` keeps the probe's sample time (a meaning change; ACR-0025 text).
- OP-014 step 9: 36 mutation timeouts not yet judged; the weekly mutation CI job (`.github/`, teammate review).
Consequences: the next roll-up folds this entry and those of #264-#269.
References: #266, #267, #268, #269, [OP-013](../../OPEN_PROBLEMS.md), [OP-014](../../OPEN_PROBLEMS.md), ACR-0029,
T-0047, T-0049.
