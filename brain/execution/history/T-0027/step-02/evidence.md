# T-0027 step 02 — evidence: node-exporter stopped on vm-166 opens a monitoring blind spot incident (2026-10-09, conantkd, session f94089c29baa)

Mutating (vm-095: agent image, Prometheus rules; vm-166: Prometheus rules, node-exporter stopped then started), run by
the agent over SSH (`code.bash` in this folder). Sanitized: no addresses, no secrets.

| Check | Result |
|---|---|
| vm-095 | `DEPLOY OK: c27546f5a580 (task/T-0027-blind-spot)`; agent, worker, scheduler recreated; `argus-v18-prometheus` recreated, rule `ArgusScrapeTargetDown` loaded; host classes in the worker image `['monitoring_blind_spot', 'disk_pressure']` |
| vm-166 | `DEPLOY OK: c27546f5a580`; `argus-v18-prometheus` recreated, rule loaded |
| Stop | `argus-v18-node-exporter` stopped 20:05:11; `ArgusScrapeTargetDown` firing (startsAt 20:07:16, the 2-minute `for`) |
| Pass 20:07:52 | `{'started': 1}` → `inc_263f471e33e3` on `vm-166/host:vm-166`: **`monitoring_blind_spot`**, escalated `no_action_escalated`; findings "1 scrape target down on the host's Prometheus: the signals they feed are unknown" and "monitoring blind spot (RB-014): no diagnosis … is claimed"; evidence pack `host.cpu`, `host.memory`; **0 model calls**; reason names `argus-v18-node-exporter` |
| Pass 20:08:52 | `{'duplicate': 1}` |
| Back | node-exporter started 20:09:03; no active alert at 20:09:24 |
| Pass 20:09:53 | `{'resolved': 1}`: the occurrence resolved (T-0026), the escalated incident unchanged |
| Baseline | both VMs on `c27546f`, LAB BASELINE OK, node-exporter up, NO INTERFERENCE; the probe scripts removed |

**Result:** T-0027 done: a host that loses a scrape target is a monitoring blind spot, escalated with evidence and no
model call, never a healthy host. Phase 7's detectors (restart loop, health, dependency, blind spot) are in place.
