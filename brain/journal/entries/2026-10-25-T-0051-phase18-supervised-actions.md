## 2026-10-25 — T-0051 Phase 18 supervised actions against a fake gateway

| Field | Value |
|---|---|
| Type | implementation checkpoint |
| Who | conantkd + Codex |
| Context | ACR-0019 and the Phase 18 row of NEXT-PHASE; Phase 17 #316 and vm-095 guard #318 are still open |
| Decision / result | Build the offline action path on the same incident LangGraph, persist frozen proposals, independent judge verdicts, approvals, notification outbox, resume intent, action ledger, holds and outcomes; keep production write gate empty and add no approval route or real gateway. |
| Consequences | This branch is stacked on #318 while #316/#318 are pending. Runtime migration 014 must be applied by its deploy order only after review. No VM mutation was done. |
| References | [Task](../../tasks/current/PHASE-18-supervised-actions.md), [ACR-0019](../../architecture/changes/ACR-0019-human-approved-remediation.md), [Phase 17 #316](https://github.com/agenticteam03/argus_production/pull/316), [vm-095 guard #318](https://github.com/agenticteam03/argus_production/pull/318) |

### Test state

- RED: `tests/test_phase18_remediation.py` initially failed on the missing remediation module and SQLite methods; both were then implemented.
- GREEN: 21 focused phase-18 tests passed after the current failure-injection and guard updates. Ruff, Brain lint/audit, the migration checker and the judge-evaluation dry run passed on this checkpoint. The earlier full offline suite passed 1,996 tests with 74 skipped before the latest guard additions; it is being rerun against this checkpoint.
- PostgreSQL migration test: pending because Docker Desktop is unavailable locally and `ARGUS_TEST_PG_OWNER_DSN` is unset. Exact-head CI: pending; the GitHub API was unreachable at the latest check, so current PR checks could not be observed.
- Paid OpenAI model comparison: pending; this checkout has no OpenAI API credential. Official catalog/pricing comparison and a provisional model choice are recorded in the task.

### Next step

Finish the full offline suite and exact-head CI, resolve review comments, then merge #316 and #318 before retargeting this PR to `main`. Phase 19 still requires ACR-0018's off-host audit exit proof and a separate approval route/gateway review; phase 20 releases the first action pair in its own PR.
