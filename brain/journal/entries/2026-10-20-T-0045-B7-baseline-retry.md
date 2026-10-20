## 2026-10-20 — T-0045 B7 follow-up: a failed baseline read is not kept

Type: implementation
Who: juanbetancurm (+ agent)
Context: the review of #188 (B7, merged): when the baseline's Prometheus read failed, `IncidentMetrics._baseline`
stored the `None` for the incident's life, so one hiccup hid the "normal" band on every later answer.
Decision / result:
- A failed read (`MetricsUnavailable`, `StaleMetrics`, `ValueError`) returns `None` without storing it; the next
  answer reads it again. "Under half the samples" is still kept, since that window never moves.
- `tests/test_t0045_b7_baseline_deploy.py`: `test_a_failed_baseline_read_is_not_kept_and_the_next_answer_reads_it_again`,
  seen red first.
- Not changed: `008_deploy_event.sql` says the verb runs "after `DEPLOY OK`" (it runs just before that line).
  `db-migrate.sh` refuses a migration whose file changed after it was applied, so the comment stays as it is.
Consequences: no route, field or contract change; reaches vm-095 with the B7 deploy.
References: #188, [T-0045](../../tasks/current/T-0045-ui-insights-backend.md).
