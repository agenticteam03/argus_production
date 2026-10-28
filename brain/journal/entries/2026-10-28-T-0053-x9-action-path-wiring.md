## 2026-10-28 - T-0053: the worker builds the supervised-action path, closed by default (X-9)

Type: implementation
Who: conantkd (+ agent)
Context: after X-4 (#355) nothing in `argus/` constructed `OfflineActionPath`, `LivePrecheck` or `HttpActionGateway`, so
opening a pair (#371) would have changed a file and nothing else. The work sat between rows X-4 and X-5 of the
coordination file with no row of its own; it is X-9 now.
Decision / result:
- `argus/infrastructure/action_wiring.py` composes reviewed parts: the HTTP gateway client, `OpenAIJudge`, `LivePrecheck`
  and `LiveVerification`, and `InvokeCapability` for the audited `container.status` read. `build()` passes the path to
  the graph runner; `Settings` gains `ARGUS_ACTION_PATH`, `ARGUS_ACTION_GATEWAY_URL`, `ARGUS_ACTION_TOKEN_FILE`,
  `ARGUS_JUDGE_MODEL` and `ARGUS_ACTION_DAILY_HOST_CAP`, all off or empty by default.
- Built only when `ARGUS_ACTION_PATH=1` and `write_gate.open` names a pair (and the runner is `langgraph`). With the flag
  on and the gate open, every missing piece is named and stops the start.
- The proposer is deterministic, narrower than ACR-0019 allows: it builds the proposal from the reviewed candidate, the
  action card and a fresh audited read, and the judge still reviews it. Only the argument-less `container.start` and
  `container.restart`, and only for `dependency_unavailable` (verified by `dependency_probe_min` reaching 1).
- Unknown fails safe: the precheck treats "cannot tell" as not detected (nothing sent); the verification treats it as
  still firing (no recovery claimed); a missing, stale or non-finite sample is never healthy.
- `identity_of` is factored out of `LivePrecheck` so the proposer and the precheck read identity the same way.
- Found by CI on Linux: `OfflineActionPath.precheck`, `execute` and `verify` took their decision time **before** the
  read and then refused a read stamped after it as "not current". Every real precheck and verification would have
  failed; Windows' coarse clock and test doubles that stamped the read at that same moment hid it. Each is now
  judged at a time taken after its read; the end-to-end test uses a ticking clock so it fails without the fix on
  any platform.
- The API mounts its private login, approval and hold routes only while `write_gate.open` names a pair
  (`approval_rows`), independent of `ARGUS_ACTION_PATH` (the API process has no action token). Before, production
  never mounted them, so nobody could have approved an action, nor obtained an `ops` session at all. The routes keep
  their own guards (private path, approver role, two keys, step-up).
- My rows: X-4 merged (#355), X-9 PR open.
Consequences: the release PR (#371) makes the engine accept a non-empty gate; after both, the worker acts on the
released pair only with `ARGUS_ACTION_PATH=1`, the token and the gateway address set in the release window. Not wired
here: the approval notice of #367 (needs the Alertmanager address in the worker). The judge and Prometheus are doubles in
the tests; their real behaviour is for the live proof.
References: [PHASE-20 task](../../tasks/current/PHASE-20-first-lab-action.md),
[coordination file](../../tasks/current/DEMO-argus-acts.md), ACR-0019.

### Test state

`tests/test_x9_action_path_wiring.py`, 30 passed (with the approval routes: mounted only with approval rows, still 404 off the private path): the gate, the proposer, the sampler, the detector checks, the judge
context, the build decisions, `Settings`, the `build()` hook, and one run from diagnosis to `recovered_verified` through
the real gateway listener with one dispatch (red first for the clock fix: `precheck observation is not current`). The code came before the tests; two mutations (a sampler that always says
healthy, a proposer that ignores the gate) each fail them. A targeted regression (`test_core`, the standing write gate,
tool isolation, the phase 18, 19 (all nine files) and 20 suites, the approval notice) passed. A broader local run was stopped by the
machine's low memory, so CI is the full check.

### Next step

Review and merge (protected `argus/actions/`: juanbetancurm's approval). Then the release window: #371, the token, the
active gateway configuration, the services, `ARGUS_ACTION_PATH=1` and the gateway address for the worker.
