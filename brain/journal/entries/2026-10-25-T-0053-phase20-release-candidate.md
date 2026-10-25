# 2026-10-25 — T-0053 first lab action candidate

| Field | Value |
|---|---|
| Type | release preparation checkpoint |
| Who | conantkd + Codex |
| Context | ACR-0031 acceptance and complete Phase 19 deployment are planning assumptions at the user's direction |
| Decision / result | Freeze one candidate gateway pair for `container.start` on the SC-03 cache and add a narrow worker client; keep the production write gate closed. |
| Consequences | No action is released, no VM state is claimed, and the draft must not be reviewed or approved yet. |
| References | [Task](../../tasks/current/PHASE-20-first-lab-action.md), [ACR-0019](../../architecture/changes/ACR-0019-human-approved-remediation.md), [Phase 19 draft #324](https://github.com/agenticteam03/argus_production/pull/324), [ACR-0031 draft #325](https://github.com/agenticteam03/argus_production/pull/325) |

### Test state

- RED: two candidate contract tests failed with `FileNotFoundError` before the manifest existed.
- GREEN: both candidate contract tests passed after adding the exact pair. The related gateway and standing-gate
  selection passed: 31 tests on the existing project virtual environment. Final-head CI remains pending.
- RED: worker-client tests failed to import the missing `gateway_client` module. GREEN: the client sends only a
  frozen released pair; a loopback listener and journal confirm one POST and status reconciliation by ID.
- Ruff is not installed in the global Python. The existing project virtual environment ran Ruff on the new Python
  files successfully.

### Next step

Confirm the prerequisite architecture and deployment evidence. Implement the release wiring and full gates named
in the task, then prepare a lease-bound VM release and rollback. Request two reviews only after the final release
candidate is complete and verified. Do not deploy or merge this checkpoint.
