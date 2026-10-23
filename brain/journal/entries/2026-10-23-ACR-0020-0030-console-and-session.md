## 2026-10-23 — Operator console in the UI and session lifetime: review proposals (ACR-0020 §3.1, ACR-0030)

Type: decision (proposal)
Who: juanes6554 (+ agent)
Context: the UI owner wants a per-host console in the UI (the MVP's terminal panel) and longer UI sessions. Argus is
read-only in this phase; ACR-0020 (the operator terminal) is still `proposed` and ACR-0018 grants
`open_terminal:<host>` to nobody until ACR-0020 decides; `/me` lists no console action. The UI signs people out 30 min
after login (`ARGUS_JWT_TTL_MIN` default 30, no refresh, §17.3).
Decision / result: proposals only, nothing accepted. ACR-0020 §3.1 adds the UI owner's changes (a `/me` action
`open_terminal` with `terminal_hosts`, an in-app right panel, a 30 min absolute terminal session, a simulated shell
behind a flag before the broker) and three open decisions (UI-1 to UI-3). ACR-0030 proposes a 30 min idle limit with
an 8 h absolute limit for human sessions.
Consequences: no console code is written until ACR-0020 is accepted with its second approval (or UI-3 allows the
flagged prototype). The UI may already warn before the token expires (ACR-0030 alternative C).
References: [ACR-0020](../../architecture/changes/ACR-0020-operator-terminal.md),
[ACR-0030](../../architecture/changes/ACR-0030-idle-session-timeout.md), [T-0016](../../tasks/current/T-0016-frontend.md).

### Next step

Team review of ACR-0020 §3.1 (UI-1 to UI-3, OD-17) and ACR-0030, with the second approvals for the safety
principles; then the console prototype (if UI-3 allows it) and the ACR-0030 implementation.
