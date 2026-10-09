# OP-011 step 03 — evidence: SC-03 gives one incident (ACR-0004) (2026-10-09, conantkd, session 75c48aa9bfad)

Mutating (vm-095: agent image; vm-166: checkout; the lab), run by the agent over SSH (`code.bash` in this folder).
Sanitized: no addresses, no secrets.

| Check | Result |
|---|---|
| vm-095 | `DEPLOY OK: cb300dfa69c1 (task/OP-011-correlation)`; schema unchanged (`… 004_alert_occurrence`); agent, worker, scheduler recreated; the ACR-0004 rule present in the image |
| vm-166 | `DEPLOY OK: cb300dfa69c1` (checkout only) |
| SC-03 start | `argus-lab-cache` stopped 13:34:06 UTC |
| Alerts (vm-166 Alertmanager) | `DependencyProbeFailed` startsAt 13:35:31; `ContainerUnhealthy` startsAt **13:36:01** |
| Pass 13:35:57 | `{'vm-166': {'started': 1}}` → `inc_8a4cf92444ae`; DIAGNOSED `dependency_unavailable`, root cause `vm-166/container:argus-lab-cache`, **closed 13:36:22** |
| Pass 13:36:57 | `{'attached': 1, 'duplicate': 1}`: `ContainerUnhealthy … attached to inc_8a4cf92444ae (same target and class dependency_unavailable (concluded, same episode))` |
| Pass 13:37:57 | `{'duplicate': 2}` |
| Incident | **one** incident since the stop: occurrences `DependencyProbeFailed started`, `ContainerUnhealthy attached`; evidence version 2; not reopened (closed 13:36:22) |
| Reset | cache started; 0 active alerts 13:38:55; both VMs on `task/OP-011-correlation`, LAB BASELINE OK, NO INTERFERENCE |

**Result:** OP-011 done. The run reproduced step 02's timing (the second alert pulled one pass after the first incident
closed, having started 21 s before the close) and gave one incident and one diagnosis.
