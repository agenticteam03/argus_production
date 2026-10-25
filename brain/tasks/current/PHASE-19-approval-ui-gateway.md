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

## Remaining work before this PR can be reviewed

1. Verify and record Phase 16 deployment and the off-host audit digest; resolve the #314 dependency and stack
   ordering through #316, #318 and #323.
2. Build the private Actions tab, colours, judge rationale, suggestions, holds and emergency stop.
3. Build the action gateway and socket proxy with exact routes, action IDs, journal, token isolation and no target
   route enabled. Add import-boundary and real-image route tests.
4. Exercise the approval flow with real WebAuthn ceremonies and the private edge; run full offline, PostgreSQL and
   CI gates on the final head. Check production wiring and the write gate remain closed.
5. Only then request review. Phase 20 has a separate release PR for the first `(capability, scope)` pair.

## Exit boundary

The draft is not a release. No approval is accepted by production, no gateway is deployed, no action token is
configured, and `write_gate.open` remains empty.
