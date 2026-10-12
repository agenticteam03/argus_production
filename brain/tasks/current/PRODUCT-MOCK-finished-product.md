# PRODUCT-MOCK — finished-product simulation

| Field | Value |
| --- | --- |
| Status | verified locally; draft review pending |
| Owner | juanbetancurm + Codex |
| Branch | `task/PRODUCT-MOCK-finished-product` |
| VM lease | not required: offline code and browser simulation only |
| Requested outcome | realistic interactive preview of Argus's final intended architecture and behavior |
| Scope | `prototype/`, this task file, its journal entry |

## Decision and implementation

Use a portable standalone HTML artifact instead of changing the real read-only React client. The prototype
requires no installation or API, embeds the actual 21-runbook library, and demonstrates a future supervised
profile alongside the current closed write gate. It is explicitly a browser-local simulation. Architecture,
production policy, API contracts, deployed services, and the existing frontend are unchanged.

The experience includes host and container inventory, deterministic alerts, incident correlation, manual requests,
bounded investigation, diagnosis, redacted hash-identified evidence, read console and refusals, policies, holds,
mock authentication and scoped principals, credential metadata, immutable proposals, human approval/denial/expiry,
precheck invalidation, action ledger, failed/indeterminate results, fresh recovery verification, external resolution,
incident history, source runbooks, and JSON evidence export. Thirteen failure scenarios cover SC-01–SC-12 and RB-002.

## Red seen

`node --test prototype/tests/simulation.test.cjs` failed before implementation. The first behavior assertion was
`expected incident.status = awaiting_approval, actual undefined`; the skeletal engine produced no approval pause.
No import error was used as the red baseline. The implemented engine then passed all original 11 behavior groups.
An additional SHA-256 / nested immutability check is now included.

## Verification

- Simulation tests: 13 passed, including human-only authority, scope and expiry, zero unauthorized writes,
  closed gates and holds, precheck invalidation, host-aware correlation, evidence-only escalation,
  denial/expiry, failed and indeterminate actions, external resolution, console refusal, SHA-256 integrity,
  nested proposal immutability, and mismatched-digest refusal.
- Final browser pass: 17 checks passed in installed headless Chrome. This includes scoped visibility,
  session expiry, evidence that stays expanded across live refresh, a downloaded JSON evidence bundle,
  desktop and mobile layout, and zero runtime exceptions / external network requests.
- Offline Python suite: first collection failed because the existing local virtual environment lacked the
  declared `croniter>=6,<7` dependency. After installing it, the full suite completed with 15 failures/errors,
  all caused by the also-missing declared `mcp>=2.3,<2.4` dependency. Installed that dependency locally;
  all three affected MCP/process-isolation test files then passed: 20 passed, 2 expected skips.
- `brain.py audit`, `brain.py lint`, JavaScript syntax validation, and `git diff --check`: passed.
- No VM access, lease acquisition, live API call, external notification, or deployment.

## Review notes

The product preview is not an ACR or a release of write authority. All responses are deterministic fixtures.
Draft source runbooks retain their real status. Incident and credential state is ephemeral and resets on reload.
The user's existing edits in `brain/execution/current/code.bash` were present at session start and are outside this task.
