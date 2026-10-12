# T-0033 — Phase 13: an executor token is rotated while Argus runs

| Field | Value |
|---|---|
| Status | `in progress` — step 1 (offline) done 2026-10-12; step 2 (one rotation on the VMs) after the merge |
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

## Step 2 (after the merge, both leases)

On main, vm-095's agent rebuilt (the AFTER-MERGE checks). Then, for vm-166's `host_probe`:
1. a `report` on `vm-166/host:vm-166` (the evidence pack reads `host.*` through the probe, no model call): reads ok;
2. `rotate-token.sh host_probe` on vm-166: the same report now shows the probe's reads `forbidden` and ends escalated
   (no crash, the worker's restart count unchanged);
3. the agent's copy replaced (laptop ssh pipe, as T-0019 step 3; owner and mode kept);
4. the same report: reads ok again, **without restarting the worker**;
5. LAB BASELINE OK, NO INTERFERENCE; rollback = `rotate-token.sh host_probe --rollback` + the old copy.

## Limits

Between the service restart and the copy on vm-095, reads of that executor are refused (seconds). The service accepts
one token only; a two-token grace window would need a change to the target services.
