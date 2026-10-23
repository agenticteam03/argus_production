# ACR-0030 — Human sessions end after 30 minutes of inactivity, not 30 minutes after login

Extends [ACR-0018](ACR-0018-operator-access-and-audit.md) (server-side sessions, accepted in #209). Independent of
[ACR-0020](ACR-0020-operator-terminal.md): a terminal session keeps its own limits.

| Field | Value |
|---|---|
| Status | `proposed` |
| Proposed by | juanes6554 (+ agent) · 2026-10-23 |
| Accepted by | pending |
| Second approval (safety principle only) | **required**: secrets (a bearer token's lifetime grows from 30 min to the absolute limit) |
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

§17.3, the token bullet, after "There are no refresh tokens: the caller logs in again." — add:

> "**Human sessions (ACR-0030).** For a human principal the token's `exp` is the session's **absolute** limit,
> `ARGUS_SESSION_ABSOLUTE_MIN` *(480)*, and the session also ends after `ARGUS_SESSION_IDLE_MIN` *(30)* without
> **user** activity. `auth_session` gains `last_active_at`. Activity is recorded only by
> `POST /api/v1/auth/session/activity` (every token may call it, like logout; the UI calls it at most once a minute,
> and only after a pointer, key or focus event); other requests, the UI's background polling included, never extend
> a session. A request on a session idle for longer is refused with 401 ("session idle; log in again") and audited
> (`access.session_idle`). Agent and service tokens keep `ACCESS_TOKEN_TTL` (30 min) and no idle check."

§20 (configuration), Authentication row: add `ARGUS_SESSION_IDLE_MIN`, `ARGUS_SESSION_ABSOLUTE_MIN`.

A migration adds `auth_session.last_active_at` (set at login). The UI part (T-0016): an activity tracker that calls
the route, a warning two minutes before the idle limit ("Stay signed in"), sign-out at the idle limit, and the
absolute limit taken from the token's `exp` as today. Privileged permissions are unchanged: they still need a login
completed with a key, and a step-up per privileged object.

**Alternatives considered:**
- A: **raise `ARGUS_JWT_TTL_MIN` to 480 on vm-095** (one environment line, no code). Fastest, but a stolen token lives
  8 h and an unattended browser stays signed in for 8 h: no idle limit. Possible as a stopgap only if the team accepts
  that risk.
- B: **rotating refresh tokens.** A standard, but a second secret to store, rotate and revoke, and §17.3 chose none;
  the server-side session already gives revocation, so an idle column is smaller.
- C: **keep 30 min; the UI only warns before `exp`.** No backend change and no risk change, but the forced re-login
  stays; it is the UI part that ships now, whatever is decided.

## 4. Consequences

- **Code:** `argus/adapters/inbound/http.py` (the idle check where `jti` is checked; the activity route; login sets
  `last_active_at`), both stores (`auth_session`), `infrastructure/wiring.py` (two settings), a migration, the
  runtime role's grants, `argus db check`; `frontend/src/services/sessionStore.js` and an activity hook.
- **Tests:** idle past the limit → 401 and `access.session_idle`; activity extends it; a `GET` (polling) does not;
  the absolute limit still ends a busy session; an agent token is unaffected; a revoked session stays revoked; the
  UI's tracker throttles to one call a minute and ignores timers; the authorization matrix gains the new route.
- **Deployment:** the migration on vm-095 (lease, `code.bash`); the two settings in the agent's environment.
- **Contract:** `contracts/ui-api.json` gains the activity route.
- **Risk:** a bearer token valid up to 8 h if stolen, bounded by the idle limit, logout and administrator
  revocation (each request checks the session row).
- **How to reverse it:** set `ARGUS_SESSION_ABSOLUTE_MIN=30` (back to today's behaviour); the column stays unused.
- **Safety principle touched:** yes, **secrets** (a token's lifetime). Read-only, the write gate, host isolation and
  evidence integrity are unchanged. Second approval required.

## 5. Decision

Proposed. To be accepted, changed or rejected in this PR's review (open decision: 30 min idle and 480 min absolute,
or other values).

## 6. Applied

- [ ] `ARCHITECTURE.md` updated (§17.3, §20), version bumped, changelog line added (with this ACR's link)
- [ ] journal entry
- [ ] the ACR, the architecture change and the first code that needs it are in the same pull request
