## 2026-10-28 - The verification samples inside its reviewed window

Type: fix
Who: conantkd (+ agent)
Context: the S4 run on vm-166 (main `a29bba5`) executed end to end: conantkd approved at 20:22:50Z, the worker
resumed it at 20:25:58Z, the gateway confirmed in about 11 s, the job worker container started at 20:26:09Z and
processed jobs again at the first scrape, 20:26:25Z (16 s). The recorded outcome was nevertheless `action_failed`
at 20:30:58Z, with `actual: healthy`, `detector_cleared: true` and `prediction_met: false`.
Cause: `_n_verify` asked once. The first call, seconds after the restart, found no healthy sample yet (the five-minute
rate had just reset and the metrics needed a scrape), so it returned nothing and the run paused until the worker's
next five-minute pass. The sample taken then was 300 s after the action, outside the 120 s window the approver saw,
and the executor recorded `action_failed` for a worker that had recovered.
Decision / result:
- `argus/orchestration/graph_runner.py`: `_verify_in_window` asks again every `verify_poll_s` (10 s) while there is
  no outcome, until the reviewed window is over; then the old fallback (pause for a fresh sample) applies. A path
  without a window is asked once, as before.
- `argus/orchestration/action_path.py`: `verify_wait` gives the seconds left of the prediction's window counted from
  the action's completion; 0 when the action, its completion or its proposal is unknown.
Consequences: a recovery is verified by a sample taken inside the window; a missing sample is still never healthy
and a recovery is never claimed without one. The worker thread may now wait up to the window (120 s) inside one
verification; typically one or two polls. `result_at` still records the time the attempt started, not the gateway's
answer (about 11 s later in this run); not changed here, it only shortens the window slightly.
References: [demo plan](../../tasks/current/DEMO-argus-acts.md), ACR-0019 section 3.12, RB-022.

### Test state

Five new tests, each red without the change: the verification is asked again inside the window and recovers, the wait
ends with the window and never claims recovery, a path without a window is asked once (`test_phase18_graph`), and the
time left (`test_verify_wait`). The phase 18, 20 and S2 files pass locally; ruff is clean. CI is the full check.

### Next step

Merge, redeploy vm-095's worker, and repeat S4 (the daily cap on vm-166 is used up until 12:53Z tomorrow, so the run
reaches the verification only after the cap resets or is raised).
