## 2026-10-23 — ACR-0030 proposed: human sessions end after 30 min of inactivity

Type: decision (proposal)
Who: juanes6554 (+ agent)
Context: the UI signs people out 30 min after login, while they work (`ARGUS_JWT_TTL_MIN` default 30, observed on
vm-095 as the token's `exp - iat`; no refresh, §17.3), and each login needs the password and a security key.
Decision / result: proposal only. ACR-0030: a 30 min idle limit and an 8 h absolute limit for human browser
sessions. After review (#307, P1) renewal needs an `HttpOnly` session-binding cookie, so a copied token cannot keep
itself alive; injected code in the person's own page can, up to the absolute limit, without passing a step-up: an
explicit residual risk for the team to accept (D-3). The UI console suggestions first proposed in this PR were
reconciled into ACR-0020 by #308 and are no longer here.
Consequences: no code until ACR-0030 is accepted with its second approval (secrets). The UI may already warn before
the token expires (alternative C).
References: [ACR-0030](../../architecture/changes/ACR-0030-idle-session-timeout.md),
[ACR-0018](../../architecture/changes/ACR-0018-operator-access-and-audit.md), [T-0016](../../tasks/current/T-0016-frontend.md).

### Next step

Team review of ACR-0030 (D-1 to D-3) with the second approval for secrets; then its backend and UI parts, tests
first.
