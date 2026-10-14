## 2026-10-14 — EVAL-search-logs: search_logs offered to health_check_failed is not used; the error pattern fixed

Type: evaluation (+ fix)
Who: conantkd (+ agent)
Context: T-0037 step 3: offer `container.search_logs` to a class with an evaluation batch. `health_check_failed` was
chosen: the class with the most room, and a targeted read where the broad snapshot had lowered it (EVAL-snapshot).
Decision / result: measured on vm-095 from a local branch, 55 cases × 5 trials:
- overall 0.98 (270/275) against `main`'s 0.97 re-graded;
- health 0.92 against 0.96;
- **the tool was used in 1 of 30 health runs**, so the differences are noise of 5 trials.

It is not offered. The cases' logs are 2–3 lines, and the tail already returns them, so log tools need long-log cases
before they can be measured. Found on the way, and fixed in the gateway with tests (red seen): the `error` pattern
missed exception class names (`KeyError`, `ValueError`, `RuntimeException`) and plurals, so a real search answered
"0 matched" for a log with a `KeyError`.
Consequences: the fix reaches the VMs when the target services are rebuilt at the next AFTER-MERGE. The offer, the
replay change and the search fixtures are not merged. On vm-095 the image `argus-v18-agent:evalsl` and `/tmp/evalsl`
are left, used by no service.
References: [evidence](../../execution/history/EVAL-search-logs/step-01/evidence.md),
[T-0037](../../tasks/current/T-0037-docker-read-verbs.md).

### Test state

`tests/test_t0037_docker_read_verbs.py`: 11 new pattern cases; red on `main`'s pattern (4 failed), green with the fix
(23 passed).

### Next step

Next AFTER-MERGE: rebuild the target services on both hosts. A task for evaluation cases with long logs before any
log tool is offered.
