## 2026-10-25 — T-0051 Phase 18 supervised actions against a fake gateway

| Field | Value |
|---|---|
| Type | implementation checkpoint |
| Who | conantkd + Codex |
| Context | ACR-0019 and the Phase 18 row of NEXT-PHASE; Phase 17 #316 and vm-095 guard #318 are still open |
| Decision / result | Build the offline action path on the same incident LangGraph, persist frozen proposals, independent judge verdicts, approvals, notification outbox, resume intent, action ledger, holds and outcomes; keep production write gate empty and add no approval route or real gateway. |
| Consequences | Retargeted to `main` after #316/#318 merged (main `7f8c14b` merged in). The migration is now `015_remediation.sql`: #322 takes 014 and merges first (agreed order: #314, #322, #323). It is applied by its deploy order only after review. No VM mutation was done. |
| References | [Task](../../tasks/current/PHASE-18-supervised-actions.md), [ACR-0019](../../architecture/changes/ACR-0019-human-approved-remediation.md), [Phase 17 #316](https://github.com/agenticteam03/argus_production/pull/316), [vm-095 guard #318](https://github.com/agenticteam03/argus_production/pull/318) |

- Review of #323 (`juanbetancurm`, changes requested on `2dd55ed`), addressed on 2026-10-26:
  - base and order: retargeted to `main`, `main` merged in, the diff is phase 18 only; migration renumbered to 015;
  - the executor now refuses, before any claim or dispatch, an approval without a stored `agree` verdict bound to the
    proposal's digest, a target outside the lab scope or on vm-095 (`check_action_scope`, shared with
    `freeze_proposal`), and any gateway but the fake one; `answer` fails closed without a verdict;
  - ACR-0019 §3.8 records the stricter phase 18 reading: a `doubt` or `disagree` stops the proposal before a request;
  - 13 guards without a failing test: the reviewer's `tests/test_phase18_guards.py` is in (pushed by `juanbetancurm`). Eight new tests here cover the new checks; removing each check makes its tests fail.
  - not changed yet: a database trigger requiring the verdict for an approval, the judge model id taken from the
    caller, and a verdict row on a failure before the model call (phase 19 items); the test state below now says the judge
    comparison is a harness and 18 cases, not a run.

### Test state

- RED: `tests/test_phase18_remediation.py` initially failed on the missing remediation module and SQLite methods; both were then implemented.
- GREEN: 21 focused phase-18 and graph tests passed on commit `666a990`. Ruff, Brain lint/audit, the migration checker and the judge-evaluation dry run also passed. Exact-head CI `test` and `frontend` checks passed; `main-guard` was skipped for this stacked PR.
- Full offline suite completed locally with 23 environment-bound failures: Windows resolved `bash` to WSL without `/bin/bash`, Git Bash subprocesses were denied by the sandbox, and placing pytest's temp root inside the checkout made deploy tests detect the parent repository. The exact-head CI test passed. PostgreSQL migration test was not run locally because Docker Desktop is unavailable and `ARGUS_TEST_PG_OWNER_DSN` is unset.
- Judge model comparison: only the harness (`ops/phase18_judge_eval.py`) and its 18 labelled cases exist; no run, live metric or winner is claimed (no API credential in this checkout). The task holds a provisional choice from the public catalog and prices.

### Next step

#322 is merged: `main` is merged here (an import conflict in `postgres_store.py` resolved), `015_remediation.sql` is in
`tests/skills/test_db_migration.py`'s list and the migration checker passes. Re-review, then merge; the deploy applies
015 after 014. Phase 19 still requires ACR-0018's off-host audit exit proof and a separate approval route/gateway
review; phase 20 releases the first action pair in its own PR.
