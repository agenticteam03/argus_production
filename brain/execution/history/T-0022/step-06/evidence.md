# T-0022 step 06 — evidence: pulled alerts open incidents, once (2026-10-09, conantkd, session 21a9ce710773)

Mutating (the lab only), run by the agent over SSH (`code.bash` in this folder). Sanitized: no addresses, no secrets.

| Check | Result |
|---|---|
| SC-03 start | `argus-lab-cache` stopped 10:47:15 UTC on vm-166 |
| Alert | vm-166's Alertmanager 10:48:56: `DependencyProbeFailed` (owner `argus-lab-api`, dependency `argus-lab-cache`), then `ContainerUnhealthy` (`argus-lab-api`, its health check needs the cache) |
| Pull | scheduler 10:49:21 `{'vm-166': {'started': 2}}`; 10:50:21 and 10:51:21 `{'duplicate': 2}`: **never twice for one alert** |
| Incidents | `inc_6f6f3aacfef8` (from `DependencyProbeFailed`) and `inc_d02d9c397b7f` (from `ContainerUnhealthy`): principal `alertmanager@vm-166`, trigger `alert`, both **DIAGNOSED**, `dependency_unavailable`, root cause `vm-166/container:argus-lab-cache` |
| Finding | two different alerts on the same target opened **two incidents** at once: ARCHITECTURE §6.4 (correlation: attach to an open incident with the same target and class) is not implemented. Recorded as OP-011; not a T-0022 regression (the webhook would do the same) |
| SC-03 reset | cache started 10:51:03; 0 active alerts 10:51:53; LAB BASELINE OK; NO INTERFERENCE |
| SC-02 on vm-095 | `argus-lab-worker` (crash loop) 10:52:19; scheduler 10:53:21 `{'vm-095': {'started': 1}}`; `inc_842722808d31` principal `alertmanager@vm-095`, **DIAGNOSED**, `container_restart_loop`, root cause `vm-095/container:argus-lab-worker` |
| SC-02 reset | worker removed; next pass 10:54:21 `{'vm-095': {}, 'vm-166': {}}`; LAB BASELINE OK; NO INTERFERENCE |

**Result:** step 6 done. Firing alerts reach Argus by the `restricted-ssh` profile from both hosts, and each alert
opens one incident. Open: OP-011 (one incident per target and class, §6.4).
