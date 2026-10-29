## 2026-10-29 - CON-3: the operator console UI (ACR-0043)

Type: feature (frontend)
Who: conantkd (+ agent)
Context: the operator console board ([OPERATOR-CONSOLE](../../tasks/current/OPERATOR-CONSOLE.md)) asks for the split-view UI
after CON-1 (#401) and a mockup spec first. CON-2 (routes, history table, contract) is not built yet.
Decision / result:
- [`argus-console-mockup-spec.md`](../../tasks/current/argus-console-mockup-spec.md): the layout, the terminal and panel
  behaviour, and in §5 the route and response shapes the UI reads, proposed for CON-2 under the private prefix scoped to the
  incident (`/api/v1/ops/console/incidents/{id}/commands|execute|history`).
- `frontend/`: a **Console** tab on the incident page with the terminal (prompt, ↑/↓ history, `clear`, the `confirm>` prompt
  for writes, input disabled while a command runs) and the Argus panel (the incident's own diagnosis, the command activity
  with Argus's analysis when the API sends one). The terminal logic is `utils/consoleSession.js`; `hooks/useConsole.js`
  reads the history every 3 s while the tab is open.
- A typed `yes` only confirms the intent; the demo answers with "proposal created ... waiting for an approver" and never
  approves. Output is text only: control characters are shown as a replacement character.
- Only the offline demo adapter has the console calls (`services/demoConsole.js`, the catalog mirrors
  `argus/console/registry.py`). The HTTP adapter gets them in CON-2 with `contracts/ui-api.json` (protected), so a real build
  hides the tab and calls no console route (`e2e/console.e2e.js`).

Consequences: CON-2 should answer the shapes of mockup spec §5, or change the spec and the UI with it. CON-4 fills the
`analysis` field the panel already shows; CON-5 adds the suggestion cards.

### Test state

Red seen first: the three new Vitest files failed on the missing modules, the two new adapter tests failed on the missing
calls, and the demo's `--since` test failed before its fix. Then: Vitest 62 files / 372 tests passed (coverage above the
floors), ESLint no errors, `vite build` passed, all 32 Playwright tests passed (one, `action-suggestions`, failed once in a parallel run and passed alone and on the rerun: flaky, not touched here). Checked by hand in demo mode with Playwright
at 1280x720 and 375 px: no horizontal scroll; the console is 516 px tall at 1280x720; a viewer gets no Console tab.

### Next step

CON-2 (routes, history table, contract entry and the HTTP adapter's console calls) and CON-4 (post-command analysis).
