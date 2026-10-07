# T-0019 batch 1 step 03 — evidence (2026-10-07, conantkd, session 3307114120d3)

Goal: deploy the db-probe on vm-166 with its secrets and the lab database (testing only), give the agent on vm-095
the same token, and prove Argus reads `database.health`. All blocks were run by the agent over SSH (S3.2 from the
laptop through a pipe); nothing needed a password; no secret was printed (only file modes and a match verdict).

Key output lines from output.bash, SANITIZED (no addresses, no secrets, no personal names).

| Block | Check | Observed | Result |
|---|---|---|---|
| S3.1 vm-166 | session, tunnel | `SESSION OK`; `tunnel key permits 18704: 1` | OK |
| | checkout | `DEPLOY OK: 78afa315f282 (task/T-0019-db-probe)` | OK |
| | secrets (generated on vm-166) | `600 0:0 …/db_probe_token`; `400 70:70 …/lab-db/postgres_password`; `400 70:70 …/lab-db/monitor_password` | OK |
| | lab database | `argus-lab-db` created, `health=healthy` after ~20 s; `argus_monitor|f|t|3` (not superuser, member of `pg_monitor`, connection limit 3); `max_connections` = 20 | OK |
| | target services | `config --services` lists `argus-v18-db-probe` (profile `db` from `vm-166.env`); the 4 services recreated + the db-probe started; `argus-lab-api` / `-cache` untouched | OK |
| | probe on the host | `loopback 18704 healthz: 200`; `health 200 ok=True max_connections=20 reserved=3 usable=17 client_connections=0 usage 0.0 lock_waits=0`; `sql text in answer: False`; `not allowlisted: 400` | OK |
| | lab and isolation | `ref=task/T-0019-db-probe`; `LAB BASELINE OK` (now with `argus-lab-db`); `NO INTERFERENCE` | OK |
| S3.2 laptop | the agent's copy of the token | `400 10010:10010 …/agent/vm-166/db_probe_token`; `TOKEN COPY MATCH` | OK |
| S3.3 vm-095 | checkout + agent | `DEPLOY OK: 78afa315f282`; agent recreated; `health 200`; `no startup errors` (the new executor has its token) | OK |
| | phase3_check through the tunnel, agent tokens | 5 new checks PASS: health 200 `0/17 max=20`; no SQL text; outside allowlist 400; another service's token 401; POST 405. **33/33 checks passed** | OK |
| | the agent's code path (capability + executor + token + tunnel + redaction, no incident) | `capability inspect_database_health level 3 status ok`; *"database argus-lab-db (argus_lab): 0/17 client connections (0.0% of usable; max_connections=20, reserved=3); by state: none; top clients: none; longest open transaction: none; lock waits=0, blocked sessions=0"* | OK |
| | lab and isolation | `LAB BASELINE OK`; `NO INTERFERENCE` | OK |

nonint-check: NO INTERFERENCE on vm-166 (yes) and vm-095 (yes).

**Result:** batch 1 is deployed on both VMs (`78afa31`). The probe reads only system views through a role that
cannot read tables, and Argus reads it with `inspect_database_health`. Not shown here: a model choosing the tool in
an investigation. No enabled class carries the tag `database` yet; that comes with SC-04
(`postgresql_connection_exhaustion`), which will also fill the 17 slots. The vm-095 agent now also runs `a90400e`
(`knowledge.runbook` Level 3).
