# OP-005 step 02 — evidence: young restarts counted on the VMs; an exporter restart invents none (2026-10-09, conantkd, session 21a9ce710773)

Mutating, both VMs, run by the agent over SSH on `conantkd`'s order; D.1 (`argus diagnose`, needs the password) run
by `conantkd` (`code.bash` in this folder). Sanitized: no addresses, no secrets.

| Check | Result |
|---|---|
| Session, nonint before | `holder=conantkd` on both; baselines saved (vm-095 54 lines, vm-166 63 lines) |
| vm-095 deploy | `DEPLOY OK: b26effa3fb4f (task/OP-005-young-restarts)` (`main` + OP-005); agent, worker, scheduler, target services and Prometheus rebuilt; `/opt/argus-v18/secrets/prometheus` created on purpose (empty, root, 0755: `main`'s monitoring compose mounts it, review of PR #38) |
| vm-095 tools | `ARGUS_TOOL_CATALOGUE=mcp`; **TOOLS ISOLATION OK**; agent `signals.yaml` has the new `restarts_10m`; Prometheus has `argus_container_created_seconds` |
| vm-166 deploy | `DEPLOY OK: 4247dc817fd4 (task/OP-005-vm166-proof)`: the OP-010 stack (T-0022, OP-010) with `main` and OP-005 merged, so vm-166 keeps its Argus-owned Alertmanager and the reserved slot; target services and Prometheus rebuilt |
| vm-166 metric and rule | `argus_container_created_seconds`: 3 series (the existing allowlisted containers); `ContainerRestartLoop` loaded with the new expression |
| SC-01 start | `argus-lab-worker` created 09:52 UTC |
| **Young count** | Prometheus counter **3** at container age 41 s: **new `restarts_10m` = 3**, old `max - min` = **1** (Docker was already at 5: exporter lag) |
| Alert | `ContainerRestartLoop` firing 09:53:09 UTC, present in vm-166's Alertmanager |
| D.1 diagnosis | `inc_312b18f2d8a8` **DIAGNOSED**, `container_restart_loop`, RB-001 recalled, root cause `argus-lab-worker`, every read on vm-166 (`container.status`, `metrics.memory_history`, `container.events`, `host.memory`); at detection `restarts_10m=9` (age ~14 min: the ten-minute delta on a continuous series) |
| SC-01 reset | `argus-lab-worker` removed |
| **Old container, exporter restarted** | `argus-lab-api` 187 h old, 0 restarts; `docker restart argus-v18-exporter` 10:08:27; 9 reads over 3 min: `restarts_10m(api)=0`, max over every container 0, no `ContainerRestartLoop` firing |
| After | vm-166 and vm-095: **LAB BASELINE OK**, **NO INTERFERENCE: non-Argus objects unchanged** |

**Result:** OP-005 verified on the VMs. vm-095 runs `task/OP-005-young-restarts` `b26effa`; vm-166 runs
`task/OP-005-vm166-proof` `4247dc8` (to be replaced by the merged stack once T-0022 and OP-010 merge).
