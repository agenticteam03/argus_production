# T-0045 — UI insights v2, backend: real data for the redesigned UI's charts, map and verdict

| Field | Value |
|---|---|
| Status | `in progress` — B1 merged (#173, #177); B2 to B4 in review (#174 to #176); B5 to B8 open. [ACR-0021](../../architecture/changes/ACR-0021-ui-insights-v2.md) is accepted, so B5 to B7 may start (see "Order and dependencies") |
| Phase | 10 — output modes (the UI) |
| Architecture | ACR-0021 (`accepted`, applied after B4), extending ACR-0017 |
| Branch | one branch per step: `task/T-0045-b<n>-<slug>` |
| Owner | backend lanes (`juanbetancurm`, `conantkd`) + agent; the frontend counterpart is `juanes6554`'s (T-0016) |
| Needs the VM lease | only for the deployment of each step (both leases: the agent image changes) |

## Goal

The redesigned UI (the "ui-graphs" prototype: a verdict card, ECharts charts with thresholds and an event lane, a
2D/3D system map with live health, a dashboard with fleet counts) reads real data. Each step below adds **optional**
fields or routes; the UI renders without them, so frontend and backend ship independently.

## Ground truth (checked on `main` `401e889`; do not re-derive)

| Fact | Where |
|---|---|
| The topology answer: `observed_at`, `hosts[{id,label,role: argus|monitored}]`, `nodes[{id,host,label,target,kind,sub,status,info}]`, `edges[{from,to,port,state: ok|broken|unknown|read,label}]`; 20 s shared cache; overlay with `incident_id` from stored `container.status` evidence | `argus/application/topology.py` (`Topology._build`, `_overlay`) |
| Node `status` values: `running`, `restarting`, `unhealthy`, `unknown` (+ Docker states in the overlay) | `Topology._status`, `_docker_status` |
| Edge state today uses `dependency_probe_min` = `min(argus_probe_success{owner=<name>})`; an owner with several dependencies gets `unknown` | `_build`, `config/signals.yaml` |
| **The exporter already exports per dependency:** `argus_probe_success{owner,dependency}` and `argus_probe_duration_seconds{owner,dependency}`; `dependency` is the inventory container name on the same host; the probe also knows the error (`ConnectionRefusedError`, timeout, DNS) but does not export it | `services/target/service.py` (`tcp`, the probes loop), `deploy/target/config/vm-166.json` (`probes`) |
| The metrics answer: `incident_id, range, from, to, series[{key (= the signal name), title, unit, max, fired, points}]`; ranges 15m/30m/1h are a **lead-in before `opened_at`**, the window ends at `closed_at + 2 min` or now; ≤ 130 points; 30 s / 10 min caches | `argus/application/incident_metrics.py` |
| Chart signals per class | `config/ui-incident-signals.yaml` |
| Signal templates (`$host`, `$name`, `$mounts`) | `config/signals.yaml` |
| Staleness: a sample older than `max_staleness_s` (90 s) is `None` | `adapters/outbound/config_adapters.py` |
| Host metrics: `[{host, target, available, observed_at, values{cpu_busy_ratio, memory_used_ratio, disk_used_ratio}}]`, 20 s cache | `adapters/inbound/http.py` (`host_metrics`) |
| Heartbeat state per host | `monitoring_state` table; `store.monitoring_state(host)` |
| Alert history per incident | `alert_occurrence` (004, `starts_at`, `status`) and its resolution (005) |
| `IncidentClassSpec` has no `severity` | `argus/domain/model.py` |
| Incident `confidence` is `high` / `medium` / `low` | the incident sample |
| Existing tests to extend | `tests/test_acr0017_topology.py`, `tests/test_acr0017_incident_metrics.py`, `tests/test_ui_host_metrics.py`, `tests/test_ui_contract.py`, `tests/test_ui_access.py` |

## Rules (every step)

1. **Read-only.** No write capability, no change to the write gate, no model call in any of these answers.
2. **Never** an IPv4/IPv6 address, an internal URL, a token or a secret in an answer (a leak test per answer, as in
   `test_acr0017_topology.py`). Container names, ports and Docker networks are allowed.
3. **Missing is `null`**, never `0`. **`unknown` is never `ok`/`healthy`.** Stale (older than `max_staleness_s`) is
   missing.
4. **Host isolation:** a target's data comes from its own host's Prometheus or the store; never another host's
   executor.
5. **Additive:** keep every existing field and value (`key` = signal name, `observed_at`, edge states `ok`,
   `broken`, `unknown`, `read`). New values are added, not renamed.
6. **Contract:** each step updates `contracts/ui-api.json`, `contracts/samples/*`, `docs/API-FOR-UI.md` and
   `tests/test_ui_contract.py` in the same PR.
7. **TDD:** red first for each behaviour, recorded in the PR and the journal entry.
8. **Protected paths** (self-merge rule): `config/inventory.yaml`, `deploy/migrations/`, `ops/`, `contracts/`,
   `deploy/ui/nginx/`, `brain/architecture/` need a teammate's approval.

## Steps

### B1 — Thresholds in the signal catalogue; host-metrics thresholds and heartbeat

- **`config/signals.yaml`:** a second, optional map `thresholds:`, keyed by signal name, with `{warning, critical,
  direction: above|below, unit?, scale?}`. It is validated at startup: unknown signal, `warning`/`critical` not
  numbers, or `direction` invalid stops the API. Initial values:

  | Signal | warning | critical | direction |
  |---|---|---|---|
  | `host_cpu_busy_ratio` | 0.75 | 0.90 | above |
  | `host_memory_available_ratio` | 0.25 | 0.10 | below |
  | `host_disk_used_ratio` | 0.75 | 0.90 | above |
  | `restarts_10m` | 2 | 3 | above |
  | `container_cpu_quota_used_ratio_5m` | 0.70 | 0.80 | above |
  | `container_cpu_throttled_ratio_5m` | 0.25 | 0.50 | above |
  | `db_connection_usage` | 0.75 | 0.90 | above |
  | `http_gateway_error_ratio_5m` | 0.10 | 0.50 | above |
  | `host_disk_used_ratio_5m` | 0.85 | 0.90 | above |

  `critical` equals the detector's threshold where a detector uses that signal (checked on `401e889`:
  `restarts_10m >= 3`, `db_connection_usage >= 0.9`, disk used `>= 0.9`, gateway error share `>= 0.5`, CPU throttled
  `>= 0.5` with quota used `>= 0.8`). A test asserts they agree, so a later detector change cannot drift silently.
- **`GET /api/v1/host-metrics`:** each row gains `thresholds: {cpu_busy_ratio:{warning,critical,direction},
  memory_used_ratio:{…}, disk_used_ratio:{…}}` and `heartbeat_age_s` (from `monitoring_state.updated_at`, or the
  heartbeat state) with `heartbeat_stale` (age > 2 × the heartbeat interval).
- **Tests:**
  - catalogue validation (bad entries refused);
  - detector and threshold numbers agree;
  - host-metrics rows carry thresholds and heartbeat;
  - no address in the answer.
- **Acceptance:** the UI's host gauges draw their ticks from the answer.

### B2 — Incident metrics: kind, thresholds, events, incident window, summary

- **`config/ui-incident-signals.yaml`:** each entry gains `kind` (`memory` | `restarts` | `cpu` | `latency` |
  `health` | `disk` | `database` | `network` | `other`), validated.
- **Answer additions:**
  - per series: `kind`, `thresholds` (from B1, scaled like the values), `detector_threshold`;
  - top level: `incident_from` = `opened_at`, `incident_to` = `closed_at` or null, `summary` (one template per class
    and per `fired` state, filled with numbers from the series, e.g. "Memory reached 62.7 MiB of 64 MiB before each
    restart"), `events: [{at, kind, label}]`.
- **Events:**
  - `restart` at each increase of `container_restart_count` in the window;
  - `oom_kill` at each 0→1 of `oom_killed`;
  - `alert_fired` / `alert_resolved` from the incident's `alert_occurrence` rows (and the resolution);
  - `deploy` from `deploy_event` (B6), empty until B6.
- **Tests:**
  - an OOM fixture gives `restart` and `oom_kill` events at the right times;
  - alert events come from the store;
  - thresholds scale with `scale`;
  - `incident_to` is null while open;
  - the summary has no address.
- **Acceptance:** the UI shows the alert/warning lines, the event lane and the incident band.

### B3 — Topology: health, problems, per-dependency links, roles, cause path

- **Port:** add `MetricsPort.dependency_probes(target) -> dict[str, ProbeSample]`, where `ProbeSample = (success:
  float | None, duration_s: float | None, at: datetime)`.
  - Prometheus adapter: one instant query each for `argus_probe_success{argus_host="$host",owner="$name"}` and
    `argus_probe_duration_seconds{…}`, grouped by `dependency`; stale → `None`.
  - Every fake in tests implements it (default `{}`).
- **Inventory:** optional `profile: scenario` per target (the scenario-only lab containers: burner, filler, leaker,
  nginx, slow, client, backend on vm-166, as `ops/e2e/scenarios.yaml` starts them). Validated.
- **Node additions:**
  - `health`:
    - `failed` when `status` is `exited`/`dead` or a critical problem;
    - `degraded` when `unhealthy`, `restarting` or a warning problem;
    - `idle` when `profile: scenario` and `status` is `unknown`/`exited`;
    - `unknown` when no fresh sample;
    - else `healthy`.
  - `idle`.
  - `networks`: declared networks from the inventory; the overlay replaces them with the ones seen at the incident.
  - `problems`: for each of `restarts_10m`, `health_unhealthy`, `container_memory_bytes` (against the memory limit
    when the overlay knows it), `container_cpu_quota_used_ratio_5m` with a threshold (B1) crossed on a fresh sample,
    `{kind, severity, summary, signal, value, threshold, unit}`; plus `{kind: "stale_metrics", severity: "warning"}`
    when every sample is missing on a running target.
- **Edge additions:**
  - `id` = `"<from>-><to>:<port>"`, and `kind` = `dependency` (`read` edges get `kind: argus_reads`);
  - per-dependency `state`:
    - `ok` if the dependency's probe `success == 1` and fresh;
    - `slow` if `ok` but `duration_s × 1000` > the link warning (default 100 ms, inventory override);
    - `broken` if `success == 0`;
    - `unknown` otherwise (no probe, stale);
    - the overlay's "no shared network" still overrides.
  - `checked_at` (sample time), `latency_ms`, and `reason` (`not reachable` for `broken` by probe, `no shared network`
    from the overlay; finer reasons after B8).
- **With `incident_id`:**
  - `role`: `root_cause` on `root_cause_target`, `affected` on `target` when different, `on_path` for nodes in
    between;
  - `cause_path`: the shortest path from `target` to `root_cause_target` over declared dependencies (BFS); `[target]`
    when they are equal; `[]` without a root cause.
- **Tests:**
  - an owner with two dependencies gets two independent link states (red today: both `unknown`);
  - stale → `unknown`;
  - idle classification;
  - the problem thresholds;
  - `cause_path` for SC-03 (api → cache) and SC-07 (client → backend);
  - roles;
  - the leak test;
  - no executor call (only `MetricsPort` and the store).
- **Acceptance:** the map shows box health, problem badges, checked links with latency, and the focused cause path.

### B4 — The incident verdict fields (`application/incident_view.py`)

- **`IncidentClassSpec.severity`:** `critical` for `container_restart_loop`, `dependency_unavailable`,
  `health_check_failed`, `nginx_upstream_failure`, `postgresql_connection_exhaustion`, `cpu_saturation`,
  `disk_pressure`; `warning` for `monitoring_blind_spot`.
- **Derived fields** (pure function of incident + class + evidence; no model, no host read):

  | Field | Rule |
  |---|---|
  | `severity` | the class's; `warning` for `undiagnosable` / `unsupported_escalated`; `ok` for `no_incident` |
  | `summary` | template per class + outcome, filled from findings; fallback: the first sentence of `diagnosis` |
  | `cause` | `{target: root_cause_target, kind: the class's problem kind, statement: first sentence of diagnosis, confidence: high 0.9 / medium 0.6 / low 0.3, confidence_label}`; `null` without a root cause |
  | `evidence_highlights` | up to 3 cited evidence: `{evidence_id, text: first line of model_text, stance: "supports"}` |
  | `not_checked` | each evidence with `status != ok` as "<capability> on <target> · <status>", plus each missing signal from detection |
  | `cause_path` | as in B3 |
  | `duration_ms` | `closed_at − opened_at` |
  | `next_actions` | `[]` until the runbook Actions section exists (NEXT-PHASE H1) |
  | `hypotheses` | `[]` until the decision schema carries them |

- **Tests:**
  - every field for an SC-01-like, an SC-03-like and an undiagnosable incident;
  - an old incident without a class still answers (defaults);
  - the role-redacted view stays redacted (a viewer gets no evidence text in `evidence_highlights`);
  - the leak test.
- **Acceptance:** the UI's verdict card renders from real data.

### B5 — Re-check lineage

- **Migration 007** (part 1): `ALTER TABLE incident ADD COLUMN parent_id text NULL REFERENCES incident (id)`; SQLite
  store the same.
- `POST /api/v1/investigations` accepts optional `parent_id`: it must exist and be readable by the caller, else 422.
  It is stored and returned in the incident view.
- `GET /api/v1/incidents?parent_id=` lists the re-checks.
- **Tests:** an unknown or unreadable parent is refused; lineage is returned; quotas are unchanged.

### B6 — The two new routes (ACR-0021, second approval)

- **`GET /api/v1/overview`** (`application/overview.py`):
  - `{observed_at, status, open_incidents:{critical,warning,info}, latest_open:[{id,target,host,severity,kind,summary,
    opened_at,next_action}], hosts:[host-metrics row + heartbeat], fleet:{healthy,degraded,failed,unknown,idle},
    links:{ok,total}, last_closed_at}`;
  - built only from the store, the topology snapshot (B3) and the host-metrics snapshot (B1); 15 s shared cache;
    any role.
- **`GET /api/v1/target-metrics?target=<host/kind:name>&range=15m|1h`:**
  - `{target, range, from, to, series:[{key, kind, title, unit, max, thresholds, points}]}`;
  - series `container_cpu_quota_used_ratio_5m` and `container_memory_bytes` for containers, the three host ratios for
    hosts;
  - 404 for a target not in the inventory; 422 for a bad range; 30 s shared cache; any role.
- **Edge:** `deploy/ui/nginx/locations.conf`:
  - `location = /api/v1/overview { limit_except GET { deny all; } limit_req …; include …proxy.conf; }`;
  - the same for `location = /api/v1/target-metrics` (the query string carries the target, no path regex needed);
  - extend `tests/test_acr0011_ui_edge.py`'s route list.
- **Tests:**
  - `/overview` counts match fixtures, and no executor is called;
  - `/target-metrics` 404/422, host isolation, nulls kept;
  - the edge serves both routes and still 404s unknown `/api/*`;
  - auth (401 without login, any role 200);
  - the leak test.

### B7 — Baseline, long ranges, deploy events

- **Ranges:**
  - `RANGES` gains `6h` (360) and `24h` (1440);
  - the step keeps ≤ 130 points (`ceil(minutes × 60 / 130)`, as today);
  - the answer lists `ranges_available`.
- **Baseline:** per series, `{p50, p95}` of the same signal over the 24 h ending 1 h before `opened_at`
  (`quantile_over_time` via a new `MetricsPort.quantiles(target, signal, end, minutes, [0.5, 0.95])`); `null` when the
  window has under 50 % samples; cached per (target, signal, day).
- **Deploy events:**
  - migration 007 (part 2): `deploy_event (id, host, commit, ref, actor, at)`, insert-only (runtime role: INSERT,
    SELECT);
  - `argus deploy record --host --commit --ref --as` (CLI) and one line in `ops/deploy.sh` after `DEPLOY OK`;
  - B2's events read it.
- **Tests:**
  - the step for 24h ≤ 130 points;
  - baseline `null` on sparse data;
  - deploy events appear in the window;
  - insert-only role for `deploy_event`.

### B8 — (optional) finer link reasons

- `services/target/service.py`: export `argus_probe_error{owner,dependency,kind="refused|timeout|dns|other"} 1` when
  a probe fails (from the exception type in `tcp()`).
- B3 maps it to `reason` (`connection refused`, `timeout`, `name not resolved`).
- **Deploy:** the target service is rebuilt on both hosts (leases, `nonint-check.sh`).
- **Tests:** exception type → kind; the edge reason.

## Order and dependencies

B1 → B2 → B3 → B4 can merge in any order after B1 (B2 and B3 use B1's thresholds). B5 and B6 come after ACR-0021 is
accepted (new route, migration). B7 after B6's migration. B8 is optional. Each merged step can be deployed alone (both
leases; `code.bash` with backup, `phase3_check` 55/55, WRITE GATE CLOSED, `nonint-check.sh` before and after; a
logged-in read through the edge showing the new fields and no address).

## Out of scope

- The frontend (T-0016; `juanes6554`'s plan).
- `hypotheses` (a later ACR); the runbook Actions section and `next_actions` (NEXT-PHASE H1).
- Scheduled edge checks (`topology_check`); this task uses the exporter's existing probes.
- The terminal ticket route (ACR-0020).

## Open decisions (answered at the acceptance of ACR-0021, its §5)

1. The initial thresholds in B1: **the spec's values** (B1, #173); `unit` and `scale` optional (#177).
2. The `idle` list: **the seven scenario-only containers of vm-166** (`profile: scenario`, B3).
3. The link warning latency: **100 ms**, per target `link_warning_ms` (B3). The heartbeat staleness: **150 s**, pinned
   by a test to the scheduler's schedule (#177).
4. The baseline window (24 h ending 1 h before the incident) and its cost on the lab Prometheus: **still open**,
   decided in B7.
