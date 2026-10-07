# T-0020 step 02 — evidence (2026-10-07, conantkd, session 3307114120d3)

Goal: deploy SC-04 detection on both VMs (no scenario yet). Run by the agent over SSH; no secret printed.

| Block | Check | Observed | Result |
|---|---|---|---|
| D.1 vm-166 | checkout | `DEPLOY OK: a102bd5083bd (task/T-0020-sc04-pg-connections)` | OK |
| | secrets | `400 70:70 …/lab-db/app_password`; `500 65534:65534 …/prometheus`; `400 65534:65534 …/prometheus/db_probe_token` | OK |
| | lab database recreated | `argus-lab-db` healthy; roles `argus_lab_app|f|-1`, `argus_monitor|f|3` | OK |
| | target services + Prometheus | rebuilt / recreated; `up{job="argus-v18-db-probe"} = 1`; `argus_db_connections_used = 0`, `usable = 17`; `DbConnectionsExhausted` count 0 | OK |
| | lab and isolation | `LAB BASELINE OK`; `NO INTERFERENCE` | OK |
| D.2 vm-095 | checkout + Prometheus + agent | `DEPLOY OK: a102bd5083bd`; Prometheus and agent recreated; `health 200`; `no startup errors`; classes `container_restart_loop`, `dependency_unavailable`, `health_check_failed`, `postgresql_connection_exhaustion` | OK |
| | lab and isolation | `LAB BASELINE OK`; `NO INTERFERENCE` | OK |

nonint-check: NO INTERFERENCE on vm-166 (yes) and vm-095 (yes). The pushes of this step first failed with GitHub
`Internal Server Error` (writes only, ~6 minutes); a retry loop pushed at 17:01 UTC.
