## 2026-10-29 — T-0016: the operator console in a side panel, its access record and alert

Type: frontend + backend (not merged, not deployed)
Who: juanes6554 (+ agent)
Context: the team built the operator console (ACR-0043: restricted commands over Argus's own tools, scoped to an
incident, on the private path with the ACR-0032 private session), as a tab of the incident page. The UI owner wanted it
reachable from Tools and from each incident, in a right-hand panel with several sessions, a 30-minute limit, the
four security-key cases, a record of who used it and an alert on refused use. The earlier simulated-shell branch
(never pushed) was dropped: this builds on the team's console without changing its components.
Decision / result:
- **Side panel** (`frontend/src/components/console/dock/`): the team's `ConsoleTerminal` and `ConsolePanel`, unchanged,
  in a right panel that widens by dragging (or the arrow keys), minimizes to a bar, goes full screen and back to its
  width, ends with Disconnect (no close button) and counts down 30 minutes. One tab per incident (the routes are
  scoped to one); "+" offers vm-095 and vm-166, then the host's incidents. Tools -> Console and "Open console on
  <host>" on an incident, for an approver (the highest role in the real `/me`, 2026-10-29), only when the build has
  the team's console flag (`VITE_ARGUS_CONSOLE=1`) or is the demo.
- **The four cases** from `/me.second_factor` and the session's access: no key (ask the administrator), one key
  (register the second), two keys on an ordinary session or an unconfirmed private one (the team's private sign-in,
  then the key), confirmed (a required reason, then enter).
- **Access record:** `POST /api/v1/ops/console/incidents/{id}/sessions {reason}` and `.../sessions/{sid}/close {why}`
  audit `console.session_opened` / `console.session_closed` as rows of the incident (its Audit tab); a record, not a
  gate. A refused console request of a signed-in principal is `security.console_refused`, added to the security
  alerts, so it reaches the team's Telegram route.
- **Demo parity:** the mock walks the four cases (a viewer has no key; an approver's private login and key are
  simulated, in memory only, and `approve_action` then appears, so Actions opens too); the mock dev server runs with
  `VITE_ARGUS_PHASE19_DEMO=1`.
- **Review round (same day, juanes6554):** the menu's roles always apply (a viewer saw Actions in the demo: the
  preview flag let any role see it); the dashboard's Pending approvals card is gone (approvals live on Actions); with
  the incident details open, Raw output and Copy summary fold into "More"; the incident's Console tab is gone (the
  console opens in the side panel only); the incident map scrolls freely (a fresh `[]` default re-ran the layout on
  every render and each layout scrolled back to the root cause); the header follows its container (below 52rem Agent
  and Actions move into Tools) and the panel stops where the page keeps 600 px; each of two or more tabs closes with
  its x; the "+" menu closes outside; the dialog's private sign-in is a compact form; the demo answers like the real
  `/me` (actions per role) and has a Security keys page with demo keys.
- **Deploy check (same day):** on vm-095 the console could never have appeared: the agent's container did not pass
  `ARGUS_OPERATOR_CONSOLE` (routes 404) and the UI image was built without `VITE_ARGUS_CONSOLE`. Both now take the one
  variable `ARGUS_OPERATOR_CONSOLE` (off by default). `tests/test_console_deploy_flow.py` walks the deployed path on the
  real API: `/me`'s key count and confirmation, the ordinary session refused and alerted, the private session confirmed
  with a key opening the console (`help`, a read, `ls -la` refused) and the record in the incident's audit. The
  security alerts are enabled (`schedules.yaml`), so `security.console_refused` reaches Telegram once deployed.
- **The record, readable:** console rows (opened with the reason, each command and its result, refusals, the end) read
  as plain lines in the incident's Audit tab, which reads the incident again on opening; the demo keeps the same rows.
- **The bell (ACR-0042):** its badge counts only unread approvals (kept in the browser); opening one or Actions marks it
  read, "Mark all as read" clears them.
- **Telegram, checked:** `security.console_refused` is posted to the Argus Alertmanager with `argus_security="true"`,
  whose route is the team's Telegram receiver (test in `test_phase16_security_alerts.py`). The scheduler sends them
  and runs the agent's image: after rebuilding it on deploy, recreate the scheduler too, or it keeps the old event list.
- **Actions and Reference sources:** UI only, easier to read (two columns on Actions; three steps explaining the
  reference sources; source rows; decision panels). Deleting one security key was left out: there is no per-key
  revocation route (only `argus webauthn reset`, all keys, by another administrator); it needs an API change, a
  step-up and its audit, so it is a task of its own.
Consequences: on the VM the console needs a deploy of this branch with `ARGUS_OPERATOR_CONSOLE=1` in `hosts.env` (the
agent and the UI build both read it), the agent, the scheduler and the UI rebuilt or recreated, and the private path on;
from `localhost` (the SSH tunnel bypasses the edge) the private login answers 404, so the real path is the deployed UI.
The team's Console tab on the incident page stays as it is. Open PRs #407 and #408 change the console components the
panel reuses; their props stay compatible.
References: [ACR-0043](../../architecture/changes/ACR-0043-operator-console.md),
[ACR-0032](../../architecture/changes/ACR-0032-private-browser-login.md), [T-0016](../../tasks/current/T-0016-frontend.md).

### Test state

Backend: `tests/test_console_sessions.py` (red seen, then green) with the console route tests; the UI contract
regenerated (only `ui-api.json`). Frontend: Vitest 406 passed (the dock rules, the adapters' session calls and the
mock's private login and key seen red first); Playwright 38 passed over two builds, among them 6 side-panel tests
with axe (written after the code); ESLint 0 errors. Browser: mock in dark and light at 1280 px and at 390 px, the
whole flow and a command; the real `localhost` shows case 3 for juanes6554 (two keys, ordinary session).

### Next step

juanes6554 reviews; then a pull request (a reviewer other than the author: routes and `contracts/`). Deploy `main` with
the console flag on vm-095 (lease, `code.bash`) to use the panel on the deployed UI.
