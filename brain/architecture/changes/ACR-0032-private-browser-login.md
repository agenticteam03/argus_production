# ACR-0032 — A private browser login whose full token works only on the private path

Extends [ACR-0018](ACR-0018-operator-access-and-audit.md) (operator access, the private path) for
[ACR-0019](ACR-0019-human-approved-remediation.md) §3.10 (approvals answered from the UI).

| Field | Value |
|---|---|
| Status | `accepted` (applied in #347) |
| Proposed by | conantkd (+ agent) · 2026-10-25, revised 2026-10-26 after review |
| Accepted by | juanbetancurm · 2026-10-27, approving review of #325 at `d4e41ed` |
| Second approval (safety principle only) | given in the same review (AGENT_PROTOCOL §4): least privilege (a full token reaches a browser) and secrets (a bearer token's binding and lifetime) |
| Architecture version | 1.8.38 |
| Task / PR | phase 19, [PR #324](https://github.com/agenticteam03/argus_production/pull/324) · this PR #325 (proposal); applied with the first code in [#347](https://github.com/agenticteam03/argus_production/pull/347) |

## 1. Detect and explain

The phase 19 UI answers an approval with a POST under `/api/v1/ops/` that needs `approve_action`, a WebAuthn-completed
session and an object-bound step-up (ACR-0019 §3.10). The browser cannot get the token that POST needs:

- `POST /api/v1/auth/token` through the public edge refuses a login without `scope=read` or `scope=investigate`
  (`argus/adapters/inbound/http.py`: `edge and not form.scopes` → 400; ACR-0011, ACR-0012);
- `_principal_dep` refuses every non-read request from a `read` token and every write but an investigation from an
  `investigate` token;
- a full token is issued only on loopback (the CLI and Swagger on vm-095).

## 2. Why the current architecture is insufficient

ACR-0018 §3 and ARCHITECTURE §17.3 let the public edge issue only narrowed tokens and put every route that needs a
privileged permission under `/api/v1/ops/`, which the edge passes only with a client certificate of the team's CA (not
revoked) from an allowlisted address, else 404 (`deploy/ui/nginx/http.conf`, `$argus_ops_ok`). No login route sits
behind that gate, and `tests/test_phase16_private_path.py` requires every route under the prefix to need a privileged
permission, which a login cannot. The private path shares the UI's origin (`ssl_verify_client optional` on the public
server), so WebAuthn's relying party and origin need no change.

## 3. Smallest reasonable change

1. **A private login.** `POST /api/v1/ops/auth/token`, the single documented exception to "every route under the
   prefix needs a privileged permission". It reuses the password check, the durable login limiter and lockout, the
   session store and the audit (`access.login` with `via: ops`). It issues a full token only to a human principal
   whose role grants a privileged permission (today `approver`) and who holds two WebAuthn credentials (ACR-0018 D3);
   anyone else gets the same answer as a wrong password.
2. **The token works only on the private path.** The session records `via = ops`. The edge sets
   `X-Argus-Ops: $argus_ops_ok` on every proxied request, replacing any client value (as `proxy.conf` does for
   `X-Argus-Edge`). The API refuses an ops session's token on any request whose `X-Argus-Ops` is not `1`, and on
   loopback (where the header is absent), and audits the refusal (`security.session_refused`, reason `off private
   path`). The header is defence in depth behind the edge's 404, never the only gate: the edge alone still decides
   whether `/api/v1/ops/` is reachable.
3. **The second factor on the private path.** The WebAuthn login completion and the step-up
   (`/api/v1/auth/webauthn/{login,step-up}/{options,verify}`) accept an ops session's token only with `X-Argus-Ops: 1`
   (rule 2), so a full token never completes its second factor from outside the allowlist.
4. **Fifteen minutes idle, one hour at most** (amended in #347, see §5). An ops session ends 15 minutes after its
   last request on the private path, and one hour after the private login whatever the activity, whatever ACR-0030
   decides for public sessions; logout and revocation end it at once, as now. Each request refreshes
   `auth_session.last_seen_at` (migration 017) in one UPDATE that also checks the deadline, so an expired session is
   never revived; an idle refusal is `security.session_refused` with reason `idle`.
5. **One token in the browser.** The private login replaces the public token in memory; the full token is never put
   in `sessionStorage`, `localStorage`, a cookie or the URL. A reload, logout or the session's end return the UI to
   the public login.

**Tests (in the implementing PR):**

- edge, on the real nginx image: `/api/v1/ops/auth/token` is 404 without a client certificate, with a revoked one,
  from an address outside the allowlist, and on the loopback server; a client's own `X-Argus-Ops` is replaced;
- API: the public login still refuses a full token through the edge; the private login shares the limiter, lockout
  and audit, and refuses a non-approver or a person with one credential; an ops token is refused without
  `X-Argus-Ops: 1` (any route, the WebAuthn ceremonies included), after 15 minutes without a request and after
  one hour; a `read` or `investigate`
  token still cannot answer an approval;
- `tests/test_phase16_private_path.py` names this route as the only one under the prefix without a privileged
  permission;
- UI: the full token never reaches `sessionStorage`; a reload returns to the public login.

**Alternatives considered**

- Full tokens on the public login when an edge header says mTLS succeeded: the public login becomes sensitive to
  proxy header configuration, the only gate is that header, and the simple rule "the public edge never issues a full
  token" is lost. Rejected.
- Operators fetch a full token on loopback and paste it into the browser: the token is exposed while copied and is
  not bound to the private path. Rejected.
- A scoped token answers after a step-up: `read`/`investigate` would no longer mean what they say. Rejected.

## 4. Consequences

- **Code:** the private login route and its role/credential check; the ops session marker and the `X-Argus-Ops`
  check in `_principal_dep`; `proxy.conf` sets the header; the ops session's idle and absolute ends; the UI's private login and
  memory-only token. No action route is released and `write_gate.open` stays empty.
- **Security alerts:** a refused or locked private login and `security.session_refused` with reason `off private
  path` join the alerting events (`infrastructure/security_alerts.py`, #344).
- **Risk:** a full token in a browser. Limited by: approvers only, two credentials, the private path for every use,
  memory only, 15 minutes idle and one hour at most, the step-up per approval. A wrong edge configuration could expose the login; the real
  nginx image test is required before deployment.
- **How to reverse:** remove the private login route and the UI control; public login behaviour is unchanged.
- **Sequencing:** the accepted ACR, the `ARCHITECTURE.md` update (§17.3, the private path) with its version bump and
  the first code go in the same PR (AGENT_PROTOCOL §4).
- **Safety principles touched:** yes (least privilege, secrets). Second approval required.

## 5. Decision

Accepted 2026-10-27 by juanbetancurm's approving review of #325, which also gives the second approval for the safety
principles. Notes for the implementing PR, both met in #347: the header must not be forgeable around the edge (the
API believes it only from the edge's own address, `ARGUS_OPS_PEER`, since the worker, the tunnel and the egress proxy
share `argus-v18-core` with the API), and the real nginx image test runs before any deployment.

**Amendment (#347, 2026-10-26, `conantkd`):** rule 4 changed from "thirty minutes, absolute" to fifteen minutes
without a request and one hour at most, so an approver who keeps working is not cut off mid-decision while an
abandoned session still ends soon. It touches the same principle (a bearer token's lifetime): the approval of #347
accepts it with its second approval (AGENT_PROTOCOL §4).

## 6. Applied

- [x] ACR accepted with the required approvals (#325)
- [x] `ARCHITECTURE.md` updated and version bumped in the implementing PR (1.8.38, #347)
- [x] Private login, the private-path binding, the session's idle and absolute ends, the UI and the tests above implemented (#347)
- [ ] Journal updated with deployment evidence
