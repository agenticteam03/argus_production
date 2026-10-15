# What the UI needs from the API (not there yet)

Task: [`T-0016`](../brain/tasks/current/T-0016-frontend.md) — the web frontend, `frontend/`.
Rule (T-0016): the UI uses **only** the routes in [`../docs/API-FOR-UI.md`](../docs/API-FOR-UI.md). When a screen
needs data that no route provides, it is **asked for here** and the screen stays hidden until the route exists —
the UI never calls an undocumented route.

This file lists the two read routes the redesigned incident page (2026-10-15) can show but that Argus does not
serve yet. Until they exist, the **Map** and **Metrics** tabs are simply absent; nothing breaks and nothing is
invented. Both are **read-only** GETs, so they stay inside the UI's read-only rule (ACR-0001). Adding them widens
the authenticated read surface, so — like ACR-0014 (host metrics) — each needs an **ACR**, a
`contracts/ui-api.json` update, a sample in `contracts/samples/`, and an edge allowlist entry. That is the API
side's work; this file is the frontend's request and the exact shape the components expect.

The UI reads either route **only when `VITE_ARGUS_INSIGHTS=1`** (see `src/services/httpArgusAdapter.js`): off by
default, so a normal build never calls a route that does not exist. The tabs and the two mini cards on the
incident page appear **automatically** once the route answers with data (the hooks
`src/hooks/useTopology.js`, `src/hooks/useIncidentMetrics.js` return `null` on 404/empty/error and the page hides
what it cannot draw).

---

## 1. `GET /api/v1/topology` — the system map

Needed by: the **Map** tab and the “Where it broke” card (`src/components/SystemMap.jsx`).

Read access: same as the other GETs (a read/investigate token). No query parameters.

Response body:

```json
{
  "hosts": [
    { "id": "vm-095", "label": "Host A", "role": "argus" },
    { "id": "vm-166", "label": "Host T", "role": "monitored" }
  ],
  "nodes": [
    {
      "id": "argus-v18-agent",
      "host": "vm-095",
      "label": "argus-v18-agent",
      "sub": "agent",
      "target": "vm-095/container:argus-v18-agent",
      "kind": "argus",
      "status": "running",
      "info": [{ "label": "Image", "value": "argus-v18-agent:1.8.13" }]
    },
    {
      "id": "argus-lab-worker",
      "host": "vm-166",
      "label": "argus-lab-worker",
      "sub": "container",
      "target": "vm-166/container:argus-lab-worker",
      "kind": "app",
      "status": "restarting"
    }
  ],
  "edges": [
    { "from": "argus-v18-agent", "to": "argus-lab-worker", "state": "ok", "label": "reads" }
  ]
}
```

- `hosts[].role`: `"argus"` draws the host box with one column, `"monitored"` with two (`layoutMap`).
- `nodes[].target`: the same string the incident uses (`vm-166/container:…`). The UI matches the incident's
  `target` and `root_cause_target` **against this** to colour the affected box and the root-cause box; it never
  guesses them (`stateOf`, `miniNodes` in `SystemMap.jsx`). A node without `target` is drawn normally.
- `nodes[].kind`: `"argus"` (the agent itself) or `"app"`.
- `edges[].state`: `"ok"` | `"broken"` | `"read"` (`label` is optional).
- `info` is optional; the side panel shows it as label → value rows.

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
      "key": "memory_used_ratio",
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

The demo (`VITE_ARGUS_MOCK=1`) already ships a fake topology and a fake metrics window
(`demoTopology` / `demoMetrics` in `src/services/demoIncidents.js`), so the Map and Metrics tabs can be seen
offline **without any flag**. Real mode needs the two routes above **and** `VITE_ARGUS_INSIGHTS=1`; until then the
HTTP adapter's two methods return `null` in real mode and the tabs stay hidden.
