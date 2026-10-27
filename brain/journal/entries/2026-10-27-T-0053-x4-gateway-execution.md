## 2026-10-27 - T-0053: execution through the gateway, a fresh precheck and a verification (X-4)

Type: implementation
Who: conantkd (+ agent)
Context: phase 18's `ActionExecutor` accepted only the fake gateway, and its precheck and verification were test
callbacks. Phase 19 put the gateway, its journal and the worker's `HttpActionGateway` on `main`.
Decision / result:
- `ActionExecutor` and `OfflineActionPath` accept exactly `REVIEWED_GATEWAYS` (the fake gateway or the reviewed HTTP
  client); any other object is still refused.
- `argus/actions/live.py`: `LivePrecheck` reads the identity, the card's preconditions, the inventory, policy and
  evidence versions, the incident's state, the detector and the host lease at execution time; `LiveVerification` samples
  the frozen prediction's signal and whether the detector cleared; `status_from_observation` takes an ok
  `container.status` observation.
- Found on the way: the proxy compares Docker's full container Id, but `container.status` reported 12 characters, so
  every real dispatch would have been refused as "target identity changed". The target service adds `container_id`
  (full Id); `id` stays short.
- My rows in the coordination file: X-1 PR #354, X-4 building.
Consequences: the target service must be redeployed on vm-166 before the first release. The production wiring (the
proposer, the judge adapter, the reads through `InvokeCapability`, the signal sampler, the detector, the lease) and
the policy engine's refusal of a non-empty gate go with the first release PR. The write gate stays closed.
References: [PHASE-20 task](../../tasks/current/PHASE-20-first-lab-action.md), ACR-0019.

### Test state

Red first: `tests/test_phase20_live_execution.py` failed on the missing `argus.actions.live`. Then 8 passed; with the
phase 18, 19 and 20 tests, OP-005's target tests, the standing write gate and tool isolation, all green.

### Next step

X-3: the gateway and socket-proxy services in the lab, the action token on the VM only, credential isolation on the
real images; the target redeployed on vm-166 with `container_id`.
