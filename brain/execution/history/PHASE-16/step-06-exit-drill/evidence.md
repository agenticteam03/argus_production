# PHASE-16 step 06 — evidence: DEPLOY-6e87828 (migration 016) and the tamper drill (2026-10-26 UTC, conantkd)

Goal: deploy `main` `6e87828` (#342: migration 016, an approval needs the judge's stored `agree` on the proposal's
digest) to vm-095, then run phase 16's exit drill (ACR-0018 step 6): the owner edits one chained audit row;
`argus audit verify` and the scheduler's chain check must name it; the edit is undone. Run by conantkd's agent over
ssh at conantkd's request, both leases (session `903b7748`). Commands: [`code.bash`](code.bash).

| Block | Observed | Result |
|---|---|---|
| D.1 (vm-166) | marker set, "before" snapshot (63 lines) | OK |
| D.2 | `ref=b6e64eb`, `LAB BASELINE OK`; evaluations running 0; `BACKUP OK` (`argus-20261026T113544Z.dump`), `VERIFY OK: 31 tables`; `DEPLOY OK: 6e87828c51e2`; `+ 016_approval_needs_agree applied`, schema 001-016 | OK |
| D.3 | agent, worker, scheduler `Recreated`, `Started`; health 200; `deploy recorded: 6e87828 (main) on vm-095` | OK |
| D.4 (read-only) | four containers `running restarts=0`; error lines 0; `016 trigger: 1`; `91/91 database checks passed`; `AUDIT CHAIN OK: 316 rows chained, 3893 written before the chain`; phase 17 live, denied hosts `['vm-095']`; `/me` 401; `ref=6e87828`, `LAB BASELINE OK` | OK |
| T.1 (drill) | row `aud_36ffb89d5d22460a` (the newest chained `security.audit_chain_verified`) edited by the owner: one key, `detail.drill = true`; the insert-only trigger on again (`O`). `argus audit verify`: `BROKEN aud_36ffb89d5d22460a: hash does not match its body (the row was edited)`, `AUDIT CHAIN BROKEN: 1 problem(s)`. Scheduler restarted: `security.audit_chain_broken: 316 chained, 3893 before, 1 problem(s)`, its stored event names the same row; the digest job refused: `audit digest skipped: the audit chain is broken (1 problem(s))` | **detected** |
| T.2 (undo) | the key removed (edited rows 0, trigger `O`); `AUDIT CHAIN OK: 318 rows chained` (two new rows: the two checks); scheduler restarted: `security.audit_chain_verified 0`; scheduler running; vm-095 `NO INTERFERENCE` | OK |
| D.5 (vm-166) | `NO INTERFERENCE: non-Argus objects unchanged` | OK |

## Notes

1. The drill shows that the owner can still edit the audit table (the insert-only trigger stops the runtime role, not
   the owner), so detection is what protects the record: the chain names the edited row at once, and a broken chain is
   never signed or shipped off host. The digests already shipped to OCI (2026-10-21 to 2026-10-25) were not affected:
   the edited row is from 2026-10-26, a day not yet closed, and it was restored before the day closed.
2. The alert to a person still waits for the team's alert receiver: today `security.audit_chain_broken` is an audit
   event and an `ERROR` log line.
3. The authorization matrix and the public-404 tests are green in CI (`main` `6e87828`); the public edge answers 404
   for `/api/v1/ops/` (checked live on 2026-10-26, NIGHT-2026-10-26).
