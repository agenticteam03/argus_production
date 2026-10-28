## 2026-10-28 - X-6: release PR 2, container.restart on the lab job worker

Type: release (write gate)
Who: conantkd (agent B)
Context: demo scenario 4 needs Argus to restart the frozen lab job worker after a human approval. The first release (#371) opened only `container.start` on the lab cache. This PR opens the second reviewed pair, as the shared scenario contract fixes it.
Decision / result:
- `config/policy.yaml`: `write_gate.open` now names `container.start` on `vm-166/container:argus-lab-cache` and `container.restart` on `vm-166/container:argus-lab-jobworker`.
- `deploy/action_gateway/first-lab-release.candidate.json`: adds `POST /containers/argus-lab-jobworker/restart` for the pair. The gateway proxy therefore grants one inspect and one write path per pair; a stop, a start of the worker, and any restart of the cache or the API stay refused.
- The pair agrees with the inventory (role `worker`, `container.restart` safe, `container.stop` never), the `container.restart` card route and the risk table (stateless, green).
- `ARCHITECTURE.md` 1.8.43: section 12.2 marks `container.restart` released on that target only, section 13.3 lists both pairs, and the changelog row links ACR-0019. The ACR's "applied" note records it.
- Tests that assumed a single pair now expect two: `test_phase20_release_candidate`, `test_write_gate_check` (the report prints `2 reviewed pair(s)`), `test_write_gate_standing`.
Consequences: nothing is deployed by this PR. The pair acts only once the leased window installs the gateway route, the action token and the worker's settings, and only through the proposal, judge and human-approval path. The deployment check (`ops/write-gate-check.sh`) now expects exactly two pairs; a VM still on one pair stops it, which is the intended signal to redeploy.
References: PR #371, PR #377 (the S4 proposal), [ACR-0019](../../architecture/changes/ACR-0019-human-approved-remediation.md), [shared scenario task](../../tasks/current/DEMO-argus-acts.md).

### Test state

RED seen: with the tests updated to two pairs and the policy and release file unchanged, six tests failed (candidate pairs, policy pairs, proxy paths, three `write_gate_check` expectations). GREEN after the change: `test_phase20_release_candidate`, `test_write_gate_check`, `test_s1_policy_gate_pairs`, `test_write_gate_standing` (56 passed), plus the related gate, brain and action-path tests listed in the PR. The full suite is left to CI.

### Next step

After the merge, the leased window on vm-166 and vm-095: gateway route and token for the worker pair, `write-gate-check.sh` expecting two pairs, then the S4 run end to end. Pair 3 (`network.restore` on the API) is a separate release PR.
