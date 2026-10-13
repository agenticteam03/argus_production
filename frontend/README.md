# Argus web frontend (`frontend/`)

The read-only web UI for Argus — task [`T-0016`](../brain/tasks/current/T-0016-frontend.md), phase 10.
Everything here is self-contained: the core team never edits this folder, and nothing in `argus/` depends on it.

> **Status:** read-only. It runs on **mock adapters by default** (the offline demo and the unit tests need no
> server); set `VITE_ARGUS_MOCK=0` to talk to the real API through the dev proxy. It only reads (ACR-0001):
> approvals, the agent chat that starts investigations and the health data stay placeholders until a new ACR
> gives the UI the matching actions (`/me`).

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

### Against the real API (read-only)

The API listens on `127.0.0.1:18000` of vm-095, so open a tunnel and disable the mock switch:

```powershell
ssh -L 18000:127.0.0.1:18000 argus-vm095      # keep it open
$env:VITE_ARGUS_MOCK = "0"; npm run dev       # Vite proxies /api to 127.0.0.1:18000 (vite.config.js)
```

The browser talks to the dev server, so there is no CORS and `ARGUS_UI_ORIGINS` stays empty. Log in with a real
Argus handle and the team password; the token has `scope=read` and cannot write. See
[`../docs/API-FOR-UI.md`](../docs/API-FOR-UI.md) for the only routes a UI may use.

## Structure

| Path | What it is |
|---|---|
| `src/routes.js` | Single source of truth for menu + router; `roles` limits who sees/opens an item |
| `src/pages/` | Login, Dashboard, Incidents list/detail, Runbooks (other routes are explicit "Coming soon" placeholders) |
| `src/components/` | Header, AgentChat, IncidentRow, RunTimeline, EvidenceAudit, RunbookCard, RunbookDrawer, `ui.jsx` primitives |
| `src/context/AuthContext.jsx` | Session in memory only — never `localStorage`, cookies or the URL |
| `src/services/index.js` | **The single swap point**: mock adapters by default, HTTP adapters with `VITE_ARGUS_MOCK=0` |
| `src/services/http*.js` | The real API adapters (`auth`/`me`, incidents, events, evidence, escalations, overview) and `session.js` (the in-memory bearer token) |
| `src/hooks/` | `useLiveOverview` (5 s poll), `useIncidentList`, `useIncident` + `usePoll`, `useRunbooks` (10 s poll) |
| `src/utils/parseRunbook.js` | Runbook Markdown → the data shown on cards |
| `../../../argus/runbooks/` | The **real** runbook library (21 runbooks), read by `fileRunbooksAdapter.js`; there is no runbook API route yet |

## Rules that apply to this folder (T-0016)

1. **Own folder** — all frontend code here (its own `package.json`, tests, README). This task never edits `argus/`.
2. **Only the contract** — use only routes/fields in `docs/API-FOR-UI.md`; missing data means a separate contract
   change, never an undocumented route.
3. **Buttons follow `/api/v1/me`** — an action appears only when the server lists it.
4. **Token in memory only** (never `localStorage`/cookies/URL), request `scope=read`, show API text as text (no raw
   HTML) so log lines cannot inject scripts. A `401` forgets the token and returns to login.
5. **Tests first** — no frontend code merges without a test that failed first; the CI job `frontend` must be green.

## Known follow-ups

- **Acceptance (Playwright) + contract check**: the API client is checked against `contracts/ui-api.json`, and the
  read-only network guard fails any non-`GET` request (T-0016 steps 2–3, still to add).
- **Menu from `/me` actions** instead of `routes.js` roles (ACR-0001 rule), once there is more than one action.
- **Write features need an ACR**: agent chat that starts an investigation, approvals, simulator, scheduler, health.
- **Incident trigger/severity** on cards need a contract change on the API side.
- **`react-router` 6 → 7**: `npm audit` reports 2 moderate advisories (open redirect via backslash in `<Link>` —
  not exploitable today because every `to` value is a constant from `routes.js`; and an SSR-only issue — we have
  no SSR). Upgrade as its own step with the route tests green.
