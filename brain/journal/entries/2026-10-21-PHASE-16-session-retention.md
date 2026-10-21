## 2026-10-21 — Phase 16: auth_session retention; maintenance audit rows chained

Type: implementation
Who: conantkd (+ agent)
Context: step 1 left `auth_session` growing by one row per login, with its owner-run retention as a follow-up (like
OP-004). Reading OP-004's code for the pattern showed its audit row is a bare `INSERT`: after migration 011 that row
has no hash, and `argus audit verify` (and the scheduler's daily check) would report the chain broken at the first
checkpoint prune that removes anything. None has yet (the last dry run found `threads=0`).
Decision / result:
- `argus db prune-sessions [--days N] [--apply]`: owner-only, preview by default, one transaction, the maintenance
  lock of OP-004; removes rows whose token expired more than 90 days ago (`ARGUS_SESSION_RETENTION_DAYS`), revoked or
  not; audited `maintenance.sessions_pruned` (`access`). The audit keeps each login and refusal.
- `append_chained` (postgres_store): the one way to write an audit row; the store and both maintenance commands use it.
- Tests: `tests/test_session_retention.py`; `tests/test_checkpoint_retention.py` now checks the chain after a prune.
Consequences: no migration and no new grant (the owner deletes). The VM dry run goes with phase 16 step 2's deploy.
ACR-0018 §6 gets its line in step 2's PR (a protected path).
References: [PHASE-16](../../tasks/current/PHASE-16-operator-access.md), OP-004.
