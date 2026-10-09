# T-0021 step 05 — evidence (2026-10-08, juanbetancurm, session b5a8c3473b0d)

Goal: on vm-095, move the executor tokens out of the worker's reach, run every target-side read through the MCP
tools process as `argus-tools`, prove the isolation from inside the worker, and measure the cost (ARCHITECTURE §12.5,
§12.6, §25 OD-3). vm-166 was not touched (it stays on `task/T-0020-sc04-pg-connections`). `code.bash` here holds the
5d blocks (5a-5c used the same deploy, rebuild and check lines).

Key output lines from output.bash, SANITIZED (no addresses, no secrets, no personal names).

| Part | Observed | Result |
|---|---|---|
| 5a (read-only) | the api's files `db_password`, `jwt_signing_key`, `openai_api_key` exist (`400 10010`); 7 tokens `400 10010` in `vm-095/`, `vm-166/` (`500 10010`); the secrets folder `500 10010`, its parent `700 root` | OK |
| 5b (direct) | `DEPLOY OK: a4c31f3`; the api sees only its 3 files, the scheduler only `db_password`, the worker everything; the image has `argus-tools` (10011), the sudoers rule and the launcher (root-owned); 0 startup errors; H-1 HEALTHY; NO INTERFERENCE | OK |
| 5c ownership | secrets folder `501 10010`; `vm-095/`, `vm-166/` `500 10011`; 7 tokens `400 10011`; api files unchanged | OK |
| 5c mcp | `ARGUS_TOOL_CATALOGUE=mcp` in `/opt/argus-v18/hosts.env`; worker recreated, `catalogue=mcp`, 0 errors | OK |
| 5c check (old code) | `FAIL executor tokens are present: 0` + STOP: the old check listed folders the worker can no longer list (fixed in `58720d0`); its other lines ok | expected false STOP |
| 5c SC-02 | `inc_757f21772cef` DIAGNOSED through the tools process (`container.status`, `container.logs` ok); `docker top`: `python -m argus worker` uid 10010, `python -m argus.tooling.mcp.tools_server` uid 10011; lab reset, LAB BASELINE OK, NO INTERFERENCE | OK |
| 5c.6 | `DEPLOY OK: 58720d0`; `isolation_check`: none readable (7 expected by the inventory), the sudo launcher, sudo refuses `cat` of a token, an extra argument and `true`, the tools process lists 16 capabilities: **TOOLS ISOLATION OK**; NO INTERFERENCE | OK |
| 5d OD-3 `container.status` | 30 pairs: direct p50 12.1 / p95 41.5 ms; mcp p50 14.3 / p95 57.9 ms; **overhead p50 2.1 / p95 45.7 ms**; not ok 0: **OD-3 OK** | OK |
| 5d OD-3 `container.logs` | 30 pairs: direct p50 12.2 / p95 39.1 ms; mcp p50 15.0 / p95 54.7 ms; **overhead p50 2.6 / p95 43.1 ms**; not ok 0: **OD-3 OK** | OK |
| 5d after | `DEPLOY OK: a5f330a`; TOOLS ISOLATION OK; NO INTERFERENCE | OK |

**Result:** step 5 done. vm-095 runs `task/T-0021-tool-isolation` `a5f330a` with the worker in `mcp` mode: the worker
(uid 10010) cannot read any executor token; only the tools process (uid 10011), started through one fixed sudo rule,
reads them; the p95 overhead per read is about 45 ms (budget 100 ms). The code default stays `direct`; vm-095 uses
`mcp` through `hosts.env`.

**State to keep in mind (for the next VM session):** vm-095 is NOT on `main` until PR #36 merges. A deploy of `main`
there before that would bring back code in which the api and the worker read the tokens themselves, while the
tokens belong to uid 10011: both would refuse to start (`missing credential`). Before
deploying `main` on vm-095 ahead of #36, run the rollback.

**Rollback** (from `code.bash`, block R): set `ARGUS_TOOL_CATALOGUE=direct` in `hosts.env` (since 2026-10-09 the
compose default is `mcp`, so removing the line is no longer enough); tokens and the two host
folders back to `10010`; the secrets folder back to `0500`; recreate the worker.
