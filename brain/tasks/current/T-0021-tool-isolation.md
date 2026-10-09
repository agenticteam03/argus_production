# T-0021 — Tool isolation: target-side reads in a separate tools process (MCP), credentials out of the worker

| Field | Value |
|---|---|
| Status | `done` (2026-10-08): steps 1-5 done, verified on vm-095 (worker in `mcp` mode). Review of PR #36 (`conantkd`, changes requested): fixed 2026-10-09, waits for re-review and the ACR's second approval |
| Phase | 4 — tools and guarded execution ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md)): "MCP tools child, UID `argus-tools`, credential-isolation test" |
| Architecture | implements §12.5 (`ToolCatalogue`, `McpChildProvider`, `InWorkerProvider`, `TOOL_CATALOGUE=mcp\|direct`), §12.6 (process identity), §25 OD-3 (benchmark). **[ACR-0002](../../architecture/changes/ACR-0002-tools-uid-sudo-launcher.md)** (proposed, safety principle: secrets): the UID switch is a fixed sudo launcher instead of `setpriv`/`gosu`; OD-3 decided (keep MCP). Architecture 1.8.2 |
| Branch | `task/T-0021-tool-isolation` (steps 1-3 from `main`; `main` with T-0014 merged in before step 4) |
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
- **Step 4 (2026-10-08): compose.** `main` (T-0014, PR #33) merged in first (conflicts in `Dockerfile` and
  `pyproject.toml` comments/dependencies only; 178 passed). Tests: `test_the_api_reads_no_executor_token_even_when_one_is_readable`
  (`tests/test_tool_isolation.py`), `test_only_the_worker_mounts_the_executor_tokens` (`tests/test_compose_split.py`),
  and `argus api` builds with `require_credentials=False, load_credentials=False` (`tests/test_worker_loop.py`). Red
  seen: 3 failed (`build() got an unexpected keyword argument 'load_credentials'`; the api still mounted the whole
  secrets folder). Then `build(load_credentials=False)` reads no executor token in either catalogue mode; `argus api`
  uses it; in `deploy/vm-095/compose.core.yml` the api mounts only `db_password`, `jwt_signing_key` and
  `openai_api_key` (its status reports `llm_configured`), the worker keeps the folder and gets
  `ARGUS_TOOL_CATALOGUE=${ARGUS_TOOL_CATALOGUE:-direct}`, the scheduler is unchanged (database only). `docker compose
  config` valid. Suite: 180 passed, 2 skipped (Docker-in-Docker tests), Postgres included.
- **Step 5a-5b (2026-10-08, vm-095).** 5a (read-only): the api's three files exist (`400 10010`); 7 executor tokens
  `400 10010` in host folders `500 10010`. 5b: `DEPLOY OK: a4c31f3`, image rebuilt, api / worker / scheduler
  recreated in `direct` mode: the api sees only `db_password jwt_signing_key openai_api_key`, the scheduler only
  `db_password`; the image has `argus-tools` (uid 10011), the sudoers rule and the launcher; no startup errors;
  H-1 HEALTHY; NO INTERFERENCE.
- **Fix found before the ownership change (2026-10-08).** `isolation_check` found the tokens by listing the host
  folders; once those belong to `argus-tools` the worker cannot list them, so the check would have said "0 tokens"
  and STOP although the isolation works. Test `test_isolation_check_takes_the_token_list_from_the_inventory`, red
  seen; the expected tokens now come from the inventory, and their presence is proved by the tools process starting
  (it refuses to start without every token). `isolation-test-setup.sh` now builds vm-095's exact layout (secrets
  folder `0501 argus`, host folders `0500 argus-tools`, tokens `0400 argus-tools`); the real image prints
  `TOOLS ISOLATION OK` with 7 tokens expected and none readable.
- **Step 5c (2026-10-08, vm-095, run with `a4c31f3`, before the fix was deployed).** Ownership changed: secrets
  folder `501 10010`, `vm-095/` and `vm-166/` `500 10011`, the 7 tokens `400 10011`, the api files unchanged
  (`400 10010`). `ARGUS_TOOL_CATALOGUE=mcp` added to `/opt/argus-v18/hosts.env`; worker recreated, `catalogue=mcp`,
  no errors. The old `isolation_check` printed the expected false `FAIL executor tokens are present: 0` (it could not
  list the folders) and STOP, and skipped its sudo probes; its other lines were ok (none readable; the sudo
  launcher; the tools process lists 16 capabilities). SC-02 `inc_757f21772cef` DIAGNOSED through the tools process
  (`container.status`, `container.logs`: ok); `docker top`: `python -m argus worker` as uid 10010 and
  `python -m argus.tooling.mcp.tools_server` as uid 10011. Lab reset, LAB BASELINE OK, NO INTERFERENCE.
- **Step 5c.6 (2026-10-08, vm-095).** `DEPLOY OK: 58720d0`, the three programs rebuilt, the worker still
  `catalogue=mcp`, no errors; `isolation_check` inside the worker: none readable (7 expected by the inventory), the
  sudo launcher, sudo refuses `cat` of a token, an extra argument and `true`, the tools process lists 16
  capabilities: **TOOLS ISOLATION OK**; NO INTERFERENCE.
- **The OD-3 benchmark (code, 2026-10-08).** `python -m argus.tooling.mcp.benchmark [N] [TARGET] [CAPABILITY]`, run
  as `argus-tools` (`docker exec -u argus-tools`), the only user that can read the tokens, so the same read goes both
  ways: in-process (`direct`) and through a tools process over stdio (`mcp`), alternating, after one unmeasured
  warm-up pair; it prints p50/p95 of each way and of the per-pair overhead and ends `OD-3 OK` (p95 overhead < 100 ms,
  every read ok) or `OD-3 STOP`. Tests in `tests/test_mcp_child.py` (an end-to-end run against a fake gateway, and
  the verdict); red seen (`No module named 'argus.tooling.mcp.benchmark'`). Suite: 183 passed, 2 skipped (Postgres
  included).
- **Step 5d (2026-10-08, vm-095): OD-3.** `DEPLOY OK: a5f330a`, worker `catalogue=mcp`. 30 pairs each on
  `vm-095/container:argus-lab-api`: `container.status` overhead p50 2.1 ms / **p95 45.7 ms**; `container.logs` p50
  2.6 ms / **p95 43.1 ms**; no failed read: **OD-3 OK** (budget 100 ms). TOOLS ISOLATION OK, NO INTERFERENCE.
  Evidence: [`../../execution/history/T-0021/step-05/evidence.md`](../../execution/history/T-0021/step-05/evidence.md).
  The code default stays `direct` (the decision to flip it is left to the review); vm-095 runs `mcp` through
  `/opt/argus-v18/hosts.env`. Not done here: SC-07 through the tools process (it needs vm-166's lab; SC-02 on
  vm-095 was used instead).
- **Review of PR #36 (2026-10-09, requested by `conantkd`).**
  - *Blocking 1, the launcher.* sudo keeps the caller's working folder and `python -m` put it first on `sys.path`:
    a worker could plant its own `argus` package in `/tmp` and have it run as `argus-tools` (reproduced by the
    reviewer with fake tokens). Fix: the launcher runs `cd /` and `python -I -u`. Red seen: the launcher test
    (`test_sudoers_allows_only_the_launcher_without_arguments`) failed on the old launcher. `isolation_check` now
    starts the launcher from a folder holding a planted `argus` package: on the agent image with the old launcher
    `FAIL the launcher ignores code planted in the caller's folder: the fake argus package RAN as argus-tools`,
    `TOOLS ISOLATION STOP`; with the fixed launcher `TOOLS ISOLATION OK` (16 capabilities).
  - *Blocking 2, the ACR.* [ACR-0002](../../architecture/changes/ACR-0002-tools-uid-sudo-launcher.md) records the
    sudo launcher (§12.6) and closes OD-3 (§25, keep MCP); architecture 1.8.2. It needs a second team member's
    approval in PR #36.
  - *Hung tools process.* A call with no answer within the timeout now ends its session (the child is closed), so the
    next call starts a new one. Red seen: `test_a_hung_tools_server_is_replaced_after_a_timeout` (the second call
    queued behind the stuck one and timed out too).
  - *Default.* `deploy/vm-095/compose.core.yml`: `ARGUS_TOOL_CATALOGUE` defaults to `mcp`, `direct` is the
    rollback. The code default (`Settings`) stays `direct`, for hosts without the token ownership change.
  - Suite: **185 passed**, 2 skipped (Postgres tests included). vm-095 still runs the old launcher until the
    redeploy (step 5e).

## Step 5 procedure (vm-095, with the lease)

1. Read-only checks: the three api files exist (a missing bind-mount source would be created as a folder);
   list the token files with owner and mode; NO INTERFERENCE before.
2. Deploy the branch; rebuild the agent image (`sudo`, user `argus-tools`); recreate api, worker, scheduler (still
   `direct`): H-1 HEALTHY; the api container has no token folder.
3. Token ownership (5a found every token `400 10010` in host folders `500 10010`, the secrets folder `500 10010`):
   the host folders `vm-095/`, `vm-166/` and their `*_token` files to `10011:10011` (folders `0500`, files `0400`);
   the secrets folder stays `10010` but becomes `0501`, so argus-tools may traverse it (the parent
   `/opt/argus-v18/secrets` is `700 root`, so no host user gains anything); the api files stay `400 10010`. From
   here `direct` cannot read the tokens: the rollback to `direct` is the folders and files back to `10010` and the
   secrets folder back to `0500`.
4. `ARGUS_TOOL_CATALOGUE=mcp` for the worker; `docker exec argus-v18-worker python -m argus.tooling.isolation_check`
   must print `TOOLS ISOLATION OK`; H-1 and SC-07 through the tools process; the OD-3 benchmark (p95 overhead per
   call < 100 ms, `mcp` vs `direct`); NO INTERFERENCE.
5. Rollback: `ARGUS_TOOL_CATALOGUE=direct` + tokens back to `10010`; `ARGUS_AGENT_CMD=serve` additionally needs the
   api's secrets folder mount back (compose comment).

