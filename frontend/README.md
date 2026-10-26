# Argus web frontend (`frontend/`)

The web UI for Argus — task [`T-0016`](../brain/tasks/current/T-0016-frontend.md), phase 10.
Everything here is self-contained: the core team never edits this folder, and nothing in `argus/` depends on it.

> **Status:** it runs on **mock adapters by default** (the offline demo and the unit tests need no
> server); set `VITE_ARGUS_MOCK=0` to talk to the real API through the dev proxy. A token with the investigate
> scope may start a bounded investigation (ACR-0012); host metrics use the proposed ACR-0014 read route. Approvals
> remain unavailable. The pill by each page title is honest about the source: **Demo data**
> while mock adapters are in use, **Live** (with the time of the last successful refresh) against the real API.

## Quick start (Node 24+)

```powershell
cd frontend
npm ci            # install dependencies (package-lock.json is authoritative)
npm run dev       # dev server → http://localhost:5173  (mock data)
npm run lint      # ESLint (recommended + React hooks)
npm test          # unit tests (Vitest), incl. the contract check and the real-build check
npm run build     # production build → dist/ (never committed; gitignored)
npx playwright install chromium   # once
npm run e2e       # acceptance tests (Playwright) on the real-mode build, API faked from contracts/samples
```

Mock logins (no real API): `viewer`, `operator`, `approver` — password `argus-demo`. They live in
`src/services/mockAuthAdapter.js` and are demo-only client-side data, not real credentials.

### Local Phase 19 action-card preview

From `frontend/` in PowerShell, run:

```powershell
$env:VITE_ARGUS_PHASE19_DEMO = "1"
npm.cmd run dev -- --host 127.0.0.1 --port 5189 --strictPort
```

Open `http://127.0.0.1:5189`, log in as `operator` with the demo password above, open **Incidents**, and choose the
first row (the cache dependency demo). Its diagnosis page shows one read-only Suggested actions card. The demo flag
adds only synthetic local data; it does not connect to a VM or permit an action. The **Actions** tab shows a frozen
demo proposal, independent judge, risk and Approve / Deny controls. Those controls are disabled because the mock
session cannot pass the private full-token and WebAuthn checks. Remove the environment variable to return to the
ordinary demo.

These logins need **no database**: replace them with your own in `.env.local` via `VITE_ARGUS_USERS`, a JSON map
of username → `{ password, role }` (see `.env.example`). A session also **survives a page reload** in the same tab
— mock and real alike — remembered until logout, closing the tab, or `VITE_ARGUS_SESSION_TTL_MIN` (default 8 h);
a real session is additionally bounded by the token's own expiry (see rule 4 below).

### Against the real API

The API listens on `127.0.0.1:18000` of vm-095, so open a tunnel and disable the mock switch:

```powershell
ssh -L 18000:127.0.0.1:18000 argus-vm095      # keep it open
$env:VITE_ARGUS_MOCK = "0"; npm run dev       # Vite proxies /api to 127.0.0.1:18000 (vite.config.js)
```

Instead of exporting the variable each time you can keep `VITE_ARGUS_MOCK=0` in `.env.development.local`
(gitignored). That file is **dev-only** — `npm test` and `npm run build` use other modes and stay on the mock
adapters unless you set the variable yourself.

The browser talks to the dev server, so there is no CORS and `ARGUS_UI_ORIGINS` stays empty. Log in with a real
Argus handle and the team password; the UI requests `scope=investigate`, which can read and start an investigation
only when `/me` lists the action. See
[`../docs/API-FOR-UI.md`](../docs/API-FOR-UI.md) for the only routes a UI may use.

## Structure

| Path | What it is |
|---|---|
| `src/routes.js` | Single source of truth for menu + router; `roles` limits who sees/opens an item |
| `src/pages/` | Login, Dashboard, Incidents list/detail, Runbooks (other routes are explicit "Coming soon" placeholders) |
| `src/components/` | Header, AgentChat, IncidentRow, RunTimeline, EvidenceAudit, RunbookCard, RunbookDrawer, `ui.jsx` primitives; the incident redesign adds AnswerBlock, WhyCard, CopySummary, RawOutputDialog, RunbooksRead, `Glyph.jsx` (the health hexagon); `map/` holds the system map (ELK layout, lazy-loaded: `mapModel.js` health/roles/links, `layout.js` and `router.js` the geometry, all unit-tested; `SystemMap.jsx`, `NodeDrawer.jsx`, `MiniMap.jsx`); `charts/` holds the incident metric charts (ECharts, lazy-loaded: `chartOptions.js` builds each option and is unit-tested, `MetricChart.jsx` owns one chart, `ChartGrid.jsx` the Metrics tab and the "Around the incident" card) |
| `src/context/AuthContext.jsx` | Session restored from `sessionStorage` on load — never `localStorage`, cookies or the URL |
| `src/services/index.js` | **The single swap point**: mock adapters by default, HTTP adapters with `VITE_ARGUS_MOCK=0`; also exports `dataSource` (`demo`/`api`) for the pill |
| `src/services/sessionStore.js` | The session that survives a reload (`sessionStorage`, TTL, bounded by the token's own JWT `exp`); holds the user and, in real mode, the token |
| `src/services/http*.js` | The real API adapters (`auth`/`me`, incidents, events, evidence, escalations, overview) and `session.js` (the in-memory bearer token) |
| `src/hooks/` | `useLiveOverview` (30 s poll), `useIncidentList` (30 s poll, up to 200 rows), `useIncident` + `usePoll` (paused while the tab is hidden), `useRunbooks` (10 s poll), `useTopology` and `useIncidentMetrics` (the Map/Metrics tabs and the Dashboard map; return `null` while their route is absent); the intervals are in `src/utils/polling.js` |
| `src/utils/parseRunbook.js` | Runbook Markdown → the data shown on cards |
| `src/utils/paging.js` | The incidents list pages in the browser (30 at a time) over the one `limit` fetch the API allows |
| `../../../argus/runbooks/` | The **real** runbook library (21 runbooks), read by `fileRunbooksAdapter.js`; there is no runbook API route yet |

## Rules that apply to this folder (T-0016)

1. **Own folder** — all frontend code here (its own `package.json`, tests, README). This task never edits `argus/`.
2. **Only the contract** — use only routes/fields in `docs/API-FOR-UI.md`; missing data means a separate contract
   change, never an undocumented route.
3. **Buttons follow `/api/v1/me`** — an action appears only when the server lists it.
4. **Token out of `localStorage`/cookies/URL** — never persisted anywhere a script on another origin or a share
   link could read it; request `scope=investigate`, show API text as text (no raw HTML) so log lines cannot inject
   scripts. The token lives in memory and, so a reload in the same tab keeps you logged in, in `sessionStorage`
   (`src/services/sessionStore.js`), bounded by its own JWT `exp`. A `401` forgets it and returns to login.
5. **Tests first** — no frontend code merges without a test that failed first; the CI job `frontend` must be green.

## Known follow-ups

- **The incident Map and Metrics tabs and the Dashboard map read two routes** (`GET /api/v1/topology`,
  `GET /api/v1/incidents/{id}/metrics`), delivered by ACR-0017. The UI draws them only when the route answers with
  data; the HTTP adapter calls them only with `VITE_ARGUS_INSIGHTS=1` (off by default), so nothing requests a
  missing route. On an incident, an operator/approver also asks for the `?incident_id=` overlay and falls back to
  the plain map if it is refused. The exact shapes the components expect are in
  [`BACKEND-REQUESTS.md`](BACKEND-REQUESTS.md).
- **Acceptance tests, the read-only guard and the contract check exist** (`e2e/`, `src/services/contract.test.js`).
  What they do not check yet: the response *fields* the UI reads (the routes, methods and query parameters are
  checked); the API's own contract test guards the bodies.
- **Menu from `/me` actions** instead of `routes.js` roles (ACR-0001 rule), once there is more than one action.
- **Bounded chat, not general conversation.** A host CPU/memory/disk question reads the current named metric
  through `GET /api/v1/host-metrics` (proposed ACR-0014). An explicit “Investigate Host T” starts ACR-0012's
  existing incident and links to it. Other free-text questions still need a separate design and contract. The
  Dashboard polls every 30 s; there is no SSE route.
- **Incidents: a real page cursor + total.** `GET /api/v1/incidents` takes only `limit` (the latest N) — no
  `offset` and no total — so the list fetches up to 200 rows once and pages in the browser (`src/utils/paging.js`).
  Real server-side paging and an exact total need a contract change (an `offset`/cursor plus a count).
- **Incident trigger/severity** on cards need a contract change on the API side.
- **`react-router` 6 → 7**: `npm audit` reports 2 moderate advisories (open redirect via backslash in `<Link>` —
  not exploitable today because every `to` value is a constant from `routes.js`; and an SSR-only issue — we have
  no SSR). Upgrade as its own step with the route tests green.
