# T-0020 — SC-04: PostgreSQL connection exhaustion (`postgresql_connection_exhaustion`, RB-004)

| Field | Value |
|---|---|
| Status | `done` 2026-10-08 (verified on vm-166 2026-10-07; PR open, waits for review) |
| Phase | 11 — synthetic incidents ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md) §7: SC-04) |
| Architecture | no change (no ACR): §3 class table (`postgresql_connection_exhaustion` · RB-004 · branch RB-013 · `model_loop`), §3.x "Argus queries only Prometheus for metrics", §4.6 `db-probe` |
| Branch | `task/T-0020-sc04-pg-connections` (started on top of `task/T-0019-db-probe`; PR #32 merged 2026-10-07; `main` merged in 2026-10-08) |
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
  slots = 94 %; the monitoring role still gets in. The app role's password is generated on vm-166. Reset:
  `docker rm -f argus-lab-leaker` closes the sessions (never `compose down`: it would remove the whole lab).
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
- **Step 2 (2026-10-07, both VMs):** deployed `a102bd5`; vm-166 Prometheus scrapes the db-probe (`up=1`, `0/17`); the
  agent has the 4 classes; LAB BASELINE OK, NO INTERFERENCE ([evidence](../../execution/history/T-0020/step-02/evidence.md)).
- **Step 3, run 1 (2026-10-07 ~17:05, not valid):** the leaker stopped at about 10 sessions with
  `can't fork: Resource temporarily unavailable`: the lab's common `pids_limit: 32` is too small for ~3 processes per
  session. The diagnosis `inc_b8370349ce57` ran before the gate: signals `db_up=1`, `db_connection_usage=0.0`, no class
  matched, `UNSUPPORTED` with an evidence pack and **no diagnosis claimed** (correct for what it saw). Reset by
  `conantkd` (leaker gone, used 0, LAB BASELINE OK, NO INTERFERENCE).
  - **red:** the leaker test now asks `pids_limit >= 3 × SESSIONS + 8` (`32 >= 56` failed); **green:** the leaker
    has its own limits (`pids_limit: 64`, `mem_limit: 192m`).
- **Step 3, run 2 (2026-10-07 17:17–17:25):** gate OK (16 sessions, 94 % for 5 min, alert firing); `inc_075fb0006098`
  **DIAGNOSED** `postgresql_connection_exhaustion`, root cause `argus-lab-leaker`, confidence high, the model read
  `inspect_database_health` and the leaker's status, no database restart. RB-004 `last_tested: 2026-10-07` (1.0.2).
  Reset: leaker gone, used 0, LAB BASELINE OK, but **nonint-check: DIFFERENCES** — two anonymous volumes left by the
  leaker's image `VOLUME` (runs 1 and 2). Fix: tmpfs on the leaker (red `KeyError: 'tmpfs'`, then green). The two
  volumes were removed by ID after `conantkd`'s go (snapshot back to the pre-scenario baseline) ([evidence](../../execution/history/T-0020/step-03/evidence.md)).
- **Step 4 (2026-10-08, Brain and PR):** `main` merged in (T-0014, T-0015 step 6, the CLI fix; only conflict
  `execution/current/code.bash`, kept the empty template: both steps are archived). Full suite **169 passed, 7 skipped**
  (176). State probe: vm-166 on `b1e7176`, vm-095 on `task/T-0021-tool-isolation` `a5f330a` (no T-0020 in its agent
  yet), LAB BASELINE OK and NO INTERFERENCE on both. After the merge: AFTER-MERGE on vm-166 (checkout only, block in
  `execution/current/code.bash`); vm-095 gets the class when it runs `main` again (after PR #36).
