# PHASE-20 — First supervised lab action

| Field | Value |
|---|---|
| Status | in progress: step 1 (the candidate pair) in this PR; X-4, X-3, X-2 and the release PRs follow |
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

## Still required (each its own PR)

1. **X-4:** wire the frozen-row `ActionExecutor` to `HttpActionGateway` (today it accepts only the fake gateway) with
   a fresh precheck, dispatch, reconciliation by ID and verification; the model and the tools child stay outside the
   token and the dispatch path.
2. **X-3:** the gateway and socket-proxy services in the lab, the action token on the VM only, credential isolation
   checked on the real images.
3. **X-2:** one deploy window on vm-095 (phase 19 and the corpus), with the leases.
4. **X-5..X-7:** one release PR per pair, opening it in `config/policy.yaml`, the gateway configuration and the
   standing write-gate test, which keeps every unreleased pair closed. Before each: the hard checks
   (`unauthorized_actions`, `actions_on_forbidden_targets`, `action_without_valid_approval`, `harmful_actions`) at 0,
   and a lease-bound VM block with `nonint-check.sh` before and after and a rehearsed rollback that empties the gate
   and stops the gateway.
5. Live proof: SC-03 on the real lab: a correct proposal, judge agreement, an authenticated approval, exactly one
   dispatch, the prediction met and `recovered_verified`; evidence without secrets.

## Current result

Step 1: red seen (`FileNotFoundError`, the candidate absent), then green.
