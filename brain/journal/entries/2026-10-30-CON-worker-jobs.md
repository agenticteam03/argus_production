## 2026-10-30 - CON-worker-jobs: the console's reads and write proposals run in the worker; a verified recovery's label

Type: fix (console, UI)
Who: conantkd (+ agent)
Context: after DEPLOY-88fe002 turned the operator console on, `worker status` answered `container.status on
vm-166/container:argus-lab-jobworker: error (forbidden): ... HTTP 401 {"error": "unauthorized"}`. The console ran its
reads in the API process (`app.runner.invoke`), and since T-0021 (§12.6) the API holds no executor token: only the
worker has the `vm-095` / `vm-166` token files. The same held for writes: `ARGUS_ACTION_PATH=1` is set on the worker
only, so in the API the gate was empty and a write was refused. The tests ran everything in one process with tools,
so they never saw it.
Decision / result:
- `console_job` (migration 022): the API inserts one row per read (`read`: a console read capability, its target and
  arguments) or per confirmed write (`propose`: the command and its released pair) and waits for the answer
  (`ARGUS_CONSOLE_JOB_TIMEOUT_S`, 30 s; `ARGUS_CONSOLE_PROPOSE_TIMEOUT_S`, 120 s). The worker claims it in a thread
  of its own (`console/jobs.py`, `ConsoleJobRunner`, on with `ARGUS_OPERATOR_CONSOLE=1`) and runs it with its guarded
  invoke or action path. The runtime role may UPDATE a job, never DELETE it.
- The worker refuses a read that is not one of the console's six read capabilities before invoke (which still applies
  policy, inventory, redaction and audit). Who may run what stays decided in the API: the console session, the
  permission, the quota, the confirmation, the history and the audit.
- The write proposal moved, unchanged, from `ConsoleService._write` to `console/proposals.py` (`propose_write`), so
  either process can run it. With no tools (`App.runs_tools=False`, set by `argus api`) the API checks the released
  pair from its own policy (`write_gate.open`) before asking for confirmation.
- A process with the tools (`argus serve`, the tests' default app) still runs reads and proposals in place.
- UI: an incident whose outcome is `recovered_verified` showed the raw value in grey; `OutcomeBadge` now says
  "Recovered Verified" in green, the same tone as "Closed".
Consequences: deploy order: backup, `ops/db-migrate.sh` (022, additive: the old image never reads it), then rebuild
the agent and the worker together (the new API needs the worker's job runner; the worker needs
`ARGUS_OPERATOR_CONSOLE=1`, now passed by `compose.core.yml`), then the UI, then `argus db check`. The API waits on a
thread for up to 30 s per read (120 s per proposal); a worker that is down shows "the worker did not answer".
References: [console guide](../../../docs/OPERATOR-CONSOLE.md); found during DEPLOY-88fe002.

### Test state

Red seen first: `tests/test_console_jobs.py` failed to collect before `console/jobs.py` existed, then failed on the
store methods; the write test refused (`rejected`) until the service chose the job path when used. The UI test
(`ui.test.jsx`, "Recovered Verified" in green) failed on the raw label. Then: `tests/test_console_jobs.py` 8 passed;
`tests/test_postgres.py::test_console_job_migration_022` added (runs on CI's Postgres); migration checker PASS;
Vitest 70 files / 461 tests.

### Next step

Review; after the merge, deploy with both leases: backup, migration 022, agent + worker + UI, `argus db check`; then
`worker status` in the console should answer from the worker.
