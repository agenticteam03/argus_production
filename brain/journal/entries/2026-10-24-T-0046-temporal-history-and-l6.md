## 2026-10-24 — T-0046: replay link probe history and offer it to diagnosis

Type: implementation
Who: conantkd (+ agent)
Context: T-0046 L5 had two verified gaps before L6: the scheduler stored its tick time instead of the exporter sample time,
and a probe that broke and recovered between 60-second ticks was never stored. Restart recovery also had no durable
source-sample cursor. `network.link_states` was registered but no incident class received it.
Decision / result:
- Accepted ACR-0031 for bounded four-hour range replay with exporter source timestamps, durable per-link cursors and
  atomic transition/audit/cursor writes. The cursor is in Argus Postgres on vm-095; Prometheus on vm-166 remains the
  existing sample source.
- Added migration 014, both stores, `MetricsPort.dependency_probe_history`, the range adapter and cursor-aware scheduler.
  An unreadable host does not advance its cursor; after the four-hour bound an omitted gap is explicitly rebased to
  `unknown`.
- Offered `network.link_states` only to `dependency_unavailable`, `health_check_failed` and
  `nginx_upstream_failure`. Baselines now read and use its evidence. The evaluation replay gained internal fixtures for
  link history and the latest probe; five cases cover SC-03, SC-07, a health failure from a dependency, and SC-08 broken
  and slow upstream links. The offer is measured with the deterministic baseline only: each of the five cases fails
  without it and passes with it. In SC-03, SC-07 and the health case the read changes the root cause; in the SC-08 cases
  it changes the mechanism (broken or slow link), not the root cause. The `model_loop` arm (`health_check_failed`) is
  not measured: a model batch needs the replay's `now` pinned first.
- Updated the task, ACR-0031 and architecture 1.8.36 in one task branch; [PR #322](https://github.com/agenticteam03/argus_production/pull/322) is open for `juanbetancurm`'s review. Version 1.8.35 is PR #314, merged first; `main` (`fcdb9d3`) is merged in.
- Review of #322 (`juanbetancurm`, changes requested on `5657763`), addressed on 2026-10-25:
  - a silent exporter no longer widens each tick's Prometheus window toward four hours: a link already `unknown` is
    read back at most the staleness limit (90 s), also after a long scheduler gap (second review, on `c60dc2b`). Trade-off: when the exporter returns during a long scheduler
    gap, an `unknown` link's samples older than 90 s before the next tick are not replayed; the link is current on that tick;
  - new tests for both staleness boundaries, a silent exporter (60 s ticks, and gaps of 30 and 60 minutes) and a SQLite probe older than the cursor; each fails
    when its code is removed;
  - the SC-08 labels now require the mechanism (`broken`; `upstream path is slow`), and a control test runs the five
    cases without the offer and expects each to fail;
  - the two evaluation arms are stored with their comparison ([evidence](../../execution/history/T-0046-l6/step-02/evidence.md));
  - stale comments in `link_transitions.py`, `catalog.py` and `schedules.yaml` updated.
- Before deployment, a read-only state probe ran on both VMs under both leases; [evidence](../../execution/history/T-0046-l6/step-01/evidence.md) records deployed commits, healthy lab baseline and `NO INTERFERENCE`. No application deploy or migration was run because PR #322 is not merged.

### Test state

Red seen before the implementation: the three new cursor/history regressions failed for the expected reasons (missed
intermediate transitions, restart replay and missing cursor persistence). The focused L6 suite passes **11 tests**.
The full local pytest suite completed with 15 failures in Bash-backed tests: Windows selected its WSL launcher, which
reports `execvpe(/bin/bash) failed: No such file or directory`. CI's first run found a serialization-format assertion
in the new Postgres test (`Z` versus `+00:00`); commit `26aeb79` normalizes UTC to `Z`. On that commit, GitHub CI's
`test` job (including the Postgres runtime test) and frontend job both pass; `main-guard` is skipped by workflow rules.
Brain lint, audit, diff check and migration checker pass. The Postgres test remains skipped only in local Windows runs
because Docker is not running.
Review fixes: `tests/test_t0046_l6_sample_history.py` 10 passed and `tests/test_t0046_l6_eval.py` 2 passed; removing
either staleness block, the window bound for an `unknown` link (both silent-exporter tests) or the SQLite `at <= cursor` guard makes its new test fail.
Paired one-trial baseline evaluation on the same branch and 66 cases (stored in `execution/history/T-0046-l6/step-02/`):
control without the offer 57/66, treatment 62/66; the four hard checks are 0 in both; no class is lower;
`dependency_unavailable` 4/7 → 6/7, `health_check_failed` 10/11 → 11/11, `nginx_upstream_failure` 5/7 → 7/7. The
earlier "60/66 before" had no stored file and predates the tighter SC-08 labels; this run replaces it. Four unrelated
cases fail in both arms. The model arm is not measured. VM deployment remains pending.

### Next step

Merge order agreed on 2026-10-25: #314 first (architecture 1.8.35, merged), then #322 (1.8.36, migration 014), then #323,
which renumbers its `014_remediation.sql` to 015 with `tests/skills/test_db_migration.py` and the `db check` lists.
Wait for `juanbetancurm`'s re-review on PR #322 (class registry, ACR and architecture are protected); CI was green on
`26aeb79`. Do not approve or merge this PR as its author. After merge, the integration owner acquires both leases,
applies migration 014 and deploys on vm-095, checks SC-03/SC-07, and records sanitized output before releasing the leases.
