## 2026-10-28 - ACR-0039: a judge's doubt reaches the approver

Type: architecture change
Who: conantkd
Context: every judge verdict of the S1 and S4 rehearsals on 2026-10-28 was `doubt` (cause supported, action addresses the cause, but risk understated), and a `doubt` stopped the proposal before any person saw it, so no action ever reached the Actions screen.
Decision / result:
- `approvable_verdict` (`agree` or `doubt`, the exact digest, never forbidden) replaces the agree-only check in the approval request, its answer, the private answer route and the executor; a `disagree`, another digest, a forbidden colour or no verdict still stops the proposal.
- A `doubt` raises the colour one level; a red one keeps the typed target.
- Migration 018 changes migration 016's trigger function the same way; SQLite renames its triggers and drops an older file's agree-only ones; `argus db check` inserts an approval after a doubt (must succeed) and refuses one after a disagreement.
- The approval notice says the judge doubted it; the pending list and the approval card show it with the raised colour; the graph audits `judge.doubt_sent_to_approver`; the answer's audit records `judge_verdict` and `risk`.
- `ARCHITECTURE.md` 1.8.47, [ACR-0039](../../architecture/changes/ACR-0039-judge-doubt-reaches-approver.md), and a note in ACR-0019 §3.8.
Consequences: deploy order on vm-095 with the lease: backup, `ops/db-migrate.sh` (018), then the new agent, worker, scheduler and UI images, then `argus db check`. The old image works on the new schema; the new image needs migration 018 before an approval row can follow a doubt. Migration number 018 was the one the demo contract reserved.
References: [ACR-0019](../../architecture/changes/ACR-0019-human-approved-remediation.md), [shared demo task](../../tasks/current/DEMO-argus-acts.md).

### Test state

RED seen: the SQLite store test and the Postgres migration test for a doubted approval failed before the change (the database refused the row). GREEN locally: the phase 18, 19 and 20 files, the notice, guards, graph, trail and wiring tests; all of `test_postgres.py` on a throwaway Postgres 16 with migrations 001 to 018; `argus db check`'s statements 98/98 as the runtime role; the migration checker; the ApprovalCard, PendingApprovals and ActionTrail vitest files. The full suite is left to CI.

### Next step

Deploy in the order above, then rerun S1 and S4: a doubted proposal should reach the Actions screen with the warning and the raised colour.
