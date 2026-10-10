# T-0028 step 02 — evidence: SC-06 on vm-166, a burner throttled at its CPU quota (2026-10-10, conantkd, session d550d6afba41)

Mutating (vm-095: agent image, Prometheus rules; vm-166: target services, Prometheus rules, the lab burner), run by the
agent over SSH on the proof branch `task/T-0028-vm-proof` (= `task/T-0027-blind-spot`, which the VMs ran, + this
task). `code.bash` in this folder. Sanitized: no addresses, no secrets.

**Run 1 (`0b6603f`, 00:44–01:11 UTC): two defects found, fixed in this task.**

| Check | Result |
|---|---|
| State probe | both VMs on `task/T-0027-blind-spot` `c27546f`, LAB BASELINE OK, NO INTERFERENCE |
| Deploy | both VMs `DEPLOY OK: 0b6603fed74b`; vm-095 agent image + Prometheus; vm-166 target services rebuilt (gateway `cpu_limit_cores`), Prometheus; `argus-lab-burner` started 00:44:53 (`NanoCpus=300000000`, 30.8 % CPU) |
| Defect 1 | `ContainerCpuThrottled` **never fired**: cAdvisor stamps its samples at each housekeeping, **35–53 s apart**, so `rate(...[1m])` was mostly empty (the burner: 5823 of 5825 periods throttled; `rate[2m]`/`[3m]` = 1.0). Fix: `[3m]` in the signal and the alert (`ffa209d`, then the alert fired at 01:08:16) |
| Defect 2 | the alert also fired for **`argus-lab-api` on both hosts** (61 % of its active periods throttled at **4 %** of its 0.2-core quota: bursty health checks) and two api incidents were diagnosed `cpu_saturation` (`inc_27edfd9d373b`, `inc_cc6d756b40e6`). The throttled share counts only the periods a container ran in. Fix: the class and the alert also need **≥ 80 % of the quota used** (`container_cpu_quota_used_ratio_5m`); on vm-166's Prometheus the api read 0.037 and the new alert was empty |
| Burner incident, run 1 | `inc_161c6400a984` DIAGNOSED `cpu_saturation` (RB-006 H5); burner removed 01:11:13 |

**Run 2 (`ed689b0`, the quota condition; agent processes recreated so they load the new signals).**

| Check | Result |
|---|---|
| Deploy | both VMs `DEPLOY OK: ed689b08ac63`; vm-095 agent, worker, scheduler recreated; Prometheus on both; burner started 01:17:08 |
| False positives | the api alerts stopped (none active from 01:23); their occurrences resolved (T-0026); no api alert since |
| Alert | `ContainerCpuThrottled` for `argus-lab-burner` pending 01:26:01 (the 3m rates refill after the Prometheus restart), firing **01:31:01** |
| Incident | pass 01:31:09 `{'started': 1}` → **`inc_39bbec3df928`**, `cpu_saturation`, **DIAGNOSED, confidence high**, root cause `vm-166/container:argus-lab-burner`; findings "100% of its CPU periods throttled … it uses 100% of its CPU quota"; the model: quota-constrained (H5), the host had spare capacity (32 % busy), "do not restart or kill speculatively"; reads `container.resources`, `host.cpu` |
| Reset | burner removed 01:33:33; no active alert 01:33:51; the occurrence resolved 01:34:09 |
| Baseline | both VMs on `ed689b0`, LAB BASELINE OK, no burner, **NO INTERFERENCE** |

**Result:** SC-06 DIAGNOSED from the pulled alert, with no false positive. The VMs stay on the proof branch until the
stack and this task merge; then both go to `main`.
