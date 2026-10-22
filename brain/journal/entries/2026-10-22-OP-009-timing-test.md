## 2026-10-22 - OP-009: the lease-expiry test no longer depends on a fast CI runner

Type: tests
Who: conantkd (+ agent)
Context: `test_a_failing_renewer_cancels_at_the_lease_expiry_not_at_its_next_attempt` failed on #249's CI (1.53 s
against a 1.25 s bound) with no change near the worker; a rerun passed. Lease 1 s and attempts every 0.7 s put the
fix at 1.0 s and the bug at 1.4 s, so only 0.25 s separated a slow runner from a failure.
Decision / result:
- Lease 2 s, attempts every 1.9 s: the fix cancels at 2.0 s, the bug at 3.8 s; the bound `1.9 <= elapsed < 3.0`
  leaves a second each way. The test checks the same thing (cancel at the lease's expiry, not at the next attempt).
- Red seen: the worker waiting a full interval while failing (the bug of PR #53's review) fails it at 3.83 s.
- The test takes about 1 s longer.
Consequences: none for the worker; no code changed outside the test.
References: `tests/test_op009_lease_loss.py`, `argus/infrastructure/worker.py` (`_renew`).
