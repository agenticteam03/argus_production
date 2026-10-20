# DEPLOY-B7 step 01 — evidence: vm-095 to main 999b5bb, T-0045 B7 and migration 008 (2026-10-20, conantkd, session b1fc8fae3d3d)

Goal: run T-0045 B7 (#188: the baseline, the 6h and 24h ranges, deploy events) on vm-095, with migration 008
(`deploy_event`). B8 and the redaction fix were already there (DEPLOY-195). vm-166 does not change: its lease was held
because the agent changes.

Run by conantkd's agent over ssh, at conantkd's request. Commands: [`code.bash`](code.bash). Times are UTC. No key,
address or project id is written here (`policies/SECURITY.md` rule 4).

| Block | Observed | Result |
|---|---|---|
| D.0 laptop | both leases claimed (`DEPLOY-B7`); markers `holder=conantkd session=b1fc8fae3d3d` on both VMs | OK |
| D.1 vm-095 before | `commit=bdcd0485e5b4` `ref=bdcd048`; `LAB BASELINE OK`; `nonint-check before` saved (54 lines); mem available 4339 MiB | OK |
| D.1 vm-095 | `BACKUP OK` (2353933 bytes, 13:08); `DEPLOY OK: 999b5bbe980e (999b5bb)`; `+ 008_deploy_event applied`, schema 001 to 008; agent, worker, scheduler `Recreated`; `health 200`; `deploy recorded: 999b5bbe980e (main) on vm-095 by conantkd` | OK |
| D.2 vm-095 | the three on ONE image `c71b991f0064`, `restarts=0`; no startup errors; `26/26 database checks passed` (B7's `deploy_event` checks included); through the edge without a login `/api/v1/topology`, `/overview`, `/me` 401, `/docs` 404; `55/55 checks passed`; `WRITE GATE CLOSED`; `commit=999b5bbe980e` `ref=999b5bb`; `LAB BASELINE OK`; `NO INTERFERENCE` | OK |
| vm-166 | `nonint-check after`: `NO INTERFERENCE`; `ref=bdcd048`, `LAB BASELINE OK` (unchanged) | OK |
| D.3 vm-095 | the logged-in check of the long ranges and the baseline: **not run** (it asks for an Argus password, which only conantkd types) | pending |
| D.4 laptop | both leases released | OK |

## Notes

- **Not in this deploy:** #203 (a failed baseline read is not kept), approved, not merged yet. It reaches vm-095 with
  the next deploy.
- **D.3 is still to do** by conantkd in their own terminal (the block in `code.bash`): the ranges include 6h and 24h,
  the baseline is on the series with enough data, and a deploy event shows only when an incident's window covers
  this deploy.
- **Rollback, if needed:** `deploy.sh bdcd048 --as conantkd` on vm-095, then the compose command of D.1. Migration 008
  stays (the old image does not read `deploy_event`).
