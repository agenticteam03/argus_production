# Frontend guidelines — juanes6554

My guidelines for the Argus web UI (T-0016, step 1). Plain language — the agent turns each one into tests first.

_Status: drafted by the agent from the code I already built (outside the repo, with Claude on the web) on
2026-10-06; I reviewed and approved it as part of this pull request._

## The look

- Dark theme, Inter font, blue accent, rounded cards — one consistent style everywhere.
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
   - the **agent chat**: type a question, press Send, watch the status line while it "works", the answer appears
     as a message (placeholder reply until the API exists);
   - **recent incidents**: empty state today; later the newest 5 with status badge, trigger and time;
   - **agent status**: WireGuard / Prometheus / LLM tokens / resolved-today rows with a data-or-"No data" dot;
   - **escalations**: the incidents Argus could not conclude on its own and raised to a human — target (opens the
     incident), outcome, route and the recorded diagnosis, newest first;
   - **pending approvals**: empty state today; later a countdown per approval, Approve/Reject only when
     `/api/v1/me` lists the approve action (level 3 — the real buttons follow `/me`; a read token never has it).
3. **Runbooks** — searchable cards (ID, title, version, status, risk badge, detector, scope, key tools, count of
   missing tools). Filters: free-text search, detector, risk, "missing tools only". Clicking **Read full runbook**
   opens a side drawer with the rendered Markdown, Escape or a click outside closes it; relative links are shown
   as plain text (only `http(s)` links open in a new tab).
4. **Placeholders** — Agent, Approvals, Alert Simulator and Scheduler show an explicit "Coming soon" box
   instead of pretending to work. Approvals, the simulator and the scheduler are writes, so the read-only UI
   hides them until a new ACR gives the UI the matching actions.

## What happens on click (summary)

- Menu items are filtered by role (viewer / operator / approver); a route the role cannot see is neither shown nor
  reachable by typing its URL.
- Log out clears the session immediately. A session survives a page reload in the same tab (remembered until
  logout, closing the tab, or a TTL, default 8 h); a real session is additionally bounded by the token's own
  expiry, and a `401` forgets it.
- The incident list loads the newest rows once (up to 200) and shows them **30 at a time**: a **Show more** button
  at the end and a line giving how many are visible and the real total (`src/utils/paging.js`). The API has no
  `offset`, so the paging happens in the browser.
- The dashboard and the incident list refresh every 30 s and pause while the tab is hidden; a running incident
  refreshes every 2–3 s while it runs; the runbook list every 10 s (no API call). The pill by the page title says **Demo data** in mock mode and, against the real API, **Live** with the time of the last
  successful refresh (or **Reconnecting…** when a poll fails) — so it is visibly live, not decorative.

## Constraints I accept (T-0016 rules)

- Read-only: nothing in this UI ever mutates Argus; mocks today, contract-only HTTP tomorrow.
- Tests first: every new behaviour needs a test that failed before the code.
- All code stays in `frontend/`.
