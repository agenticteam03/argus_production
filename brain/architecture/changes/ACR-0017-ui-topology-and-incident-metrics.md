# ACR-0017 — System map and incident metrics in the UI (two read routes)

| Field | Value |
|---|---|
| Status | `accepted` (`juanes6554`, approving #159, 2026-10-15); step 1 applied (incident metrics, ARCHITECTURE 1.8.14); the topology route pending |
| Proposed by | juanbetancurm (+ agent) · 2026-10-15 |
| Accepted by | `juanes6554` · #159 (2026-10-15) |
| Second approval (safety principle only) | `juanes6554`, approving #159 (least privilege, host isolation) |
| Architecture version | 1.8.12 → 1.8.14 (incident metrics; 1.8.13 is ACR-0015's); the topology route takes the next free version |
| Task / PR | T-0016 (UI) · this PR proposes it; backend PRs by juanbetancurm; the frontend connection by juanes6554 after it is applied |

## 1. Detect and explain

The UI redesign merged in #158 (`juanes6554`) draws two things that the API cannot feed today:
- a **system map**: the Map tab, the "Where it broke" card and the Dashboard live map;
- **charts around an incident**: the Metrics tab and the "Around the incident" card.

Both are built and tested against demo data and stay **hidden** in a real build (`VITE_ARGUS_INSIGHTS` unset), so
nothing breaks today. The frontend's requests are written down in `frontend/BACKEND-REQUESTS.md`.

The data already exists inside Argus:

| Need | Source today |
|---|---|
| Hosts, containers, declared dependencies and their ports, declared networks | `config/inventory.yaml` (`depends_on`, `tcp_ports`, `networks`) through the inventory port |
| Whether each dependency answers **now** | the exporter's probe per client and dependency, `argus_probe_success{owner,dependency}`, on each host's Prometheus (the signal `dependency_probe_min` reads its minimum) |
| A container's restarts, health, OOM | `container_restart_count`, `health_unhealthy`, `oom_killed`, `last_exit_code` signals |
| A container's **actual** networks and state at the time of an incident | the incident's stored `container.status` evidence (`values.values.networks`, `state`, …) |
| Metric histories | `MetricsPort.range(target, signal, minutes, step_s)` (T-0036) and the named signals in `config/signals.yaml` |

**Example of why the map must use real networks, not only the declared ones.** In SC-07 the inventory declares the
backend on `argus-lab-app`, but the incident's evidence shows it **only on `argus-lab-iso`**. A map built from the
inventory alone would hide the fault it should explain.

## 2. Why the current architecture is insufficient

- **§7.1 (HTTP API)** lists no route for a topology or for an incident's metric window. The public-edge paragraph
  (ACR-0011, ACR-0012, ACR-0014) says the edge proxies **only** the UI contract's routes.
- **§17.1 layer 14 / ACR-0011:** every new route through the public edge widens its read surface, so it needs an ACR
  and a second approval, as ACR-0014 did for `/host-metrics`.
- **`MetricsPort.range`** returns a window that **ends now**. An incident's chart must end at the incident's
  `closed_at`, so the port needs an end time. That is a small port signature change, recorded here.

## 3. Smallest reasonable change

### 3.1 `GET /api/v1/topology[?incident_id=<id>]`

| | |
|---|---|
| Access | JWT, any role (read, investigate or full token); `incident_id` overlay: operator/approver only (it uses evidence) |
| Parameters | none, or `incident_id` matching `^inc_[A-Za-z0-9_-]+$` (else 422; unknown → 404) |
| Built from | the inventory, the latest metric snapshot per container (cached), and, with `incident_id`, that incident's stored evidence |
| Cache | the global part shared by all viewers for 20 s; the overlay per incident for 20 s while open, 10 min once closed |
| Never | VM IP addresses (private or public); Argus's internal endpoints (`url`s of executors and Alertmanager, tunnel ports); tokens or credentials; evidence content beyond the fields listed below |

**Response** (the shape of `frontend/BACKEND-REQUESTS.md` §1, kept):

```json
{
  "observed_at": "2026-10-14T15:39:20Z",
  "hosts": [{"id": "vm-095", "label": "Host A", "role": "argus"}, {"id": "vm-166", "label": "Host T", "role": "monitored"}],
  "nodes": [
    {"id": "vm-166/container:argus-lab-client", "host": "vm-166", "label": "argus-lab-client", "sub": "app container",
     "target": "vm-166/container:argus-lab-client", "kind": "container", "status": "running",
     "info": [{"label": "Networks", "value": "argus-lab-app"}, {"label": "Restarts (10 min)", "value": "0"}]}
  ],
  "edges": [
    {"from": "vm-166/container:argus-lab-client", "to": "vm-166/container:argus-lab-backend",
     "port": 8080, "state": "broken", "label": "tcp 8080 · no shared network"},
    {"from": "vm-095/host:vm-095", "to": "vm-166/host:vm-166", "state": "read", "label": "Argus reads"}
  ]
}
```

**Rules:**
- **Nodes:**
  - one per inventory target;
  - `target` equals the incident `target` / `root_cause_target` text exactly;
  - the UI marks the cause and the affected target itself;
  - Argus's own containers are not listed (only its host, with `role: "argus"`).
- **`status`** from a fixed list: `running`, `restarting`, `unhealthy`, `stopped`, `unknown`.
  - It is derived from the signals: `container_restart_count` change in 10 min → `restarting`;
    `health_unhealthy = 1` → `unhealthy`; no recent samples → `unknown`. **Unknown is never shown as ok.**
- **`info`** from an allowlist only:
  - networks;
  - declared dependency ports;
  - memory limit;
  - restarts in 10 min;
  - health;
  - last exit code;
  - OOM killed.

  **Lab dependency ports and Docker network names are shown on purpose**: they explain the incident.
- **Edges:**
  - one per declared `depends_on`, with the inventory's `tcp_ports` as `port`;
  - `state` comes from `argus_probe_success{owner,dependency}`: `ok` (1), `broken` (0), or `unknown` (no
    sample, or the owner not running: the exporter only probes active owners);
  - one `read` edge from the Argus host to each monitored host.
- **With `incident_id`** (operator/approver): for the incident's target and root cause, `status` and `Networks` come
  from the **incident's stored `container.status` evidence**, labelled "at the time of the incident". A broken edge
  whose two ends share no network gets the label "no shared network".
- **No new reads** on the hosts: inventory, cached snapshots and stored evidence only.

### 3.2 `GET /api/v1/incidents/{incident_id}/metrics?range=15m|30m|1h`

| | |
|---|---|
| Access | JWT, any role (numbers only, like `/host-metrics`) |
| Parameters | `range` ∈ {`15m`, `30m`, `1h`}, default `30m` (else 422); unknown incident → 404 |
| Window | from `opened_at − range` to `(closed_at or now) + 2 min` |
| Step | `max(30 s, ceil(window / 130))`: **at most ~130 points per series**, whatever the incident's length |
| Signals | a **fixed list per incident class**, in `config/ui-incident-signals.yaml` (validated at startup like `routing.yaml`); unknown or no class → the host's CPU and memory only. Only names from `config/signals.yaml` |
| Reads | `MetricsPort.range` on the **incident's own host** only (host isolation); no read through an executor; no PromQL from the browser |
| Cache | per (incident, range): 30 s while open, 10 min once closed |

**Response** (the shape of `frontend/BACKEND-REQUESTS.md` §2, kept):

```json
{"from": "2026-10-14T15:09:00Z", "to": "2026-10-14T15:41:19Z",
 "series": [{"key": "probe", "title": "TCP to argus-lab-backend:8080", "unit": "", "max": 1, "fired": true,
             "points": [["2026-10-14T15:09:00Z", 1], ["2026-10-14T15:37:30Z", 0], ["2026-10-14T15:38:00Z", null]]}]}
```

- **Points:** `null` means **no sample** (a gap), never 0.
- **`fired: true`:** on the signal(s) the class's detector uses (`required_signals`).
- **First list in `config/ui-incident-signals.yaml`:**

| Class | Series |
|---|---|
| `dependency_unavailable` | `dependency_probe_min` (fired), `container_restart_count`, `host_cpu_busy_ratio`, `host_memory_available_ratio` |
| `container_restart_loop` | `container_restart_count` (fired), `container_memory_bytes`, `oom_killed`, `container_cpu_cores` |
| `health_check_failed` | `health_unhealthy` (fired), `container_restart_count`, `container_memory_bytes` |
| `postgresql_connection_exhaustion` | `db_connection_usage` (fired), `db_up` |
| `disk_pressure` | `host_disk_used_ratio` (fired), `host_disk_hours_to_full` |
| `cpu_saturation` | `container_cpu_throttled_ratio` (fired), `container_cpu_cores` |
| `nginx_upstream_failure` | the gateway-error ratio (fired), `container_restart_count` |
| `monitoring_blind_spot` | `scrape_targets_down` (fired) |

*(Exact signal names to confirm against `config/signals.yaml` when implementing: several carry a window suffix, such
as `restarts_10m`, `host_disk_used_ratio_5m`, `container_cpu_throttled_ratio_5m`, `http_gateway_error_ratio_5m`. The
startup validation refuses an unknown name.)*

### 3.3 Port change

`MetricsPort.range(target, signal, minutes, step_s)` gains an optional `end: datetime | None = None` (`None` = now,
the current behaviour). The Prometheus adapter already supports an end offset (`PrometheusClient.range(...,
end_offset_s)`, T-0038). Existing callers are unchanged.

### 3.4 Text changes in `ARCHITECTURE.md` (when applied)

**§7.1, two rows after `GET /api/v1/host-metrics`:**

> `GET /api/v1/topology` | system map | JWT, any role (`incident_id` overlay: operator/approver) | Inventory targets,
> declared dependencies with their ports, live state from named signals and the dependency probe; with
> `incident_id`, the incident's stored status evidence for its target and root cause; never VM addresses, Argus's
> internal endpoints or secrets; no new host read (ACR-0017).
>
> `GET /api/v1/incidents/{id}/metrics` | an incident's metric window | JWT, any role | `range` 15m/30m/1h; a fixed
> signal list per class (`config/ui-incident-signals.yaml`); the incident's host only; ≤ ~130 points per series;
> missing is null (ACR-0017).

**Other changes:**
- **§7.1 public-edge paragraph:** add both routes to the proxied GET routes.
- **§ ports (MetricsPort):** the optional `end`.
- **Changelog:** one line for the new version.

**What is shown and what is not:**
- **Shown:** container names, Docker networks, dependency ports and status. The UI needs them to explain an
  incident.
- **Never shown:** VM IP addresses, Argus's internal endpoints, tokens and other secrets.

**Other technical options (not chosen):**
- **The browser queries Prometheus directly.** It would expose PromQL and Argus's private telemetry, and bypass the
  inventory and signal allowlist (as in ACR-0014).
- **The map makes fresh Docker reads on every page view.** It would add load on the hosts and need auditing outside
  an incident. The stored evidence (for an incident) and the probes and signals (for the global map) give the same
  picture without new reads.

## 4. Consequences

- **Code:**
  - two handlers in `argus/adapters/inbound/http.py`;
  - an application service (`argus/application/insights.py`) composing the inventory, `MetricsPort`, the incident
    store and the evidence store;
  - `config/ui-incident-signals.yaml` and its loader;
  - `MetricsPort.range(..., end=None)` and its adapters (Prometheus, the evaluation replay).
- **Contract:**
  - `contracts/ui-api.json` (two routes);
  - `contracts/samples/topology.json`, `incident-metrics.json`;
  - `tests/test_ui_contract.py`.
- **Edge:**
  - `deploy/ui/nginx/locations.conf`: `location = /api/v1/topology` and
    `location ~ ^/api/v1/incidents/[A-Za-z0-9_-]+/metrics$`, both `limit_except GET`, with the API rate limit;
  - `tests/test_acr0011_ui_edge.py` (the allowlist equals the contract).
- **Tests (first):**
  - auth on both routes;
  - the overlay is refused to a viewer;
  - parameter validation (`incident_id` pattern, `range` list);
  - **no IP, no executor URL, no token in any response** (a test scans the JSON for the inventory's `url` and
    `alertmanager` values and for IP patterns);
  - `unknown`, never ok, when a signal is missing;
  - the probe drives the edge state;
  - the SC-07 overlay shows the iso network and the "no shared network" label;
  - the step keeps ≤ 130 points for a 6-hour incident;
  - null gaps;
  - the incident's host only;
  - the caches.
- **Frontend (`juanes6554`, after this is applied and deployed):**
  - `VITE_ARGUS_INSIGHTS=1`;
  - the two calls in `contract.test.js`;
  - `.env.example`;
  - the overlay call with `incident_id` on the incident page.
- **Deployment:**
  - the agent (API) and the UI edge on vm-095 (lease), as usual;
  - smoke test: both routes 401 without a login and 200 with one; the SC-07 map shows the broken link and the
    probe going down inside the incident band.
- **Load:**
  - topology: one cached snapshot every 20 s (signals for ~10 targets);
  - metrics: at most 4–6 range queries per (incident, range) per 30 s, against the incident's host Prometheus;
  - both well under `/host-metrics`' budget per minute.
- **Risk:**
  - the UI shows container names, networks and dependency ports **on purpose**: it needs them;
  - the only thing to guard against is a VM address, an internal endpoint or a secret slipping into a response:
    covered by the response-scan test.
- **How to reverse it:**
  - remove the two Nginx locations and set `VITE_ARGUS_INSIGHTS` back to unset; the UI hides the tabs again;
  - the API routes can stay unused or be removed;
  - `MetricsPort.range`'s optional `end` is backwards compatible.
- **Safety principle:** **yes**, least privilege (a wider public read surface) and host isolation (metrics reads
  stay on the incident's host). **No write, the write gate unchanged, no new executor or token, no evidence
  content beyond the allowlisted status and network fields, audited read paths unchanged.**

## 5. Decision

Proposed by `juanbetancurm` for the team. Needs a teammate's acceptance and the second approval (least privilege,
host isolation) before the implementing PRs merge. The implementation follows in up to three PRs:
1. the port change, the metrics route, its config and tests;
2. the topology route and its tests;
3. the contract, the samples, the edge and `ARCHITECTURE.md`. These can travel with 1 and 2.

The frontend connects only after the routes are deployed.

## 6. Applied

- [x] `ARCHITECTURE.md` updated for the incident metrics route (§7.1 row, public-edge paragraph, the port, 1.8.14 and changelog line); the topology route's row follows with its PR
- [x] journal entry (step 1)
- [x] the ACR's application and the first code that needs it (the metrics route) are in the same pull request
