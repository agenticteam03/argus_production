# T-0019 — Phase 3: the target-side probe verbs, in 3 batches (first: `db-probe` and `database.health`)

| Field | Value |
|---|---|
| Status | `in progress` — batch 1 `done` (PR #27 merged); batch 2 `in progress` 2026-10-12 (`task/T-0019-batch2-host-probe`); batch 3 `planned` |
| Phase | 3 — target services ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md): "DB probe (with SC-04)") |
| Architecture | no change (no ACR): §4.6 (target-side probe services), §4.7 (inspection policy), §12.2 (catalogue) |
| Branch | batch 1: `task/T-0019-db-probe` (PR #27 merged). Batch 2: `task/T-0019-batch2-host-probe` (from `main` 48a895b). Batch 3: its own branch from `main` |
| Owner | `conantkd` (+ agent) |
| Needs the VM lease | the read-only checks, the deploy and the verification (vm-166 target side, vm-095 agent) |

## Goal (plain language)

Argus can read the health of a PostgreSQL database on the target host: how full its connection slots are, which
clients hold them and in which state, long transactions and lock waits — through a probe that runs **on the target
host** with a **read-only monitoring role** and never reads business rows or SQL text. It is the last missing
target-side service of phase 3 and the evidence SC-04 (connection exhaustion, RB-004) will need.

## Scope: 3 batches (decided 2026-10-07, `conantkd`)

ARCHITECTURE §4.6 lists the verbs of the three target-side probes. Implemented today: `host-probe` cpu, memory,
disk, uptime; `network-probe` dns, tcp, http. The rest come in three batches, **one pull request each**, every
batch deployed and verified on vm-166 before the next one starts:

| Batch | Probe verbs (§4.6) → capabilities (§12.2) | Level | Serves |
|---|---|---|---|
| **1** | new `db-probe`: `database_health` → `database.health` | 3 | SC-04 (RB-004, connection exhaustion) |
| **2** | `host-probe`: `load`, `io`, `top_processes`, `socket_summary`, `directory_sizes`, `kernel_oom_records` → `host.load`, `host.io`, `host.top_cpu`, `host.top_memory`, `host.socket_summary`, `host.directory_sizes`, `host.kernel_oom_records` | 2 | SC-05 (disk pressure), SC-06 (CPU saturation), OOM classes |
| **3** | `host-probe`: `journal`, `read_file`, `process_details` (+ `service_config`) under the inspection policy (§4.7); `network-probe`: `connectivity`, `listening_ports`, repeated `tcp_connection` → `host.journal`, `host.read_file`, `host.service_config`, `host.process_details`, `network.connectivity`, `network.tcp_connection`, `network.listening_ports` | 2–3 | SC-08 (nginx upstream), deep diagnosis |

Batch 3 goes last because it reads files and logs: it needs the §4.7 inspection policy (deny patterns win,
redaction, bounds) in `config/policy.yaml` first. It also closes the network-probe gap seen in SC-07 (T-0018 runs 2–3): the
`network-probe` only reports that DNS/TCP fails from the app network, not why, and the model stopped at "DNS failure"
unless it happened to read both sides' status. **Goal for `network.connectivity` (decided 2026-10-07, `conantkd`):**
for a source → destination pair of the inventory, answer the networks of each side, whether they share one, and
DNS/TCP from the source's network — so every "cannot reach" case is explained, not only SC-07 (the general mechanism
of §4.6/§12.2 instead of the tool-description fix of T-0018). Every new Level 3 line in `policy.yaml` is reviewed on its own
(PR #27 note). The detailed design of batches 2 and 3 is written when each starts.

## Batch 2 design (2026-10-12, `conantkd` + agent; from step 01's read-only checks)

**No new mount, privilege or token.** Every verb reads what `argus-v18-host-probe` already mounts read-only
(`/proc` → `/host/proc`, `/` → `/rootfs`), as root in the container without extra capabilities. No shell, no
`cmdline`, no `environ`, no network addresses.

| Probe route | Capability (model name) | Reads | Bounds | Safety class | Tags (who is offered it) |
|---|---|---|---|---|---|
| `GET /load` | `host.load` (`get_host_load`) | `/proc/loadavg` (1/5/15, runnable/threads), cpus, PSI `cpu`/`memory`/`io` (`some`/`full` avg10/avg60) | none needed | SAFE | `cpu` → `container_cpu_saturation` |
| `GET /io` | `host.io` (`get_io_metrics`) | `/proc/diskstats` sampled 1 s apart for the whole devices of `/sys/block` (no loop/ram/zram): read/write KiB/s, IOPS, busy %; PSI `io` | ≤ 8 devices, 1 s | SAFE | `disk` → `disk_pressure` |
| `GET /processes?by=cpu\|memory&n=` | `host.top_cpu` (`get_top_cpu_processes`), `host.top_memory` (`get_top_memory_processes`) | `/proc/<pid>/stat` sampled 0.5 s apart: pid, command name (`comm`, 15 chars), state, CPU % of one core, RSS MiB; the container from `/proc/<pid>/cgroup` (`docker-<id>.scope` → 12-hex id), else `host` | ≤ 4096 pids read, n ≤ 10 | SENSITIVE (process names) | top_cpu: `cpu`; top_memory: `memory` → `container_restart_loop` |
| `GET /sockets` | `host.socket_summary` (`get_socket_summary`) | the host's network namespace (pid 1): `sockstat`, TCP/TCP6 counts by state, listening ports | ≤ 65 536 sockets read, ≤ 20 ports listed; no addresses | SAFE | `sockets` — **offered to no class yet**: the lab's traffic is inside Docker networks, not the host's namespace |
| `GET /directory_sizes?path=` | `host.directory_sizes` (`get_directory_sizes`) | the largest direct children of a **declared mount** (inventory `mounts`, re-checked by the probe), one filesystem (`-xdev`), symlinks not followed | ≤ 50 000 entries and 4 s; says `complete: false` and how much it read when cut | SAFE | `disk` → `disk_pressure` |
| `GET /oom?minutes=` | `host.kernel_oom_records` (`get_kernel_oom_records`) | the end of `/var/log/kern.log` and `kern.log.1` (rsyslog's text copy of the kernel log): `oom-kill:` + `Killed process` records → time, memcg or global, container id, command name, pid, anon RSS; `oom_kill` since boot from `/proc/vmstat` | ≤ 4 MiB read per file, window ≤ 1440 min, last 10 records listed, counts by container | SENSITIVE (process names) | `memory`, `stability` → `container_restart_loop` |

- **All Level 2** (§12.2). Each gets a `config/policy.yaml` line (`max_per_incident`), which is also what offers it
  (wiring offers only capabilities the policy knows).
- **Containers are named by id.** The probe has no Docker socket, so it cannot name a container; it gives the 12-hex
  id that the read gateway's status already returns, and `container.status` now shows that `id=` so the model can
  match them. (Reading Docker's `config.v2.json` to get the name was rejected: that file holds the environment.)
- **Kernel OOM records from `kern.log`, not the journal** (§12.2's note says "from the journal"): the probe has no
  `journalctl` and `/dev/kmsg` needs `CAP_SYSLOG`; rsyslog writes the same kernel messages as text. A host without
  `kern.log` answers `source: unavailable` (unknown, never "no OOM"). Recorded in the PR for review; no ACR (the
  verb, its privilege and its output are §4.6's).
- **Evaluation (§21.2):** the new tools are offered to `container_cpu_saturation`, `disk_pressure` and
  `container_restart_loop`. The replay cases have no answer for the new routes (their `host_probe` `"*"` answer has
  none of the new keys), so the capabilities must show **unknown** when a key is missing, and step 03 re-runs one
  model trial of those three classes to show they did not get worse.

## Steps (batch 2)

1. Read-only checks on vm-166 (what the kernel and the probe container can read). **Done.**
2. Tests first (red), then code: the probe verbs, the capabilities, the policy lines, `container.status` `id=`,
   `phase3_check`.
3. Deploy (target services on both VMs, the agent on vm-095; both leases), verify every verb through the agent's
   code path, NO INTERFERENCE; one model trial of the three classes that are offered the new tools.
4. Brain (plan, task, journal), PR.

## Decisions for batch 1 (2026-10-07, `conantkd`)

- **`argus-lab-db` is always on** (lab baseline on vm-166), **for testing only**: it gives the probe something to
  measure and a healthy reference before SC-04. A production deployment does not need it — the probe points at the
  real database instead. This must be stated in the PR (comment) and where the environment is described
  (`infrastructure/environment.md`, `docs/INCIDENTS.md` targets table, the compose file comment).
- **Driver: `pg8000`** (pure Python, no compiler in the Alpine image), version pinned with hashes.
- **Tool levels:** `database.health` is Level 3; `max_tool_level` is already 3 (fixed in PR #27).
- **Review note from PR #27 (`juanbetancurm`):** with `max_tool_level: 3` the level no longer stops a Level 3
  capability, so every Level 3 line in `config/policy.yaml` deserves its own careful review. `database.health` is the
  first new one: its limit per incident and its allowed targets (only allowlisted databases) are reviewed on their
  own in this task's PR.
- **Branch:** on top of T-0018, as above.

## Design (to confirm step by step)

- **Lab DB:** `argus-lab-db`, `postgres:16-alpine`, profile `base-166`, network `argus-lab-app`, data in tmpfs,
  hard limits, `max_connections=20` (RB-004's lab case), no published port. A role `argus_monitor` with
  `pg_monitor` only (no table privileges); its password generated on vm-166, never printed.
- **Probe:** `ROLE=db_probe` in `services/target/service.py` (one codebase, one role per container), route
  `GET /database/health?name=<allowlisted db>`: max/reserved connections, counts by state and by
  `application_name`, the longest transactions (age, state, wait event — **no query text**), lock waits, usage
  percent. Queries only system views (`pg_stat_activity`, `pg_locks`, `pg_settings`). Token `db_probe`.
- **Deployment:** `argus-v18-db-probe` in `deploy/target/compose.target.yml`, `127.0.0.1:18704` in
  `compose.loopback.yml` (the tunnel already forwards 18704).
- **Agent side:** capability `database.health` (`inspect_database_health`, executor `db_probe`, Level 3), policy
  limit, `db_probe` in `EXECUTOR_KINDS`, inventory (`vm-166/container:argus-lab-db`, executor URL through the
  tunnel), the agent's `db_probe` token (generated on the VMs, never printed). Ordering matters: the agent refuses
  to start when a host executor has no token, so the secrets come before the agent restart.

## Steps (batch 1)

1. Read-only checks on vm-166: PyPI reachable for the image build; nothing on `127.0.0.1:18704`; memory headroom.
2. Tests first, then code (probe, capability, inventory, compose, policy).
3. Secrets (generated on the VMs), deploy, verify: the probe answers for the healthy lab DB, Argus reads it through
   `inspect_database_health`, the answer holds no SQL text and no rows. NO INTERFERENCE.
4. Brain: plan (phase 3 → 100 % for the DB probe), environment, INCIDENTS, journal; PR with the `argus-lab-db`
   "testing only" note as a comment.

## Red seen / evidence

- **Batch 1 step 1 (2026-10-07, read-only, over SSH):** PyPI 200, Docker Hub reachable (postgres image to pull),
  port 18704 free, `argus-lab-app` present, 4.4 GB memory available, docker disk 27 %, NO INTERFERENCE
  ([evidence](../../execution/history/T-0019/step-01/evidence.md)). The tunnel already forwards 18704.
- **Batch 1 step 2 (2026-10-07, code, tests first):** `tests/test_db_probe.py`, 15 tests:
  - **red:** 15 of 15 failed for the right reasons (no `pg_connect` / `DB_QUERIES` / `db_health` / `render_host`,
    `db_probe` not an executor kind, the capability refused as unknown, no compose service, no requirements file,
    no `argus-lab-db`); one test was itself wrong (its regex read `extract(epoch FROM now())` as a table) and was fixed;
  - **green:** 15/15; full suite 118 passed, 6 skipped (124). The driver (`pg8000` 1.31.5 + 4 dependencies, pure
    Python) is pinned with hashes; the db-probe has its own image target (`db`), the other roles stay stdlib-only.
- **Batch 1 step 3 (2026-10-07, both VMs, over SSH):** secrets generated on vm-166 (never printed), the agent's
  copy through a pipe (`TOKEN COPY MATCH`); `argus-lab-db` healthy, `argus_monitor` not superuser, `pg_monitor`,
  limit 3; probe health `0/17`, no SQL text, outside allowlist 400; agent rebuilt, `phase3_check` 33/33;
  `inspect_database_health` status ok through the agent's own code path; LAB BASELINE OK, NO INTERFERENCE on both
  ([evidence](../../execution/history/T-0019/step-03/evidence.md)). A model choosing the tool comes with SC-04 (no
  enabled class has the tag `database` yet).
- **Batch 2 step 01 (2026-10-12, read-only, over SSH, vm-166):** Ubuntu 22.04, kernel 6.8, cgroup v2, PSI `cpu io
  memory`; the probe sees every pid (no `hidepid`) and pid 1's network namespace; `dmesg_restrict=1`; the kernel's OOM
  records are in rsyslog's `kern.log` (weekly rotation; `kern.log.1` = 301 MB; 37 134 OOM lines in 7 days from a lab
  container); walk of `/` from the host 181 531 entries in 11 s, of `/srv/argus-lab-fill` 2 entries; NO
  INTERFERENCE ([evidence](../../execution/history/T-0019/step-04/evidence.md)).
(filled in as the steps run)
