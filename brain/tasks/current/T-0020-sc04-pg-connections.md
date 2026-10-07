# T-0020 — SC-04: PostgreSQL connection exhaustion (`postgresql_connection_exhaustion`, RB-004)

| Field | Value |
|---|---|
| Status | `in progress` — 2026-10-07 |
| Phase | 11 — synthetic incidents ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md) §7: SC-04) |
| Architecture | no change (no ACR): §3 class table (`postgresql_connection_exhaustion` · RB-004 · branch RB-013 · `model_loop`), §3.x "Argus queries only Prometheus for metrics", §4.6 `db-probe` |
| Branch | `task/T-0020-sc04-pg-connections`, **on top of `task/T-0019-db-probe`** (PR #32 open). Its PR opens after #32 merges, with `main` merged in first |
| Owner | `conantkd` (+ agent) |
| Needs the VM lease | the deploy, the scenario runs and their verification |

## Goal (plain language)

A worker on vm-166 leaks database sessions (opens them, starts a transaction and never finishes it) until the lab
database is almost out of connection slots. Argus must **detect** it from a metric (not only when a client fails),
open a `postgresql_connection_exhaustion` incident on `argus-lab-db`, read the database's health, and name the
worker as the root cause without proposing to restart the database.

## Decisions (2026-10-07, `conantkd`)

- **Metrics source: the db-probe publishes `/metrics`** (token-protected) and vm-166's Prometheus scrapes it with
  that token. Same code, same `argus_monitor` role (limit 3), no third-party image. Alternatives not chosen: the
  upstream `postgres_exporter` (another image, other metric names, another connection), and no metric at all
  (only the RB-003 branch when clients already fail).

## Design (to confirm step by step)

- **Metrics** (`ROLE=db_probe`, `GET /metrics`, computed at scrape time, one connection per scrape): per allowlisted
  database, label `container="<target name>"`: `argus_db_up` (1, or 0 when the database cannot be read: then no
  other series — unknown, never zero), `argus_db_connections_max`, `argus_db_connections_usable`,
  `argus_db_connections_used`, `argus_db_connections{state=…}`, `argus_db_oldest_xact_seconds`,
  `argus_db_lock_waits`.
- **Prometheus (vm-166):** job `argus-v18-db-probe`, `authorization.credentials_file` from
  `/opt/argus-v18/secrets/prometheus/` (owner `nobody`, mode 400), on both hosts the same compose (empty on vm-095).
- **Signal** `db_connection_usage` = `min_over_time((used / (usable > 0))[5m:30s])`: the slot ratio sustained for
  5 minutes (RB-004's calibration default: above 90 % for 5 minutes). Unknown capacity gives no value.
- **Alert** `DbConnectionsExhausted`: usage ≥ 0.9 for 5 m.
- **Class** `postgresql_connection_exhaustion` (family `database`, RB-004, branch RB-013, `model_loop`, tags
  `database`, `logs`, `container`, `knowledge`): matches at ≥ 0.9; no value → no match (a container without a
  database has no such series).
- **RB-004:** `detector: postgresql_connection_exhaustion`, version bump; `last_tested` after the first run.
  `database.health` becomes `READ_ONLY_SENSITIVE`, as RB-004's tool table says (application and role names).
- **Lab (`sc04` profile, vm-166):** `argus-lab-leaker` (image `postgres:16-alpine`, only `psql`): opens 16 sessions as
  the ordinary role `argus_lab_app`, each `BEGIN; SELECT 1;` and then waits (idle in transaction). 16 of 17 usable
  slots = 94 %; the monitoring role still gets in. The app role's password is generated on vm-166. Reset: `down`
  of the profile closes the sessions.
- **Inventory:** `argus-lab-db` gets `tcp_ports: [5432]`; `vm-166/container:argus-lab-leaker` depends on it.

## Steps

1. Tests first, then code (metrics, signal, alert, class, RB-004, lab workload, inventory, Prometheus job).
2. Deploy on both VMs (secrets for Prometheus and the app role generated on vm-166, never printed).
3. SC-04 on vm-166: start the leaker → readiness gate (signal ≥ 0.9, alert firing) → `argus diagnose` (Luis's
   password) → verify (`postgresql_connection_exhaustion`, root cause the leaker, `inspect_database_health` used,
   no restart of the database) → reset → LAB BASELINE OK, NO INTERFERENCE.
4. Brain, PR.

## Red seen / evidence

- **Step 1 (2026-10-07, code, tests first):** `tests/test_sc04_pg_connections.py`, 12 tests:
  - **red:** every test failed for the right reason (no `db_metrics`, no detector, no `db_connection_usage` signal,
    no Prometheus job, no `tcp_ports` / leaker in the inventory, RB-004 `detector: null`, `READ_ONLY_SAFE`, the
    scripted diagnosis did not get the class);
  - **green:** 12/12 (+ 15 db-probe tests); full suite 131 passed, 6 skipped (137).
  - The db-probe's health and metrics share one read (`db_health`); `/metrics` sits behind the same token.
