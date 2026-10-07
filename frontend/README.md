# Argus web frontend (`frontend/`)

The read-only web UI for Argus — task [`T-0016`](../brain/tasks/current/T-0016-frontend.md), phase 10.
Everything here is self-contained: the core team never edits this folder, and nothing in `argus/` depends on it.

> **Status:** prototype running on **mock adapters** — not connected to the Argus API yet. The HTTP adapters,
> the contract check and the acceptance tests arrive with T-0015 (steps 1–5) and T-0016 steps 2–3.

## Quick start (Node 24+)

```powershell
cd frontend
npm ci            # install dependencies (package-lock.json is authoritative)
npm run dev       # dev server → http://localhost:5173
npm test          # unit tests (Vitest)
npm run build     # production build → dist/ (never committed; gitignored)
```

Mock logins (no real API): `admin@argus.dev`, `operator@argus.dev`, `viewer@argus.dev` — password `argus-demo`.
They live in `src/services/mockAuthAdapter.js` and are demo-only client-side data, not real credentials.

## Structure

| Path | What it is |
|---|---|
| `src/routes.js` | Single source of truth for menu + router; `roles` limits who sees/opens an item |
| `src/pages/` | Login, Dashboard, Runbooks (other routes are explicit "Coming soon" placeholders) |
| `src/components/` | Header, AgentChat, RunbookCard, RunbookDrawer, `ui.jsx` primitives |
| `src/context/AuthContext.jsx` | Session in memory only — never `localStorage`, cookies or the URL |
| `src/services/` | **Ports & adapters**: `index.js` is the single swap point (mocks today, HTTP tomorrow); `AuthPort.js` documents the shape |
| `src/hooks/` | `useLiveOverview` (5 s poll), `useRunbooks` (10 s poll) |
| `src/utils/parseRunbook.js` | Runbook Markdown → the data shown on cards |
| `src/services/demoRunbooks/` | **DEMO ONLY**: copies of RB-001/RB-002 — delete together with the mock adapter when the API serves runbooks |

## Rules that apply to this folder (T-0016)

1. **Own folder** — all frontend code here (its own `package.json`, tests, README). This task never edits `argus/`.
2. **Only the contract** — once T-0015 lands, use only routes/fields in `docs/API-FOR-UI.md`; missing data means a
   separate contract change, never an undocumented route.
3. **Buttons follow `/api/v1/me`** — an action appears only when the server lists it.
4. **Token in memory only** (never `localStorage`/cookies/URL), request `scope=read`, show API text as text (no raw
   HTML) so log lines cannot inject scripts.
5. **Tests first** — no frontend code merges without a test that failed first; the CI job `frontend` must be green.

## Known follow-ups

- **HTTP adapters + contract/Playwright tests** (T-0016 steps 2–3) once T-0015 steps 1–5 merge.
- **`react-router` 6 → 7**: `npm audit` reports 2 moderate advisories (open redirect via backslash in `<Link>` —
  not exploitable today because every `to` value is a constant from `routes.js`; and an SSR-only issue — we have
  no SSR). Upgrade as its own step with the route tests green.
- **`demoRunbooks/` removal** together with the mock runbooks adapter (noted in the adapter's header comment).
- Acceptance tests (Playwright), read-only network guard and lint join the `frontend` CI job as they land.
