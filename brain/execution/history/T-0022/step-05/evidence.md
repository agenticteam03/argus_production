# T-0022 step 05 — evidence: vm-095 pulls firing alerts from both hosts (2026-10-09, conantkd, session 21a9ce710773)

Mutating, both VMs, run by the agent over SSH on `conantkd`'s order (`code.bash` in this folder). Sanitized: no
addresses, no secrets. Ref `task/OP-010-reserved-slot` `50f33ae` (T-0022 + OP-010 + `main` with #41) on both hosts.

| Check | Result |
|---|---|
| A.1 vm-166 | `SESSION OK`; `DEPLOY OK: 50f33ae23a2e`; checkout only (same code as `4247dc8`); `permitopen` 18090, 18091, 18701-18704; NO INTERFERENCE |
| B.1 vm-095 deploy | `SESSION OK`; baseline 54 lines; `DEPLOY OK: 50f33ae23a2e`; tunnel, agent, worker, scheduler recreated; `argus-v18-alertmanager`, `-node-exporter`, `-cadvisor` created; Prometheus recreated |
| Jobs | vm-095 `up`: exporter, node-exporter, cadvisor = 1; 1 Alertmanager seen by Prometheus |
| Alertmanagers | vm-095 (`argus-v18-alertmanager:9093`) and vm-166 through the tunnel (`argus-v18-tunnel:18091`): status `disabled` (no cluster), nothing firing |
| Scheduler | first pass 10:45:21 `{'vm-095': 'unavailable', 'vm-166': {}}` (vm-095's Alertmanager still starting; vm-166 read anyway); from 10:46:21 `{'vm-095': {}, 'vm-166': {}}` every 60 s |
| Tools | **TOOLS ISOLATION OK** |
| Resources | Prometheus 24 MiB, cAdvisor 18 MiB, Alertmanager 10 MiB, node-exporter 7 MiB; ~0 % CPU; 4670 MiB available |
| After | `ref=task/OP-010-reserved-slot`; **LAB BASELINE OK**; **NO INTERFERENCE** (vm-095: no new host listener; the Alertmanager is on `argus-v18-core` only) |

**Result:** step 5 done.
