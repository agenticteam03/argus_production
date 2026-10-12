# T-0019 step 08 — batch 3b on the VMs (2026-10-12, conantkd, both leases, session 66378486227b)

Branch `task/T-0019-batch3b-host-verbs` `9ac49ec` (stacked on 3a, #98) on both VMs; they left the 3c branch
(verified in step 07).

## Deploy (B.1)

| Check | vm-166 | vm-095 |
|---|---|---|
| deploy | `DEPLOY OK: 9ac49ec13506`; target services up: 5 | backup `argus-20261012T210205Z.dump`; `DEPLOY OK: 9ac49ec13506`; target services up: 4 |
| agent | — | agent, worker, scheduler recreated, one image `2915950cd605`, running, restarts 0; health 200; 20/20 database checks; `phase3_check` 55/55; WRITE GATE CLOSED |
| after | `ref=task/T-0019-batch3b-host-verbs`, LAB BASELINE OK, NO INTERFERENCE | same |

## The four routes from vm-166 (B.2, loopback port; contents not printed)

The first run of B.2 started one second after the probe was recreated and got no connection (`000` on every route; the
events show the deploy's own recreate at 21:01:28, no crash, restarts 0). Run again:

| Request | Answer |
|---|---|
| `/service_config?target=vm-166/container:argus-lab-nginx` | 200: `default.conf`, contains `proxy_read_timeout 2s`, not truncated |
| `…&path=/etc/passwd` | 403 path not allowed by the inspection policy |
| `/read_file?…&path=/var/log/syslog` | 403 (`files` is empty) |
| `/read_file?…&path=/opt/argus-v18/secrets/host_probe_token` | 403 |
| `/journal?…&unit=docker.service&lines=20` | 200: source syslog, program dockerd, 20 lines, all `dockerd[` |
| `/journal?…&unit=ssh.service` | 403 unit not allowed |
| `/journal?…&lines=201` | 400 lines must be 1-200 |
| `/process_details?target=vm-166/host:vm-166&pid=<dockerd>` | 200: dockerd, S, 31 threads, 127 open files, limit [524287, 524288]; no `cmdline`/`environ` key |
| `/process_details?target=vm-166/container:argus-lab-nginx&pid=…` | 403 process details not allowed for this target |

Probe memory: peak 23 MiB (limit 64), `oom_kill` 0, restarts 0.

## The agent's code path (B.3, vm-095 tools process, no model)

- `inspect_service_config ok`: one file, nginx's configuration with `proxy_read_timeout 2s`. The agent's redactor
  replaced the file's **path** in the text with `[REDACTED HIGH-ENTROPY]` (a long path reads as a token to it); the
  content is intact. Cosmetic; noted for a follow-up.
- `get_journal_logs ok`: `docker.service` on vm-095, program dockerd, 5 lines (vm-095's rsyslog writes ISO times; the
  program filter is the same).

Phase 3 is complete: every `host-probe` and `network-probe` verb of §4.6 exists (with 3c, #101).
