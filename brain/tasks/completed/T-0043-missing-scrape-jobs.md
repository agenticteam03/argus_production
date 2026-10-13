# T-0043 — A scrape job that disappears is a blind spot too

| Field | Value |
|---|---|
| Status | `done` 2026-10-13 — #128 merged; on both VMs since the AFTER-MERGE to `main` `ad72617` (#132, 2026-10-13): both Prometheus recreated, 10 rules, every target up |
| Phase | 7 — monitoring and detection ("open: an expected-jobs list for absent scrape targets", [`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md)) |
| Architecture | no change: RB-014 / `monitoring_blind_spot` (T-0027) read one more case |
| Branch | `task/T-0043-missing-scrape-jobs` (from `main`) |
| Owner | `conantkd` (+ agent) |
| Needs the VM lease | the AFTER-MERGE (both Prometheus recreated: their config changes) |

## Problem

`ArgusScrapeTargetDown` (`up == 0`) and the signal `scrape_targets_down` see a target that is scraped and fails. A job
that is gone from a host's Prometheus (a config edit, a failed reload) has no `up` series at all: nothing fires, and
the signal read 0 — the host looked fully monitored.

## Change

- **`external_labels: {argus_host: <host>}`** in each `prometheus-<host>.yml`: an alert whose expression has no
  `argus_host` (an `absent()`) still reaches intake as that host's. The existing alerts already carry the same label
  from their series: their labels and fingerprints do not change.
- **`ArgusScrapeTargetMissing`** (`for: 2m`): `absent(up{job=…})` for the jobs every host scrapes —
  `argus-v18-exporter`, `argus-v18-node-exporter`, `argus-v18-cadvisor`.
- **`scrape_targets_down`** = the targets down **plus** those expected jobs with no `up` series, so
  `monitoring_blind_spot` (RB-014) matches the incident.
- Not covered: `argus-v18-db-probe` (vm-166 only; a shared rule would fire forever on vm-095). A per-host list would
  need per-host rule files.

## Tests

`tests/test_t0043_missing_scrape_jobs.py`, 4 (red seen): the external label per host and the expected jobs scraped;
the rule; the signal; the promtool case. `tests/promql/op005_test.yml`: one case (a missing job and a job down = 2).
`tests/test_t0027_blind_spot.py`: its signal check follows the new expression.
