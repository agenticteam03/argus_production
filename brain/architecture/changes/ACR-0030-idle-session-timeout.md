# ACR-0030 — Human sessions end after 30 minutes of inactivity, not 30 minutes after login

Extends [ACR-0018](ACR-0018-operator-access-and-audit.md) (server-side sessions, accepted in #209). Independent of
[ACR-0020](ACR-0020-operator-terminal.md): a terminal session keeps its own limits.

| Field | Value |
|---|---|
| Status | `proposed` |
| Proposed by | juanes6554 (+ agent) · 2026-10-23 |
| Accepted by | pending |
| Second approval (safety principle only) | **required**: secrets (a bearer token's lifetime grows from 30 min to the absolute limit; a new session-binding secret) |
| Architecture version | the next free version when applied |
| Task / PR | T-0016 · PR (this proposal) |

## 1. Detect and explain

Operators are signed out of the UI 30 minutes after they log in, even while they are working, and every new login
needs the password **and** a security-key assertion (ACR-0018). Evidence (code, `OBSERVED` by reading it):

- `argus/infrastructure/wiring.py`: `jwt_ttl_min` = `ARGUS_JWT_TTL_MIN`, default **30**; no file under `deploy/` sets
  it. `OBSERVED` on vm-095 (2026-10-23, a UI login through the tunnel): the token's `exp - iat` is 30 min.
- `argus/adapters/inbound/http.py` (`/api/v1/auth/token`): `exp` and the session row's `expires_at` are login time +
  `jwt_ttl_min`; nothing extends them.
- §17.3: "There are no refresh tokens: the caller logs in again."
- `frontend/src/services/sessionStore.js`: the UI keeps the session for `VITE_ARGUS_SESSION_TTL_MIN` (480) but never
  past the token's `exp`, so the UI's 8 h never applies: the token's 30 min wins.

## 2. Why the current architecture is insufficient

§17.3 ties a human session's whole life to one fixed token lifetime (`ACCESS_TOKEN_TTL`, 30 min) with no way to
continue. A short absolute limit is right for agents and services, but for a person it means a forced re-login with a
security key every half hour, which pushes people to raise `ARGUS_JWT_TTL_MIN` (a longer-lived token with no idle
limit at all) — weaker than an idle limit.

## 3. Smallest reasonable change

### 3.1 Threat model (revised after review: a client's word is not proof of a person)

A first draft let any holder of the bearer token report activity. That proves nothing: a **stolen** token could call
the activity route once a minute and live to the absolute limit, so the idle limit would not bound the thief
(review of #307, P1). Renewal must need something the bearer token alone does not carry:

- **A session-binding secret.** At a browser login the API also sets a random 256-bit value in a cookie the page's
  scripts cannot read: `__Host-argus_bind`, `HttpOnly; Secure; SameSite=Strict; Path=/`, expiring with the session.
  `auth_session` keeps only its SHA-256 (`binding_hash`). It is never in a response body, a URL, a log or storage.
  The terminal (ACR-0020) lives on its own origin and never receives it.
- **Who can renew, and who cannot:**

| Holder | Has the token | Has the binding cookie | Can keep the session alive |
|---|---|---|---|
| the person, in the UI | yes | yes (the browser sends it) | yes, up to the absolute limit |
| a thief who copied the token out of the browser, a log or a proxy | yes | no | **no**: the session ends `ARGUS_SESSION_IDLE_MIN` after the person's last activity (or at logout, revocation or the absolute limit) |
| code injected into the UI page (XSS) | yes | it cannot read it, but the browser attaches it | **yes**, up to the absolute limit: **accepted residual risk** (below) |
| a login without a browser (CLI, Swagger) | yes | no | no: such a session never renews and ends at the idle limit after login, as strict as today |

- **The accepted residual risk.** Code running inside the person's own page already acts as that person while the page
  is open; this ACR lets it keep the session open while the page stays open, up to the absolute limit. It cannot
  export the session (the cookie is unreadable), and it cannot use any privileged permission: each privileged object
  needs a fresh step-up with the person's security key (ACR-0018), which needs the person's presence. The defences
  against injected code stay the SPA's strict CSP (no inline or third-party scripts), no `dangerouslySetInnerHTML`
  with API text, and the terminal's separate origin (ACR-0020).
- **A token used while the person is still active** remains usable by a thief until the session ends, as it is today
  within 30 min. Checking the binding cookie on **every** request would close that too (open decision D-2).

### 3.2 The change to the text

§17.3, the token bullet, after "There are no refresh tokens: the caller logs in again." — add:

> "**Human browser sessions (ACR-0030).** For a human principal the token's `exp` is the session's **absolute**
> limit, `ARGUS_SESSION_ABSOLUTE_MIN` *(480)*, and the session also ends after `ARGUS_SESSION_IDLE_MIN` *(30)* without
> **user** activity. `auth_session` gains `last_active_at` and `binding_hash`. A browser login also sets the binding
> cookie `__Host-argus_bind` (`HttpOnly; Secure; SameSite=Strict`; only its SHA-256 is stored). Activity is recorded
> only by `POST /api/v1/auth/session/activity`, which requires the bearer token **and** the matching binding cookie
> **and** an `Origin` equal to the UI's origin; anything else is refused with 403 and audited
> (`security.session_renewal_refused`). The UI calls it at most once a minute and only after a pointer, key or focus
> event; no other request, the UI's background polling included, extends a session. A request on a session idle for
> longer is refused with 401 ("session idle; log in again") and audited (`access.session_idle`). A session without a
> binding (CLI, Swagger) is never renewed. Agent and service tokens keep `ACCESS_TOKEN_TTL` (30 min) and no idle
> check."

§20 (configuration), Authentication row: add `ARGUS_SESSION_IDLE_MIN`, `ARGUS_SESSION_ABSOLUTE_MIN`.

A migration adds `auth_session.last_active_at` (set at login) and `binding_hash` (null for logins without a browser).
The UI part (T-0016): an activity tracker that calls the route, a warning two minutes before the idle limit ("Stay
signed in", which counts as activity), sign-out at the idle limit, and the absolute limit taken from the token's
`exp` as today. Privileged permissions are unchanged: they still need a login completed with a key, and a step-up
per privileged object.

**Alternatives considered:**
- A: **raise `ARGUS_JWT_TTL_MIN` to 480 on vm-095** (one environment line, no code). Fastest, but a stolen token lives
  8 h and an unattended browser stays signed in for 8 h: no idle limit. Possible as a stopgap only if the team accepts
  that risk.
- B: **rotating refresh tokens.** A standard, but a second secret to store, rotate and revoke, and §17.3 chose none;
  the server-side session already gives revocation, so an idle column is smaller.
- C: **keep 30 min; the UI only warns before `exp`.** No backend change and no risk change, but the forced re-login
  stays; it is the UI part that ships now, whatever is decided.
- D: **renewal by a security-key assertion** (user verification) instead of a cookie. The strongest proof of a person,
  but a key prompt every 30 min of work is the same friction as today's re-login.
- E: **report activity with the bearer token alone** (the first draft). Rejected in review: a stolen token renews
  itself, so the idle limit would not bound a thief.

## 4. Consequences

- **Code:** `argus/adapters/inbound/http.py` (the idle check where `jti` is checked; the activity route with its
  cookie and `Origin` checks; login sets `last_active_at`, `binding_hash` and the cookie), both stores (`auth_session`), `infrastructure/wiring.py` (two settings), a migration, the
  runtime role's grants, `argus db check`; `frontend/src/services/sessionStore.js` and an activity hook.
- **Tests:** idle past the limit → 401 and `access.session_idle`; activity with the token and the cookie extends it;
  activity with the token but no cookie, a wrong cookie, another session's cookie or a foreign `Origin` → 403 and
  `security.session_renewal_refused`, and the session still ends at the idle limit (the stolen-token case); a CLI
  login never renews; the cookie is `HttpOnly`, `Secure`, `SameSite=Strict`, `__Host-` and never in a body or log;
  a `GET` (polling) does not extend;
  the absolute limit still ends a busy session; an agent token is unaffected; a revoked session stays revoked; the
  UI's tracker throttles to one call a minute and ignores timers; the authorization matrix gains the new route.
- **Deployment:** the migration on vm-095 (lease, `code.bash`); the two settings in the agent's environment; the
  edge's exact-route allowlist gains `location = /api/v1/auth/session/activity` (`deploy/ui/nginx/locations.conf`),
  like the other `/api/v1/auth/*` routes; the cookie is set and read only by the API, same origin as the UI.
- **Contract:** `contracts/ui-api.json` gains the activity route.
- **Risk:** a stolen token alone cannot renew: it ends within the idle limit after the person's last activity, or at
  logout or revocation (each request checks the session row). Injected code in the person's own page can keep the
  session open up to the absolute limit without being able to export it or pass a step-up (§3.1, accepted residual
  risk, to be confirmed in review).
- **How to reverse it:** set `ARGUS_SESSION_ABSOLUTE_MIN=30` (back to today's behaviour); the column stays unused.
- **Safety principle touched:** yes, **secrets** (a token's lifetime and a new binding secret). Read-only, the write gate, host isolation and
  evidence integrity are unchanged. Second approval required.

## 5. Decision

Proposed. To be accepted, changed or rejected in this PR's review. Open decisions:
- **D-1:** the values: 30 min idle and 480 min absolute, or others (a shorter absolute limit shrinks the residual risk).
- **D-2:** check the binding cookie on renewal only (this text), or on **every** request of a bound session (a stolen
  token becomes useless off the person's browser, at the cost of a check on every route).
- **D-3:** accept the residual risk of §3.1 (injected code in the person's page keeps the session open while the page
  is open).

## 6. Applied

- [ ] `ARCHITECTURE.md` updated (§17.3, §20), version bumped, changelog line added (with this ACR's link)
- [ ] journal entry
- [ ] the ACR, the architecture change and the first code that needs it are in the same pull request
