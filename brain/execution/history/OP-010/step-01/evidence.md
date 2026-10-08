# OP-010 step 01 — evidence: the db-probe keeps a slot of its own; SC-04 at 100 % (2026-10-08, conantkd, session d77b4b79ab5a)

Mutating, vm-166 only, run by the agent over SSH with Luis's go (`code.bash` in this folder). Sanitized: no
addresses, no secrets.

| Check | Result |
|---|---|
| Session, nonint before | `SESSION OK`; baseline saved (63 lines) |
| Deploy | `DEPLOY OK: 81716ae0ae04 (task/OP-010-reserved-slot)` |
| Target services | rebuilt; read-gateway, host-probe, db-probe recreated; network-probe, exporter started |
| `argus-lab-db` | recreated with `reserved_connections=1`, Up (healthy) |
| Probe before the leak | `argus_db_up=1`, `usable=16`, `used=0`, **`argus_db_monitor_slot_reserved=1`** |
| SC-04 at 100 % (`SC04_SESSIONS=16`) | "leaker: opened 16 sessions"; 23:28:30-23:33:33 every sample `up=1 used=16` (the probe never locked out) |
| Signal and alert | `usage_5m` = **1** at 23:33:03 (5 min); `DbConnectionsExhausted` firing at 23:33:33 |
| vm-166's Alertmanager (T-0022 path) | `['DbConnectionsExhausted']` active |
| Reset | leaker removed; `used after reset=0`; `ref=task/OP-010-reserved-slot`; **LAB BASELINE OK** |
| nonint after | **NO INTERFERENCE: non-Argus objects unchanged** |

**Before (T-0020):** 17 ordinary slots shared by the leaker and `argus_monitor`; at 17 of 17 the probe could not
connect (only `argus_db_up 0`, no usage value, the class could not match). SC-04 therefore ran at 16 of 17 only.

**Notes:**
- A first extraction of the block picked the wrong `M.1` (the T-0020 AFTER-MERGE block earlier in `code.bash`): it
  ran only the SESSION grep (`NOT YOUR SESSION`, its `<you>` placeholder) and `nonint-check before`, then stopped at
  a syntax error on `<you>`. Nothing was deployed or changed; the correct block then ran from the start.
- Not run here: the diagnosis at 100 % (`argus diagnose` on vm-095). vm-095's agent runs `task/T-0021-tool-isolation`,
  which has no `postgresql_connection_exhaustion` class. It runs with T-0022 step 5, after #36 and #38 merge.
