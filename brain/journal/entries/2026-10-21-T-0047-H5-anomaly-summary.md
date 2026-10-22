## 2026-10-21 — T-0047 H5 step 1: `analysis.anomaly_summary`, offered to no class

Type: implementation
Who: juanbetancurm (+ agent)
Context: ACR-0024 §3.7 adds a Level 3 read of deterministic facts, so the model can see which signal moved first and
how unusual a level is without reading every history. Step 1 builds it, offered to no class; step 2 offers it to
`dependency_unavailable` and `container_restart_loop` with an evaluation batch.
Decision / result:
- `summarize_anomalies` (`analysis.anomaly_summary`, executor `prometheus`, tag `anomaly`, `max_per_incident` 1). It
  reads the class's signals (`ui-incident-signals.yaml`) on the target, its declared dependencies on the same host (at
  most 3) and, for host-scope signals, its host.
- Per series: last value, the peak in the bad direction, the onset and the deviation from the 24 h baseline that ends
  an hour before the window (p5 / p50 / p95; unknown under half sampled). The onset is the first of two consecutive
  samples past the warning line. The answer also says which onset came first. Facts with numbers, never a cause.
- Unknown is never calm: a failed read, an empty series and a missing baseline are each said so.
- The read only gets its arguments, the target and its inventory entry, so the model names the incident class (one
  of the 8 registered names, pinned by a test). The prometheus executor holds the warning lines and the class signal
  lists from startup (the worker, the tools process and the evaluation replay).
- A 0/1 state signal has no line in `signals.yaml`; its bad state is its line. A "below" signal is compared with the
  baseline's p5, the others with its p95.
Consequences: step 2 needs per-target `range` fixtures in the eval cases (today a fixture series answers every
target) before a batch can measure "which onset came first".
References: [ACR-0024](../../architecture/changes/ACR-0024-hypotheses-and-cause-ranking.md),
[T-0047](../../tasks/current/T-0047-hypotheses-cause-ranking.md).
