# DEPLOY-NIGHT step 01 — evidence: vm-095 to main 024aa6f, migration 009; OP-004 / OP-008 dry runs (2026-10-21 UTC, conantkd, session 8cba6e61d3c4)

Goal: run on vm-095 what main gained since DEPLOY-215 (b2e3548): migration 009 `link_event` (#220), T-0046 L1 (#219),
#221 (one link per dependency; `host.read_file` no longer raises), and the ACR-0027 / ACR-0028 texts; then preview
OP-004 and OP-008 without deleting anything. vm-166 does not change: L1 renders the same target config (its test).

Run by conantkd's agent over ssh, unattended, at conantkd's request ("puedes tomar el lease de las vm"). Commands:
[`code.bash`](code.bash). Times are UTC. No key, address or project id is written here.

| Block | Observed | Result |
|---|---|---|
| D.0 laptop | both leases claimed (`DEPLOY-NIGHT`); markers `holder=conantkd session=8cba6e61d3c4` on both VMs | OK |
| D.0b vm-166 before | `commit=bdcd0485e5b4` `ref=bdcd048`; `LAB BASELINE OK`; `nonint-check before` saved (63 lines) | OK |
| D.1 vm-095 before | `commit=b2e354813dcf` `ref=b2e3548`; `LAB BASELINE OK`; `nonint-check before` saved (54 lines); mem available 4252 MiB | OK |
| D.1 vm-095 | `BACKUP OK` (2357344 bytes, 04:52); `DEPLOY OK: 024aa6f94406 (024aa6f)`; deploy event recorded once, by `deploy.sh`; `+ 009_link_event applied`, schema 001 to 009; agent, worker, scheduler `Recreated`, `Started`; `health 200` | OK |
| D.2 vm-095 | the three on ONE image `14f1b1bd174e`, `restarts=0`; no startup errors; `29/29 database checks passed` (009's three included); without a login `/api/v1/topology`, `/overview`, `/me` 401, `/docs` 404; `55/55 checks passed`; `WRITE GATE CLOSED`; `commit=024aa6f94406` `ref=024aa6f`; `LAB BASELINE OK`; `NO INTERFERENCE` | OK |
| D.3 vm-166 after | `ref=bdcd048` unchanged; `LAB BASELINE OK`; `NO INTERFERENCE` | OK |
| D.4 OP-004 | `ops/checkpoint-retention.sh --dry-run --as conantkd` (30 days): `DRY RUN: threads=0 checkpoints=0 blobs=0 writes=0` | nothing old enough |
| D.4 OP-008 | `db-backup.sh prune --as conantkd` (preview): `PRUNE DRY RUN: 13 backup sets would be removed` (2026-10-13 and 14); nothing removed | preview only |
| D.4 vm-095 | `nonint-check after` the dry runs: `NO INTERFERENCE` | OK |
| D.5 laptop | both leases released | OK |

## Notes

- **`argus db prune-checkpoints` inside the agent container refuses** (`PermissionError: checkpoint retention requires
  argus_owner`), as designed: the runtime role has no DELETE. The wrapper `ops/checkpoint-retention.sh` mounts the
  owner's secret into a one-off container; it needs `--as <lease holder>`.
- **No deletion was run.** Removing 13 backup sets is a data deletion: a stop condition of AGENT_PROTOCOL §6, left
  for conantkd or the team (`db-backup.sh prune --apply --as <handle>`).
- **Rollback, if needed:** `deploy.sh b2e3548 --as conantkd` on vm-095, then the compose command of D.1. Migration
  009 stays (the old image does not read `link_event`).
