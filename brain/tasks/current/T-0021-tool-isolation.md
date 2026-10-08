# T-0021 — Tool isolation: target-side reads in a separate tools process (MCP), credentials out of the worker

| Field | Value |
|---|---|
| Status | `in progress` (2026-10-08): steps 1-3 done; step 4 after T-0014 merges |
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
- **The UID switch is a single sudo rule** (decided in step 3): the worker (`argus`, not root) may start exactly
  `/usr/local/bin/argus-tools-server` as `argus-tools`, with no arguments; the launcher is root-owned and fixes its
  own environment. A non-root process cannot `setpriv` to another UID, and running the worker as root would let it
  read the tokens. A compromised worker can only ask the tools server for the published reads.
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

- The full offline suite passes; an investigation gives the same reads and outcome through `mcp` as `direct`; the
  red of steps 1-3 is recorded below.
- On vm-095 the worker UID cannot read an executor token; a diagnosis runs through the tools process; OD-3 recorded.
- Brain: `CURRENT_STATE.md`, `tdd/CURRENT_TEST_STATE.md`, `IMPLEMENTATION_PLAN.md` (phase 4), a logbook entry.

## Red seen / evidence

- **Step 1 (2026-10-08): the MCP tools server and client.** `tests/test_mcp_tools.py` (8 tests, in-memory
  transport). Red seen: 7 errors, `No module named 'argus.tooling.mcp'`. Then `argus/tooling/mcp/tools_server.py`
  (low-level MCP `Server`: lists the `tools_child` read capabilities with their argument schemas; `handle()` refuses
  an unpublished name (`forbidden`), a bad or out-of-inventory target (`invalid_args` / `out_of_scope`) and invalid
  arguments before executing, then calls the same `Dispatcher`; a refusal is an `is_error` result with its
  category), `argus/tooling/mcp/client.py` (`McpToolsClient`: one background thread holds ONE MCP session task,
  calls are queued to it; a dead or closed server raises `ToolsUnavailable`), `argus/tooling/providers.py`
  (`McpCatalogue`: `runs_in="worker"` stays in-worker, the rest goes through MCP; `ToolsUnavailable` becomes an
  `error` / `upstream_error` observation, never a crash). A read through MCP equals the direct read (status, values,
  redaction, host). Rule 10 guard: only `argus/tooling/mcp/` imports the MCP SDK. `mcp` 2.3.0 added (pure Python
  wheel). Suite: 127 passed, 6 skipped (Postgres and Docker-in-Docker tests skipped here).
- **Step 2 (2026-10-08): the real child process.** `tests/test_mcp_child.py` (4 tests). Red seen: 4 failed
  (`cannot import name 'child_client'`; `ARGUS_TOOL_CATALOGUE=mcp` still gave the `DirectProvider`). Then
  `child_client(env, command)` starts `<python> -m argus.tooling.mcp.tools_server` over stdio, passing only
  `ARGUS_CONFIG_DIR` / `ARGUS_SECRETS_DIR` (+ `PYTHONPATH`); the child builds its own dispatcher with
  `wiring.tools_dispatcher()` (catalogue, inventory, executor tokens: no database, no model key, no runbooks). A call
  that fails in the transport ends the session: that call is an `error` observation, the next call starts a new
  child (test: the child is killed with SIGKILL, then answers again). `ARGUS_TOOL_CATALOGUE=direct|mcp` (default
  `direct`; anything else refuses startup) and `ARGUS_TOOLS_COMMAND` (the interpreter, for step 3's UID switch) in
  `Settings`; in `mcp` mode the worker's dispatcher holds no executor token. An investigation through MCP gives the
  same reads and outcome as `direct`. Credential loading and the target executors moved into `_credentials()` /
  `_target_executors()`, shared by `build()` and the tools process. Suite: 131 passed, 6 skipped.
- **Step 3 (2026-10-08): credential isolation.** `tests/test_tool_isolation.py` (4 offline tests + 1 real-image
  test with `ARGUS_TEST_DOCKER=1`). Red seen: 4 failed (in `mcp` mode `build()` still demanded every executor token;
  `ARGUS_TOOLS_COMMAND` was not the whole command; no sudoers rule, no launcher, no `isolation_check`). Then: in
  `mcp` mode the worker reads no executor token (`_credentials(load=False)`: the inventory is still validated);
  `ARGUS_TOOLS_COMMAND` is the whole command line; `deploy/agent/argus-tools-server` (the root-owned launcher) and
  `deploy/agent/argus-tools.sudoers` (`argus ALL=(argus-tools) NOPASSWD: /usr/local/bin/argus-tools-server ""`);
  `Dockerfile`: `sudo` installed, user `argus-tools` (uid 10011), the launcher and the rule copied, the tools command
  set; `python -m argus.tooling.isolation_check` (read-only, for vm-095 in step 5). Real image (built on the laptop,
  tokens `0400 argus-tools`, run as `argus`): `TOOLS ISOLATION OK` — the worker reads no token; sudo refuses `cat` of
  a token, an argument to the launcher, and root; the tools process starts as `argus-tools` and lists its 16
  capabilities. With the tokens readable by the worker: `TOOLS ISOLATION STOP`. Suite: 135 passed, 7 skipped.

