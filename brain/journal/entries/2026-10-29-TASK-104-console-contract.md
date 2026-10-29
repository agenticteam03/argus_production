## 2026-10-29 - TASK-104: the console routes in the UI contract and the HTTP adapter (ACR-0043)

Type: feature (contract, frontend)
Who: conantkd (+ agent)
Context: CON-2 (#404) merged the console routes, the history table and the scenario 1 read commands, but left out the
contract entry and the real adapter's calls. Until now only the offline demo adapter answered the console, so a real build
kept the Console tab hidden.
Decision / result:
- `contracts/ui-api.json` (protected) declares `GET .../commands`, `POST .../execute` and `GET .../history` under
  `/api/v1/ops/console/incidents/{incident_id}/`. `tests/test_ui_contract.py` mounts them with `ARGUS_OPERATOR_CONSOLE=1`.
  Only `ui-api.json` was regenerated; the samples are unchanged.
- `httpArgusAdapter` gets `getConsoleCommands`, `getConsoleHistory` and `executeConsoleCommand`, called only when the build
  sets `VITE_ARGUS_CONSOLE=1` (off by default, like `VITE_ARGUS_INSIGHTS`). Without the flag, `commands` answers `null`, so
  the tab stays hidden, and no console route is ever requested. `execute` sends `confirmation` and `suggestion_id` (CON-5)
  only when the console gives them.
- `docs/API-FOR-UI.md` describes the three routes as merged: refusals are stored with a null `command`, history `output` is
  lines, a budget refusal is only audited, and writes do not run until CON-6.
Consequences: a build with `VITE_ARGUS_CONSOLE=1` against an API with `ARGUS_OPERATOR_CONSOLE=1`, on the private path, shows
the real console. Neither flag is turned on anywhere by this change. The history has no `analysis` until CON-4 is wired.

### Test state

Red seen first: the new adapter test that sends `suggestion_id` failed before the change, and the contract test failed
before `ui-api.json` was regenerated. Then `tests/test_ui_contract.py` and `tests/test_console_routes.py` passed, as did
Vitest for `src/services` (110). The full Vitest, ESLint, `vite build`, Playwright and `brain.py audit`/`lint` results are
in the PR.

### Next step

Wire CON-4's analysis into `history` (`http.py`, protected), then CON-6 (writes).
