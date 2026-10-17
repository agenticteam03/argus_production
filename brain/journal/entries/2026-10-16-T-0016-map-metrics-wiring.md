## 2026-10-16 — T-0016: the frontend connection to ACR-0017's map and metrics routes

Type: implementation
Who: juanes6554 (+ agent)
Context: ACR-0017's two read routes were deployed in DEPLOY-161 (agent on main `0b3b4e8`). The 2026-10-15 redesign
(#158) had drawn the Map and Metrics tabs, but the real adapter called only the plain topology, never the
`?incident_id=` overlay; the Dashboard had no map; and neither route was exercised by the contract test. The
backend author asked for the wiring plus the two calls in the contract tests.
Decision / result: `httpArgusAdapter.getTopology(incidentId)` sends `?incident_id=` and reads `VITE_ARGUS_INSIGHTS`
per call (so a test can turn it on without reloading the module); `useTopology(incidentId)` refetches on the id and,
if the overlay is refused (403 — the API allows operators and approvers only), falls back to the plain map, because
the API decides permissions, never the UI (ACR-0001). `IncidentDetail` asks for the overlay for operators and
approvers; `Dashboard` gained the live **System map** card; `SystemMap` gained a first-class **`unknown`** node and
edge state so an unknown edge is never drawn as the green **ok** (the real samples are all `unknown`), a shared
`MapLegend`, and a read-only `SystemMapCard`; the mock adapter mirrors the overlay call. Nothing is requested unless
`VITE_ARGUS_INSIGHTS=1` (off by default), and the hooks hide what they cannot draw, so an older API is unaffected.
Care points honoured: a `null` metric sample stays a gap and `fired` stays red (already in `MetricChart`); the SC-07
"no shared network" link now shows because the overlay is fetched; no IPs/URLs/secrets (server-side).
Consequences: the two Map/Metrics tabs, the "Where it broke" card and the Dashboard map are now fed by the real
routes; a real-mode click-through on vm-095 and the deploy build passing the flag remain.
References: [ACR-0017](../../architecture/changes/ACR-0017-ui-topology-and-incident-metrics.md),
`frontend/BACKEND-REQUESTS.md`, `brain/tasks/current/T-0016-frontend.md`.

### Test state

`frontend/`: `npm test` 23 files / 131 tests (the contract test now calls both routes plus the overlay; two new
adapter tests; two new map-style tests), `npx playwright test` 21/21 (5 new ACR-0017 tests: Map/Metrics tabs,
Dashboard map, operator overlay, viewer plain map, refused-overlay fallback), `npm run lint` 0 errors,
`npm run build` green. Red seen: the new contract/style/overlay assertions and the 5 new e2e tests before the
wiring.

### Next step

Open the PR (`task/T-0016-map-metrics-wiring`), have a teammate review it (ACR-0017 touched a safety principle), then
a person's real-mode login on vm-095 with `VITE_ARGUS_INSIGHTS=1`.
