# DEPLOY-195 step 01 — evidence: both VMs to main bdcd048, B8 and the redaction fix (2026-10-20, conantkd, session ad0eb3554825)

Goal: run what merged since `2c7248b` (DEPLOY-189):
- T-0045 B8 (#192): the exporter's `argus_probe_error`, and the map's finer link reasons;
- the redaction fix (#195): a token glued to a non-ASCII letter is masked.

The rest (#191, #194) is Brain only. No migration: 008 comes with B7 (#188, in review).

Run by conantkd's agent over ssh while conantkd was away; conantkd authorized taking the leases and deploying.
Commands: [`code.bash`](code.bash). Times are UTC. No key, address or project id is written here
(`policies/SECURITY.md` rule 4).

| Block | Observed | Result |
|---|---|---|
| D.0 laptop | both leases claimed (`DEPLOY-195`); markers `holder=conantkd session=ad0eb3554825` on both VMs | OK |
| D.1 vm-095 before | `commit=2c7248b48c09` `ref=2c7248b`; `LAB BASELINE OK`; `nonint-check before` saved (54 lines); mem available 4268 MiB | OK |
| D.1 vm-095 | `BACKUP OK` (2353823 bytes, 05:20); `DEPLOY OK: bdcd0485e5b4 (bdcd048)`; schema 001 to 007 (nothing new); agent, worker, scheduler `Recreated`; target services (exporter, network-probe, host-probe, read-gateway) `Recreated` | OK |
| D.2 vm-166 | before: `commit=ccc810eb622c` `ref=main`, `LAB BASELINE OK`, `nonint-check before` saved (63 lines); `DEPLOY OK: bdcd0485e5b4 (bdcd048)`; target services (exporter, network-probe, read-gateway, host-probe, db-probe) `Recreated`; `failure_kind` in the exporter image; `argus_probe_success{owner="argus-lab-api"} = 1`; `count(argus_probe_error) = 0` (no probe failing); every `argus-v18-*` up; `commit=bdcd0485e5b4` `ref=bdcd048`; `LAB BASELINE OK`; `NO INTERFERENCE` | OK |
| D.3 vm-095 | `health 200`; the three on ONE image `9a902825d866`, `restarts=0`; no startup errors; `23/23 database checks passed`; in the worker, a glued token is masked: `True`; B8's reasons present and `ProbeSample.error_kind`: `True`; map 15 nodes, 6 edges, states ok / read / unknown, no reason (nothing broken), no address; through the edge without a login `/api/v1/topology`, `/overview`, `/me` 401, `/docs` 404; `55/55 checks passed`; `WRITE GATE CLOSED`; `commit=bdcd0485e5b4` `ref=bdcd048`; `LAB BASELINE OK`; `NO INTERFERENCE`; mem available 4327 MiB | OK |

## Notes

- **vm-166** moved from `ccc810e` (main of 2026-10-17) to `bdcd048`: its target services are rebuilt on the current
  code, B8's exporter included.
- **A broken link with its new reason was not seen live:** no probe was failing. It shows during a scenario that
  breaks a dependency (SC-03, SC-07).
- **Rollback, if needed:** `deploy.sh 2c7248b --as conantkd` on vm-095 (`ccc810e` on vm-166), then the compose
  commands of D.1 and D.2. No migration to undo.
