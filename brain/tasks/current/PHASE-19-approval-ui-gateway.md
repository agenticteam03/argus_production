# PHASE-19 — Private approvals and action gateway

| Field | Value |
|---|---|
| Status | draft implementation; **do not review or approve** this PR yet |
| Phase | 19 of [NEXT-PHASE](NEXT-PHASE-supervised-remediation.md) |
| Architecture | [ACR-0019](../../architecture/changes/ACR-0019-human-approved-remediation.md), accepted; no new ACR needed for this slice |
| Branch | `task/T-0052-approval-gateway`, stacked on Phase 18 PR #323 |
| VM lease | none; this draft makes no VM change |

## Goal and assumption

Prepare the private approval UI and action gateway on the Phase 18 contract. At the user's direction, proceed with
Phase 16 **assumed** applied and deployed. That is a planning assumption, not VM evidence. Before release, verify
the off-host audit digest, Phase 16 exit proof, and deployed state against the VMs. Keep the write gate closed and
do not connect a real target or credential in this draft.

## Implemented draft slice

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

[ACR-0031 draft PR #325](https://github.com/agenticteam03/argus_production/pull/325) records a gap found while wiring the
private UI: the public browser login cannot issue a full token, while approval POSTs require one. The ACR proposes a
private login protected by the existing mTLS/allowlist. It is **proposed only**; no private login or full browser
token has been implemented. Acceptance and the required safety approval must precede that step.

## Remaining work before this PR can be reviewed

1. Verify and record Phase 16 deployment and the off-host audit digest; resolve the #314 dependency and stack
   ordering through #316, #318 and #323.
2. Resolve ACR-0031, then build the private Actions tab, colours, judge rationale and suggestions. Add a deliberate
   path to release ordinary holds; the emergency stop must not be cleared by an unreviewed UI toggle.
3. Run gateway/proxy real-image tests with a throwaway Docker engine and prove socket/token isolation; Docker Desktop
   is unavailable on this Windows host. Keep the released route map empty in the repository and deployment absent.
4. Exercise the approval flow with real WebAuthn ceremonies and the private edge; run full offline, PostgreSQL and
   CI gates on the final head. Check production wiring and the write gate remain closed.
5. Only then request review. Phase 20 has a separate release PR for the first `(capability, scope)` pair.

## Exit boundary

The draft is not a release. No approval is accepted by production, no gateway is deployed, no action token is
configured, and `write_gate.open` remains empty.
