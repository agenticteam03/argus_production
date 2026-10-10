# DEPLOY-MAIN-2 step 01 — evidence: both VMs from the proof branches to `main` `ebbe9c9` (2026-10-10, conantkd, session 4ef1e84354ce)

Run by the agent over SSH (`code.bash` in this folder). Sanitized: no addresses, no secrets. Both leases for the
deploy; vm-166's released afterwards.

| Check | Result |
|---|---|
| Before | vm-095 on `task/T-0030-vm-proof` `a56f014`, vm-166 on `task/T-0029-vm-proof` `eebfa72`. `main` contains every code line of both proof branches (checked file by file: only moved blocks and extended lines differ); no new migration (004 and 005 already applied) |
| Backup (vm-095) | `BACKUP OK: argus-20261010T124807Z.dump` (12 tables, 12415 rows) before the agent rebuild |
| Deploy | `DEPLOY OK: ebbe9c9c7e6e (main)` on both; `ref=main` |
| vm-166 rebuild | target services (exporter, read-gateway, host-probe, network-probe) rebuilt; Prometheus recreated. Rules loaded: `HttpGatewayErrors`, `ArgusScrapeTargetDown`, `ContainerCpuThrottled` |
| vm-095 rebuild | agent, worker, scheduler (one image) rebuilt, **restarts=0**; target services rebuilt; Prometheus recreated, the same three rules loaded, `count(up == 0)` empty. `argus db check`: **20/20**; `/healthz` ok, LLM configured |
| After | `LAB BASELINE OK`, **NO INTERFERENCE** on both |
| H-1 (run by `conantkd`, shared password) | `argus diagnose vm-166/container:argus-lab-api --check` on vm-095: `inc_ccfcdf8b5758`, **outcome HEALTHY** (cross-host path through the tunnel works on `main`) |

**Result:** both VMs run `main` `ebbe9c9` with T-0026 to T-0030, OP-004 and OP-008 deployed. H-1 is HEALTHY from vm-095
through the tunnel.
