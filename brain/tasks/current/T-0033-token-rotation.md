# T-0033 — Phase 13: an executor token is rotated while Argus runs

| Field | Value |
|---|---|
| Status | `done` — step 1 (offline) 2026-10-12; step 2 (one rotation on the VMs, no worker restart) 2026-10-12 |
| Phase | 13 — failure and recovery ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md): "token rotation") |
| Architecture | no change (no ACR): secrets are still read only through `Settings` (§17.2); a rejected token is re-read from the same file |
| Branch | `task/T-0033-token-rotation`, from `main` |
| Owner | `juanbetancurm` (+ agent) |
| Needs the VM lease | step 2: both (vm-166's service, vm-095's agent copy) |

## Goal (plain language)

Each target service (read gateway, host probe, network probe) checks a bearer token that it reads **once, at start**
(`services/target/service.py`). The agent keeps a copy of every token in `/opt/argus-v18/secrets/agent/<host>/`, and
its tools process (the MCP child, §12.6) also read them **once, at start**. So after a rotation, every read of that
executor was refused (HTTP 401, `forbidden`) until someone restarted the worker. Phase 13 asks that a rotation be an
escalation at worst, never a crash or a wrong attribution, and that Argus recover from it.

## Step 1 (done, offline)

- `Dispatcher` (`argus/tooling/dispatch.py`): when an executor answers `forbidden`, it re-reads that one token from its
  file. If the file changed, it keeps the new token and retries **once**; if not (or the new one is also rejected),
  the read stays a `forbidden` error, as before. Never a loop; the target is not blamed (the observation says the
  executor refused the credential).
- `wiring.py`: the tools process (`tools_dispatcher`) and the direct mode re-read through `Settings.secret`, the same
  files they read at start.
- `ops/rotate-token.sh <docker_read|host_probe|network_probe> --as <dev>` on the target host: a new random token
  (same owner and mode, never printed; the old one kept as `.prev`, mode 0400), then that one service recreated.
  `--rollback` restores `.prev`. `db_probe` is excluded: its host's Prometheus scrapes it with the same token.
- Tests: `tests/test_t0033_token_rotation.py` (4; red seen: `Dispatcher` had no reload): a rotated token is re-read and
  the read succeeds, then kept; a token still rejected is retried once at most; no reload = the old behaviour; the
  tools process re-reads its own files.

## Step 2 (done 2026-10-12, both leases, session 351b0fdf7301)

Deploy of `main` `244453b` on vm-095 (agent, worker, scheduler; vm-166 checkout only), then vm-166's `host_probe`
token rotated. The same `report` on `vm-166/host:vm-166` (evidence pack, no model call): before, reads ok
(`inc_0c261186a482`); after the rotation with the agent's old copy, both reads `forbidden` (HTTP 401) and the incident
escalated, no crash (`inc_80d405b583de`); after the agent's copy was replaced (same owner and mode, hashes equal), reads
ok again (`inc_fda8fb3307eb`) with the **worker not restarted** (restarts 0, same start time). LAB BASELINE OK, NO
INTERFERENCE. [Evidence](../../execution/history/T-0033/step-02/evidence.md).

## Limits

Between the service restart and the copy on vm-095, reads of that executor are refused (seconds). The service accepts
one token only; a two-token grace window would need a change to the target services.

## Follow-up (2026-10-12, `conantkd`, from the review of #94)

`ops/rotate-token.sh`: `--rollback` restores `.prev`'s content with the **live file's owner and mode** (it used to take
`.prev`'s 0400, unreadable for a service that reads through its group); a failed `docker compose` recreate exits 1 and
says the service still holds the previous token and how to roll back (it used to be hidden by `| grep … || true`, and
"recreated" was printed). `ARGUS_DEPLOY_HOME`, `ARGUS_DOCKER` and `ARGUS_HOSTNAME` let the script run against a fake
`/opt/argus-v18` (like `ops/deploy.sh`). Tests: `tests/test_t0033_rotate_token_script.py` (4; red seen 3/4).
