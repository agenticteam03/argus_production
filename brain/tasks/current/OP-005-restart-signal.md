# OP-005 — Count restarts of young containers

**Owner:** `conantkd` · **Branch:** `task/OP-005-young-restarts` · **Status:** offline implementation verified; VM proof pending.

## Goal

Make `restarts_10m` match Docker's counter during a container's first ten minutes, without treating an old container's
missing historical scrape as new restarts. Use the design accepted in `OPEN_PROBLEMS.md` OP-005.

## Steps

1. **Offline, done:** publish Docker's `.Created` as `argus_container_created_seconds` for existing allowlisted
   containers; use the approved young-first PromQL expression. Three unit tests were red against the old code, then
   green. Five synthetic-series cases passed with `promtool test rules` (`prom/prometheus:v3.5.0`); the CI step that runs them is a separate PR (it changes
   `.github/workflows/`, so a teammate approves it).
2. **VMs, pending:** with the session lease and state probe, deploy the branch's exporter on both hosts and the signal
   to the agent, then run SC-01 immediately after its third restart on vm-166. Compare Docker's count and Prometheus
   `restarts_10m`, require `3`, and confirm a diagnosis. Restart the exporter with an old healthy container present;
   require no restart-loop incident. Reset the lab, `LAB BASELINE OK`, and `NO INTERFERENCE` on both hosts.

## Acceptance

- Young (3 minutes, counter 3) gives 3.
- Old with a missing sample ten minutes ago gives no value; old with a continuous series uses the ten-minute delta.
- A container recreated under the same name uses the new counter, even if an old sample exists ten minutes ago.
- The exporter derives the creation time from Docker inspect; absent containers emit no series.
- The VM proof records SC-01's diagnosis and non-interference before OP-005 is marked fixed.

## Red seen and offline evidence

- `tests/test_op005_young_restarts.py`: three failures before implementation (`created_at_seconds` absent, metric
  absent, old expression). After implementation: 3 passed.
- `tests/promql/op005_test.yml`: five cases passed with Prometheus 3.5.0 `promtool test rules`.
- **Review of PR #41 (2026-10-09, `conantkd`):** the alert `ContainerRestartLoop` still used `max_over_time -
  min_over_time`; it now has the same expression as `restarts_10m` over every container (with pulled alerts the alert
  opens the incident, so it must not see a young loop later than the detector). Test first:
  `test_the_restart_loop_alert_counts_like_the_signal` (red seen); `promtool check rules` SUCCESS (4 rules). The CI
  step moved to its own PR so this one can be fast-tracked. `main` merged in.
