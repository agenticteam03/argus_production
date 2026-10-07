# Frontend guidelines — juanes6554

My guidelines for the Argus web UI (T-0016, step 1). Plain language — the agent turns each one into tests first.

_Status: drafted by the agent from the code I already built (outside the repo, with Claude on the web) on
2026-10-06; I reviewed and approved it as part of this pull request. Updated the same day in the review of this
pull request (`conantkd`) to follow ACR-0001: the UI only reads in this release._

## The look

- Dark theme, Inter font, blue accent, rounded cards — one consistent style everywhere.
- One header bar: logo top-left, menu in the middle, notifications bell and account menu top-right.
- Everything must feel calm and readable during an incident: status colors only for status (green/amber/red).

## Framework

React 18 + Vite 5 + Tailwind CSS 4, `react-router-dom` for routing, `react-markdown` + `remark-gfm` for runbook
rendering. Unit tests with Vitest; Playwright acceptance tests come next (T-0016 step 2).

## The screens

1. **Login** — username (an Argus handle, not an email) + password, show/hide password button, inline error message, "Forgot password?" link
   (decorative for now), hero image on the right side. Clicking **Log in** with a demo account enters the app;
   a wrong password shows the error without leaving the page.
2. **Dashboard** — the landing screen after login:
   - **recent incidents**: empty state today; later the newest 5 with status badge, trigger and time
     (`GET /api/v1/incidents`);
   - **read-only view**: the user's role and a short note that starting investigations and answering approvals
     are not in the web UI in this release (CLI or Swagger instead).
3. **Runbooks** — searchable cards (ID, title, version, status, risk badge, detector, scope, key tools, count of
   missing tools). Filters: free-text search, detector, risk, "missing tools only". Clicking **Read full runbook**
   opens a side drawer with the rendered Markdown, Escape or a click outside closes it; relative links are shown
   as plain text (only `http(s)` links open in a new tab).
4. **Placeholders** — Incidents shows an explicit "Coming soon" box instead of pretending to work.

## What happens on click (summary)

- Menu items follow the `actions` of `/api/v1/me` (roles: viewer / operator / approver), never the role itself; a
  route the user cannot see is neither shown nor
  reachable by typing its URL.
- Log out clears the session immediately (session lives in memory only).
- The dashboard refreshes every 5 s, the runbook list every 10 s; a "Live / Reconnecting…" pill shows whether
  data is flowing.

## Constraints I accept (T-0016 rules)

- Read-only: nothing in this UI ever mutates Argus; mocks today, contract-only HTTP tomorrow.
- **Not in the UI in this release (ACR-0001):** answering approvals, starting investigations (agent chat), the
  alert simulator and the scheduler, and data the API does not serve (WireGuard, Prometheus, LLM tokens). Each one
  needs a new ACR first; answering approvals touches a safety principle and also needs a second approval.
- Tests first: every new behaviour needs a test that failed before the code.
- All code stays in `frontend/`.
