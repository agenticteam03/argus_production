# PHASE-20 — First supervised lab action

| Field | Value |
|---|---|
| Status | draft release candidate; not ready for review, approval, merge or deployment |
| Phase | 20 of [NEXT-PHASE](NEXT-PHASE-supervised-remediation.md) |
| Architecture | [ACR-0019](../../architecture/changes/ACR-0019-human-approved-remediation.md), accepted; [ACR-0031 draft PR #325](https://github.com/agenticteam03/argus_production/pull/325), assumed accepted for planning only |
| Branch | `task/T-0053-first-lab-action`, stacked on Phase 19 PR #324 |
| VM lease | none; no VM operation in this draft |

## Goal and boundary

Release exactly `container.start` for `vm-166/container:argus-lab-cache` in the lab, with a human approval, one
journaled dispatch and a fresh prediction check. No other capability, host or target may gain a write route. The
release requires its own PR and two reviewers under ACR-0019 §3.13.

At the user's direction, proceed **as if ACR-0031 were accepted and Phase 19 deployed**. That assumption guides the
draft; it is not an observed acceptance, merge, CI result or VM state. The current Phase 19 PR #324 and ACR PR #325
remain drafts. No active write gate or action gateway deployment is included in this checkpoint.

## STEP T-0053.1 — Freeze the first candidate pair

- **Goal:** name and validate the only Docker route proposed for the first lab release.
- **Why:** the reviewed pair must match the inventory, action card, risk table and both gateway ACL layers before a
  write gate can be opened.
- **Where:** laptop, Phase 20 branch. **Changes:** candidate JSON and an offline contract test; reversible by
  removing this branch. No VM change.
- **Command:** `python -m pytest -q tests/test_phase20_release_candidate.py`.
- **Expected:** two passing tests, one released pair in the candidate, and `config/policy.yaml` still closed.
- **If it fails:** inspect the candidate path, then compare its pair with inventory, action card and risk table.

The candidate is `deploy/action_gateway/first-lab-release.candidate.json`. It is not the active gateway config and
is not referenced by a compose service.

## STEP T-0053.2 — Bound worker dispatch to the gateway contract

- **Goal:** send a frozen action row over the gateway's narrow HTTP contract and reconcile its journal by ID.
- **Why:** the worker must not construct arbitrary Docker requests or repeat a write after an ambiguous response.
- **Where:** laptop, Phase 20 branch. **Changes:** `argus/actions/gateway_client.py` and offline/loopback tests;
  reversible by removing this branch. No production wiring or VM change.
- **Command:** `python -m pytest -q tests/test_phase20_gateway_client.py`.
- **Expected:** a non-released pair reaches no network, and the real loopback listener accepts one exact action and
  answers a status query without a second Docker call.
- **If it fails:** inspect the frozen proposal digest, the candidate pair and the gateway's response status.

The client reads a credential through a worker-only callback; no token or endpoint is configured in this draft.

## Work still required for the release PR

1. Confirm ACR-0031 acceptance and Phase 19 merge/deployment from GitHub and VM evidence. Complete the private
   approval login and real WebAuthn/mTLS flow if the deployed Phase 19 lacks them.
2. Connect the new client to the worker's frozen-row `ActionExecutor` and fresh precheck/verification adapters. Open
   only the lab-scoped pair in the policy and route it only on vm-166. Keep the model and tools child outside the
   token and dispatch path. Update the standing write-gate test to preserve every unreleased pair.
3. Run the full authorization, binding, failure-injection, token-isolation, Docker-image and evaluation gates. The
   hard checks for unauthorized, forbidden, unapproved and harmful actions must remain zero. Record the measured
   judge model and cost and check accuracy against the preceding run.
4. Prepare the VM blocks in `brain/execution/current/code.bash`, with lease ownership, before/after
   `nonint-check.sh`, a narrow release and a rehearsed rollback that empties the gate and stops the gateway. Do not
   execute a VM block without the matching lease.
5. Obtain two reviewers on the final release head. Then run SC-03 five times on the real lab: correct proposal,
   judge agreement, authenticated approval, exactly one dispatch, fresh prediction met and
   `recovered_verified`. Record gateway journal, action outcome and rollback evidence without secrets.

## Current result

The candidate contract test went RED because the manifest was absent, then GREEN with only the reviewed pair. The
client test went RED because the module was absent, then GREEN, including a real loopback listener and journal.
This is a **draft checkpoint**, not a released action. Production policy and deployment remain closed.
