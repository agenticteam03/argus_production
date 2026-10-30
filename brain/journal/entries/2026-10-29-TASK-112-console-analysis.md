## 2026-10-29 - TASK-112 and TASK-123: Argus's comment after each console command, wired and fixed after review (ACR-0043)

Type: feature (console analysis, store)
Who: conantkd (+ agent)
Context: `argus/console/analysis.py` (#406) had no caller. CON-4b runs it after each console command, stores the result per
command (migration 021) and lets the history read carry it. Conan's review of the first commit asked for two changes.
Decision / result:
- Each read that answers `ok` is analysed in the background: before snapshot, the settle delay, two samples, `analyse()`,
  the deterministic `rank()`. The model never ranks; a comment may only state what the output or the metrics show.
- Review fix 1: a job holds a worker slot only around a sample and the model call, never while it sleeps, so a run of reads
  cannot queue later analyses past `analysis_stuck_s`.
- Review fix 2: a write's `ok` is a proposal waiting for approval, not an action that ran. The runner holds the write (the
  metrics from before it, `awaiting_action`, in the same `console_analysis` row) and shows nothing. When the history is read
  and the action row says `confirmed`, the settle delay counts from `result_at` and the analysis starts. A failed or
  indeterminate action gets a non-retryable "nothing to compare". No evidence is appended and no ranking is recomputed
  before the action ran.
- Also: one re-check at a time per command, a taken hypotheses step is retried, the history docstring is corrected.
- Cost: every read now costs one model call (up to 20 a minute per person, within ACR-0043); `ARGUS_CONSOLE_ANALYSIS=0`
  switches it off.
Consequences: the migration `021_console_analysis.sql` is a protected path and needs Conan's review, as do `ui-api.json`
and `http.py`. Nothing here is run on the lab.

### Test state

Red seen first for the slot test and the hypotheses-retry test. The wiring, parser, analysis, handler, routes, store, write
path, contract, private-login and Postgres-file tests ran green after the merge of #410 and the contract line was
regenerated; Ruff on `argus services` is clean.

### Next step

Run the console on the lab (reads, then a write through an approval) and confirm the metric names per command.
