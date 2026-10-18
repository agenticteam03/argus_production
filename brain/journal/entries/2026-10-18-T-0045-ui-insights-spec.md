## 2026-10-18 — T-0045 proposed: the backend for the redesigned UI's charts, map and verdict (ACR-0021)

Type: decision (proposed)
Who: juanbetancurm (+ agent)
Context: the redesigned UI prototype ("ui-graphs": verdict card, ECharts charts with thresholds and events, 2D/3D map
with live health, dashboard fleet view) needs fields the API does not serve. A review of the code against the draft
plan found: the target exporter already exports `argus_probe_success` and `argus_probe_duration_seconds` per
`owner` and `dependency`, but the topology reads only the per-owner minimum (an owner with two dependencies shows both
links `unknown`); `series.key` is the signal name and the topology's time field is `observed_at`, so the plan adds
fields (`kind`) instead of renaming.
Decision / result: proposed [ACR-0021](../../architecture/changes/ACR-0021-ui-insights-v2.md) (new fields on the
ACR-0017 routes, two new routes `GET /api/v1/overview` and `GET /api/v1/target-metrics`, one `MetricsPort` method,
migration 007) and [T-0045](../../tasks/current/T-0045-ui-insights-backend.md), the step-by-step specification
(B1–B8) with the ground truth, contracts, rules and tests an agent implements from.
Consequences: no code changes in this PR. B1–B4 need no new route; B5–B7 need the ACR accepted (migration, routes).
References: [ACR-0021](../../architecture/changes/ACR-0021-ui-insights-v2.md),
[T-0045](../../tasks/current/T-0045-ui-insights-backend.md), ACR-0017.

### Test state

No code change (specification only).

### Next step

Team review of ACR-0021 (second approval: two public routes) and the open decisions in T-0045; then B1.
