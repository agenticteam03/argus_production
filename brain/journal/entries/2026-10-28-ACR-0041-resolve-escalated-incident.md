## 2026-10-28 - ACR-0041: closing an escalated incident by hand

Type: architecture change
Who: conantkd
Context: escalated incidents stayed escalated after a person fixed the problem outside Argus, and the database's forward-only rule did not allow closing them.
Decision / result:
- `POST /api/v1/incidents/{id}/resolve` with a reason; permission `resolve_incident` for operators and approvers, with a full or investigate token; only an escalated incident, once; it keeps its outcome and diagnosis and gains `resolution: {by, at, reason}`; the audit records `incident.resolved`.
- Migration 019: the forward-only function allows exactly escalated to closed with a resolution; `argus db check` proves the allowed and the refused case.
- The edge proxies the route (rate-limited like investigations); the UI contract, `docs/API-FOR-UI.md`, the incident page (Resolve with the reason, then the resolution shown) and both adapters.
- `ARCHITECTURE.md` 1.8.49 and [ACR-0041](../../architecture/changes/ACR-0041-resolve-escalated-incident.md).
Consequences: deploy order on vm-095 with the lease: backup, `ops/db-migrate.sh` (019), the agent, worker, scheduler and UI images, `argus db check`. The old image works on the new schema; the new image needs 019 before it can close one.
References: [ACR-0005](../../architecture/changes/ACR-0005-pull-alert-resolution.md), [ACR-0012](../../architecture/changes/ACR-0012-ui-start-investigation.md).

### Test state

RED seen: `tests/test_incident_resolve.py` (six tests, no route, permission or store method), and the Postgres test failing on the forward-only rule. GREEN locally: those six; all of `test_postgres.py` on Postgres 16 with migrations 001 to 019; `argus db check` statements 102/102 as the runtime role; the migration checker; the UI contract (one new route, `incident.json` with `resolution`, `me.json` with the permission, a new `incident-resolved.json`); the edge tests; vitest 340 tests including `ResolveIncident` and the adapter contract; eslint and ruff clean. The full suite is left to CI.

### Next step

Deploy in the order above, then close one of the escalated demo incidents from its page.
