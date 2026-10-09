# T-0022 step 04 — evidence: vm-166 monitoring services and tunnel permitopen (2026-10-08, conantkd, session d77b4b79ab5a)

Mutating, vm-166 only, run by the agent over SSH with Luis's go (`code.bash` in this folder). Sanitized: no
addresses, no keys.

| Check | Result |
|---|---|
| Session, nonint before | `SESSION OK`; baseline saved (62 lines) |
| Deploy | `DEPLOY OK: dde432f6edaa (task/T-0022-alerting)` |
| Tunnel account `permitopen` | `127.0.0.1:18090`, **`:18091`**, `:18701`-`:18704` (backup `authorized_keys.pre-T0022`) |
| Containers | `argus-v18-alertmanager`, `-node-exporter`, `-cadvisor` (healthy) started; `argus-v18-prometheus` recreated; all Up |
| Scrape jobs | `argus-v18-exporter=1`, `argus-v18-db-probe=1`, `argus-v18-node-exporter=1`, `argus-v18-cadvisor=1` |
| Root filesystem `/` (node-exporter, `pid: host`) | present (`node_filesystem_size_bytes{mountpoint="/"}`): the Docker Desktop gap is closed |
| `host_disk_used_ratio` vm-166 | 0.2741 (step 2: 28 % used) |
| cAdvisor sees `argus-lab-api` | yes (`container_cpu_cfs_periods_total`) |
| Alert rules loaded | 5 |
| Alertmanagers seen by Prometheus | 1 |
| Alertmanager | cluster `disabled` (no gossip); firing now `[]` (lab baseline healthy) |
| Memory / CPU | prometheus 21.9/256 MiB, cadvisor 15.9/128 MiB, alertmanager 10.9/64 MiB, node-exporter 6.6/48 MiB; CPU ≤ 0.1 % |
| `deploy.sh status` | `ref=task/T-0022-alerting`; **LAB BASELINE OK** |
| nonint after | the only difference: `> tcp 127.0.0.1:18091` (the new Argus-owned Alertmanager, in the Argus port range; expected). No protected object changed |

**Notes:**
- The first M.2 run's `q()` helper failed on the VM's Python 3.10 (an f-string with a backslash); the four
  Prometheus queries were re-run read-only with the fixed helper (results above). `code.bash` now has the fix.
- `nonint-check.sh` compares the listener set too, so a new Argus port shows as a difference: expected here. The
  step's expected text was corrected to say so.
- Not yet read from vm-095: the tunnel forward and the scheduler come in step 5 (after #36).
