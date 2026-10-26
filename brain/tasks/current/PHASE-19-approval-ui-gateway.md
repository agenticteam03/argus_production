# PHASE-19 — Private approvals and action gateway

| Field | Value |
|---|---|
| Status | in review (#324): the first phase 19 slice, routes unmounted in production; the follow-ups below complete the phase |
| Phase | 19 of [NEXT-PHASE](NEXT-PHASE-supervised-remediation.md) |
| Architecture | [ACR-0019](../../architecture/changes/ACR-0019-human-approved-remediation.md), accepted; no new ACR needed for this slice |
| Branch | `task/T-0052-approval-gateway`, on `main` (phase 18 #323, #340, #342 merged) |
| VM lease | none; this draft makes no VM change |

## Goal and assumption

Prepare the private approval UI and action gateway on the Phase 18 contract. ACR-0019 §5's precondition holds on
main: phase 16's off-host audit digest (step 5) and its exit proof (step 6, #343) are deployed on vm-095. Keep the
write gate closed and do not connect a real target or credential in this draft.

## Implemented draft slice

- The incident detail now renders Phase 17 `next_actions` as read-only suggestion cards with the exact action,
  target, risk colour, basis, grounds and cited evidence IDs. It never presents a write control, including if an
  unexpected `is_executable` value appears in the response. This is the first frontend integration of the reviewed
  cards; a separately flagged local mock incident makes the card visible without API interception.
- The private Actions screen now opens a known approval ID and shows the frozen action, judge verdict/reasons,
  risk, evidence, prediction, alternatives and rollback. Approve / Deny controls are shown only on that screen;
  they require `/me` to grant `approve_action` in a full session. A red approval also requires the exact typed target.
  The decision code requests an object-bound WebAuthn step-up before POSTing the digest and decision. In the opt-in
  local demo the controls remain disabled; the public production token cannot reach this screen. A pending-approval
  list and the real private browser login are still to be built after ACR-0032.
- An opt-in `/api/v1/ops/approvals/{id}` read route presents the frozen proposal and bound judge verdict. It is
  mounted only when the composition root explicitly supplies `action_rows`; production wiring does not.
- The answer route requires a full token, `approve_action`, an authenticated human, a ready WebAuthn session, exact
  digest, a fresh object-bound step-up, and typed target confirmation for red risk. The existing store atomically
  records an answer and a resume intent. It is also unmounted in production.
- The ordinary `/me` response does not advertise `approve_action` while action rows are absent. No route calls an
  action executor or gateway.
- Opt-in private holds require `place_hold`, a human with a WebAuthn-ready full session, a step-up bound to the exact
  target scope, and a known inventory target or `*` for emergency stop. Hold insertion and the chained audit record
  commit atomically. The Phase 18 precheck already refuses a global or target hold.
- The action-gateway core has an empty route map by default. Its test-only released map rejects vm-095, non-lab
  targets and route mismatches. It checks the credential, action ID and target identity, writes a durable receipt
  before calling an injected proxy, and refuses any duplicate ID. An import-boundary test keeps the model and MCP
  code out of this module. A narrow HTTP handler is exercised on loopback with a fake transport; it denies unlisted
  paths, missing credentials and duplicate action IDs. Its receipt and result are separate insert-only journal
  events, enforced by database triggers. A second socket-proxy ACL allows only exact inspect and released POST paths;
  Docker inspect is reduced to the container ID before it crosses back. The gateway's proxy transport rechecks
  identity before POST. An image and separate-role startup exist, but the committed configuration has no routes;
  startup refuses an empty release map. No compose service, token or real Docker connection is deployed.
- An approval arriving after a target or global hold is rejected before consuming its step-up; the execution
  precheck independently checks the hold again.

## Proposed architecture decision

[ACR-0032 draft PR #325](https://github.com/agenticteam03/argus_production/pull/325) records a gap found while wiring the
private UI: the public browser login cannot issue a full token, while approval POSTs require one. The ACR proposes a
private login protected by the existing mTLS/allowlist. It is **proposed only**; no private login or full browser
token has been implemented. Acceptance and the required safety approval must precede that step.

## Review fixes (2026-10-26)

- Every approval answer writes a chained audit row with the answer and its resume intent, in one transaction; a
  denial needs a reason (ACR-0019 §3.12).
- `approve_action` and `place_hold` belong to the `approver` role only (ACR-0018 §5); an operator gets 403.
- A red approval types the host-qualified target; the view returns `reversible`; the UI shows the target identity,
  the arguments and reversible yes/no.
- A whole host can be held. A target or host hold is released over the private API with its own step-up and an
  audit row; the emergency stop is released only with `argus hold release` on vm-095. `argus hold place|list|release`.
- The gateway records Docker's 304 as `confirmed` and an identity change before the write as `failed` (not sent).
- Exit proofs on real images (`tests/test_phase19_real_images.py`, `ARGUS_TEST_DOCKER=1`, run in CI): in the agent
  image the action token is readable by the worker only, not by `argus-tools` directly or through sudo; the gateway
  and proxy images run as two containers, only the proxy mounts Docker's socket, and the released pair, token, action
  id, duplicate refusal, 304 and the proxy's refusal of unreleased paths hold against a real Docker engine. The test
  found the proxy could not create its socket in a root-owned volume: the image now owns `/run/argus-v18` and
  `/var/lib/argus-v18`.
- `SELF_MERGE_PROTECTED` reserved `services/action-gateway/`, but the code is the package `services/action_gateway/`:
  both are protected now.

## Follow-ups after this PR (phase 19 is not done until they are)

1. Resolve ACR-0032 (#325), then connect the private login and add a pending-approval list to the Actions tab.
2. The worker's gateway client and the token mount itself (the image-level isolation is proved); keep the released
   route map empty and deployment absent.
3. Leases as holds (ACR-0019 §3.11): a source for the precheck's `host_lease_clear`.
4. When the routes are mounted: `ARCHITECTURE.md` (§4.5, §14.3, the API) and ACR-0019 §6 "Applied", with a version
   bump; the deploy PR binds the gateway to an Argus port reachable only from the worker, with its firewall rule in
   the rollback block.
5. Exercise the approval flow with real WebAuthn ceremonies and the private edge once ACR-0032 is applied. Phase 20
   has a separate release PR for the first pair.

## Exit boundary

This PR is not a release. No approval is accepted by production, no gateway is deployed, no action token is
configured, and `write_gate.open` remains empty.
