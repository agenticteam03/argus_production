# Environment — the two VMs (no addresses in this file)

Facts are `OBSERVED` (a command returned them; date given) unless marked otherwise. Addresses live only in each
developer's `~/.ssh/config` (template: [`ssh-config.example`](ssh-config.example)) and in `/opt/argus-v18/hosts.env`
on each VM (template: `deploy/hosts.env.example`). **What runs on a VM is authoritative over this file**: check it
with the state probe (`/opt/argus-v18/DEPLOYED`, `docker ps`).

## 1. Hosts

| Argus name | Label | Role | OS / arch | Size | Reach it with |
|---|---|---|---|---|---|
| **`vm-095`** | VM 0.95 | **Host A:** the agent (API, Postgres, tunnel sidecar) + a light target host | Ubuntu 26.04, aarch64 | 1 vCPU, 5.9 GB RAM, no swap | `ssh argus-vm095` |
| **`vm-166`** | VM 0.166 | **Host T:** primary target host + monitoring | Ubuntu 22.04, aarch64 | 1 vCPU, 5.9 GB RAM, no swap | `ssh argus-vm166` |

(`OBSERVED` 2026-10-01.) Both: Docker 29.8 + Compose v5.5, `sudo` without password for the `ubuntu` user, the cloud
provider's default host firewall (only SSH open from outside). All three developers have `sudo` on both VMs.
Both VMs are in the same cloud private network; between them **only port 22 is reachable** — every other port is
filtered by the cloud network rules, which the team cannot change (SSH access only, no cloud console).

Constraints: 1 vCPU each — CPU scenarios must be capped and time-boxed. vm-095 reports "System restart required":
**do not reboot** either VM — they host other workloads; a reboot is a team decision.

## 2. Topology (as built)

```text
vm-095                                               vm-166
 network argus-v18-core 172.30.0.0/24                 Argus services publish on 127.0.0.1 ONLY
  ├─ argus-v18-tunnel (autossh) ───── SSH :22 ───────▶ user argus-v18-tunnel (nologin; may only forward to
  │    forwards :18701-18704, :18090                    127.0.0.1:18701-18704 and 18090)
  ├─ argus-v18-agent   API 127.0.0.1:18000             ├─ argus-v18-read-gateway   127.0.0.1:18701
  ├─ argus-v18-postgres (no host port)                 ├─ argus-v18-host-probe     127.0.0.1:18702
  ├─ argus-v18-read-gateway / -host-probe /            ├─ argus-v18-network-probe  127.0.0.1:18703
  │  -network-probe / -exporter (no host ports)        ├─ argus-v18-exporter       (internal only)
  ├─ argus-v18-prometheus (vm-095 metrics)             ├─ argus-v18-prometheus     127.0.0.1:18090
  └─ argus-lab-api (healthy twin)                      └─ argus-lab-api + argus-lab-cache (baseline)
```

- The agent reaches vm-095's executors by container name on `argus-v18-core`, and vm-166's through the tunnel
  sidecar (`http://argus-v18-tunnel:18701` …). See `config/inventory.yaml`.
- Alerts are **pulled** (v1.8 `ReconcileFiringAlerts` through the tunnel); there is no push webhook.
- The tunnel's peer address comes from `/opt/argus-v18/hosts.env`; compose for the core needs
  `--env-file /opt/argus-v18/hosts.env`. The peer's SSH host key is pinned in `/opt/argus-v18/secrets/tunnel/known_hosts`.

## 3. Names, places, ports, networks (Argus objects only)

| Kind | Argus uses | Rule |
|---|---|---|
| Container / compose names | `argus-v18-*` (platform), `argus-lab-*` (synthetic workloads) | nothing else is ours |
| Directories | `/opt/argus-v18/app` (code, 0755), `/opt/argus-v18/secrets` (0700 root), `/opt/argus-v18/baseline` (non-interference snapshots), `/opt/argus-v18/hosts.env`; legacy `/opt/argus-runbooks/056b36e` (vm-095, unused after the next agent redeploy) | nothing outside them |
| Ports | 18000–18799, bound to `127.0.0.1` only | never `0.0.0.0` or a public address |
| Docker networks | `argus-v18-core` 172.30.0.0/24 (vm-095), `argus-v18-mon` 172.30.1.0/24, `argus-lab-app` 172.30.2.0/24 | explicit subnets |
| Volumes | `argus-v18-*` (e.g. `argus-v18-pgdata`, `argus-v18-agent-data`) | — |
| Markers (from B6) | `/opt/argus-v18/DEPLOYED` (deployed commit), `/opt/argus-v18/SESSION` (lease holder) | written by `ops/deploy.sh` / `brain.py` |

## 4. Protected objects — NEVER touch

A pre-existing, separate Argus deployment (owned by `conantkd`) runs on both VMs, linked by a WireGuard tunnel.
It is **never** stopped, modified, reused, scraped or attached to, unless the team, including `conantkd`, decides
otherwise in an ACR.

| VM | Protected |
|---|---|
| vm-095 | `/opt/argus` (+ `/opt/argus-old-*`, `/opt/argus-backup-*`, `/opt/argus-eval`); compose project `argus`: `argus-api-1`, `argus-worker-1`, `argus-scheduler-1`, `argus-postgres`; network `argus_default`; volume `argus_argus-pgdata` |
| vm-166 | `/opt/argus-lab`; compose projects `gateways`, `monitoring`, `probes`: `prometheus`, `alertmanager`, `cadvisor`, `node-exporter`, `docker-read-gateway`, `host-probe`, `network-probe` |
| vm-166 | the older `labmvp` objects it uses: `lab-victim`, `mvp-exporter`, network `labmvp_default`, volume `labmvp_agent-data`, `/home/ubuntu/lab-agent` |
| both | the WireGuard interface `wg0` (UDP 51820) and its host firewall rules |

`ops/nonint-check.sh before|after` snapshots everything that is **not** ours (containers, networks, volumes,
listening ports, firewall rules, interfaces including `wg0`) and must print `NO INTERFERENCE` after every mutating step.

## 5. Agent on vm-095

| Item | Value |
|---|---|
| API / Swagger | `127.0.0.1:18000` on vm-095 → from a laptop: `ssh -N -L 18000:127.0.0.1:18000 argus-vm095`, then http://127.0.0.1:18000/docs |
| CLI | `sudo docker exec -it -e ARGUS_USER=<your-github-handle> argus-v18-agent argus diagnose <target> --reason "…"` (`--raw` for JSON) |
| Users | one per developer (GitHub handle), role operator, one shared team password |
| Database | `argus-v18-postgres` (Postgres 16), system of record; migrations `ops/db-migrate.sh`; `argus db check` |
| Model | OpenAI `gpt-5.6-luna` via the Responses API (no `temperature`) |
| Runbooks | inside the image (`argus/runbooks/`, D-002); until the next redeploy the running agent reads the mounted `/opt/argus-runbooks/056b36e` |

## 6. Laptop prerequisites (each developer)

Python 3.12+, Git (with `core.autocrlf input`), the GitHub CLI (`gh auth login`), Docker Desktop (for the Postgres
tests), the team SSH key in `~/.ssh/`, and the two aliases from [`ssh-config.example`](ssh-config.example).
