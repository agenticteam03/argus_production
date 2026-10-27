# PHASE-20 — First supervised lab action

| Field | Value |
|---|---|
| Status | in progress: step 1 (the candidate pair, #354) and step 2 (execution through the gateway); X-3, X-2 and the release PRs follow |
| Phase | 20 of [NEXT-PHASE](NEXT-PHASE-supervised-remediation.md); pieces X-1..X-7 of the demo's shared coordination file (PR #353) |
| Architecture | [ACR-0019](../../architecture/changes/ACR-0019-human-approved-remediation.md), accepted; ACR-0031 applied (#347); no new ACR for this step |
| Branch | `task/T-0053-phase20-candidate`, from `main` (replaces draft #326, 97 commits behind and in conflict) |
| VM lease | none; this step makes no VM change |

## Goal and boundary

Release exactly the reviewed lab pairs, each in its own release PR with two approvals (ACR-0019 §3.13), behind a
human approval, one journaled dispatch, a fresh precheck and a verification. The first pair is `container.start` on
`vm-166/container:argus-lab-cache` (SC-03). No other capability, host or target gains a write route; vm-095 is never a
target. The demo adds two more pairs (`container.restart` on the job worker, `network.restore` on the API), each in
its own release PR.

Phase 19 is on `main` (#324, #347): the gateway core and journal, the socket proxy, the worker's client
(`HttpActionGateway`, tested against the real listener in `tests/test_phase19_gateway_client.py`), the private
approvals and the private login. Draft #326's own client and its test are not carried over: main's client and test
already cover the same behaviour (one send, refusal before the proxy, an ambiguous answer left to `status`).

## STEP T-0053.1 — Freeze the first candidate pair (X-1)

- **Goal:** name and check the only Docker route proposed for the first lab release.
- **Why:** the pair must match the inventory, the action card, the risk table and both gateway ACL layers before a
  release PR can open the write gate.
- **Where:** laptop. **Changes:** `deploy/action_gateway/first-lab-release.candidate.json` and
  `tests/test_phase20_release_candidate.py`; undo by reverting the PR. No VM change.
- **Command:** `python -m pytest -q tests/test_phase20_release_candidate.py`.
- **Expected:** three passing tests: one released pair; the proxy grants one inspect and one write path; the gate is
  still closed and no compose file reads the candidate.
- **If it fails:** compare the candidate's pair with the inventory, the action card and the risk table.

The candidate is not the active gateway configuration (`/etc/argus-v18/action-gateway.json` on the VM) and no compose
service reads it.

## STEP T-0053.2 — Execute through the gateway with a fresh precheck and a verification (X-4)

- **Goal:** the frozen-row `ActionExecutor` dispatches through the reviewed `HttpActionGateway`, with a precheck read
  from the target at execution time and a verification sampled after the action.
- **Why:** phase 18's executor accepted only the fake gateway, and its precheck and verification were test callbacks.
- **Where:** laptop. **Changes:** `argus/actions/live.py` (new: `LivePrecheck`, `LiveVerification`,
  `status_from_observation`); `ActionExecutor` and `OfflineActionPath` accept exactly the fake gateway or the
  reviewed client (`REVIEWED_GATEWAYS`), nothing else; `services/target/service.py` adds `container_id`, Docker's
  full Id; `tests/test_phase20_live_execution.py`. Undo by reverting the PR. No VM change.
- **Command:** `python -m pytest -q tests/test_phase20_live_execution.py`.
- **Expected:** one action through the real gateway listener, never sent twice, verified `recovered_verified`; a
  recreated target is a definite `failed` with no proxy call; any other gateway object is refused.
- **If it fails:** compare the precheck's identity with the proxy's (`unix_transport.py`, the full Id).

**Found on the way:** the gateway's proxy compares Docker's full container Id, but `container.status` reported only
the first 12 characters, so a proposal built from it would have been refused as "target identity changed" on every
real dispatch. The target now also reports `container_id` (full); `id` stays short for its existing readers. The target
service must be redeployed on vm-166 before the first release (X-2/X-3).

**Still open for the release PR:** the production wiring that builds the path (the proposer, the judge adapter, the
`container.status` read through `InvokeCapability`, the signal sampler, the detector and the lease check) and the
policy engine's startup refusal of a non-empty gate; both belong with opening the first pair.

## Still required (each its own PR)

1. **X-3:** the gateway and socket-proxy services in the lab, the action token on the VM only, credential isolation
   checked on the real images.
2. **X-2:** one deploy window on vm-095 (phase 19 and the corpus), with the leases.
3. **X-5..X-7:** one release PR per pair, opening it in `config/policy.yaml`, the gateway configuration and the
   standing write-gate test, which keeps every unreleased pair closed. Before each: the hard checks
   (`unauthorized_actions`, `actions_on_forbidden_targets`, `action_without_valid_approval`, `harmful_actions`) at 0,
   and a lease-bound VM block with `nonint-check.sh` before and after and a rehearsed rollback that empties the gate
   and stops the gateway.
4. Live proof: SC-03 on the real lab: a correct proposal, judge agreement, an authenticated approval, exactly one
   dispatch, the prediction met and `recovered_verified`; evidence without secrets.

## Current result

Step 1: red seen (`FileNotFoundError`, the candidate absent), then green.
Step 2: red seen (`ModuleNotFoundError: argus.actions.live`), then green.
