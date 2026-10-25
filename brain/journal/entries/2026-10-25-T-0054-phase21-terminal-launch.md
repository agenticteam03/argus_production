# 2026-10-25 — T-0054 Phase 21 terminal launch draft

| Field | Value |
|---|---|
| Type | implementation checkpoint |
| Who | conantkd + Codex |
| Context | ACR-0020 and the merged offline broker core establish the 21A contract; the privileged route is not built |
| Decision / result | Add an offline launch authorization policy ahead of ticket issuance; record the isolated-origin ticket gap in ACR-0033 draft PR #327. |
| Consequences | No principal gains `open_terminal:<host>` and no API route, WebSocket, SSH or recording deployment is added. |
| References | [Task](../../tasks/current/PHASE-21-operator-terminal.md), [ACR-0020](../../architecture/changes/ACR-0020-operator-terminal.md), [proposed ACR-0033 draft PR #327](https://github.com/agenticteam03/argus_production/pull/327) |

### Test state

- RED: the new launch-policy suite failed collection because `argus.application.terminal_launch` was absent. A
  later test showed an empty step-up token could reach the consumer and produced a second RED.
- GREEN: 26 focused launch-policy and existing broker-core tests passed. Ruff passed on the new Python files.
- Brain lint/audit passed locally. Final-head CI remains pending after the branch checkpoint.

### Next step

Implement durable ticket issuance and consumption only after validating the prerequisite access proof and deciding
ACR-0033. Add private ticket/list/kill routes, exact permission matrix and public 404 tests, then the browser and
broker deployment stages. Do not enable a terminal grant before the complete exit drill and safety review.
