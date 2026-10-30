## 2026-10-30 — X-10: an approval wakes its paused run within seconds

Type: fix (worker, stores)
Who: conantkd (+ agent)
Context: production incident `inc_6a4980a4d8ed` ([DEMO-argus-acts](../../tasks/current/DEMO-argus-acts.md), row X-10).
The approval was created at 04:08:23 UTC, and the run interrupted in `GraphRunner._n_await_approval`. A person approved
at 04:09:56. The answer wrote a `resume_intent` row that nothing in production reads (it stayed `pending`,
`attempts=0`). The incident stayed `running`, claimed by the worker with a 300 s lease, until `Worker.recover()`
requeued it after the claim expired at 04:13:38: 3 min 42 s after the answer. By then the cache had been started by
hand (04:13:39), so the fresh precheck refused the action ("incident, detector or action precondition changed") and
the run ended `no_action_escalated`. That refusal was correct and stays.

Root cause: a paused run and a live run looked the same in the incident row (`claimed_by` = the worker,
`claimed_until` in the future), and the approval did not wake the paused run.

Decision / result:

- **Park.** After `runner.run()` returns, the worker asks `GraphRunner.paused(incident_id)`, which reads the graph's
  pending interrupts. If the run is paused, `park_claim` clears `claimed_by` in one statement, with no status change,
  and only when the claim is still this worker's. The claim then ends at the pending approval's `expires_at`, or after
  one lease when no approval waits (a paused verification). `claimed_by IS NULL` on a `running` row is the durable
  "parked" mark. An unanswered approval is still resumed by `recover()` at its expiry and ends `expired`. A lost claim
  is not parked.
- **Wake on the answer.** `answer_action_approval` requeues the incident (`status = 'queued'`, claim cleared) in the
  same transaction that writes `resume_intent`, and only when the incident is `running` and parked. It never touches
  a live run's claim, and a denial wakes the run too. We requeue directly instead of setting
  `claimed_until = now()`: the worker's next poll (`idle_s`, 1 s) picks the run up, and no recover tick is needed.
  The state change is the same as `requeue_expired`'s for that row.
- **Check after the park.** After the park commits, `wake_answered` requeues the incident when a `resume_intent`
  exists for the approval it waits on. This covers an answer given while the run was still live.
- **Postgres row lock.** A live row does not match the wake's `claimed_by IS NULL`, so a plain `UPDATE` would skip it
  without waiting for a park that has not committed yet. If the answer then committed after the worker's check, the
  run would stay parked until the approval expired, and then the expired proposal's precheck would refuse the action.
  The answer therefore takes `SELECT … FOR UPDATE` on the incident row before it wakes the run. The test showed it:
  without the lock the answer did not wait. SQLite serializes writers (`BEGIN IMMEDIATE`), so it needs no lock.
- **`recover_every_s`** defaults to 5 s and can be set with `ARGUS_WORKER_RECOVER_S`, so a parked run whose approval
  expired resumes within about 5 s. `requeue_expired` is one cheap `UPDATE`.
- **No migration.** Migration 019's `incident_forward_only` trigger allows claim changes without a status change, as
  `renew_claim` already relies on, and `running → queued` is what `requeue_expired` already does. `FOR UPDATE` needs
  the `UPDATE` grant the runtime role already has. Both statements were added to `argus db check`.

Consequences: approve → resumed ≤ ~1 s (worker poll), then the fresh precheck and execution: approve → execute within
about 6 s. Verification still needs a fresh Prometheus scrape (15–30 s). `resume_intent` is still not consumed by
anything; it now serves as the "answered" marker for the worker's check. Deploy: recreate `argus-v18-agent` (the API, which
answers approvals) and then `argus-v18-worker` on vm-095, from the same image. Order matters. A new worker next to an
old API would park runs that the old answer never wakes, and they would wait for the approval's expiry (30 min), which
is worse than today. A new API next to an old worker is harmless, because nothing is parked. Set
`ARGUS_WORKER_RECOVER_S` only to change the 5 s default.

References: `argus/infrastructure/worker.py` (`_park_if_paused`), `argus/orchestration/graph_runner.py` (`paused`),
`argus/adapters/outbound/{postgres,sqlite}_store.py` (`park_claim`, `wake_answered`, `answer_action_approval`),
`tests/test_approval_wakes_paused_run.py`, `tests/test_postgres.py`.

### Test state

Red seen: before the change, 9 of the 10 new SQLite tests (`tests/test_approval_wakes_paused_run.py`) failed for the
right reason: the claim stayed with the worker and the answer did not requeue the run. The lost-claim test is a guard
and passed before. The Postgres concurrency test (`tests/test_postgres.py`) failed when the `FOR UPDATE` line was
removed: the answer did not wait for the park in flight. Green: both new files pass. The Postgres file ran on a local
throwaway Postgres 16 (28 passed, `argus db check` included). Full suite on Windows with Postgres: 2776 passed, 62
skipped. The 22 failures and 7 errors are environmental (MCP child processes, `write-gate-check.sh`, the OCI sink and
the gateway client in this laptop's environment): the same set fails on unmodified `main`, and the one extra test
(`test_phase19_gateway_client`) is flaky and passed 3 times of 3 when re-run. After rebasing onto `main` with #414:
208 targeted tests passed (worker, graph, approvals, console, Postgres). `ruff check argus services ops` (0.8.6) is
clean; `brain.py lint` and `audit` are clean. CI: pending.

### Next step

After the merge, in the next deploy window (leases needed): recreate `argus-v18-agent`, then `argus-v18-worker`, on vm-095.
Then on a staged scenario, measure approve → `action.executed` in the incident audit (expected ≤ ~6 s). A scheduled
incident that waits for an answer longer than `ARGUS_SCHEDULE_MAX_QUEUED_AGE_S` (900 s) is skipped as stale when it
is requeued, because `stale()` looks at `opened_at`. The approval TTL is 30 min, so this needs a follow-up:
staleness should apply only to runs that never started.
