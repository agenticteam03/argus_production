# ACR-0025 — A live dependency graph: link states recorded over time, used by the charts and the investigation

Area B of the next-phase plan ("dependency graph with live connectivity checks"). The NEXT-PHASE proposal (#170) left
it as a separate track; this ACR is that track. **Reads and records only.**

| Field | Value |
|---|---|
| Status | `proposed` |
| Proposed by | juanbetancurm (+ agent) · 2026-10-20 |
| Accepted by | pending |
| Second approval (safety principle only) | not required (no safety principle touched: see §4) |
| Architecture version | the next free version when applied |
| Task / PR | [T-0046](../../tasks/current/T-0046-live-dependency-graph.md) · PR (this one) |

## 1. Detect and explain

What exists (ACR-0017, ACR-0021 B3 and B8): every target host's exporter probes each declared dependency on every
scrape (`argus_probe_success{owner,dependency}`, `argus_probe_duration_seconds`, and since B8 `argus_probe_error` with
`refused` / `timeout` / `dns`), and `GET /api/v1/topology` reads the latest sample per link when asked
(`MetricsPort.dependency_probes`, shared 20 s) and shows `ok` / `slow` / `broken` / `unknown` with B8's reason
(`connection refused`, `timeout`, `name not resolved`). So the map is "live" only while someone is looking, and only as a snapshot.

What is missing:
- **No history.** When the cache link broke, and whether it broke before or after the API's errors began, is not
  stored anywhere Argus can read later. Prometheus keeps 7 days, but nothing turns the samples into transitions.
- **The investigation does not see link states** unless the model happens to call `network.tcp_connect` on the right
  port; the probe the exporter already runs every scrape is invisible to it.
- **The incident charts** show restarts, OOM kills, alerts and deploys (ACR-0021 B2, B7), but not "link to
  argus-lab-cache broken".
- **The inventory does not say which port a dependency uses or whether it is required**: the probe uses the
  dependency's only `tcp_ports` entry, and every link counts the same.

## 2. Why the current architecture is insufficient

- §7.1 `GET /api/v1/topology`: link state from "the dependency probe" at read time; no `since`, no `required`.
- §7.3: the scheduler reads alerts and the monitoring heartbeat; nothing reads link states.
- §16.1 stores no link state.
- §12.2 offers no read of link states to a class.
- §5.8: `depends_on` is a list of target refs only.

## 3. Smallest reasonable change

### 3.1 Recording transitions (§7.3, the reconcile tick)

On each reconcile tick (`every_s`, 60 s), the scheduler reads `MetricsPort.dependency_probes(owner)` for every owner
with a declared **container** dependency, **on the owner's own host's Prometheus** (the read the topology already does;
for vm-166 through the tunnel), and derives each link's state with the topology's rules (`ok`, `slow` above
`link_warning_ms`, `broken`, `unknown` when the sample is stale or missing). It stores a row **only when a link's state
changes** (and once at startup), so the table grows with events, not with time. Audited `link.changed` (system
principal). Configuration: `reconcile_firing_alerts.link_states.enabled` (off until deployed).

- **This is a new read for the scheduler**, which today reads only Alertmanager (§7.3): it gets the `MetricsPort`.
- **When a host's Prometheus cannot be read** (`MetricsUnavailable`, the tunnel down), the tick is **skipped for that
  host**: nothing is recorded, so an outage does not write a burst of `unknown` transitions and then a burst of
  recoveries. A sample that is read but stale is `unknown` (Argus reached Prometheus, and Prometheus has no fresh
  probe).
- **A host-kind dependency** (`argus-lab-filler` → `vm-166/host:vm-166`: a filesystem, not a port) is never probed and
  never recorded; it stays `not_checked`, as on the map today.

### 3.2 Storage (§16.1 row 2; a new migration, `<next free number>_link_event.sql`)

`link_event` (`id`, `owner`, `dependency`, `state`, `latency_ms`, `reason` (B8's), `at`): insert-only for the runtime role
(SELECT, INSERT), like `deploy_event` (migration 008); `db-check` proves it. Retention: with the incident data
(months); transitions are few.

### 3.3 The topology answer (§7.1; no new route)

Per link, additive: `since` (the time of the last transition, from `link_event`) and `required`. A broken **required**
link is a `problem` on its owner (`dependency_broken`, critical). A link whose owner is idle (`profile: scenario` and not
running) stays as today. The UI keeps polling (20 s, matching the shared snapshot); see alternative B.

### 3.4 The incident charts (§7.1 `GET /api/v1/incidents/{id}/metrics`)

`events` gain `link_broken` / `link_recovered` (and `link_slow`) for the links of the incident's target and of its
declared dependencies inside the window, from `link_event`. Label: "Link argus-lab-api → argus-lab-cache broken".

### 3.5 The investigation (§12.2, a new Level 2 row)

| Tool | Capability | Executor | Notes |
|---|---|---|---|
| `read_link_states` | `network.link_states` | `argus_internal` | the current state and the transitions of the last `minutes` (≤ 240) of the links of the incident's target and its declared dependencies, from `link_event` and the latest probe sample; tag `link_states`, which no class has yet; `max_per_incident` 2 |

Level 2, not Level 1: a Level 1 read reaches every class without a tag (§10.4 step 3; `graph_runner.py`:
`s.tags & cls.tool_tags or s.level == 1`), so it could not be measured before it is offered. With its own tag it is
offered by adding `link_states` to the tool tags of `dependency_unavailable`, `health_check_failed` and
`nginx_upstream_failure` after an evaluation batch (SC-03, SC-07, SC-08 cases). That changes the class registry
(`argus/detectors/classes.py`), so it needs a teammate's review (OP-014 step 8). A stored observation like any other
read (§5.4).

### 3.6 The inventory (§5.8, `config/inventory.yaml`)

A `depends_on` entry may be a mapping: `{ref, port, required}`. A plain ref stays valid (port: the dependency's only
`tcp_ports` entry; `required: true`). The loader refuses a port the dependency does not list, a `port` on a host-kind
ref (a host dependency has no port and is never probed, §3.1), and a dependency on another host (cross-host links stay
`not_checked`, host isolation).

### 3.7 Not in this ACR

Undeclared connections seen on the hosts ("observed but not declared": needs per-container socket reads,
`host.socket_summary` is offered to no class); cross-host links; a push channel to the browser.

**Alternatives considered:**
- A — keep reading only at request time: the map stays a snapshot; no "since", no charts, no evidence.
- B — a server-sent-events route that pushes link changes to the browser: a new long-lived public route, an edge
  change and an authorization review, for a gain the 20 s poll already gives at this scale. Revisit with phase 16
  (ACR-0018 sessions).
- C — a scheduled `CheckDependencies` task calling `network.tcp_connect` per link through `InvokeCapability` (the plan's
  first idea): duplicates the probe the exporter already runs every scrape, adds executor load on vm-166 and a system
  principal for target reads. Reading the existing probe samples adds no target traffic.
- D — store every sample: Prometheus already keeps them for 7 days; only transitions are worth keeping longer.

## 4. Consequences

- **Code:** `infrastructure/scheduler.py` (the tick step; the scheduler gets the `MetricsPort`, a new read for it), `application/links.py` (new: the
  state rules shared with `topology.py`), `application/topology.py` (`since`, `required`, the problem),
  `application/incident_metrics.py` (link events), the stores (the new migration), `capabilities/catalog.py`
  (`network.link_states`), `adapters/outbound/config_adapters.py` (the `depends_on` mapping).
- **Tests:** transitions only (no row when nothing changes); a stale or missing sample → `unknown`, never `ok`; an
  unreadable Prometheus skips that host's tick (no row); a host dependency is never probed; per-host reads only
  (the existing host-isolation pattern); insert-only table; `since` and the required-link problem; link events in the
  window; the inventory loader refusals; evaluation SC-03 shows `argus-lab-api → argus-lab-cache` broken before the API's
  errors, SC-07 shows the client's link broken, healthy runs show `ok`.
- **Contract:** `contracts/ui-api.json`, the topology and incident-metrics samples (additive fields and event kinds).
- **Deployment:** the new migration before the new image (vm-095); the scheduler restarted with `link_states.enabled: true`.
  Nothing on vm-166 (the exporter already probes).
- **Risk:** one Prometheus query per owner and tick (today: four owners with a container dependency, all on vm-166,
  through the tunnel), bounded by the tick and the existing timeouts. When the tunnel is down, vm-166's tick is skipped
  (no false `unknown` transitions); the alert and heartbeat reconciliation of the same tick are unaffected.
- **Reverse:** `link_states.enabled: false`; the fields are additive; the table stays (forward-only migrations).
- **Safety principle:** **no.** Read-only (Prometheus reads already done by the topology), no write, no new executor,
  host isolation kept (each host's own Prometheus; no cross-host link), no secrets, and `link_event` is not evidence
  (the read in §3.5 stores its result as a normal observation).

## 5. Decision

Pending.

## 6. Applied

- [ ] `ARCHITECTURE.md` updated (§5.8, §7.1, §7.3, §12.2, §16.1), version bumped, changelog line added
- [ ] journal entry
- [ ] the ACR, the architecture change and the first code that needs it are in the same pull request
