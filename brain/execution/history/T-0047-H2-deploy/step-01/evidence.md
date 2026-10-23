# T-0047 H2/H3 deploy step 01 — evidence: vm-095 to main 6c83da3, migration 012 (2026-10-21 UTC, conantkd, session e8bc76e91b9d)

Goal: run on vm-095 T-0047 H2 (#236: migration 012 `incident_hypothesis`, the ranking, `state_hypotheses`, the
context slot) and H3 (#237: the hypotheses in the incident answer), with the migration before the image. vm-166 does
not change. Run by conantkd's agent over ssh at conantkd's request ("si haz la migración"). Commands:
[`code.bash`](code.bash). No key, address or token is written here.

| Block | Observed | Result |
|---|---|---|
| D.0 | both leases claimed (`T-0047-H2-deploy`); markers on both VMs; vm-166 `ref=bdcd048`, `LAB BASELINE OK`, `nonint-check before` saved (63 lines) | OK |
| D.1 vm-095 | `ref=2324186`, `LAB BASELINE OK`, `before` saved (54 lines); `BACKUP OK` (2416766 bytes, 20:18); `DEPLOY OK: 6c83da35c0f6 (6c83da3)`; **`+ 012_incident_hypothesis applied`**, schema 001 to 012; agent, worker, scheduler `Recreated`, `Started`; `health 200` | OK |
| D.2 vm-095 | one image `450b941cbb58`, `restarts=0`; no error in the agent or the worker (the scheduler's 4 matches are its `argus_probe_error` queries, not errors); **`38/38 database checks passed`** (012's included); `AUDIT CHAIN OK: 84 rows chained, 3893 written before the chain`; without a login `/api/v1/topology`, `/me` 401, `/docs` 404; `55/55 checks passed`; `WRITE GATE CLOSED`; `ref=6c83da3`; `LAB BASELINE OK`; `NO INTERFERENCE`; `incident_hypothesis` empty (no model run since) | OK |
| D.3 | vm-166 `NO INTERFERENCE`; both leases released | OK |

## Notes

- The first rows arrive with the next model-strategy investigation (for example SC-01: `container_restart_loop`);
  `dependency_unavailable` runs the deterministic baseline (D-003) and states no hypotheses.
- **Rollback:** `deploy.sh 2324186 --as conantkd` and the compose command of D.1; migration 012 stays.
