## 2026-10-28 - ACR-0042: the bell counts the approvals waiting for an approver

Type: architecture change
Who: conantkd (+ agent)
Context: the header's bell was decorative, and the only list of waiting approvals is private and privileged
(ACR-0032), so an approver browsing the dashboard never learned that an approval waited.
Decision / result:
- `GET /api/v1/approvals/waiting` returns only `{"waiting": N}`, counted with the private list's filter (pending, still
  verifying, in scope; at most 50). Permission `count_waiting_approvals`, an approver's while the action routes are
  mounted, not privileged: any token kind, no second factor, a human only. `/me` lists it.
- `pending_approvals` and the count share `waiting_approvals`, so they cannot disagree.
- The edge proxies the route; the UI contract and `docs/API-FOR-UI.md` list it (rule 14, a routes row, the `/me` action).
- The bell (`NotificationBell.jsx`, `useWaitingApprovals.js`) polls every 30 s while `/me` lists the action, badges the
  count (50+ at the cap), leads to Actions, and inside a confirmed private session names each approval and links to
  its incident.
- `ARCHITECTURE.md` 1.8.50 and [ACR-0042](../../architecture/changes/ACR-0042-approvals-waiting-count.md).
Consequences: least privilege, narrowly: an approver's password without the keys reveals how many approvals wait in
that scope and nothing about them; second approval requested in the review. Deploy: the agent and UI images on
vm-095, no migration. An approver sees the bell after signing in again (the UI keeps `/me` from the login).
References: [ACR-0032](../../architecture/changes/ACR-0032-private-browser-login.md), [ACR-0019](../../architecture/changes/ACR-0019-human-approved-remediation.md).

### Test state

RED seen: `tests/test_acr0042_waiting_count.py` (three of four fail without the route and the permission). GREEN
locally: those four; the phase 16 private path, phase 19 approval view and private login, X-9 wiring, UI contract,
ACR-0011 edge, UI access and ACR-0018 matrix files (198 tests); vitest 343 tests including the bell and the adapter
contract; eslint without new warnings; ruff clean on `argus/`. CI is the full check.

### Next step

Review (with the second approval for least privilege), then deploy the agent and UI images on vm-095.
