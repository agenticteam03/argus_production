## 2026-10-28 - S4: Argus proposes and verifies a worker restart

Type: implementation
Who: conantkd (agent B)
Context: demo scenario 4. The lab job worker freezes while running and healthy, `lab:jobs` grows, and `worker_stalled` fires (#366). Until now the baseline returned no cause for a running worker with healthy dependencies, so no restart was ever proposed.
Decision / result:
- `BaselineStrategy._worker_stalled`: a running worker whose declared dependencies were all read as running, with no broken link, is itself the root cause (RB-022, "alive, not consuming"). A dependency that was not read is unknown, never healthy, so the result stays `None`. The dependency-down and broken-link branches are unchanged.
- RB-022 1.1.0: `actions:` front matter with `container.restart` (`root_cause`, role `worker`, same guard as the card); the decision tree now says when a restart may be proposed. The safety wording (preserved evidence, human approval) is kept. `config/actions/container.restart.yaml` lists RB-022 as a source.
- `action_wiring.py`: `VERIFY_SIGNALS["worker_stalled"] = ("jobs_processed_rate", 0.01)`. The proposer was already class-agnostic apart from that table; its rationale now reads correctly when the cause and the symptom are the same container.
- Verification: the executor accepts the outcome only when the frozen prediction's signal on the worker is healthy (`jobs_processed_rate >= 0.01`) AND the detector has cleared (`LiveVerification` adds `detector_cleared`). Two checks must hold in the window; the card's own `verify` block (`up == 1`) is reviewed metadata that the live path does not use, and would be true on a frozen worker.
- Evaluation case `tests/eval/cases/worker-stalled.yaml` (replays offline with the baseline, no model call). One case does not remove `worker_stalled` from `AWAITING_CASES`.
Consequences: the 120 s window looks sufficient on paper: the worker serves its first job within seconds of the restart, Prometheus scrapes every 15 s, and the rate over 5 m turns positive as soon as the reset counter grows, which also stops the `rate == 0` trigger. This is not measured; the leased vm-166 window must confirm it. No write capability is released by this PR; the second pair is the separate release PR.
References: PR #366, PR #373, [ACR-0036](../../architecture/changes/ACR-0036-stalled-worker-class.md), [ACR-0019](../../architecture/changes/ACR-0019-human-approved-remediation.md), [shared scenario task](../../tasks/current/DEMO-argus-acts.md).

### Test state

RED seen: the four new tests failed for the right reasons before the change (the attribution returned `None`, RB-022 had no `actions`, `worker_stalled` was missing from `VERIFY_SIGNALS`), and the evaluation test failed while the case did not exist. GREEN on `tests/test_s4_class.py`, `test_s4_eval_case.py`, `test_x9_action_path_wiring.py`, `test_evaluation.py` and the related phase 20 and write-gate tests. The full suite was not run locally on purpose; CI is the full verification.

### Next step

Merge, then the leased vm-166 window: `sc10` profile with `FAULT_ENABLE=1`, the jobworker scrape in Prometheus, freeze, detect, propose, approve, restart, verify. Measure how long `jobs_processed_rate` takes to turn positive after the restart. The release of `container.restart` on the worker (pair 2) follows in its own PR.
