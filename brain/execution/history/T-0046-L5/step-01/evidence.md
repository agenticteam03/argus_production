# T-0046 L5 step 01 — evidence: vm-095 to main 2324186, link recording on (2026-10-21 UTC, conantkd, session 803eaa13bf32)

Goal: turn the link recorder on (ACR-0025 §3.1, T-0046 L5) now that a scheduler restart is no transition (#231), and
check it on the lab. Also deployed: #234 (the gateway envelope is not a dropped field), #232 and #233 (tests and CI
only). vm-166 does not change. Run by conantkd's agent over ssh at conantkd's request. Commands:
[`code.bash`](code.bash). No key, address or token is written here.

| Block | Observed | Result |
|---|---|---|
| D.0 | both leases claimed (`T-0046-L5-deploy`); markers on both VMs; vm-166 `ref=bdcd048`, `LAB BASELINE OK`, `nonint-check before` saved (63 lines) | OK |
| D.1 vm-095 | `SESSION OK`; `ref=a4479df`, `LAB BASELINE OK`, `before` saved (54 lines); `BACKUP OK` (2380312 bytes, 18:12); `DEPLOY OK: 232418612a85 (2324186)`; no migration (schema 001 to 011); agent, worker, scheduler `Recreated`, `Started`; `health 200` | OK |
| D.2 vm-095 | one image `a548c3690576`, `restarts=0`; scheduler `link states: 4 owner(s) recorded`, first tick `4 link change(s) recorded`, next tick `0`; `35/35 database checks passed`; `AUDIT CHAIN OK: 8 rows chained, 3893 written before the chain`; `link_event`: 4 rows, one per declared container link: `argus-lab-api → argus-lab-cache` `ok` (0.5 ms); `argus-lab-client → backend`, `leaker → db`, `nginx → slow` `unknown` | OK, see note |
| D.3 vm-095 | scheduler restarted: `4 link change(s) recorded` (the startup row), then `0`; rows 4 → 8; `api → cache` `since` stays `18:13:04` | OK: #231 holds |
| D.4 | vm-095: `restarts=0`, `55/55 checks passed`, `WRITE GATE CLOSED`, `ref=2324186`, `LAB BASELINE OK`, `NO INTERFERENCE`; vm-166: `ref=bdcd048`, `LAB BASELINE OK`, `NO INTERFERENCE`; both leases released | OK |

## Notes

- **The three `unknown` links are right:** their owners (`argus-lab-client` SC-07, `argus-lab-leaker` SC-04,
  `argus-lab-nginx` SC-08) are `profile: scenario` containers that are not running, so nothing probes their links;
  missing data is `unknown`, never healthy. Only `api`, `cache` and `db` run on vm-166 between scenarios.
- **Left for L5:** SC-03 and SC-07 once each, to see the transitions recorded in the right order against the errors.
  They start lab scenarios on vm-166 (and an investigation), so they wait for conantkd's go.
- **Rollback:** `link_states.enabled: false` and restart the scheduler; the rows stay (insert-only).
