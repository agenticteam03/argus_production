# ACR-0031 — A private browser login for approval actions

| Field | Value |
|---|---|
| Status | `proposed` in the Phase 19 draft; **do not review or approve yet** |
| Proposed by | conantkd (+ Codex) · 2026-10-25 |
| Accepted by | pending |
| Second approval (safety principle only) | pending; least privilege and credential exposure |
| Architecture version | pending after ACR-0018 and ACR-0019 are applied |
| Task / PR | [PHASE-19](../../tasks/current/PHASE-19-approval-ui-gateway.md) · draft PR #324 |

## 1. Detect and explain

The Phase 19 UI must answer an approval through the private path with `approve_action` and an object-bound step-up
(ACR-0019 §3.10). The answer is a POST. The current browser login is `/api/v1/auth/token` through the public edge;
it only issues `read` or `investigate` tokens. `_principal_dep` refuses every approval POST from either scope. A full
token is currently issued only on loopback. Thus a browser using the private path cannot complete the designed flow.

## 2. Why the current architecture is insufficient

ACR-0018 §3 and ARCHITECTURE §17.3 require the public edge to issue only narrowed tokens and place every route
requiring a privileged permission under `/api/v1/ops/`. The private path's mTLS and address allowlist protect
privileged routes, but no login route behind those controls issues the full token that an approval POST needs. The
private path test currently enforces that every route under `/api/v1/ops/` itself requires a privileged permission;
an unauthenticated login cannot satisfy that rule. This is a design gap, not a failed Phase 16 deployment.

## 3. Smallest reasonable change

Add `POST /api/v1/ops/auth/token` as the **single documented exception** to the rule that every private-prefix route
requires a privileged permission. The existing edge's mTLS certificate check, CRL and address allowlist protect the
entire prefix; the API reuses the existing password verification, durable login limiter, session store and audit
events. This endpoint issues a full token only after those checks. Public `/api/v1/auth/token` continues to issue
only `read` or `investigate` through the edge. A full browser token stays in memory and is not saved to
`sessionStorage`; reloading requires another private login. WebAuthn login completion, two enrolled credentials,
role permission and a single-use step-up are still required for each privileged write.

The private-edge test must name this endpoint as the sole unauthenticated exception and prove that requests without
a valid client certificate and allowlisted address receive 404 before reaching the API. API tests must prove the
public login still refuses a full edge token, private login shares lockout/audit, and scoped tokens still refuse
approval POSTs.

**Alternatives considered**

- Allow full tokens on the existing public login when an edge header says mTLS succeeded. This makes one public
  endpoint security-sensitive to proxy header configuration and weakens the simple public-token rule.
- Require operators to fetch a full token from loopback and paste it into the browser. This exposes a privileged
  token during copying and does not provide the intended UI flow.
- Allow a scoped token to answer after step-up. That changes the meaning of the token's `read`/`investigate` scope
  and would make existing access rules misleading.

## 4. Consequences

- Code and tests: private login route, explicit private-edge test exception, browser session handling and an
  end-to-end mTLS/WebAuthn approval test. No action route or write gate is released by this ACR.
- Risk: a privileged token enters a browser; the private edge and in-memory storage limit its exposure. An error in
  the mTLS/allowlist configuration could expose the login, so the real Nginx image test is required before release.
- How to reverse: remove the private login route and the browser control; existing public login behavior remains.
- Safety principle: **yes** — least privilege and credential exposure. Acceptance and the second approval are
  required before implementation.

## 5. Decision

Pending. This proposed record in a draft PR is not an acceptance or permission to change the login behavior.

## 6. Applied

- [ ] ACR accepted with the required approval
- [ ] `ARCHITECTURE.md` updated and version bumped in the implementing PR
- [ ] Private login, browser session handling and edge tests implemented in that PR
- [ ] Journal updated with deployment evidence
