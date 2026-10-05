# T-0013 step 5 verification on the VMs (2026-10-05, run by conantkd as reviewer, sanitized)

Branch deployed on vm-095: `c87d76c` (`task/T-0013-langgraph-skeleton`); vm-166: `main` `8eff994`.

- Migration 002 already applied (`= 002_checkpoints (already applied)`); agent runner = `langgraph`;
  `argus db check`: 15/15 (checkpoint insert allowed, checkpoint DELETE refused).
- H-1 -> `HEALTHY`; SC-09 -> `UNSUPPORTED -> escalated`; both checkpointed in Postgres.
- SC-01, first run: `UNSUPPORTED` because Prometheus showed `restarts_10m=2` (detector needs >= 3; the metric lags
  Docker by one scrape). Not a LangGraph defect.
- SC-01, second run (more waiting): `DIAGNOSED`, class `container_restart_loop`, RB-001 cited, checkpoints 12 -> 13.
- `nonint-check.sh after`: NO INTERFERENCE on both VMs; the SC-01 lab worker was removed.
