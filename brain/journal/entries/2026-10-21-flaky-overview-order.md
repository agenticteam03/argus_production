## 2026-10-21 — A flaky overview test: incidents tied on their creation time

Type: fix (tests only)
Who: juanbetancurm (+ agent)
Context: `test_t0045_b6_overview.py::test_open_incidents_are_counted_by_severity_and_the_worst_one_is_the_status`
failed once in a full local run and passed alone. The stores sort incidents by the `opened_at` column, which is
written at creation and never updated; the test created three incidents a moment apart and then changed `opened_at`
only in their stored bodies. When the clock gave two of them the same creation time, the order was the insertion
order (oldest first) and "newest first" failed. Forcing equal creation times reproduces it every time.
Decision / result:
- `tests/test_core.py`: `incident()` takes an optional `opened_at`, so a test can create an incident at its real time.
- `tests/test_t0045_b6_overview.py`: `_inc` passes it instead of changing `opened_at` after the insert.
Consequences: no product change; in Argus an incident's `opened_at` is set once, at creation.
References: T-0045 B6 (`d6ba12a`).
