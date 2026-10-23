# DEPLOY-215 step 01 — evidence: vm-095 to main b2e3548, #203 and #208's ops scripts (2026-10-21 UTC, conantkd, session 7f28f8ad8737)

Goal: run #203 (a failed baseline read is not kept) and #208's ops scripts (`db-backup.sh`'s `1>&"$fd"`, shellcheck
annotations) on vm-095. Everything else merged since 999b5bb is CI, Brain or tests. No migration. vm-166 does not
change: its lease was held because the agent changes.

Run by conantkd's agent over ssh, at conantkd's request. Commands: [`code.bash`](code.bash). Times are UTC. No key,
address or project id is written here (`policies/SECURITY.md` rule 4).

| Block | Observed | Result |
|---|---|---|
| D.0 laptop | both leases claimed (`DEPLOY-215`); markers `holder=conantkd session=7f28f8ad8737` on both VMs | OK |
| D.0b vm-166 before | `commit=bdcd0485e5b4` `ref=bdcd048`; `LAB BASELINE OK`; `nonint-check before` saved (63 lines) | OK |
| D.1 vm-095 before | `commit=999b5bbe980e` `ref=999b5bb`; `LAB BASELINE OK`; `nonint-check before` saved (54 lines); mem available 4187 MiB | OK |
| D.1 vm-095 | `BACKUP OK` (2357056 bytes, 01:10); `DEPLOY OK: b2e354813dcf (b2e3548)`; no migration applied, schema 001 to 008; agent, worker, scheduler `Recreated`, `Started`; `health 200`; deploy event recorded; `BACKUP OK` again with the new `db-backup.sh` (2357338 bytes, 01:11) | OK |
| D.2 vm-095 | the three on ONE image `507daee927c0`, `restarts=0`; no startup errors; `26/26 database checks passed`; without a login `/api/v1/topology`, `/overview`, `/me` 401, `/docs` 404; `55/55 checks passed`; `WRITE GATE CLOSED`; `commit=b2e354813dcf` `ref=b2e3548`; `LAB BASELINE OK`; `NO INTERFERENCE` | OK |
| D.3 vm-166 after | `ref=bdcd048` unchanged; `LAB BASELINE OK`; `NO INTERFERENCE` | OK |
| D.4 laptop | both leases released | OK |

## Notes

- **Two deploy events for this deploy.** `deploy.sh` now records the event itself (the image deployed by DEPLOY-B7
  has `argus deploy record`), and the code.bash, copied from DEPLOY-B7, recorded it again. Both rows say
  `b2e354813dcf (main) on vm-095 by conantkd`. The incident charts read `deploy_event`, so an incident whose window
  covers this deploy may show it twice (not checked). Next code.bash: drop the manual `argus deploy record`.
- **The new `db-backup.sh`** (#208, `1>&"$snap_write"`) ran on the VM: the second backup is `BACKUP OK`.
- **Rollback, if needed:** `deploy.sh 999b5bb --as conantkd` on vm-095, then the compose command of D.1.
