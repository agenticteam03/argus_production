## 2026-10-13 — EVAL-snapshot: the snapshot offered to health_check_failed lowers it (0.88 → 0.72); not offered

Type: evidence / decision
Who: conantkd (+ agent)
Context: T-0034 offered `capture_diagnostic_snapshot` to no class until measured.
Decision / result: offered to `health_check_failed` on a branch and measured against `main` (55 cases, 5 trials, same
model): the model used it in 19 of 25 health runs, read more (7.8 vs 4.6 per run) and escalated more:
`health_check_failed` 0.88 → 0.72, overall 0.96 → 0.94, hard 0 0 0 both. The offer is reverted; the snapshot stays in
the catalogue, offered to no class.
Consequences: the same rule for the other new reads (T-0036–T-0039): each offered to a class only with a batch that
shows it helps.
References: [evidence](../../execution/history/EVAL-snapshot/step-01/evidence.md).

### Next step

None for the snapshot in this class. Candidates for the next batch: the metric histories or `search_logs` for the
class whose misses they address.
