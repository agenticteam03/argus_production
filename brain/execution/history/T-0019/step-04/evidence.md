# T-0019 batch 2 step 01 (history step-04) — evidence (2026-10-12, conantkd, session cd4367edd721)

Goal: before writing the host-probe verbs of batch 2, learn what vm-166's kernel offers and what
`argus-v18-host-probe` (root in the container, no extra capability, `/proc` → `/host/proc:ro`, `/` → `/rootfs:ro`)
can read. Read-only; run by the agent over SSH. Process and cgroup names were masked before printing.

| Check | Observed | Consequence for the design |
|---|---|---|
| Session, lab | `SESSION OK`, `LAB BASELINE OK` | — |
| OS | Ubuntu 22.04.5, kernel 6.8 (oracle), aarch64, systemd 249 | — |
| cgroup | `cgroup2fs`; 12 `docker-<id>.scope` cgroups visible under `/rootfs/sys/fs/cgroup/system.slice` | a process's container is read from `/proc/<pid>/cgroup` (`docker-<64 hex>.scope`; seen relative, `0::/../…`, because of the probe's cgroup namespace) |
| PSI | `cpu io memory`, also visible in the probe (`/host/proc/pressure`) | `load` and `io` report pressure stall averages |
| `/proc` | mounted without `hidepid`; the probe sees 206 pids and reads another process's `stat` and `cgroup` | `top_processes` works from `/host/proc`; command name only (`comm`), never `cmdline` or `environ` |
| Host network namespace | the probe reads `/host/proc/1/net/sockstat` (`TCP: inuse 23 orphan 1 tw 2 alloc 56`) and `tcp`/`tcp6` | `socket_summary` reads pid 1's namespace (the host's), not the probe's own |
| Block devices | `sda` (whole disk) | `io` samples `/proc/diskstats` for the devices of `/sys/block` (no partitions, loops or RAM disks) |
| Kernel log | `kernel.dmesg_restrict=1` (no `/dev/kmsg` without `CAP_SYSLOG`); `/var/log/kern.log` (rsyslog, traditional format `Oct  4 00:00:15 host kernel: [uptime] …`) readable in the probe through `/rootfs`; weekly rotation, `kern.log.1` = **301 MB**; the journal is persistent (3.7 GB) | `kernel_oom_records` reads the **end** of `kern.log` and `kern.log.1`, bounded in bytes; no new privilege |
| OOM volume | `oom_kill` since boot (6 days) = 18 567; `kern.log.1` 67 594 OOM lines, `.2.gz` 97 162; journal 37 134 in 7 days; latest on 10-09 (a lab container, `CONSTRAINT_MEMCG`, `cpuset=docker-<id>.scope`) | records are counted and grouped by container id; only the last few are listed |
| Directory walk | `/`: 181 531 entries (capped at 200 000) in 11.1 s from the host; `/srv/argus-lab-fill`: 2 entries, 22 ms | `directory_sizes` is bounded in entries and time and says when it is partial; `/` will usually be partial |
| Probe headroom | 15 MiB of 64 MiB, CPU 0.01 % | reads stay within the 64 MiB limit (bounded buffers) |
| Memory | 4 843 MB available | — |
| Isolation | `NO INTERFERENCE: non-Argus objects unchanged` | — |

**Result:** nothing blocks batch 2, and no new mount or privilege is needed: every verb reads what the probe already
mounts. The kernel's OOM records come from rsyslog's `kern.log` (the same kernel messages as the journal, as text),
because the probe has no `journalctl` and `/dev/kmsg` needs `CAP_SYSLOG`.
