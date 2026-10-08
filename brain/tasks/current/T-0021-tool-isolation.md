# T-0021 — Tool isolation: target-side reads in a separate tools process (MCP), credentials out of the worker

| Field | Value |
|---|---|
| Status | `planned` (2026-10-08) |
| Phase | 4 — tools and guarded execution ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md)): "MCP tools child, UID `argus-tools`, credential-isolation test" |
| Architecture | no change (no ACR): implements §12.5 (`ToolCatalogue`, `McpChildProvider`, `InWorkerProvider`, `TOOL_CATALOGUE=mcp\|direct`), §12.6 (process identity), §25 OD-3 (benchmark) |
| Branch | `task/T-0021-tool-isolation` (steps 1-3 from `main`; step 4 after T-0014 is merged) |
| Owner | `juanbetancurm` (+ agent) |
| Needs the VM lease | step 5 only (vm-095) |

## Goal (plain language)

Today every read of a target host runs inside the agent process, and that process holds every executor token (read
gateway, probes, Prometheus). If the agent process were ever tricked (prompt injection, a bug), it could use those
tokens directly. The architecture puts target-side reads in a **separate tools process**, started by the worker
under its own user `argus-tools`: only that process can read the tokens, it serves only the published read
capabilities, and it talks to the worker over stdin/stdout (MCP), with no network port. Policy, audit and evidence
stay in the worker (`InvokeCapability`). This is the main safety condition before Argus reads a real system.

## Decisions (proposed, to confirm at the start)

- **MCP Python SDK `mcp>=2.3,<2.4`** (pure Python wheel, so ARM64 needs no compiler). The server publishes the
  registry's `runs_in="tools_child"` capabilities as MCP tools with the argument models' JSON schemas.
- **`TOOL_CATALOGUE=direct` stays the default** until step 5 proves `mcp` on vm-095; then the default becomes `mcp`
  and `direct` is the rollback (§12.5, OD-3).
- **The api and scheduler stop receiving executor tokens** (§12.6): building the application for the api no longer
  loads them; only the tools process reads them.
- **One tools process per worker, started once and restarted if it dies** (a dead child → the call returns an
  `error` observation, never a crash, never a retry of a write: there are no writes here).

## Steps

1. **Red: the MCP tools server and client (code only).** In-memory transport in tests: the server lists exactly the
   `tools_child` capabilities; it refuses an unpublished name, invalid arguments and a target outside the static
   deployment scope; a call returns the same `Observation` as `DirectProvider` (same redaction, size limit and
   attribution guard, which stay in `dispatch.py`); `knowledge.runbook` (`runs_in="worker"`) is served in-worker.
2. **Red: the real child process.** `McpChildProvider` spawns `python -m argus.tooling.mcp.tools_server` over stdio;
   a test runs it as a real subprocess with a fake executor; a killed child gives an `error` observation and the
   next call starts a new child. `TOOL_CATALOGUE=mcp|direct` in the wiring; the existing suite passes with both.
3. **Red: credential isolation (Docker test).** The image gains user `argus-tools`; the worker starts the child with
   `setpriv` under that UID; token files `0400 argus-tools`. Test: the worker UID cannot open a token file, the child
   can; the api (`build` for the API) needs no token file.
4. **Compose + ops (after T-0014 merges):** the worker container mounts the executor tokens for the child only; the
   api and scheduler mounts lose them; `ops/` notes for the ownership change on vm-095.
5. **VM (vm-095, lease) + OD-3 benchmark:** deploy, change the token ownership, `TOOL_CATALOGUE=mcp`; H-1 and SC-07
   through the tools process; benchmark `mcp` vs `direct` (p95 overhead per call < 100 ms, §25 OD-3); NO
   INTERFERENCE. Rollback: `TOOL_CATALOGUE=direct`.

## Done when

- The full offline suite passes with `TOOL_CATALOGUE=direct` and `mcp`; the red of steps 1-3 is recorded below.
- On vm-095 the worker UID cannot read an executor token; a diagnosis runs through the tools process; OD-3 recorded.
- Brain: `CURRENT_STATE.md`, `tdd/CURRENT_TEST_STATE.md`, `IMPLEMENTATION_PLAN.md` (phase 4), a logbook entry.

## Red seen / evidence

(none yet)
