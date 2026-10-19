# ACR-0021 — UI insights v2: live health, per-dependency links, chart context, the verdict, an overview

Extends [ACR-0017](ACR-0017-ui-topology-and-incident-metrics.md) for the redesigned UI (the "ui-graphs" prototype:
verdict card, ECharts charts with thresholds and events, a 2D/3D system map with live health). Implementation:
[T-0045](../../tasks/current/T-0045-ui-insights-backend.md). ACR-0018 to ACR-0020 are proposed in #170; this is the
next free number.

| Field | Value |
|---|---|
| Status | `accepted` (not yet applied to `ARCHITECTURE.md`: see §6) |
| Proposed by | juanbetancurm (+ agent) · 2026-10-18 |
| Accepted by | `conantkd` and `juanes6554`, by their approvals of the acceptance pull request (`task/ACR-0021-accepted`), which merges only with both · 2026-10-19 |
| Second approval (safety principle only) | **required**: least privilege (two new routes on the public edge); given by the second of the two approvals above |
| Architecture version | the next free version when applied |
| Task / PR | T-0045 · #172 (proposed) · `task/ACR-0021-accepted` (accepted) |

## 1. Detect and explain

The redesigned UI draws, for each box of the map, its health and problems (value against threshold); for each link,
whether it was checked and how fast it answered; for each chart, the alert and warning lines, the normal range, the
incident window and the events (OOM kill, restart, deploy, alert fired/resolved); on the incident page a verdict
(summary, severity, likely cause, confidence, top evidence, what could not be checked, next steps); on the dashboard a
status banner, fleet counts and host heartbeats; in the node drawer short CPU/memory sparklines.

The API serves none of these fields. The UI can compute some of them (badly: it would need the thresholds and the
dependency map), and others need data only the server has (thresholds, probe results per dependency, alert
occurrences, deploy times, heartbeat age).

Found while reviewing the code (they change how this is built):
- the target exporter **already** exports `argus_probe_success` and `argus_probe_duration_seconds` with labels
  `owner` and `dependency` (`services/target/service.py`), but the topology reads only the minimum per owner
  (`dependency_probe_min`), so an owner with two dependencies shows both links `unknown`;
- `series.key` in the metrics answer is the signal name, and the topology's top-level time is `observed_at`: both are
  kept (no rename).

## 2. Why the current architecture is insufficient

§7.1 rows (as of 1.8.16):
- `GET /api/v1/topology`: "live state from `restarts_10m`, `health_unhealthy` and the dependency probe
  (`dependency_probe_min`)" — no health, no problems, one probe value per owner.
- `GET /api/v1/incidents/{id}/metrics`: "`range` 15m/30m/1h … a fixed signal list per class" — no thresholds,
  baseline, events or incident window.
- `GET /api/v1/host-metrics`: "fixed CPU busy, memory used and root-disk used ratios" — no thresholds, no heartbeat.
- There is no aggregate dashboard route and no per-target metric route; §17.1 layer 14 limits the public edge to the
  UI contract's routes, so adding routes needs an ACR.

## 3. Smallest reasonable change

**§7.1, `GET /api/v1/topology`** — after "…`dependency_probe_min`)": "; per node a `health` (`healthy` | `degraded`
| `failed` | `unknown` | `idle`), `idle` (inventory `profile: scenario` and not running), `networks` (declared, or seen
at the incident), `problems` (signal, value, threshold, severity) and, with `incident_id`, a `role` (`root_cause` |
`affected` | `on_path`) and a `cause_path`; per link an `id`, a `kind` (`dependency` | `argus_reads`), the state from
**that dependency's** probe (`argus_probe_success{owner,dependency}`; `slow` above the link's warning latency), its
`checked_at`, `latency_ms` and `reason`. The existing states (`ok`, `broken`, `unknown`, `read`) keep their meaning."

**§7.1, `GET /api/v1/incidents/{id}/metrics`** — "`range` 15m/30m/1h" → "`range` 15m/30m/1h/6h/24h (lead-in before
the incident)"; add: "per series a `kind` (`memory` | `restarts` | `cpu` | `latency` | …), `thresholds`
(`warning`, `critical`, `direction` from `config/signals.yaml`), `detector_threshold` and a `baseline` (p50/p95 over a
healthy window before the incident, or null); top level `incident_from`, `incident_to`, `events` (`oom_kill`,
`restart`, `deploy`, `alert_fired`, `alert_resolved`, from counters, alert occurrences and deploy records) and a
template `summary`."

**§7.1, `GET /api/v1/host-metrics`** — add "per value its `thresholds`; per host `heartbeat_age_s` and
`heartbeat_stale` (the monitoring heartbeat, ACR-0009)".

**§7.1, `GET /api/v1/incidents/{id}`** — "role-redacted view" → "role-redacted view, plus the verdict fields
(`summary`, `severity`, `cause`, `evidence_highlights`, `not_checked`, `cause_path`, `duration_ms`, `parent_id`;
`next_actions` once the runbook Actions section exists), derived deterministically from the stored incident, its
class and its evidence (never a model call)".

**§7.1, `POST /api/v1/investigations`** — add "optional `parent_id`: the incident this one re-checks (readable by the
caller)".

**§7.1, two new rows:**

| Route | Use case | Auth | Notes |
|---|---|---|---|
| `GET /api/v1/overview` | the dashboard aggregate | JWT, any role | worst open severity, open counts by severity, the latest open incidents with their first next step, per host the CPU/memory/disk ratios with thresholds and heartbeat age, fleet health counts, checked links OK/total; built from the store and the existing topology and host-metrics snapshots; **no new host read**; shared 15 s |
| `GET /api/v1/target-metrics?target=&range=` | a box's recent signals | JWT, any role | an inventory target only (else 404); CPU and memory (container) or CPU, memory, disk (host); `range` 15m/1h; that target's host only; missing is null; shared 30 s |

**§5.8:** `IncidentClassSpec` gains `severity` (`critical` | `warning`) used by the verdict.

**§8.1 (`MetricsPort`):** one method, `dependency_probes(target) -> {dependency: (success, duration_s, sample_time)}`,
for the per-link state (the Prometheus adapter reads `argus_probe_success` and `argus_probe_duration_seconds` by
`owner`; the fakes return fixtures).

**§16:** migration 007: `incident.parent_id` (nullable) and an insert-only `deploy_event` (host, commit, ref, actor,
at) written by `ops/deploy.sh` through a new CLI verb `argus deploy record`.

**Alternatives considered:**
- A: **compute in the browser** from today's answers: the UI would need thresholds, the inventory graph and alert
  history it cannot get; the frontend would re-implement detection logic.
- B: **one big `/ui-state` route:** couples every screen to one cache and one failure; separate answers keep their own
  caches and graceful degradation.
- C: **put per-target metrics in the topology answer:** makes the 20 s map answer heavy for one drawer.

## 4. Consequences

- **Code:** `application/topology.py`, `application/incident_metrics.py`, a new `application/incident_view.py` and
  `application/overview.py`, the Prometheus adapter and fakes, `adapters/inbound/http.py`, the stores, migration 007,
  `argus deploy record`, `ops/deploy.sh`, `config/signals.yaml` (thresholds), `config/ui-incident-signals.yaml`
  (`kind`), `config/inventory.yaml` (`profile`), `detectors/classes.py` (`severity`).
- **Contract:** `contracts/ui-api.json`, samples, `docs/API-FOR-UI.md`, the frontend contract test.
- **Edge:** `deploy/ui/nginx/locations.conf` gains `/api/v1/overview` and `/api/v1/target-metrics` (GET, rate-limited).
- **Risk:** more data on public routes (still no address, internal URL or secret: a leak test on every answer); more
  Prometheus queries (bounded by the shared caches; `/overview` reads only snapshots).
- **How to reverse it:** the new fields are optional (old clients ignore them); remove the two routes from
  `locations.conf` to close them.
- **Safety principles:** least privilege (two public routes) → second approval. Read-only, write gate, host isolation,
  evidence integrity, secrets unchanged.

## 5. Decision

Proposed in #172. **Accepted** with the two approvals of the acceptance pull request: one teammate's, plus a second
one for least privilege (the two public routes). The implementation steps, contracts and tests are in T-0045.

Answers to T-0045's open decisions, from the steps already built and reviewed:
1. **Thresholds:** the spec's initial values, shipped in B1 (#173). `unit` and `scale` are optional (#177).
2. **`idle`:** the seven scenario-only containers of vm-166 (`profile: scenario`, B3, #175).
3. **Link warning:** 100 ms by default, `link_warning_ms` per target (B3). **Heartbeat staleness:** 150 s, pinned by a
   test to the scheduler's schedule (#177).
4. **Baseline window:** still open; it is decided in B7.

**Before acceptance**, B1 to B4 were built under T-0045's "Order and dependencies" (additive fields, no new route, no
migration): B1 in #173 and #177 (merged), B2 to B4 in #174 to #176. B5 to B7 start once this record is accepted.

## 6. Applied

The text of `ARCHITECTURE.md` is applied in **one** pull request, once B4 has merged. That pull request covers what
is then built (§5.8 `severity`, §8.1 `dependency_probes`, the §7.1 fields of the topology, incident metrics,
host-metrics and incident routes) and bumps the version. B6 adds the two new routes' rows and `locations.conf`, and
B5/B7 the §16 migration. Until then, the difference is recorded in `SUMMARY.md` ("Known differences").

- [ ] `ARCHITECTURE.md` updated (§5.8, §7.1, §8.1, §16, changelog), version bumped
- [ ] `contracts/ui-api.json`, samples, `docs/API-FOR-UI.md`, `locations.conf`
- [ ] journal entry
- [ ] the ACR, the architecture change and the first code that needs it are in the same pull request
