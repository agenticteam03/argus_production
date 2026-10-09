# T-0022 step 02 — evidence: discovery for phase 7 (2026-10-08, conantkd, session d77b4b79ab5a)

Read-only, run by the agent over SSH on both VMs. Sanitized: no addresses, no keys.

| Check | vm-095 | vm-166 |
|---|---|---|
| CPU, architecture, cgroup | 1 vCPU, `aarch64`, `cgroup2fs` | same |
| Memory | 5900 MiB total, 4779 available; Argus containers ~410 MiB in use | 5909 MiB total, 4896 available; Argus ~190 MiB |
| Root disk | 96G, 83G free (15 %) | 49G, 36G free (28 %) |
| Argus ports in use (18000-18799) | 18000 | 18090, 18701, 18702, 18703, 18704 — **18091 free** |
| Docker networks (ours) | `argus-v18-core` 172.30.0.0/24, `argus-v18-mon` 172.30.1.0/24, `argus-lab-app` 172.30.2.0/24 | `argus-v18-mon`, `argus-lab-app`; other projects' networks not touched |
| Images present | `prom/prometheus:v3.5.0` | `prom/alertmanager:v0.34.0`, `quay.io/prometheus/node-exporter:v1.12.1`, `ghcr.io/google/cadvisor:v0.60.5`, `prom/prometheus:v3.5.0` (+ another deployment's `v3.14.0`) |
| Registry reachable | Docker Hub 401, gcr 401 (reachable, auth required) | same |
| Tunnel account `permitopen` | — (client side) | `127.0.0.1:18090`, `:18701`, `:18702`, `:18703`, `:18704` |

**Decisions from this:**
- The same image tags on both hosts: those already on vm-166 (nothing to pull there; using an image changes nothing
  of another deployment).
- The three new containers join `argus-v18-mon`; no new network.
- vm-166 Alertmanager on `127.0.0.1:18091`, one more `permitopen` and one more tunnel forward.
- 1 vCPU: cAdvisor limited (`--docker_only`, 30 s housekeeping, only the metrics used, a CPU limit).
