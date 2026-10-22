## 2026-10-22 — T-0047 H5 step 2, part A: the replay gives a dependency its own metric series

Type: work
Who: juanbetancurm (+ agent)
Context: `analysis.anomaly_summary` (H5 step 1, #252) reads the incident class's signals on the target and its declared
dependencies and says which crossed its warning line first. The replay answered every target with the same series per
signal, so in a dependency case the victim and its dependency had identical histories and the order meant nothing.
Decision / result:
- `FixtureExecutor.range` reads `range_by_target.<target>.<signal>` for a target named there (no fallback), else
  `range.<signal>` as before; every other case is unchanged.
- The six dependency cases got the victim's `dependency_probe_min` series and the dependency's own memory and restart
  series (a stopped container's series end when it stops; a crash-looping cache's restart count climbs). Labels
  unchanged.
- The offline evaluation of `tests/eval/cases` is identical before and after: registered 32/61, `--strategy baseline`
  57/61, hard 0 (only the latencies differ).
Consequences: part B offers the read to `dependency_unavailable` and `container_restart_loop` (class registry,
`conantkd` reviews) with a model batch. The six `restart-*` cases also got `restarts_10m` and `oom_killed` series
(ending at their snapshot values), so the read has the signal their class fires on.
References: [T-0047](../../tasks/current/T-0047-hypotheses-cause-ranking.md), ACR-0024 §3.7, #252.

### Test state

T-0047 H5 step 2 A: `tests/test_t0047_h5_anomaly_summary.py` 17 passed (8 new, red seen: the replay answered the
dependency with the victim's series); offline evaluation identical before/after.
