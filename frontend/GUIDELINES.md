# Frontend guidelines — juanes6554

My guidelines for the Argus web UI (T-0016, step 1). Plain language — the agent turns each one into tests first.

_Status: drafted by the agent from the code I already built (outside the repo, with Claude on the web) on
2026-10-06; I reviewed and approved it as part of this pull request._

## The look

- Dark theme by default, Inter font, blue accent, rounded cards — one consistent style everywhere. A **light theme**
  keeps the same layout and accent: a sun/moon button in the header switches it, the choice is remembered in the
  browser, and the app opens dark when nothing is saved. Components use the colour tokens in `src/index.css`
  (`text-ink`, `text-body`, `bg-ink/5`, `bg-scrim`…), never fixed greys or white overlays.
- Times are shown in Colombia time (**COT**, UTC-5, no daylight saving) and the Live pill says so.
- One header bar: logo top-left, menu in the middle, notifications bell and account menu top-right.
- Everything must feel calm and readable during an incident: status colors only for status (green/amber/red).

## Framework

React 18 + Vite 5 + Tailwind CSS 4, `react-router-dom` for routing, `react-markdown` + `remark-gfm` for runbook
rendering. Unit tests with Vitest; Playwright acceptance tests come next (T-0016 step 2).

## The screens

1. **Login** — username + password, show/hide password button, inline error message, "Forgot password?" link
   (decorative for now), hero image on the right side. Clicking **Log in** with a demo account enters the app;
   a wrong password shows the error without leaving the page. The demo accounts can be replaced in `.env`
   (`VITE_ARGUS_USERS`) so the login needs no database, and a mock login survives a page reload in the same tab.
2. **Dashboard** — the landing screen after login:
   - a **status summary** at the top: whether something needs attention or everything is fine, with the issues
     listed (a host at 75 % / 90 % of CPU, memory or disk, a stale or missing host sample, a broken link on the map,
     an incident escalated to a person in the last 24 h), a heartbeat per host, and counts (hosts reporting, active
     runs, links OK and components when the map answers). Nothing missing is shown as healthy;
   - **recent incidents**: empty state today; later the newest 5 with status badge, trigger and time;
   - **host metrics**: live CPU, memory and root-disk usage for Host A and Host T, with the sample time; a missing
     signal is shown as "No data" (proposed ACR-0014). WireGuard and token totals remain outside this API;
   - **escalations**: the incidents Argus could not conclude on its own and raised to a human — target (opens the
     incident), outcome, route and the recorded diagnosis, newest first;
   - **system map** (ACR-0017): the live topology of both hosts, with the same legend as the incident's Map tab; it
     hides itself while the route is absent or the flag is off;
   - **start an investigation** (ACR-0012): a target from the inventory's list, check or report, an optional reason;
     it opens the new incident. Shown only when `/me` lists `start_investigation` (an operator or approver); an
     incident page offers "Investigate again" on its target. A quota answer says when to try again;
   - **pending approvals**: empty state today; later a countdown per approval, Approve/Reject only when
     `/api/v1/me` lists the approve action (level 3 — the real buttons follow `/me`; a read token never has it).
3. **Runbooks** — searchable cards (ID, title, version, status, risk badge, detector, scope, key tools, count of
   missing tools). Filters: free-text search, detector, risk, "missing tools only". Clicking **Read full runbook**
   opens a side drawer with the rendered Markdown, Escape or a click outside closes it; relative links are shown
   as plain text (only `http(s)` links open in a new tab).
4. **Placeholders** — Agent, Approvals, Alert Simulator and Scheduler show an explicit "Coming soon" box
   instead of pretending to work. Approvals, the simulator and the scheduler remain hidden until an ACR gives
   the UI the matching actions.

### The incident page (2026-10-15 redesign)

- **One answer first.** The top of the page shows the root cause and, when the API provides it, the next step for a
  person; a **Copy summary** button copies a plain-text summary ready to paste in a ticket, and **Raw output** opens
  the incident's raw API document in a dialog.
- **Ask about this incident:** a small chat on the Incident & Diagnosis tab. Its answers (what happened, root cause,
  evidence, runbooks read, next step, who decided, how long) are built from the incident's own data: no model is
  called and nothing is sent. A question the data cannot answer says so.
- **Tabs, in this order:** **Incident & Diagnosis** (default), then **Map** and **Metrics** *only when their route
  answers*, then **Runtime Timeline**, **Evidence** and **Audit**. The tab lives in the URL (`?tab=…`) so a link
  opens the right one.
- **Why Argus concluded this:** the target → root-cause chain, confidence, who decided (rules or AI), the findings,
  the runbooks it read (each opens on the Runbooks page) and the evidence it cites (each jumps to the Evidence tab).
- **Map and Metrics are honest.** They read `GET /api/v1/topology` and `GET /api/v1/incidents/{id}/metrics`, which
  Argus now serves (ACR-0017). The UI never invents them: the real adapter asks for them only with
  `VITE_ARGUS_INSIGHTS=1` (off by default), and the tabs stay hidden until the route answers. On an incident, an
  operator or approver also asks for the overlay (`?incident_id=…`) that adds the target and root cause from the
  incident's evidence; a viewer (or a refused overlay) gets the plain map. `unknown` is a first-class state — it is
  never drawn as `ok`, and a `null` metric sample is a gap, never a zero.

## What happens on click (summary)

- Menu items are filtered by role (viewer / operator / approver); a route the role cannot see is neither shown nor
  reachable by typing its URL.
- Log out clears the session immediately. A session survives a page reload in the same tab (remembered until
  logout, closing the tab, or a TTL, default 8 h); a real session is additionally bounded by the token's own
  expiry, and a `401` forgets it.
- The incident list loads the newest rows once (up to 200) and shows them **30 at a time**: a **Show more** button
  at the end and a line giving how many are visible and the real total (`src/utils/paging.js`). The API has no
  `offset`, so the paging happens in the browser.
- The Dashboard, Incidents and Agent pages have a **Refresh** button next to the Live pill that reads again right away.
- The incident list filters by status, outcome and **host**; once a host is chosen, a **target** inside that host
  can be chosen too (both lists come from the incidents already loaded).
- The dashboard, the incident list and the Agent page refresh every 30 s and pause while the tab is hidden; a running incident
  refreshes every 2–3 s while it runs; the runbook list every 10 s (no API call). The pill by the page title says **Demo data** in mock mode and, against the real API, **Live** with the time of the last
  successful refresh (or **Reconnecting…** when a poll fails) — so it is visibly live, not decorative.

## Constraints I accept (T-0016 rules)

- The UI reads through the contract. ACR-0012 permits exactly one bounded write for authorized accounts: start an
  investigation; it cannot change a target. ACR-0014 proposes a read-only host-metrics route.
- Tests first: every new behaviour needs a test that failed before the code.
- All code stays in `frontend/`.
