# What the UI needs from the API (delivered)

Task: [`T-0016`](../brain/tasks/current/T-0016-frontend.md) — the web frontend, `frontend/`.
Rule (T-0016): the UI uses **only** the routes in [`../docs/API-FOR-UI.md`](../docs/API-FOR-UI.md). When a screen
needs data that no route provides, it is **asked for here** and the screen stays hidden until the route exists —
the UI never calls an undocumented route.

This file originally requested the two read routes the redesigned incident page (2026-10-15) draws. They are now
**delivered and merged** by [ACR-0017](../brain/architecture/changes/ACR-0017-ui-topology-and-incident-metrics.md)
(backend steps #160/#161, deployed in DEPLOY-161; the frontend connection is T-0016). Both are **read-only** GETs,
inside the UI's read-only rule (ACR-0001), and both are declared in `contracts/ui-api.json` with samples under
`contracts/samples/`. The shapes the components expect are below; they match the samples.

The UI reads either route **only when `VITE_ARGUS_INSIGHTS=1`** (see `src/services/httpArgusAdapter.js`): off by
default, so a build against an API that predates the routes never calls a missing one. When it is on, the tabs and
the cards appear **automatically** once the route answers with data (the hooks `src/hooks/useTopology.js`,
`src/hooks/useIncidentMetrics.js` return `null` on 404/empty/error and the page hides what it cannot draw).

---

## 1. `GET /api/v1/topology[?incident_id=<id>]` — the system map

Needed by: the **Map** tab, the “Where it broke” card and the **Dashboard live map**
(`src/components/SystemMap.jsx`).

Read access: a read/investigate token (any role). With `incident_id`, the overlay adds the incident's target and
root cause from its stored evidence, and is **operator/approver only** (a viewer gets `403`; the UI then falls back
to the plain map, `useTopology`).

Response body:

```json
{
  "observed_at": "2026-10-14T15:39:20Z",
  "hosts": [
    { "id": "vm-095", "label": "vm-095", "role": "monitored" },
    { "id": "vm-166", "label": "vm-166", "role": "monitored" }
  ],
  "nodes": [
    {
      "id": "vm-166/container:argus-lab-worker",
      "host": "vm-166",
      "label": "argus-lab-worker",
      "sub": "container",
      "target": "vm-166/container:argus-lab-worker",
      "kind": "container",
      "status": "restarting",
      "info": [{ "label": "Memory limit", "value": "64 MiB" }]
    }
  ],
  "edges": [
    { "from": "vm-166/container:argus-lab-worker", "to": "vm-166/host:vm-166", "state": "unknown", "label": "declared dependency" }
  ],
  "incident_id": "inc_f4b1b8c6be87"
}
```

- `hosts[].role`: `"argus"` draws the host box with one column, `"monitored"` with two (`layoutMap`).
- `nodes[].target`: the same string the incident uses (`vm-166/container:…`). The UI matches the incident's
  `target` and `root_cause_target` **against this** to colour the affected box and the root-cause box; it never
  guesses them (`stateOf`, `miniNodes` in `SystemMap.jsx`). A node without `target` is drawn normally.
- `nodes[].kind`: the inventory kind, `"container"` or `"host"` (the mock demo also uses `"argus"`).
- `nodes[].status`: may be `"unknown"` — Argus does not know. The UI draws an unknown box with its own style and
  **never as “ok”** (`stateOf`, `RECT`).
- `edges[].state`: `"ok"` | `"unknown"` | `"broken"` | `"read"` (`label` is optional). `"unknown"` is neither green
  nor red — it has its own dashed style, so it is never read as a working dependency (`EDGE`, `DASH`).
- `info` is optional; the side panel shows it as label → value rows.
- Never VM addresses, Argus's internal endpoints or secrets; container/network/port names are intentional.

## 2. `GET /api/v1/incidents/{id}/metrics?range=15m|30m|1h` — the incident's metrics window

Needed by: the **Metrics** tab and the “Around the incident” card (`src/components/MetricChart.jsx`).
`range` defaults to `30m` in the UI (`RANGES` in `MetricChart.jsx`).

Response body:

```json
{
  "from": "2026-10-06T15:30:00Z",
  "to": "2026-10-06T16:00:00Z",
  "series": [
    {
      "key": "container_memory_bytes",
      "title": "Memory",
      "unit": "%",
      "max": 1,
      "fired": true,
      "points": [
        ["2026-10-06T15:30:00Z", 0.42],
        ["2026-10-06T15:31:00Z", 0.61],
        ["2026-10-06T15:32:00Z", null]
      ]
    }
  ]
}
```

- `points`: `[time, value]` pairs; **`value: null` is a gap in the line, never a zero** (the chart draws a break).
  `time` may be an ISO-8601 string or epoch milliseconds.
- `series[].max`: the top of the y-axis (optional; defaults to the largest sample, at least 1).
- `series[].fired`: the series is drawn red (an alert fired for it).
- The UI shades the incident window on top of the series, from the incident's own `opened_at`/`closed_at`, so the
  route does not need to return it.

---

## Why not just wire them with mock data?

The demo (`VITE_ARGUS_MOCK=1`) also ships a fake topology and a fake metrics window (`demoTopology` / `demoMetrics`
in `src/services/demoIncidents.js`), so the Map and Metrics tabs can be seen offline **without any flag**. Real mode
needs the two routes above **and** `VITE_ARGUS_INSIGHTS=1`; without the flag the HTTP adapter's two methods return
`null` in real mode and the tabs stay hidden.
