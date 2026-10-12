## 2026-10-11 — PRODUCT-MOCK: finished-product simulation

- Request: create a practical interactive mock of final Argus behavior from repository architecture and knowledge.
- Branch: `task/PRODUCT-MOCK-finished-product`. Code-only work; no VM lease is needed or claimed.
- Added a portable offline prototype in `prototype/index.html`, backed by a testable deterministic simulation engine.
  It shows two hosts, monitored containers, 13 failure scenarios, investigation, diagnosis, source runbooks,
  evidence, scoped mock identities, token metadata, policies and holds, human approvals, precheck, one-action ledger,
  recovery verification, external restoration, history, and JSON export.
- The supervised path releases only the simulated cache-restart pair. Real Argus remains read-only; no architecture,
  API, policy, deployed service, or production frontend was changed.
- Preserved pre-existing user changes to `execution/current/code.bash`.

### Test state

- Red seen: approval-pause assertion failed against the skeletal engine before implementation.
- Simulation: 13 tests passed, including nested immutability and mismatched-digest refusal.
- Browser: 17 final checks passed, including scoped visibility, expired sessions, live evidence expansion,
  downloaded JSON export, desktop/mobile layouts, and no browser exceptions or external network requests.
- Offline Python suite: local `croniter` dependency was missing at collection; installed the already-declared
  dependency into `.venv`. The full run then completed with 15 missing-MCP failures/errors. Installed the
  already-declared `mcp>=2.3,<2.4` dependency; all three affected test files passed (20 passed, 2 expected skips).
- Brain audit and lint, JavaScript syntax checks, and whitespace validation passed.

### Next step

Open `prototype/index.html` and review the guided cache incident or inject another failure. The prototype is a local
product-design artifact; promotion of any write capability or changes to the real frontend/API require their own
architecture and implementation work under the existing release rules.
