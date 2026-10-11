# E2E-6 — The runner's Prometheus gates on vm-095

| Field | Value |
|---|---|
| Status | `done` — step 1 (the runner fix) 2026-10-11; step 2 (SC-02 × 5 on vm-095) 5/5 PASS 2026-10-11 |
| Phase | 12 (end-to-end tests) — [`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md) |
| Found by | the first SC-02 batch through the runner (2026-10-11, `juanbetancurm`): 5 × ERROR in the pre-gate |
| Architecture | no change (no ACR): the test runner only, nothing deployed |
| Branch | `task/E2E-6-prom-gate-vm095` (from `main`) |
| Owner | `juanbetancurm` (+ agent), quality lane |
| Needs the VM lease | step 2 only (vm-095) |

## Goal (plain language)

SC-02 is the first scenario the runner runs on vm-095. Its PromQL gates went to `127.0.0.1:18090`, which only vm-166
publishes (`deploy/monitoring/compose.loopback.yml`); vm-095's Prometheus joins `argus-v18-core` with no host port
(`compose.core-join.yml`). Every query came back empty, so every run waited 15 minutes in the pre-gate and ended
`pre-gate never clean: … JSONDecodeError`. Nothing was started; NO INTERFERENCE after each run.

## Step 1 (done, offline)

- Read-only check on vm-095 first (P.1): nothing listens on 18090; `argus-v18-prometheus` has `ports=[9090/tcp]` only;
  `docker exec argus-v18-prometheus wget -qO- 'http://127.0.0.1:9090/api/v1/query?query=…'` answers
  `{"status":"success",…}`, also for the SC-02 metric.
- `ops/e2e/run.py`: `promql_cmd(host, promql)`. vm-166 keeps the same `curl` to 127.0.0.1:18090; vm-095 runs the query
  inside `argus-v18-prometheus` (busybox `wget`; the runner URL-encodes the query, as `wget` cannot). The gate is built
  for the scenario's `host`, where it already ran.
- Why not publish 18090 on vm-095: that is a deploy change on the agent's host (both leases, a new listening port) for
  a test tool; the container query needs nothing on the VM.

Tests: `tests/test_e2e_runner.py`, two new (red seen 2/2: the gate was the 18090 `curl` on vm-095): a vm-095 gate goes
through the container with the encoded query; the catalogue's SC-02 pre-gate and gate do. The existing vm-166 test is
unchanged and passes; 39/39. `run.py --dry-run SC-02` shows both gates through the container.

## Step 2 (done, vm-095's lease)

`ops/e2e/run.py --runs 5 SC-02` on vm-095's agent at `e3286df` (SC-02 does not depend on #80), 2026-10-11
20:12–20:56 UTC: **5/5 PASS**, 0 fail, 0 error. Every run: `diagnosed`, `container_restart_loop`, root cause
`vm-095/container:argus-lab-worker`, first runbook RB-008. Incidents `inc_93f9571319e6`, `inc_0a8b51586243`,
`inc_9006ee3161e1`, `inc_2f03f49d29b3`, `inc_65431bb42ff9`. Run 1 took 31 s; runs 2–5 took 591–696 s, of which the
pre-gate wait is most. The pre-gate and gate answered through the container on every run (no JSONDecodeError).
