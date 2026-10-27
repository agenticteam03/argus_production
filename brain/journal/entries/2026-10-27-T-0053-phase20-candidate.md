## 2026-10-27 - T-0053: phase 20's first lab release candidate, rebuilt on main (X-1)

Type: implementation
Who: conantkd (+ agent)
Context: draft #326 was stacked on the phase 18 and 19 drafts and fell 97 commits behind `main`, in conflict. Phase 19
is merged (#324, #347), with its own worker client and tests.
Decision / result:
- Only phase 20's own content is carried over: the candidate pair (`container.start` on
  `vm-166/container:argus-lab-cache`) and its contract test, now also checking that no compose file reads it.
- #326's `GatewayClient` and its test are dropped: main's `HttpActionGateway` and `tests/test_phase19_gateway_client.py`
  cover the same behaviour.
- The task file states the remaining pieces (X-4, X-3, X-2, X-5..X-7). The write gate stays closed.
Consequences: #326 can be closed once this merges. No VM change, no release.
References: [PHASE-20 task](../../tasks/current/PHASE-20-first-lab-action.md), ACR-0019.

### Test state

Red first: `tests/test_phase20_release_candidate.py` failed with `FileNotFoundError` (no candidate). Then 3 passed;
with the phase 19 gateway, client, socket-proxy and standing write-gate tests: 33 passed.

### Next step

X-4: wire `ActionExecutor` to `HttpActionGateway` with a fresh precheck, dispatch, reconciliation by ID and verification.
