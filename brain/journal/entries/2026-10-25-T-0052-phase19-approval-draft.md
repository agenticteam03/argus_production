## 2026-10-25 — T-0052 Phase 19 approval draft

| Field | Value |
|---|---|
| Type | implementation checkpoint |
| Who | conantkd + Codex |
| Context | Phase 18 PR #323 remains in review; Phase 16 deployment is assumed for planning at the user's direction |
| Decision / result | Start a draft PR for the private approval contract. Keep routes opt-in and the production write gate closed. |
| Consequences | The draft is explicitly not ready for review, approval, merge or deployment. |
| References | [Task](../../tasks/current/PHASE-19-approval-ui-gateway.md), [ACR-0019](../../architecture/changes/ACR-0019-human-approved-remediation.md), [proposed ACR-0031 draft PR #325](https://github.com/agenticteam03/argus_production/pull/325) |

### Test state

- RED: the new answer-route test returned 404 before its implementation.
- GREEN: focused approval tests and existing authentication/write-gate tests passed locally. Full suite and
  exact-head CI remain to be recorded after the draft push.
- The first PR head `ab7091d` passed exact-head `test` and `frontend` CI. This continuation added holds and the
  closed gateway core. RED was observed for the missing hold route, missing gateway behavior, and absent cross-scope
  approval check; focused tests are green. The six Phase 16 allowlist-script failures on Windows are environmental:
  `bash.exe` enters WSL without `/bin/bash`. Ruff passed. Exact-head `test` and `frontend` CI passed on `d117994`;
  PostgreSQL ran as part of Linux CI. The later gateway listener/image scaffold needs its own final-head CI.
- A further RED showed that a global hold placed after the approval request still allowed an answer. The answer
  now refuses it before consuming step-up. The gateway's loopback HTTP contract also went red on its missing
  handler and green with exact-path authentication and journal-status tests against a fake proxy.
- The ACR-0019 journal contract exposed a single-row status update. RED showed no append-only event table; GREEN
  now records separate `received` and terminal events, with triggers refusing update/delete.
- The socket proxy's empty ACL and HTTP handler went RED then GREEN. A further RED showed raw Docker inspect fields
  crossing the proxy; it now returns only `Id`. The Unix transport rechecks identity immediately before POST.
  Closed image configuration refuses startup and no compose mounts an action token. Docker Desktop is unavailable
  locally, so image-level and PostgreSQL tests await Linux CI or a throwaway Docker host.

### Next step

Resolve proposed ACR-0031 before a private full-token browser login. Complete the Actions UI and test the gateway
and proxy real images. Verify Phase 16 deployment and stacked dependencies before
requesting any review or approval. Do not open a real action route in this PR.
