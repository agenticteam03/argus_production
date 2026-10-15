# LF-3 step 02 — evidence: vm-095 to `main` 5d4b347, then the self-hosted Langfuse capacity gate (failed) (2026-10-14/15, conantkd, session d7bfceb6737f)

Goal: vm-095 on `main` after #152 (ACR-0013 tracing code, off by default) and #154 (record only), then ACR-0013's
six-service Langfuse stack on Host A and the worker's tracing switched on (`deploy/langfuse/README.md`). Leases:
vm-095 + vm-166 (the agent changes). Commands: [`code.bash`](code.bash). Times are UTC. No address, key or Langfuse
project id is written here (`policies/SECURITY.md` rule 4).

| Block | Observed | Result |
|---|---|---|
| L.0 laptop | both leases claimed (`LF-3`); both VMs' marker `holder=conantkd session=d7bfceb6737f` | OK |
| L.1 vm-095 | `commit=37822c9` `ref=main`; `LAB BASELINE OK`; `NO INTERFERENCE`; mem available 4244 MiB of 5900; disk free 67G | OK |
| L.1 vm-166 | `commit=ccc810e` `ref=main`; `LAB BASELINE NOT OK: argus-lab-cache argus-lab-api` (the cache `Exited (0)` since about 22:07, before this session, by someone else: not repaired here, not touched); `NO INTERFERENCE` | reported |
| L.2 vm-095 → `main` | `SESSION OK`; `BACKUP OK` (2237475 bytes); `DEPLOY OK: 5d4b34772dd1 (main)`; migrations 001–006 already applied; agent, worker, scheduler on one image `752d1dd391fc`, `restarts=0`; `health 200`; `worker: no startup errors`; `20/20`; `55/55`; `WRITE GATE CLOSED`; UI `healthy`; `/api/v1/me` 401, `/docs` 404; `commit=5d4b347` `ref=main`; `LAB BASELINE OK`; `NO INTERFERENCE` | OK |
| L.3 Langfuse stack | `runtime.env` written, 8 values, `600 root`; images pulled; minio, postgres, clickhouse healthy, redis, worker, web started; `langfuse health 200 after ~60 s`; memory: web 1022 of 1280 MiB, worker 524 of 768, ClickHouse 488 of 768, minio 77, postgres 40, redis 10; mem available 2434 MiB; `argus health 200`; nonint: one difference, `> tcp 127.0.0.1:18300` (the Langfuse web listener, an Argus port, expected) | OK |
| L.3 extra (read-only) | from inside `argus-v18-worker`: `argus-v18-langfuse-web` resolves on `argus-v18-core`, `/api/public/health` 200. Compose sets no `container_name`: the containers are `argus-v18-langfuse-argus-v18-langfuse-<service>-1` (L.8 now stops by service name) | OK |
| L.4 browser | through `ssh -N -L 18300:127.0.0.1:18300`: account, organization, project and one API key pair created (Langfuse audit log `apiKey.create` at 00:46:15) | OK |
| L.5 developer's terminal | first try: `install: invalid user: '10010'` twice (vm-095's `install` is uutils and refuses a numeric owner), nothing written; corrected block: `400 10010 42 bytes` for both key files | OK (2nd try) |
| L.6 tracing on | `hosts.env` with the three ACR-0013 lines (copy kept as `hosts.env.before-lf3`); worker and agent recreated; `health 200`; `tracing=1`, 2 key files; the block took more than 5 minutes (below) | OK, slow |

## The capacity failure (01:00)

While L.6 ran, a separate read-only query to the Langfuse database also hung. Diagnosis (L.D) at 01:00:20:

- `load average: 176.42, 172.07, 125.05`; pressure: CPU `some avg10=29.31`, memory `avg10=28.15`, **I/O
  `avg10=99.61 avg60=99.58 avg300=99.49`**; mem available 2176 MiB.
- Kernel at 01:00:26: `MergeMutate invoked oom-killer` … `oom-kill:constraint=CONSTRAINT_MEMCG` … `Memory cgroup out of
  memory: Killed process … (clickhouse-serv) total-vm:9092880kB, anon-rss:701172kB`. Docker restarted it
  (`restarts=1 exit=137`).
- Reading: a ClickHouse background merge grew to its 768 MiB cgroup limit; reclaim inside the cgroup re-read files from
  the shared disk for minutes (I/O pressure 99 % over 5 minutes), which slowed every container on the host, Argus
  included. Argus did not fail (health 200, no restart), but a recreate and a query took minutes.

## L.R — stopped and rolled back (README "If the capacity budget is insufficient")

- `compose stop`: the six services stopped (volumes kept). At 01:01:03 I/O pressure `avg10=17.94`, load 99; at
  01:01:27 I/O `avg10=1.89`, load 71 and falling; `argus health 200`; agent, worker, scheduler, UI `running
  restarts=0`; `NO INTERFERENCE`.
- Then `hosts.env` restored from `hosts.env.before-lf3` (keys `ARGUS_VM095_PRIVATE_IP ARGUS_VM166_PRIVATE_IP
  ARGUS_TOOL_CATALOGUE` only); both key files removed (`langfuse key files: 0`); worker and agent recreated; `health
  200`; `tracing=0`; the six `Exited` (not removed, `unless-stopped` keeps them down); `NO INTERFERENCE`; at 01:06:10
  load `1.22, 55.17, 86.98`.

## L.C — Langfuse Cloud reachable (for ACR-0015)

From inside `argus-v18-worker`: `https://cloud.langfuse.com/api/public/health` 200 `{"status":"OK","version":"4.59.0"}`;
the US region the same.

## State at the end

vm-095: `main` `5d4b347`, Argus as before tracing (off), the Langfuse stack stopped with its volumes and
`/opt/argus-v18/secrets/langfuse/runtime.env` kept (removed once ACR-0015 is decided). vm-166: unchanged, its
`argus-lab-cache` still stopped (not ours). Both leases released.

## Not done

L.7 (a trace seen in Langfuse) and L.8 (Langfuse away, measures) were not run: the stack failed the capacity gate first.
