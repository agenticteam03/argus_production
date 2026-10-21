# DEPLOY-A4479DF step 01 — evidence: vm-095 to main a4479df, migrations 010 and 011 (2026-10-21 UTC, conantkd, session a33994e2488b)

Goal: run on vm-095 what main gained since DEPLOY-NIGHT (024aa6f): phase 16 step 1 (#223: server-side sessions,
logout, revocation, the persisted login limiter, permissions per route, the audit hash chain, EdDSA ready but off),
ACR-0026 (#210), ACR-0028 field allowlists (#222), #225, T-0046 L3 (#226, `link_states` shipped off) and L4 (#227),
T-0047 H1 (#228, log-only) and React Router 7 (#229). vm-166 does not change: nothing under `services/`,
`deploy/target`, `deploy/monitoring` or `deploy/lab` changed since its `bdcd048`.

Run by conantkd's agent over ssh at conantkd's request ("listo despliega"). Commands: [`code.bash`](code.bash). Times
are UTC. No key, address, token or password is written here.

| Block | Observed | Result |
|---|---|---|
| D.0 laptop | both leases claimed (`DEPLOY-A4479DF`); markers `holder=conantkd session=a33994e2488b` on both VMs | OK |
| D.0b vm-166 before | `commit=bdcd0485e5b4` `ref=bdcd048`; `LAB BASELINE OK`; `nonint-check before` saved (63 lines) | OK |
| D.1 vm-095 before | `SESSION OK`; `commit=024aa6f94406` `ref=024aa6f`; `LAB BASELINE OK`; `nonint-check before` saved (54 lines); mem available 4274 MiB | OK |
| D.1 vm-095 | `BACKUP OK` (2360749 bytes, 16:50); `DEPLOY OK: a4479dfbdee1 (a4479df)`; deploy event recorded; `+ 010_session_login applied`, `+ 011_audit_chain applied`, schema 001 to 011; agent, worker, scheduler `Recreated`, `Started` (the scheduler re-reads `schedules.yaml`); UI `Recreated`, `healthy`; `health 200`; `POST /api/v1/auth/logout` without a token 401 (routed by the edge) | OK |
| D.2 vm-095 | the three on ONE image `3d337d41c674`, `restarts=0`, 0 error lines in 10 min; `35/35 database checks passed`; `AUDIT CHAIN OK: 1 rows chained, 3893 written before the chain (migration 011)`; the scheduler: `audit chain check: every 86400 s`, `security.audit_chain_verified: 0 chained, 3893 before, 0 problem(s)`; no `link states` line (off, as shipped); without a login `/api/v1/topology`, `/me` 401, `/docs` 404; `55/55 checks passed`; `WRITE GATE CLOSED`; `ref=a4479df`; `LAB BASELINE OK`; `NO INTERFERENCE` | OK |
| D.2b ACR-0028 live | through the worker's MCP tools process: `container.logs` (3 keys kept), `container.detailed_logs` (5), `container.search_logs` (6), `host.kernel_oom_records` (8), `host.top_cpu` (7), `host.top_memory` (7) all `ok`; each dropped exactly `host` and `role` | OK, see note |
| D.4 vm-166 after | `ref=bdcd048` unchanged; `LAB BASELINE OK`; `NO INTERFERENCE` | OK |
| D.4 laptop | both leases released | OK |

## Notes

- **ACR-0028 on real gateway answers:** the declared paths match what the read gateway returns; the minimized values
  keep the read's data. The only names dropped are `host` and `role`, the envelope the gateway adds to every answer
  (`services/target/service.py`). The attribution guard reads `host` before minimization (`tooling/dispatch.py`),
  so it still works. **Follow-up:** because the envelope is always dropped, every sensitive read's audit carries
  `dropped_fields: ["host", "role"]`, which hides a real new field among them; the envelope should be left out of
  `dropped_fields`.
- Not exercised live: `database.health` (given the API container, not a database: `invalid_args`, correct),
  `host.service_config` (`forbidden`: the unit is not allowlisted, correct), and four reads that need a specific
  argument (`host.directory_sizes`, `host.journal`, `host.process_details`, `host.read_file`); the canary tests of
  #222 cover their paths.
- **The audit chain starts here:** the 3893 rows written before migration 011 have no hash and are reported as
  "before the chain"; every row from now on is chained. EdDSA stays off: no `jwt_ed25519_key` is installed (phase 16
  step 2, conantkd's secret).
- **Every open UI session must log in once:** a token issued before migration 010 has no session row and is refused
  (`security.session_refused`).
- Not run: the logged-in check of D.3 (login, `/me` permissions, logout, the token refused): it needs an Argus
  password typed in a human's terminal. The unit and authorization-matrix tests cover it; conantkd can run it.
- **Rollback, if needed:** `deploy.sh 024aa6f --as conantkd` on vm-095, then the compose commands of D.1.
  Migrations 010 and 011 stay.
