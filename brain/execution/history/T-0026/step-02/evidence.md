# T-0026 step 02 — evidence: SC-03's alerts resolve when the cache is back (2026-10-09, conantkd, session f94089c29baa)

Mutating (vm-095: backup, migration 005, agent image; vm-166: checkout; the lab), run by the agent over SSH
(`code.bash` in this folder). Sanitized: no addresses, no secrets.

| Check | Result |
|---|---|
| State probe | both VMs on `task/OP-011-correlation` `cb300df`, LAB BASELINE OK, NO INTERFERENCE |
| vm-095 | `BACKUP OK` (`argus-20261009T183857Z.dump`) before the migration; `DEPLOY OK: ea01c68b7df5 (task/T-0026-alert-resolution)`; schema `… 004_alert_occurrence, 005_alert_resolution`; agent, worker, scheduler recreated (the scheduler image has `resolve_absent`) |
| `argus db check` | **20/20** as `argus_runtime`: insert occurrence, resolve it; `firing` again refused by the trigger; changing its incident and DELETE refused (permission denied) |
| vm-166 | `DEPLOY OK: ea01c68b7df5` (checkout only) |
| SC-03 start | `argus-lab-cache` stopped 18:40:14; `DependencyProbeFailed` startsAt 18:41:46, `ContainerUnhealthy` 18:42:01 |
| Passes while firing | 18:41:56 `{'started': 1}` → `inc_ed6a85ccd28f`, DIAGNOSED `dependency_unavailable`, closed 18:42:19; 18:42:56 `{'attached': 1, 'duplicate': 1}` (concluded, same episode); then `{'duplicate': 2}` ×3: nothing resolved while the alerts were active |
| Cache back | started 18:46:13; no active alert on vm-166's Alertmanager at 18:46:54 |
| Pass 18:46:56 | `{'resolved': 2}`: both occurrences `resolved`, `resolved_at` 18:46:56; audit `incident.alert_resolved` ×2 (`via: absent_from_pull`, `still_firing` 1 then 0) and `incident.alerts_all_resolved` (`incident_status: closed`, `closed: False`) |
| Incident | unchanged: closed, `diagnosed`, closed_at 18:42:19 |
| Pass 18:47:56 | `{}` |
| Baseline | both VMs on `ea01c68`, LAB BASELINE OK, NO INTERFERENCE; the probe scripts removed |

**Result:** T-0026 done. In this pull deployment an alert that stops is noticed in the next pass, each occurrence is
resolved on its own, and a concluded incident is not changed (ACR-0005).
