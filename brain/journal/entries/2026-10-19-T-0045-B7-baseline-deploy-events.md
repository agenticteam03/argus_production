## 2026-10-19 — T-0045 B7: baseline, the 6h and 24h ranges, deploy events (migration 008)

Type: implementation
Who: conantkd (+ agent)
Context: the redesigned UI's incident charts draw a "normal" band, a longer lead-in and deploy markers. Step B7 of
[T-0045](../../tasks/current/T-0045-ui-insights-backend.md), after ACR-0021's acceptance and B5.
Decision / result:
- **Ranges:** `GET /api/v1/incidents/{id}/metrics` accepts `6h` and `24h`, with at most ~130 points per series as
  before. The answer lists `ranges_available`.
- **Baseline:** each series gains `baseline`, `{p50, p95, from, to}`.
  - It covers the same signal over the 24 h that end an hour before the incident opened, scaled like the values.
  - It is `null` when under half of that window has samples, or when the read fails: unknown, never a guessed band.
  - It takes one 289-sample `MetricsPort.range` read per incident and signal, kept for the incident's life. The
    quantiles are computed in Python (linear between ranks, as `quantile_over_time`), so there is no new port method.
  - This answers T-0045's open decision 4 (the window and its cost).
- **Deploy events:**
  - `deploy_event` (migration **008**; B5 took 007), insert-only for the runtime role, with the commit checked as hex.
  - `argus deploy record --commit --ref --as [--host]` validates against the inventory and the formats, writes it and
    audits it (`deploy.recorded`).
  - `ops/deploy.sh` calls it through the running agent before its `DEPLOY OK` line. It is never fatal: on the deploy
    that first brings the verb (the old image still runs), or on vm-166 (no agent), it prints the command to run after
    the rebuild.
  - The charts show the incident host's deploys inside the window, labelled with ref and short commit, never who.
- `db-check` gains three checks: the insert succeeds; an UPDATE and a DELETE are refused.
Consequences:
- Additive fields only. ARCHITECTURE 1.8.20 (§7.1, §16.1; B6 took 1.8.19).
- **Deploying this step:** `db-migrate.sh` (008) before the image; then record that deploy itself with
  `argus deploy record` after the rebuild.
- vm-166's deploys are recorded from vm-095 with `--host vm-166`, since the database lives there.
References: [ACR-0021](../../architecture/changes/ACR-0021-ui-insights-v2.md), `docs/API-FOR-UI.md`.

### Test state

- `tests/test_t0045_b7_baseline_deploy.py` is new: ranges, baseline (values, window, sparse, failed read, read once),
  deploy events, the store and the CLI. All red first, except the unknown-range guard.
- `tests/test_deploy.py`: two new tests (the record call before the verdict; a failure never stops the deploy), seen
  red first. Its helper never reaches the machine's Docker.
- `tests/test_postgres.py`: `test_deploy_events_migration_008` (CI's Postgres).
- `tests/test_acr0017_incident_metrics.py`: the key set gains `baseline`; the cache test counts the chart's reads apart
  from the baseline's.
- `contracts/ui-api.json` and `incident-metrics.json` regenerated; the other samples untouched.
- Full offline suite green.

### Next step

Review (protected paths: `ops/`, `deploy/migrations/`, `contracts/`). Then deploy with migration 008 and record that
deploy. B8 is optional.
