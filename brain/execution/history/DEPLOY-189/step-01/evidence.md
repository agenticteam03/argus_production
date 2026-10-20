# DEPLOY-189 step 01 — evidence: vm-095 to main 2c7248b, the UI with Map and Metrics (2026-10-20, conantkd, session 7ae70b96a6ee)

Goal: run on vm-095 what merged since `dfa7332` (DEPLOY-176):
- T-0045 B6 (#184): `GET /api/v1/target-metrics` and `GET /api/v1/overview`, and their two edge locations;
- the B5 follow-up (#185): `db-check` proves migration 007;
- the UI image built with `VITE_ARGUS_INSIGHTS=1` (#164). It merged on 2026-10-17, but no deploy since rebuilt
  `argus-v18-ui` (DEPLOY-166 and DEPLOY-176 changed the agent image only), so the Map and Metrics tabs were not served.

The rest (#186, #187, #189) is Brain only. No migration: 008 comes with B7 (#188, in review).

Leases: vm-095 and vm-166 (the agent changes). vm-166 itself was not changed (no file under `services/` or `ops/`
changed). Commands: [`code.bash`](code.bash). Times are UTC. No key, address or project id is written here
(`policies/SECURITY.md` rule 4).

| Block | Observed | Result |
|---|---|---|
| D.0 laptop | both leases claimed (`DEPLOY-189`); markers `holder=conantkd session=7ae70b96a6ee` on both VMs | OK |
| D.1 before | `commit=dfa73326026b` `ref=dfa7332`; `LAB BASELINE OK`; `nonint-check before` saved (54 lines); mem available 4168 MiB | OK |
| D.1 backup, deploy | `BACKUP OK` (2351409 bytes, 03:26); `DEPLOY OK: 2c7248b48c09 (2c7248b)` | OK |
| D.1 migrate | 001 to 007 already applied, nothing new; schema 001 to 007 | OK |
| D.1 build | agent, worker and scheduler `Recreated` and `Started` (first try) | OK |
| D.2 UI | `argus-v18-ui` `Recreated`, `Started`; `running health=healthy restarts=0`; ports 80 and 443 only; **insights in bundle: 1** (the Map and Metrics calls are built in) | OK |
| D.3 | `health 200`; the three on ONE image `5da4fe392026`, `restarts=0`; no startup errors in agent or worker; **`23/23 database checks passed`** (#185's read included); B6 modules import; through the edge without a login: `/api/v1/overview` 401, `/api/v1/target-metrics` 401 (the new locations exist and need a login), `/topology` 401, `/incidents/inc_smoke/metrics` 401, `/me` 401, `/docs` 404; `55/55 checks passed`; `WRITE GATE CLOSED`; `commit=2c7248b48c09` `ref=2c7248b`; `LAB BASELINE OK`; `NO INTERFERENCE: non-Argus objects unchanged`; mem available 4219 MiB | OK |

CI on `main` for `2c7248b`: `ci` success.

## Notes

- **Not yet done: D.4**, the browser click-through by a person (Dashboard "System map", the incident Map and Metrics
  tabs as operator/approver, the plain map as viewer). Record its result in the review of this PR.
- **Rollback, if needed:** `deploy.sh dfa7332 --as conantkd`, then the compose commands of D.1 and D.2. No migration
  to undo.
