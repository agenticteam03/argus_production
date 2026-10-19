## 2026-10-19 — EVAL-offers: the unoffered capabilities measured; ACR-0023 proposed; four replay fixes; long-log cases

Type: evaluation
Who: conantkd (+ agent, unattended overnight on vm-095)
Context: `cpu_history`, `disk_history`, `request_path`, `search_logs` and `baseline` are offered to no class until an
evaluation batch measures them. One batch per offer, each the base plus one tag, 61 cases × 5 trials.
Decision / result:
- No capability is offered to a class. `cpu_history` and `disk_history` are used and change nothing; `request_path`
  0.72 → 0.74; `search_logs` is called in 4 of 50 health runs; `baseline` in 1 of 25 cpu runs. Health alone moves
  between 0.66 and 0.82 in batches that do not touch it, so a class-level number is read with the mechanism.
- Proposed: [ACR-0023](../../architecture/changes/ACR-0023-log-read-pattern-matches.md). `container.logs` also
  brings the last 30 min's lines that match a named failure pattern and are not in its tail. Measured (H1): it changes
  the evidence of 3 cases; in `health-api-vm166-01-longlog` 1/5 → 5/5, every diagnosis citing the line outside the
  tail. The agent finds a buried cause without a runbook telling it to search.
- The replay now answers like the gateway in four places: an earlier metric window is its own fixture (it was the
  current one), a fixture is stamped with the time it is read (a fixed date read as a week-old sample), `/connectivity`
  is built from the two status fixtures, and a long log answers `logs`, `logs_window` and `search`. Two vm-166 health
  cases answered their own health URL with 200 against their health check; they now agree.
- 6 `-longlog` twins of the health cases (the cause outside the log's tail) and derived cpu and disk history fixtures.
- The OpenAI account ran out of credits during one batch; it and a partial one were discarded and rerun.
- Also here (asked by conantkd): `main-guard` gets `checks: read`. It has been red on every push to `main` since #177,
  the first self-merge: `verify-main` reads the commit's check runs to validate a self-merge and got
  `Resource not accessible by integration (HTTP 403)`. A permission gap, not a broken review rule.
Consequences: with ACR-0023 accepted, each log read makes up to 6 more gateway requests and carries up to 6 more
redacted lines; architecture 1.8.17. The evaluation has 61 cases; `ambiguous-health-no-cause-longlog` joins
`BASELINE_MISSES`.
References: [evidence](../../execution/history/EVAL-offers/step-01/evidence.md).

### Test state

`tests/test_evaluation.py`: five new tests; `tests/test_acr0023_log_matches.py`: five (two red first, three guard what
must not change); `test_resume_inside_evidence_pack_does_not_repeat_completed_reads` now compares reads with their
parameters. Full offline suite green on the final commit.

### Next step

The team decides ACR-0023 in PR #179. A cause that matches no pattern ("maintenance mode is ON") is still missed.
