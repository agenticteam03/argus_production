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
  │    forwards :18701-18704, :18090, :18091 (T-0022)   127.0.0.1:18701-18704, 18090 and 18091)
  ├─ argus-v18-agent   API 127.0.0.1:18000             ├─ argus-v18-read-gateway   127.0.0.1:18701
  ├─ argus-v18-postgres (no host port)                 ├─ argus-v18-host-probe     127.0.0.1:18702
  ├─ argus-v18-read-gateway / -host-probe /            ├─ argus-v18-network-probe  127.0.0.1:18703
  │  -network-probe / -exporter (no host ports)        ├─ argus-v18-db-probe       127.0.0.1:18704 (T-0019)
  ├─ argus-v18-prometheus (vm-095 metrics)             ├─ argus-v18-exporter       (internal only)
  ├─ argus-v18-alertmanager (T-0022, no host port)     ├─ argus-v18-prometheus     127.0.0.1:18090
  ├─ argus-v18-node-exporter, -cadvisor (T-0022)       ├─ argus-v18-alertmanager   127.0.0.1:18091 (T-0022)
  └─ argus-lab-api (healthy twin)                      ├─ argus-v18-node-exporter, -cadvisor (T-0022, internal)
                                                       └─ argus-lab-api + argus-lab-cache + argus-lab-db (baseline)
```

- **`argus-lab-db` is for testing only** (T-0019): a lab PostgreSQL (`postgres:16-alpine`, tmpfs, 20 connection
  slots) that gives `argus-v18-db-probe` a database to measure and SC-04 something to exhaust. A production
  deployment does not need it: the probe points at the real database through the inventory (`database` on a
  target). The probe logs in as `argus_monitor` (`pg_monitor` only, connection limit 3); its password and the
  probe's token are in `/opt/argus-v18/secrets/` on vm-166 (the agent's copy of the token on vm-095).
- **The db-probe needs a slot of its own (OP-010), on every database it reads:** PostgreSQL 16
  `reserved_connections >= 1` and `GRANT pg_use_reserved_connections TO <monitoring role>`. Without them a leak of
  every ordinary slot locks the probe out at the worst moment. The probe publishes
  `argus_db_monitor_slot_reserved` (1 = the prerequisite holds) and `inspect_database_health` says so when it does
  not. `argus-lab-db`: `reserved_connections=1`, so 16 ordinary slots.

- **`/srv/argus-lab-fill` is for testing only** (T-0023, SC-05): a 256M ext4 image `/opt/argus-v18/lab/fill.img`,
  loop-mounted (`nodev,nosuid,noexec`) by `ops/lab-fill-mount.sh`; not in `fstab`, so after a reboot it is absent until
  the script runs again (node-exporter has no series for it, the host-probe answers 409, the filler refuses: unknown,
  never the root disk's numbers). node-exporter and the host-probe bind `/` with `rslave` so they see it.
  `--remove` unmounts it and deletes the image.

- The agent reaches vm-095's executors by container name on `argus-v18-core`, and vm-166's through the tunnel
  sidecar (`http://argus-v18-tunnel:18701` …). See `config/inventory.yaml`.
- **Transport profile `restricted-ssh`** (ACR-0002): alerts are **pulled**. The scheduler on vm-095 reads each
  host's Argus-owned Alertmanager (`/api/v2/alerts`; vm-166's through the tunnel on 18091) every 60 s
  (`reconcile_firing_alerts` in `deploy/scheduler/schedules.yaml`). There is no push webhook from vm-166.
- **Argus-owned exporters (T-0022):** `argus-v18-node-exporter` (host view `/:/host:ro`, `pid: host` for the
  host mount table) and `argus-v18-cadvisor` (`/`, `/var/run`, `/sys`, `/var/lib/docker` mounted **read-only**:
  accepted risk, ARCHITECTURE §4.3) on `argus-v18-mon`, no host port. The other deployment's node-exporter and
  cAdvisor on vm-166 are never scraped. Volume `argus-v18-alertmanager` on each host.
- The tunnel's peer address comes from `/opt/argus-v18/hosts.env`; compose for the core needs
  `--env-file /opt/argus-v18/hosts.env`. The peer's SSH host key is pinned in `/opt/argus-v18/secrets/tunnel/known_hosts`.

## 3. Names, places, ports, networks (Argus objects only)

| Kind | Argus uses | Rule |
|---|---|---|
| Container / compose names | `argus-v18-*` (platform), `argus-lab-*` (synthetic workloads) | nothing else is ours |
| Directories | `/opt/argus-v18/app` (code, 0755), `/opt/argus-v18/secrets` (0700 root), `/opt/argus-v18/baseline` (non-interference snapshots), `/opt/argus-v18/hosts.env`; legacy `/opt/argus-runbooks/056b36e` (vm-095, unused after the next agent redeploy) | nothing outside them |
| Ports | 18000–18799, bound to `127.0.0.1` only | never `0.0.0.0` or a public address |
| Docker networks | `argus-v18-core` 172.30.0.0/24 (vm-095), `argus-v18-mon` 172.30.1.0/24, `argus-lab-app` 172.30.2.0/24, `argus-lab-iso` 172.30.3.0/24 (vm-166, exists only while SC-07 runs; T-0018) | explicit subnets; a new range only after a read-only check that it is free on that VM |
| Volumes | `argus-v18-*` (e.g. `argus-v18-pgdata`, `argus-v18-agent-data`) | — |
| Markers (from B6) | `/opt/argus-v18/DEPLOYED` (deployed commit), `/opt/argus-v18/SESSION` (lease holder) | written by `ops/deploy.sh` / the `brain.py start` marker line |
| Deploy key (from B6d) | `/opt/argus-v18/secrets/deploy/` (read-only key for this repository + pinned GitHub host key) | one per VM; registered on GitHub as read-only |

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
