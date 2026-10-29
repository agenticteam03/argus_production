# ACR-0042 — The bell: a public count of the approvals waiting for an approver

| Field | Value |
|---|---|
| Status | `accepted` |
| Proposed by | `conantkd` · 2026-10-28 |
| Accepted by | `conantkd` · 2026-10-28 |
| Second approval (safety principle only) | requested from the reviewer: least privilege (a count leaves the private path) |
| Architecture version | proposed: `1.8.49` → `1.8.50` |
| Task / PR | demo of 2026-10-28 · PR to be numbered on opening |

## 1. Problem

An approver learns that an approval waits only by opening Actions and signing in privately, or by reading an
incident. The header's bell is decorative. A proposal waits up to its expiry while nobody knows it is there.

## 2. Why the current architecture is insufficient

The only list of waiting approvals is `GET /api/v1/ops/approvals` (ACR-0032): privileged (`approve_action`), on the
private path, with an `ops` token and a WebAuthn-completed session. The ordinary UI session (an `investigate` token on
the public edge) cannot ask it, and the edge answers 404 to it on purpose. There is no way to tell an approver
"something waits" without a private session.

## 3. Smallest reasonable change

- `GET /api/v1/approvals/waiting` returns only `{"waiting": N}`: the private list's own filter (pending, still
  verifying, in the caller's scope), counted, at most 50. Nothing else: no approval id, incident, capability, target,
  risk or verdict.
- A new permission `count_waiting_approvals`, granted to the `approver` role only while the action routes are mounted
  (with `approve_action` and `place_hold`). It is **not** privileged: any token kind (read, investigate, full), no
  second factor; a human principal only. `/me` lists it as an action.
- The edge proxies exactly `GET /api/v1/approvals/waiting` like the other read routes. The UI contract and
  `docs/API-FOR-UI.md` list it.
- The UI's bell asks every 30 s while `/me` lists the action, shows the count, and leads to Actions. Inside a confirmed
  private session it also reads the private list and names each approval, linking to its incident.

**Alternatives considered:**

- The bell reads only the private list: rejected; it would work only inside a private session, which ends after 15
  minutes without use, so it would rarely warn.
- A push channel (Telegram, e-mail) for approvals: deferred; a separate change with its own secrets.
- Return the incident ids too, so the bell can link: rejected; that leaves the private path with more than a count.

## 4. Consequences

- Code and tests: `argus/adapters/inbound/http.py` (the permission, the route, `/me`); `deploy/ui/nginx/locations.conf`;
  `contracts/ui-api.json`, `tests/test_ui_contract.py`, `docs/API-FOR-UI.md`; the frontend bell
  (`NotificationBell.jsx`, `useWaitingApprovals.js`) and both adapters; `tests/test_acr0042_waiting_count.py`.
- Least privilege: someone holding an approver's password but not their security keys learns how many approvals wait
  in that approver's scope (0 to 50), and nothing about them. Seeing, opening and deciding stay privileged and private.
  The count adds no new way to act.
- Load: one store scan per approver every 30 s, bounded like the private list (50 results, pages of 100).
- Deployment: the agent image and the UI image on vm-095; no migration.
- Reversal: remove the route, the permission and the bell.
- Safety principle changed: least privilege, narrowly (above). Second approval requested in the PR's review.

## 5. Decision

`conantkd` chose the public count on 2026-10-28 over a bell that reads only the private list.

## 6. Applied

- [x] `ARCHITECTURE.md` updated, version bumped to 1.8.50, changelog line added with this ACR's link
- [x] journal entry
- [x] the ACR, the architecture change and the code that needs it are in the same pull request
