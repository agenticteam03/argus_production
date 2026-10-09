# OP-010 step 02 — evidence: SC-04 at 100 % DIAGNOSED, opened by the pulled alert (2026-10-09, conantkd, session 21a9ce710773)

Mutating (the lab only), run by the agent over SSH (`code.bash` in this folder). Sanitized: no addresses, no secrets.
Both VMs on `task/OP-010-reserved-slot` `50f33ae`.

| Check | Result |
|---|---|
| Leaker | `SC04_SESSIONS=16` started 10:57:12 UTC on vm-166 |
| Probe at 100 % | every minute 10:58-11:02: `argus_db_up=1`, `used=16`, `usable=16`, `argus_db_monitor_slot_reserved=1`: the probe never lost the database |
| Alert | `DbConnectionsExhausted` active in vm-166's Alertmanager 11:02:54 (`for: 5m`) |
| Pull | scheduler 11:03:21 `{'vm-166': {'started': 1}}` |
| Incident | `inc_03e42714762f`, principal `alertmanager@vm-166`, **DIAGNOSED**, `postgresql_connection_exhaustion`, root cause `vm-166/container:argus-lab-leaker`; reads `database.health` (argus-lab-db) and `container.status` (the leaker); diagnosis: 16 sessions held idle in transaction by the leaker, the database is the victim, no lock waits |
| Reset | leaker removed 11:04:00; 0 active alerts 11:04:20; LAB BASELINE OK; NO INTERFERENCE (vm-166 and vm-095) |

**Result:** OP-010 fixed: at 100 % of the ordinary slots the database is still read, the alert fires, and the incident
is DIAGNOSED with the right root cause.
