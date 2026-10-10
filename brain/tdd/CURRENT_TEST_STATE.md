# Current test state

**Last updated:** 2026-10-09 · **Commit:** `task/OP-009-lease-loss` after merging `main` (up to #44)

**T-0028 (SC-06), 2026-10-09 (`task/T-0028-sc06-cpu`):** 11 tests in `tests/test_t0028_sc06_cpu.py` (red seen
11/11: no CPU limit in the gateway, no signal, class, alert, burner or inventory entry); 5 evaluation cases
`tests/eval/cases/cpu-*.yaml` (baseline 5/5, hard 0 0 0). Full suite on the laptop: green.

**OP-009 follow-up, 2026-10-09 (`task/OP-009-renew-gap`, review note of PR #53):**
`test_a_failing_renewer_cancels_at_the_lease_expiry_not_at_its_next_attempt` (red seen: cancelled at 1.44 s with a
1 s lease and 0.7 s attempts; now at the expiry; 5/5 stable runs). Full suite on the laptop: green.

**Alert identity to milliseconds, 2026-10-09 (`task/alert-identity-ms`, review note of PR #45):** 3 tests in
`tests/test_alert_identity.py` (red seen: a pushed copy with a nanosecond `startsAt` and a pulled one with milliseconds
opened two incidents); the stored identity format is pinned by a test. Full suite on the laptop: green.

**OP-009, 2026-10-09 (`task/OP-009-lease-loss` after merging `main` up to #50):** **306 passed**, 3 skipped on the
laptop with a throwaway `postgres:16-alpine` (the OD-3 benchmark passed too); the T-0025 baseline evaluation still
gives hard 0 0 0 with the runners' new `cancel` argument. Before `main` up to #44: 243 passed, 3 skipped on the laptop with a
throwaway `postgres:16-alpine` (the Postgres tests included; skipped: the two real-Docker tests and the `/proc`
test). The OD-3 timing benchmark failed once in the full run (p95 overhead 123 ms against 100 ms) and passed alone:
the known Windows timing flake. OP-009's own tests: 7 in `tests/test_op009_lease_loss.py` and
`test_worker_lease_uses_the_database_clock` (red seen on 2026-10-08, see below).

**OP-001, 2026-10-09 (`task/OP-001-runbook-detectors`, PR #44):** the architecture-to-runbook metadata test failed
before the edits, then passed. The new mapping and index tests plus 20 related knowledge/SC-04 tests pass locally.
The Windows full suite passed with nine skips when pytest's temporary directory was placed outside the Git worktree;
the first local run used an in-worktree temporary directory and caused five unrelated `test_deploy.py` path failures.
After merging `main` (#41), only the existing OD-3 timing benchmark failed locally: p95 MCP overhead was 227 ms
against its 100 ms budget (294 ms isolated). It is unaffected by OP-001 and is recorded as timing-flaky on the OP-005
branch too. Linux CI `test` and `frontend` passed on the fast-track record commit; rerun after this merge from `main`.

**OP-005, 2026-10-09 (`task/OP-005-young-restarts`):** three new unit tests were red against the old exporter/signal,
then passed. Five PromQL synthetic-series cases passed with Prometheus 3.5.0 `promtool test rules` (young, old with
scrape gap, old with continuous history, recreated same name, and missing creation metric). The full local Windows
worktree suite finished with 6 unrelated failures: 5 `tests/test_deploy.py` fixtures see their temporary `app` as an
existing Git clone; the OD-3 timing benchmark measured 155 ms p95 overhead against its 100 ms budget. Review of PR #41
(`main` merged in, + 1 test: the restart alert counts like the signal, red seen): 228 passed, 9 skipped on the laptop
(237); the only failure is the same timing-flaky benchmark (passes alone; green in CI). The VM checks follow.

| Stage | Result | Where / when |
|---|---|---|
| 3. Offline suite | **286 passed**, 3 skipped with a throwaway Postgres (`ARGUS_TEST_PG_OWNER_DSN`, as in CI) on `task/OP-011-correlation` after ACR-0004 (2026-10-09): + 4 tests in `test_op011_correlation.py` (an alert that started before the incident closed joins it, not reopened; an escalated incident too; a recurrence, another class or an old close → a new incident; SC-03 with the alerts one pass apart → one incident; red seen 3/4, the negative case was already green), `latest_concluded_incident` in `test_postgres.py`. Before: **275 passed**, 10 skipped on the laptop on `task/OP-011-correlation` (OP-011, 2026-10-09): + 9 `test_op011_correlation.py` (two alerts on one target and class → one incident, `attached`, evidence version 2; still `duplicate` after the incident closes; audited; another class, stale metrics, no class, another dependency, closed or outside the window → a new incident; one SC-03 pull pass → `started` 1, `attached` 1; the webhook the same; red seen 9/9) and + 1 `test_postgres.py::test_alert_occurrences` (migration 004; red seen `relation "alert_occurrence" does not exist`, then the 7 Postgres tests green against a throwaway `postgres:16-alpine`). The OD-3 timing benchmark failed once on Windows and passed on rerun. Before: **273 passed**, 2 skipped (275 with the Postgres tests, as in CI, after #41; on the laptop 265 passed, 9 skipped) on `task/T-0024-sc05-disk` after merging OP-010 (with T-0022 and `main`): + 15 `test_t0024_sc05_disk.py` (disk signals per declared mount, `$mounts` from the inventory and validated, `disk_pressure` with time to full, host scope, RB-005 metadata, the alert on every real filesystem, `rslave`, the host-probe refuses an unmounted mount, the bounded filler, the mount script; red seen 15/15). Before: **254 passed**, 2 skipped (256 with the Postgres tests, as in CI) on `task/OP-010-reserved-slot` after merging T-0022 (with `main`): + 6 `test_op010_reserved_slot.py` (the lab reserves a slot for the monitoring role only, SC-04 sized for 100 %, the probe counts the reserved slot and reports `monitor_slot_reserved`, the query reads only `pg_roles`, the health text warns without it; red seen 6/6). Before: **252 passed**, 2 skipped (254 with the Postgres tests, as in CI, after #41; on the laptop 244 passed, 9 skipped, plus the timing-flaky `test_benchmark_compares_direct_and_mcp_on_the_same_read` under load) on `task/T-0022-alerting` after merging `main` (#38, #39, #40): + 17 `test_t0022_alerting.py` (alert intake shared by webhook and pull, identity `fingerprint + startsAt`, host-level alerts, refused targets audited, the Alertmanager source keeps only its host, reconciliation survives a host that is down, the pull config, inventory `alertmanager`, the monitoring stack, Alertmanager sends nothing, Prometheus alerting and scrape jobs, the tunnel forward, the new signals; red seen 16/17). Before: **231 passed**, 2 skipped (233 with the Postgres tests, as in CI; on the laptop 224 passed, 9 skipped) on `task/T-0020-sc04-pg-connections` after merging `main` (#39, #40): + 13 `test_sc04_pg_connections.py` (T-0020, including the review of PR #38: a query that fails after connecting is `argus_db_up 0`, red seen). Before: **218 passed**, 2 skipped (220 with the Postgres tests, as in CI; on the laptop 211 passed, 9 skipped) on `task/T-0023-e2e-runner` after merging `main` (#39: the T-0021 review fixes). Before: **217 passed**, 2 skipped (Postgres tests in CI) on `task/T-0023-e2e-runner` after the review of PR #40: + 6 `test_e2e_runner.py` (red seen 6/6: a view without evidence/audit passed; a reset ran with nothing started). Before: **211 passed**, 2 skipped (Postgres tests included) on `task/T-0023-e2e-runner`: + 27 `test_e2e_runner.py` (T-0023: step 1, red seen: the runner did not exist; then 5 for a dropped connection, red seen 4). Before: **183 passed**, 2 skipped (185, Postgres tests included) on `task/T-0021-tool-isolation` `a5f330a` (T-0014 merged in): + 8 `test_mcp_tools.py`, 6 `test_mcp_child.py`, 6 `test_tool_isolation.py` (+1 needs Docker), 1 `test_compose_split.py` (T-0021 steps 1-5, red seen in each). Before: **162 passed**, 1 skipped (163, Postgres tests included) on `task/T-0014-worker-scheduler` `169ca07`: + `test_a_running_worker_takes_back_a_claim_that_expires_later` (red seen: `recover_every_s` missing). Before: **161 passed**, 1 skipped (162, Postgres tests included with a throwaway `postgres:16-alpine`) on `task/T-0014-worker-scheduler` after merging `main`: + 8 `test_worker_lease.py`, 7 `test_worker_loop.py`, 16 `test_scheduler.py`, 4 `test_compose_split.py`, 1 `test_deploy.py` (T-0014 steps 1-4, red seen in each step). Before: **119 passed**, 6 skipped (125) on `task/T-0019-db-probe`: + 15 `test_db_probe.py` (red seen 15/15). Before: **104 passed**, 6 skipped (110) on `task/op-007-restarting-probe-fix`: + `test_exporter_keeps_the_probe_of_an_owner_in_a_restart_loop` (OP-007, red seen: `owner_active` missing). Before: **103 passed**, 6 skipped (109; the 5 Postgres tests and the real-Docker backup test): 89 before + 7 `test_sc07_network.py` + 7 `test_knowledge_runbook.py` (T-0018: `query_runbook` reads the library in-worker, refuses unknown/malformed ids, is limited by policy, and the context names the branch runbooks) | laptop, 2026-10-07 (OP-007 / T-0018) |
| 3. Frontend unit tests | **20 passed** (Vitest: `parseRunbook` 11, `routes` 4, `mockAuthAdapter` 5) and `vite build` OK Base branch: **39 passed** (Vitest: `httpAuthAdapter` 4, `httpArgusAdapter` 6, `session` 3, `index` 2, `fileRunbooksAdapter` 1, `parseRunbook` 11, `routes` 6, `mockAuthAdapter` 6) and `vite build` OK (348 modules) | CI job `frontend` (T-0016, PR #24) |
| 4. Postgres integration | **95 passed, 0 skipped** (full suite with `ARGUS_TEST_PG_OWNER_DSN` against a throwaway `postgres:16-alpine` and `ARGUS_TEST_DOCKER=1`: the 5 Postgres tests and the real-Docker backup test included) on `task/T-0017-pg-backup-drill` after merging `main`; container removed afterwards | laptop, 2026-10-06 (T-0017, PR #25) |
| 5. CI | first run on `9ccc61d`: audit, lint, gitleaks ✓; tests ✗ (runbook library not available in CI) → fixed in PR #1 (pinned runbooks checkout with a read-only deploy key) | GitHub, 2026-10-02 |
| 7. Deployment validation | OP-011 on both VMs (2026-10-09): migration 004 applied after `BACKUP OK`; SC-03 on vm-166 → **one** incident `inc_8a4cf92444ae` DIAGNOSED, occurrences `DependencyProbeFailed started` + `ContainerUnhealthy attached` (pulled after the incident closed, started before: ACR-0004), then `duplicate` 2; NO INTERFERENCE. Before (step 02, open incidents only): the same run gave two incidents. Before: T-0024 on both VMs (2026-10-09): SC-05 lab fs to 92.6 %, `HostDiskPressure` pulled, `inc_4d78232433a1` DIAGNOSED (`disk_pressure`, root cause the filler); NO INTERFERENCE. Before: OP-010 (2026-10-09): SC-04 at 100 % on vm-166, `argus_db_up=1` throughout, the pulled `DbConnectionsExhausted` opened `inc_03e42714762f` DIAGNOSED (root cause the leaker); NO INTERFERENCE. Before: T-0022 on both VMs (2026-10-09): monitoring on vm-095, alerts pulled from both Alertmanagers every 60 s; SC-03 alert → 2 incidents DIAGNOSED (OP-011), never twice per alert; SC-02 on vm-095 alert → DIAGNOSED; TOOLS ISOLATION OK; NO INTERFERENCE. Before: OP-005 on both VMs (2026-10-09): young SC-01 container at counter 3 -> `restarts_10m` 3 (old expression 1), `ContainerRestartLoop` firing, `inc_312b18f2d8a8` DIAGNOSED; exporter restart with an old container -> 0, no alert; TOOLS ISOLATION OK on vm-095; NO INTERFERENCE. Before: T-0023 step 2 (2026-10-09, both VMs): the scenario runner, SC-01 **5/5** and SC-03 **5/5** PASS, H-1, H-2, SC-09, SC-11 1/1, NO INTERFERENCE after every run. Before: T-0021 step 5e on vm-095 (2026-10-09): the review fixes `6f45218` deployed, the launcher with `cd /` and `python -I`, `isolation_check` with the planted-package probe **TOOLS ISOLATION OK**, NO INTERFERENCE. Before: T-0021 on vm-095 (2026-10-08): worker in `mcp` mode, tokens readable only by `argus-tools`, `isolation_check` **TOOLS ISOLATION OK**, SC-02 DIAGNOSED through the tools process, **OD-3 OK** (p95 overhead 45.7 ms `container.status`, 43.1 ms `container.logs`), NO INTERFERENCE. T-0020 on vm-166 (2026-10-07): **SC-04 DIAGNOSED** (`inc_075fb0006098`, root cause `argus-lab-leaker`, RB-004), gate 94 % for 5 min and alert firing, LAB BASELINE OK, NO INTERFERENCE after removing the leaker's two anonymous volumes. T-0014 on vm-095 (2026-10-08): api / worker / scheduler running; H-1 HEALTHY through the worker; worker killed mid-run (SC-02), run **resumed from its checkpoint** (`incident.resumed`) and DIAGNOSED; schedule submitted once per slot, not resubmitted after a scheduler restart, `schedule.coalesced` while busy; NO INTERFERENCE. T-0019 batch 1 on both VMs (2026-10-07): `phase3_check` **33/33** (5 new db-probe checks), `inspect_database_health` ok through the agent's code path, NO INTERFERENCE. T-0018 on both VMs (2026-10-07): H-1 on vm-166 `HEALTHY`; **SC-07 DIAGNOSED** (`inc_fb92d115abb2`), NO INTERFERENCE. T-0017 on vm-095 (2026-10-06): `BACKUP OK`, `VERIFY OK: 11 tables, 4603 rows match`, NO INTERFERENCE. T-0013 on vm-095 (2026-10-04): `argus db check` 15/15; H-1, SC-09, SC-01 on LangGraph, each checkpointed in Postgres; NO INTERFERENCE on both VMs. Earlier: `phase3_check` 28/28 (2026-10-01) | VMs |

## Currently red

Nothing (`main-guard` green again since PR #9).

## Notable tests

- `test_deployable_files_have_unix_line_endings` — blocks CRLF in files that go to Linux.
- `test_runbook_library_lives_in_the_repository` — D-002: 21 runbooks + index + conventions load from `argus/runbooks/`, the
  default location; no `/opt/argus-runbooks` mount, no `runbooks.lock`. Red seen: the default still pointed to the old
  sibling folder.
- OP-006 (`tests/test_graph_runner.py`): the recursion limit is 100 with the default budgets; a 20-step x 5-read
  budget ends `escalated` (budget exhausted), not with `GraphRecursionError`. Red seen: `GraphRecursionError:
  Recursion limit of 100 reached`.
- Lab baseline (`tests/test_deploy.py`, 3 tests): `deploy.sh status` prints `LAB BASELINE OK` only when every
  `argus-lab-*` container runs and none is unhealthy; it names the stopped/unhealthy ones; without docker it says
  so and never claims OK. Red seen: none of the three found any lab line.
- `test_provider_error_escalates_at_once`, the freshness-gate and identity tests — see `tests/test_core.py`.
- `tests/brain/test_brain.py` — lease claim/refusal/race/expiry/renew/handoff/release, audit (planted secrets,
  addresses, files), lint, archive-step, checkpoint. Red seen: every lease test failed first (a Windows text-mode
  pipe turned LF into CRLF in the `git mktree` input) → fixed by feeding git bytes.
- `tests/test_postgres.py` — contract, forward-only states, SQLite import, a full run on Postgres (needs
  `ARGUS_TEST_PG_OWNER_DSN`).
- The 4 `verify-main` / `guard-push` tests (PR #1) were written **after** the code — no red seen; recorded honestly.
- `tests/test_deploy.py` — `ops/deploy.sh` against a throwaway bare repository: init keeps the old folder, session check,
  newer commit + rebuild hints, local modifications refused, unknown ref refused, status. Red seen: all 6 failed before
  the script existed. Runs with Git for Windows' bash locally and bash in CI.
- `tests/test_db_backup.py` (T-0017) — `ops/db-backup.sh` with a fake `docker`: session check; dump + sha256 +
  fingerprint, root-only; a database that changes during the dump is refused; `verify` restores into a
  network-less tmpfs `argus-lab-pgrestore`, never touches the live database and always removes the container;
  mismatch and tampered dump refused; `verify latest`. Plus one real-Docker test (`ARGUS_TEST_DOCKER=1`). Red seen:
  6 failed against a stub (`assert 1 == 0`); `verify latest` failed with `VERIFY STOP: no such dump: latest`.
- `tests/test_graph_runner.py` (T-0013) — LangGraph runner = plain runner in 5 scenarios; resume after a crash without
  repeating completed reads; the `ARGUS_RUNNER` switch. Red seen: the runner was still `SkeletonRunner`.
- `test_graph_runner_resumes_from_postgres_after_a_restart` (T-0013) — a new app resumes a crashed run from the Postgres
  checkpoint without repeating reads; `test_checkpoint_migration_covers_every_library_migration` guards library upgrades.
- `test_resume_inside_act_does_not_repeat_completed_reads` / `..._inside_evidence_pack_...` (T-0013 review) — a crash
  between two reads of one step resumes with only the missing read. Red seen: completed reads ran twice.
- `tests/test_ui_access.py` (T-0015, ACR-0001) — a `scope=read` token is refused (403, audited) on every non-GET
  route, found by walking the registered routes, and accepted on every `/api/` GET; old tokens count as full; `/me`;
  CORS only for `ARGUS_UI_ORIGINS`. Red seen per step.
- `tests/test_ui_contract.py` (T-0015) — the API's UI routes match `contracts/ui-api.json`; a scripted SC-03-like
  run keeps the shapes of `contracts/samples/*.json`. Red seen: files missing. Regenerate deliberately with
  `ARGUS_UPDATE_UI_CONTRACT=1`.
