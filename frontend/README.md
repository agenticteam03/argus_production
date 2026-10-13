# Argus web frontend (`frontend/`)

The read-only web UI for Argus — task [`T-0016`](../brain/tasks/current/T-0016-frontend.md), phase 10.
Everything here is self-contained: the core team never edits this folder, and nothing in `argus/` depends on it.

> **Status:** read-only. It runs on **mock adapters by default** (the offline demo and the unit tests need no
> server); set `VITE_ARGUS_MOCK=0` to talk to the real API through the dev proxy. It only reads (ACR-0001):
> approvals, the agent chat that starts investigations and the health data stay placeholders until a new ACR
> gives the UI the matching actions (`/me`). The pill by each page title is honest about the source: **Demo data**
> while mock adapters are in use, **Live** (with the time of the last successful refresh) against the real API.

## Quick start (Node 24+)

```powershell
cd frontend
npm ci            # install dependencies (package-lock.json is authoritative)
npm run dev       # dev server → http://localhost:5173  (mock data)
npm test          # unit tests (Vitest)
npm run build     # production build → dist/ (never committed; gitignored)
```

Mock logins (no real API): `viewer`, `operator`, `approver` — password `argus-demo`. They live in
`src/services/mockAuthAdapter.js` and are demo-only client-side data, not real credentials.

These logins need **no database**: replace them with your own in `.env.local` via `VITE_ARGUS_USERS`, a JSON map
of username → `{ password, role }` (see `.env.example`). A session also **survives a page reload** in the same tab
— mock and real alike — remembered until logout, closing the tab, or `VITE_ARGUS_SESSION_TTL_MIN` (default 8 h);
a real session is additionally bounded by the token's own expiry (see rule 4 below).

### Against the real API (read-only)

The API listens on `127.0.0.1:18000` of vm-095, so open a tunnel and disable the mock switch:

```powershell
ssh -L 18000:127.0.0.1:18000 argus-vm095      # keep it open
$env:VITE_ARGUS_MOCK = "0"; npm run dev       # Vite proxies /api to 127.0.0.1:18000 (vite.config.js)
```

Instead of exporting the variable each time you can keep `VITE_ARGUS_MOCK=0` in `.env.development.local`
(gitignored). That file is **dev-only** — `npm test` and `npm run build` use other modes and stay on the mock
adapters unless you set the variable yourself.

The browser talks to the dev server, so there is no CORS and `ARGUS_UI_ORIGINS` stays empty. Log in with a real
Argus handle and the team password; the token has `scope=read` and cannot write. See
[`../docs/API-FOR-UI.md`](../docs/API-FOR-UI.md) for the only routes a UI may use.

## Structure

| Path | What it is |
|---|---|
| `src/routes.js` | Single source of truth for menu + router; `roles` limits who sees/opens an item |
| `src/pages/` | Login, Dashboard, Incidents list/detail, Runbooks (other routes are explicit "Coming soon" placeholders) |
| `src/components/` | Header, AgentChat, IncidentRow, RunTimeline, EvidenceAudit, RunbookCard, RunbookDrawer, `ui.jsx` primitives |
| `src/context/AuthContext.jsx` | Session restored from `sessionStorage` on load — never `localStorage`, cookies or the URL |
| `src/services/index.js` | **The single swap point**: mock adapters by default, HTTP adapters with `VITE_ARGUS_MOCK=0`; also exports `dataSource` (`demo`/`api`) for the pill |
| `src/services/sessionStore.js` | The session that survives a reload (`sessionStorage`, TTL, bounded by the token's own JWT `exp`); holds the user and, in real mode, the token |
| `src/services/http*.js` | The real API adapters (`auth`/`me`, incidents, events, evidence, escalations, overview) and `session.js` (the in-memory bearer token) |
| `src/hooks/` | `useLiveOverview` (5 s poll), `useIncidentList` (5 s poll, up to 1000 rows), `useIncident` + `usePoll`, `useRunbooks` (10 s poll) |
| `src/utils/parseRunbook.js` | Runbook Markdown → the data shown on cards |
| `src/utils/paging.js` | The incidents list pages in the browser (30 at a time) over the one `limit` fetch the API allows |
| `../../../argus/runbooks/` | The **real** runbook library (21 runbooks), read by `fileRunbooksAdapter.js`; there is no runbook API route yet |

## Rules that apply to this folder (T-0016)

1. **Own folder** — all frontend code here (its own `package.json`, tests, README). This task never edits `argus/`.
2. **Only the contract** — use only routes/fields in `docs/API-FOR-UI.md`; missing data means a separate contract
   change, never an undocumented route.
3. **Buttons follow `/api/v1/me`** — an action appears only when the server lists it.
4. **Token out of `localStorage`/cookies/URL** — never persisted anywhere a script on another origin or a share
   link could read it; request `scope=read`, show API text as text (no raw HTML) so log lines cannot inject
   scripts. The token lives in memory and, so a reload in the same tab keeps you logged in, in `sessionStorage`
   (`src/services/sessionStore.js`), bounded by its own JWT `exp`. A `401` forgets it and returns to login.
5. **Tests first** — no frontend code merges without a test that failed first; the CI job `frontend` must be green.

## Known follow-ups

- **Acceptance (Playwright) + contract check**: the API client is checked against `contracts/ui-api.json`, and the
  read-only network guard fails any non-`GET` request (T-0016 steps 2–3, still to add).
- **Menu from `/me` actions** instead of `routes.js` roles (ACR-0001 rule), once there is more than one action.
- **Real agent chat and health need the API, not just permission.** A `scope=read` token is refused by design
  (ACR-0001), and `POST /api/v1/investigations` is not in the contract *and* only **starts** an investigation for
  a target — no route answers a free-text question. The health card's four fields have no route either (the only
  ops route, `/healthz`, is not in the contract and returns different data). Both need a new route + contract,
  samples and guard, plus an ACR. The **Live** pill is short polling (5 s); there is no SSE route, so it is fresh,
  not pushed.
- **Incidents: a real page cursor + total.** `GET /api/v1/incidents` takes only `limit` (the latest N) — no
  `offset` and no total — so the list fetches up to 1000 rows once and pages in the browser (`src/utils/paging.js`).
  Real server-side paging and an exact total need a contract change (an `offset`/cursor plus a count).
- **Incident trigger/severity** on cards need a contract change on the API side.
- **`react-router` 6 → 7**: `npm audit` reports 2 moderate advisories (open redirect via backslash in `<Link>` —
  not exploitable today because every `to` value is a constant from `routes.js`; and an SSR-only issue — we have
  no SSR). Upgrade as its own step with the route tests green.
