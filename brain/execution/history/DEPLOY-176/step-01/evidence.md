# DEPLOY-176 step 01 — evidence: vm-095 to main dfa7332 (2026-10-19, conantkd, session da7842d3a746)

Goal: run on vm-095 what merged since `19b1085`:
- T-0045 B1 to B5 (#173, #177, #174, #175, #176, #181), with migration 007 for `incident.parent_id`;
- ACR-0023, the log read with pattern matches (#179).

The rest (#178 CI, #180 and #182 ACR-0021 records, #183 review rule) is CI and Brain only.

Leases: vm-095 and vm-166 (the agent changes). vm-166 itself was not changed: no file under `services/`, `deploy/` or
`ops/` changed except `deploy/migrations/007`. Commands: [`code.bash`](code.bash). Times are UTC. No key, address or
project id is written here (`policies/SECURITY.md` rule 4).

| Block | Observed | Result |
|---|---|---|
| D.0 laptop | both leases claimed (`DEPLOY-176`); markers `holder=conantkd session=da7842d3a746` on both VMs | OK |
| D.1 before | `ref=19b1085`; `LAB BASELINE OK`; `nonint-check before` saved (54 lines); mem available 4164 MiB | OK |
| D.1 backup, deploy | `BACKUP OK` (2350550 bytes); `DEPLOY OK: dfa73326026b (dfa7332)` | OK |
| D.1 migrate | 001 to 006 already applied; **`+ 007_incident_parent applied`**; schema 001 to 007 | OK |
| D.1 build | agent, worker and scheduler `Recreated` and `Started` (first try) | OK |
| D.2 | `health 200`; the three on ONE image `7faf29330d6a`, `restarts=0`; no startup errors in agent or worker; **`22/22 database checks passed`** (the two new B5 checks included); B1 and B4 modules import, ACR-0023 `LOG_SCAN` has 6 patterns; `55/55 checks passed`; `WRITE GATE CLOSED`; `commit=dfa73326026b` `ref=dfa7332`; `LAB BASELINE OK`; `NO INTERFERENCE: non-Argus objects unchanged`; mem available 4219 MiB | OK |

CI on `main` for `dfa7332`: `main-guard` success (`test` and `frontend` run on pull requests only since #178).

## Notes

- **Order:** migration 007 was applied before the new image started, as #181 requires. The previous image ignores
  the new column, so the rollback stays safe.
- **Rollback, if needed:** `deploy.sh 19b1085 --as conantkd`, then the compose command of D.1. Migration 007 stays;
  the old image does not read `parent_id`.
- **An earlier attempt the same day** (prepared for `77002a7`) was not run: the deploy was not yet authorized. Nothing
  changed on either VM then. The leases were handed off and claimed again for this run.
- **The B5 follow-up** (#185, a `db-check` read that proves 007) is not merged yet. Once it is deployed, the count is
  23.
