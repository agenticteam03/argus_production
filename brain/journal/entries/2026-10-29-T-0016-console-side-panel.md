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
Consequences: on the VM the console needs a deploy of `main` with `ARGUS_OPERATOR_CONSOLE=1` and the private path;
from `localhost` (the SSH tunnel bypasses the edge) the private login answers 404, so the real path is the deployed UI.
The team's Console tab on the incident page stays as it is. Open PRs #407 and #408 change the console components the
panel reuses; their props stay compatible.
References: [ACR-0043](../../architecture/changes/ACR-0043-operator-console.md),
[ACR-0032](../../architecture/changes/ACR-0032-private-browser-login.md), [T-0016](../../tasks/current/T-0016-frontend.md).

### Test state

Backend: `tests/test_console_sessions.py` (red seen, then green) with the console route tests; the UI contract
regenerated (only `ui-api.json`). Frontend: Vitest 393 passed (the dock rules, the adapters' session calls and the
mock's private login and key seen red first); Playwright 37 passed over two builds, among them 5 side-panel tests
with axe (written after the code); ESLint 0 errors. Browser: mock in dark and light at 1280 px and at 390 px, the
whole flow and a command; the real `localhost` shows case 3 for juanes6554 (two keys, ordinary session).

### Next step

juanes6554 reviews; then a pull request (a reviewer other than the author: routes and `contracts/`). Deploy `main` with
the console flag on vm-095 (lease, `code.bash`) to use the panel on the deployed UI.
