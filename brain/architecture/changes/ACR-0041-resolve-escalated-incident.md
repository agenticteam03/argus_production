# ACR-0041 — Closing an escalated incident by hand

| Field | Value |
|---|---|
| Status | `accepted` |
| Proposed by | `conantkd` · 2026-10-28 |
| Accepted by | `conantkd` · 2026-10-28 |
| Second approval (safety principle only) | not required |
| Architecture version | proposed: `1.8.48` → `1.8.49` |
| Task / PR | demo of 2026-10-28 · PR to be numbered on opening |

## 1. Problem

An escalated incident stays escalated forever. When a person fixes the problem outside Argus (restarts a container by hand, resets a scenario), the incident keeps showing as needing attention on the dashboard, the agent page and the map drawer, and nothing records what fixed it. The forward-only rule (migrations 001 and 007) treats `escalated` as final, so not even the database allows closing it.

## 2. Why the current architecture is insufficient

Only alert resolution closes incidents (§7, ACR-0005), and only a queued one; a concluded (escalated) one is not changed. There is no way for the accountable person to say "this is fixed, here is how".

## 3. Smallest reasonable change

- `POST /api/v1/incidents/{id}/resolve` with `{"reason"}` (1-500 characters, not blank, nothing else). Permission `resolve_incident`, granted to `operator` and `approver` (never `viewer`); a human principal; a full or `investigate` token, like starting an investigation (ACR-0012), because it acts on nothing. `/me` lists `resolve_incident` when it applies.
- Only an `escalated` incident, once: 409 otherwise, 404 for an unknown id. It becomes `closed`, keeps its `outcome` and `diagnosis`, and gains `resolution: {by, at, reason}` (a new optional field of the incident, `null` elsewhere). The audit records `incident.resolved` on the incident with the reason and the outcome.
- Migration 019 replaces the forward-only function: `escalated` may become `closed` only when the new body carries a `resolution` object and the old one did not; every other change of a final status, and any identity change, is still refused. `argus db check` proves both (an escalated row closes with a resolution; another without one is refused).
- The edge proxies exactly `POST /api/v1/incidents/{id}/resolve` with the investigation's rate limit and a 4 KB body. The UI contract and `docs/API-FOR-UI.md` list the route; the incident page shows Resolve (with the reason) on an escalated incident when `/me` lists the action, and the resolution once it is closed.

**Alternatives considered:**

- Close automatically when the alert resolves: deferred; it needs the "stable for N minutes" rule and is a separate change.
- A separate insert-only `incident_resolution` table, leaving the incident escalated: rejected; every list and count reads the incident's status.

## 4. Consequences

- Code and tests: `argus/domain/model.py`, `argus/ports/ports.py`, both stores, `argus/adapters/inbound/http.py`; `deploy/migrations/019_incident_resolution.sql`; `deploy/ui/nginx/locations.conf`; `contracts/` and `docs/API-FOR-UI.md`; `ResolveIncident.jsx`, the incident page, both adapters; their tests.
- Deployment on vm-095 with the lease: backup, `ops/db-migrate.sh` (019), the agent, worker, scheduler and UI images, `argus db check`. The old image works on the new schema; the new image needs 019 to close an escalated incident.
- Risk: an operator could hide an open problem. The reason is mandatory, the person and time are recorded on the incident and in the audit chain, and a new alert opens a new incident.
- Reversal: a migration restoring 007's function, and removing the route and permission.
- Safety principle changed: no; nothing on a target is touched.

## 5. Decision

`conantkd` chose it on 2026-10-28 among the proposed ways to close escalated incidents: a person closes one by hand, with a reason.

## 6. Applied

- [x] `ARCHITECTURE.md` updated, version bumped to 1.8.49, changelog line added with this ACR's link
- [x] journal entry
- [x] the ACR, the architecture change and the code that needs it are in the same pull request
