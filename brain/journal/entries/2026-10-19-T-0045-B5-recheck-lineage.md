## 2026-10-19 — T-0045 B5: re-check lineage (`parent_id`, migration 007)

Type: implementation
Who: juanbetancurm (+ agent)
Context: the redesigned UI offers "Re-check" on an incident and shows the re-checks under it; the API had no link between
the two. Step B5 of [T-0045](../../tasks/current/T-0045-ui-insights-backend.md), which waits for ACR-0021's acceptance
(PR #180) because it adds a migration and a query parameter.
Decision / result:
- `POST /api/v1/investigations` accepts an optional `parent_id` (`^inc_[A-Za-z0-9_-]+$`, at most 64 characters). It must
  name an existing incident, else 422 and nothing is created. Every role reads every incident, so "readable by the caller"
  is "exists". The `investigation.requested` audit records it. Quotas are unchanged: a re-check is a manual incident.
- The incident keeps `parent_id`; the detail and every list row return it (`null` when it re-checks nothing).
  `GET /api/v1/incidents?parent_id=<id>` lists that incident's re-checks, newest first; a malformed id is 422.
- Postgres: `deploy/migrations/007_incident_parent.sql` adds `incident.parent_id` (foreign key to `incident.id`, indexed
  with `opened_at`) and extends the forward-only trigger: the parent never changes, like the other identity columns. No
  new grant. Two new `db-check` checks: a missing parent and a changed parent are both refused. `import_sqlite` copies
  the column when the old file has it.
- SQLite: an older file gains the column at start, like `claimed_by`.
Consequences: additive fields only. The UI ignores them until it reads them. Deploying needs `ops/db-migrate.sh` (007)
before the new image.
References: [ACR-0021](../../architecture/changes/ACR-0021-ui-insights-v2.md), `docs/API-FOR-UI.md`.

### Test state

`tests/test_t0045_b5_recheck_lineage.py` (new, red seen first) and `test_recheck_lineage_migration_007` in
`tests/test_postgres.py`, run on a local throwaway Postgres 16 with the other Postgres tests. `contracts/ui-api.json`
regenerated; `incident.json` and `incidents.json` samples gain `parent_id`. Offline suite green locally (965 passed, 24 skipped; `tests/brain` 81 passed, with one git test that
hangs on the laptop deselected; CI runs it).

### Next step

B6 (the two new routes) and B7 (baseline and deploy events), after #180 merges.
