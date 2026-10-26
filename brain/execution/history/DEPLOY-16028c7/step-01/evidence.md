# DEPLOY-16028c7 step 01 — evidence: vm-095 to main 16028c7, migrations 014 and 015 (2026-10-26 UTC, conantkd)

Goal: run on vm-095 T-0046 L6 (#322: probe history replayed from a per-link cursor, migration 014) and phase 18 (#323:
the offline supervised action path, migration 015). Phase 18 adds no route, gateway or wiring; `write_gate.open` stays
empty. No UI, contract or compose change; vm-166 does not change. Run by conantkd's agent over ssh at conantkd's
request, both leases (session `13d7ed00`). Commands: [`code.bash`](code.bash). Sanitized: no name, address or key.

| Block | Observed | Result |
|---|---|---|
| D.1 vm-166 | marker; `before` saved (63 lines) | OK |
| D.2 vm-095 | `ref=01db0d7`, `LAB BASELINE OK`; `before` saved (54 lines); evaluations running: 0; `BACKUP OK` (2480535 bytes, 04:32Z); **`VERIFY OK: 22 tables, 33508 rows match`**; `DEPLOY OK: 16028c787c4d (16028c7)`; **`+ 014_link_probe_cursor applied`**, **`+ 015_remediation applied`**, schema 001 to 015 | OK |
| D.3 vm-095 | agent, worker, scheduler `Recreated`, `Started`; `health 200`; `deploy recorded: 16028c7 (main) on vm-095 by conantkd` | OK |
| D.4 vm-095 | four `running restarts=0` (the UI untouched); error lines 0, 0, 0; **new tables: 9**; **link cursors after a tick: 4**; **`89/89 database checks passed`**; `AUDIT CHAIN OK: 273 rows chained`; `phase 17 live; denied hosts: ['vm-095']`; `audit_digest: enabled: false`; `/me` 401; `ref=16028c7`, `LAB BASELINE OK`; `NO INTERFERENCE` | OK |
| D.5 vm-166 | `NO INTERFERENCE` | OK |

## Notes

1. The leases stay held for the night's further steps (renewed at each step); they are released at the end of the
   session, recorded in its handoff.
2. **Rollback:** `deploy.sh 01db0d7 --as conantkd` and the compose command of D.3; migrations 014 and 015 stay (the old
   image does not read their tables).
