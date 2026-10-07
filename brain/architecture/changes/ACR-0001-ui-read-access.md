# ACR-0001 — User interfaces as read-only-capable clients of the HTTP API (OD-10)

An Architecture Change Record is the **only** way to change `brain/architecture/ARCHITECTURE.md`. ACRs are never
fast-tracked: this one needs a teammate's approval in its pull request.

| Field | Value |
|---|---|
| Status | `accepted` |
| Proposed by | juanbetancurm (+ agent) · 2026-10-06 |
| Accepted by | conantkd (+ agent) · 2026-10-06 |
| Second approval (safety principle only) | not required — see §4 (no safety principle is changed; access is narrowed) |
| Architecture version | from `1.8.0` → `1.8.1` |
| Task / PR | T-0015 (step 1) · PR #22 |

## 1. Detect and explain

The team plans a web frontend for operators (T-0016, `juanes6554`), next to the existing console (`argus diagnose …`)
and Swagger. Before any frontend code exists, the architecture must say whether such a client is allowed, how it
authenticates, and what it may do. Today it says the opposite of the plan (quote below), so building it would be a
silent architecture change — which the change process forbids.

## 2. Why the current architecture is insufficient

- **§25 OD-10:** *"A dedicated approval/incident UI beyond Swagger, CLI and (later) Slack links — not needed for this
  release."* The team now needs one.
- **§17.3:** a human login always yields a token with the user's full role. There is no way to give a frontend a
  token that can **only read**, so a bug in a frontend would have every power of the logged-in user (start
  investigations, and later answer approvals).
- **§7.1:** the route table has no "who am I" route, so a frontend would have to guess, from the role, which
  buttons to show — permission logic duplicated outside Argus. The table also omits three read routes that the
  implementation already serves and the frontend will need: `GET /api/v1/incidents/{id}/events`,
  `GET /api/v1/evidence/{id}`, `GET /api/v1/escalations`.

## 3. Smallest reasonable change

**§25 OD-10**, before → after:

> before: `not needed for this release`
>
> after: **decided by ACR-0001 (2026-10-06):** dedicated user interfaces are allowed as **separate clients of the
> HTTP API**, never inside the core. In this release a UI holds **only read-only tokens**; a UI write action needs a
> new ACR (§5). The team's web frontend lives in
> `frontend/` and runs as container `argus-v18-ui` (static files + a proxy to the API) on a **loopback port of
> Host A**, reached like Swagger (SSH tunnel). Answering approvals stays in Swagger/CLI in this release.

**§17.3**, one new bullet after the JWT bullet:

> - **Read-only tokens.** The login may ask for `scope=read` (the OAuth2 form field). The JWT then carries
>   `access: "read"` (otherwise `access: "full"`). This claim is separate from `scopes` (the target-scope names) and
>   can only **narrow** what the role allows: a read token is refused with 403 on every route that is not a `GET`,
>   whatever the role, before any use case runs, and the refusal is audited (`access.read_only_refused`).

**§7.1**, four rows added to the table:

> | `GET /api/v1/me` | — (who am I) | JWT (read or full) | `user`, `role`, `access`, and the `actions` this token may use (e.g. `view_incidents`, `view_timeline`, `view_evidence`); a UI shows a control only when its action is listed |
> | `GET /api/v1/incidents/{id}/events` | run events of an incident | JWT | already implemented (the node timeline used by the CLI) |
> | `GET /api/v1/evidence/{id}` | one evidence record | JWT: operator or approver | already implemented |
> | `GET /api/v1/escalations` | escalations waiting for a human | JWT | already implemented |

and one new request rule:

> - **Browser clients:** cross-origin requests are refused unless their origin is listed in `ARGUS_UI_ORIGINS`
>   (empty by default: no CORS headers at all). In production the UI container proxies the API on the same
>   origin, so the list stays empty there.

**§2.4** (code organization), one line: `frontend/ — the team's web UI (its own toolchain; talks to the API only)`.

**Changelog:** `1.8.1 · 2026-10-06 · user interfaces as read-only-capable API clients; GET /api/v1/me; existing read
routes documented · ACR-0001`.

**Alternatives considered:**
- **A — Keep OD-10 as is and give the frontend normal (full) tokens.** Rejected: a frontend bug, or a stolen
  browser token, could start investigations or, later, answer approvals; the frontend would also re-implement
  permission rules from the role.
- **B — A separate "UI backend" service with its own database copy.** Rejected: a second source of truth, more to
  deploy and secure, and no benefit for a read-only view.
- **C — Server-side pages inside the API (templates).** Rejected: puts UI code in the core, against the hexagonal
  boundaries (§2), and blocks `juanes6554` from choosing his own toolchain.

## 4. Consequences

- **Code (T-0015 steps 2–5):** `adapters/inbound/http` (read-token check, `GET /api/v1/me`, optional CORS),
  `docs/API-FOR-UI.md`, `contracts/ui-api.json` + `contracts/samples/` with a contract test. The domain, the
  application use cases, policy, tools and the skeleton are **not touched**.
- **Deployment:** a new container `argus-v18-ui` on Host A, loopback port only (T-0016); no new public or private
  listener; the API listener is unchanged.
- **Tests:** a read token is refused on every non-`GET` route (403, audited) and accepted on every `GET`; the same
  user's full token is unaffected; `/me` lists the right actions per role and access; no CORS headers unless
  configured; the contract test turns CI red when a change would break the UI.
- **Risk:** low. The change only adds a narrower kind of token and read routes; a mistake in the read-token check
  is caught by the tests above, and the worst case is a frontend that cannot read (it never gains rights).
- **How to reverse it:** remove the `access` claim handling and `/me`, restore OD-10 to "not needed", delete
  `frontend/` and the UI container. Existing CLI, Swagger and tokens keep working throughout.
- **Safety principle touched?** **No.** Read-only stays (nothing here writes; the write gate is untouched), host
  isolation and evidence integrity are untouched, no secret is added (the UI holds only the user's own short-lived
  token). It **narrows** access and adds no public port. One teammate's approval in the PR is enough.

## 5. Decision

**Accepted by `conantkd` (reviewer of PR #22), 2026-10-06.**

- **Read-only in this release.** User interfaces are allowed as separate clients of the HTTP API, and a UI logs in
  with `scope=read` only. It shows incidents, timelines, evidence and escalations; it never starts an
  investigation and never answers an approval. Starting investigations stays in the CLI and Swagger.
- **Open for more, through a new ACR.** This is the scope of this release, not a permanent limit. A later ACR may
  let a UI do more, for example starting investigations or answering approvals. The mechanism is already in
  place: `GET /api/v1/me` lists the actions a token may use, and a UI shows a control only when its action is
  listed, so a new UI action is a change on the API side (a new action, a new kind of token) plus that ACR, never
  permission logic in the UI.
- **Approvals stay out of user interfaces** until an ACR says otherwise. Answering an approval releases a write,
  so that ACR touches a safety principle and needs a second approval.
- Clarification of alternative A: a UI holding the user's full token is not adopted **in this release**; it is
  not ruled out forever.

## 6. Applied

- [x] `ARCHITECTURE.md` updated to `1.8.1` (§2.4, §7.1, §17.3, §25 OD-10), changelog line added with this ACR's link
- [x] journal entry
- [x] the ACR, the architecture change and the first code that needs it are in the same pull request (T-0015)
