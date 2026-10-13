# Current test state

**Last updated:** 2026-10-12 (roll-up) · **Commit:** `main` after #96 (`817d88f`)

`tests/test_t0035_monitoring_heartbeat.py`: 3 new tests (red seen): the `platform` route, the default when only
another family has one, and `load_routing` (a file with a `platform` route, no file, an unknown family refused).

No code change. Local CI unchanged.

`tests/test_t0039_prior_incidents.py`: 7 tests (red seen: no capability).

`tests/test_t0037_docker_read_verbs.py`: 12 tests (red seen: no route, no capability).

`tests/test_t0043_missing_scrape_jobs.py`: 4 tests (red seen); one promtool case; the T-0027 signal check updated.

`tests/test_t0042_routing.py`: 10 tests (red seen: no `route` in the notification).

`tests/test_t0040_trace_request_path.py`: 6 tests (red seen: no capability).

`tests/test_t0038_compare_baseline.py`: 14 tests (red seen: no capability).

`tests/test_t0036_metric_histories.py`: 14 tests (red seen: no `mounts` parameter in the Prometheus client).

`tests/test_e2e8_catalogue.py` 11 (red seen), `tests/test_e2e_runner.py` 39 unchanged, green.

`tests/test_eval4_health_wording.py`: the word list updated; 1 test added with the two answers seen (pass) and a
diagnosis naming no check (still fails).

`tests/test_t0033_rotate_token_script.py`: 3 tests added (red seen: `db_probe` refused).

`tests/test_t0035_monitoring_heartbeat.py`: 22 tests (red seen: no `argus.application.monitoring`);
`tests/test_postgres.py`: 1 test added (the state and the escalated incident under the runtime role; runs on CI).

`tests/test_local_ci.py`: 1 test added (red seen: the HEAD mode checked this checkout).

23 floor paths refused by both the agent and the probe with an allow-everything list (16 were allowed: red seen); 5
ordinary paths still allowed; name patterns on directories; the open uses `O_NOFOLLOW` (red seen); a symlink swapped
in after the walk is refused (Linux only, skipped on Windows); a stale probe copy still gets the floor.

`tests/test_redaction_paths.py`: 8 tests added (red seen: the URL and the other-path cases unmasked, and a token under
the declared directory kept); 5 declared paths at a path start still readable.

`tests/test_redaction_paths.py`: 18 tests (red seen: the three URL-path secrets unmasked on `main`, and no
`declared_paths`).

`tests/test_local_ci.py`: 9 tests (red seen: no `ops/local_ci.py`).

`tests/brain/test_brain.py`: 2 tests added (red seen: the merge of main after a roll-up refused; a summary edited during
the merge still refused).

`tests/test_redaction_paths.py`: 8 tests (red seen 3/3 on the paths); the core and knowledge tests that use the
redactor pass.

`tests/test_t0019_batch3c_network.py`: 15 tests (red seen: no `/connectivity` route, no `attempts`, no capability, no
case answers).

Review of #101 (`juanbetancurm`): `/tcp` attempts now share an 8 s budget (under the agent's 10 s client
timeout; each attempt waits `min(3 s, what is left)`, `budget_exhausted` when spent); before, 5 attempts to
a port that never answers could take 17 s and end the read `timeout`. One more test (16), red seen. The
scope of `to` (allowlisted, same host, not checked against the incident's scope) is noted in the task file.

`tests/test_t0019_batch3b_host_verbs.py`: 18 tests (red seen: no routes, no capabilities, no case answers; the symlink
test runs where symbolic links can be made, CI).

`tests/test_combined_capabilities.py`: 8 tests (red seen: no `max_subcalls`, no snapshot, no `refs_of`).

`tests/test_tool_allowed_values.py`: 3 tests (red seen: no `allowed_values`, the probes offered on every target).

`tests/test_eval4_health_wording.py`: 4 tests (red seen 3/4 with the old labels).

`tests/test_t0033_rotate_token_script.py`: 4 tests (red seen 3/4: hard-coded paths, mode 0400 after a rollback,
"recreated" after a failed compose); the mode check runs where the filesystem has POSIX modes (CI).

`tests/test_t0019_batch3a_inspection.py`: 33 tests (red seen: no `argus.policy.inspection`), green. `tests/test_sc07_network.py`'s render test now copies `policy.yaml` too (the renderer has two inputs).
Full suite green on the laptop (pytest exit 0).

No new tests (a model evaluation). Model evaluation on vm-095, 55 cases × 5: 0.96 (core 0.99), abstention 0.98, hard
0 0 0 (EVAL-2 E.4: 0.93, 0.95, 0.96).

**2026-10-12, `main` `2fa4d01` (#91-#94), full suite on a laptop (roll-up, `conantkd`):** green, 20 skipped (Postgres
and environment). New since EVAL-2: `tests/test_op012_incident_budget.py` 3 (red seen: 16 `container.status` reads
under LangGraph, the policy allows 8), `tests/test_eval3_sigkill.py` 3 (red seen 2/3: the baseline answered
`diagnosed`), `tests/test_t0033_token_rotation.py` 4 (red seen: no reload in `Dispatcher`). The MCP benchmark
(`test_mcp_child.py`, p95 overhead < 100 ms) can fail on a loaded laptop; alone it passes.

**T-0033 step 2, 2026-10-12:** No new tests (a VM proof). Main's CI green on `244453b`; T-0033's 4 tests and OP-012's 3
run in CI.

**T-0019 batch 2, 2026-10-12 (`task/T-0019-batch2-host-probe`):** `tests/test_t0019_host_probe_batch2.py` 36 tests
(red seen for each step: probe verbs, capabilities, policy, memory bounds, walk share, case answers, prompt rule,
invalid-decision reasons); full suite 555 passed, 20 skipped. Model evaluation on vm-095 (EVAL-2 + batch 2, 5 trials):
0.92 (core 0.95), abstention 1.00, disk 1.00, hard 0 0 0.

**EVAL-2, 2026-10-12 (`task/EVAL-2-model-trials`):** `tests/test_eval2_fixes.py` 7 new (red seen: no round for a
stopped writer, no prompt rule, two contradictory fixtures, a store left behind); full suite green. Model evaluation on
vm-095, 55 cases × 5: 0.93 (core 0.95), abstention 0.96, hard 0 0 0; baseline 52/55.

**EVAL-1, 2026-10-11:** red seen (the baseline escalated the writer cases; after the review, it named the writer
with empty logs); `tests/test_evaluation.py`, `test_e2e5_confirm_writer.py`, `test_t0024_sc05_disk.py` green (108);
baseline evaluation 55 cases, 52 pass, `disk_pressure` 7/8 (the declared miss), hard 0 0 0.

**E2E-5, 2026-10-11 (`task/E2E-5-confirm-writer`):** 7 tests in `tests/test_e2e5_confirm_writer.py` (red seen: no
strategy; the skeleton test fails with `model_loop`, the filler's logs never read); SC-05 class test updated to the new
strategy; core, graph and evaluation tests green.

**LANES-2 follow-up, 2026-10-11:** `test_rollup_orders_same_day_entries_by_when_they_reached_the_branch` (red seen:
file-name order); the roll-up tests pass; replayed on `main` before #73: the hand-set order of #73.

**E2E-3, 2026-10-11 (`task/E2E-3-container-mounts`):** 5 tests in `tests/test_e2e3_container_mounts.py` (red seen
4/5: no `host_mounts` from the gateway or in `container.status`); gateway, SC-05/06/07/08 and evaluation tests green;
baseline evaluation 45/47, hard 0 0 0. Review (`conantkd`): + 1 test, the tool's description and "when" name the
host mounts (red seen); full suite green on the laptop.

**E2E-2 step 2 (2026-10-10, `conantkd`):** both VMs on `main` `0f076f2`, vm-095's agent rebuilt. Runner batch: SC-07
5/5, SC-05 4/5 (the miss read and explained), 0 errors, NO INTERFERENCE after every run.

**T-0031 (phase 8), 2026-10-10 (`task/T-0031-write-gate-standing`):** 25 write-gate tests in CI
(`tests/test_write_gate_standing.py`, `tests/test_write_gate_check.py`); the standing cases pin existing behaviour,
red seen by three mutations; the check's cases red before the module and script existed (and the host-only
fail-open on a failed `docker ps`). `WRITE GATE CLOSED` on vm-095 and, host-only, on vm-166.

**E2E-2 follow-up (2026-10-10, `task/E2E-2-disk-partial`):** 4 more tests in `tests/test_e2e2_evidence_gaps.py` (12
in all), red seen 2/4; the offline suite passes.

**E2E-2, 2026-10-10 (`task/E2E-2-evidence-gaps`):** 8 tests in `tests/test_e2e2_evidence_gaps.py` (red seen 6/8:
no `networks` on `TargetInfo`, `host.disk_usage` read `/` by default); SC-05, SC-07, core and evaluation tests green;
baseline evaluation 45/47 (the two known baseline misses), hard 0 0 0.

**E2E-1 (phase 12), 2026-10-10:** runner batches on vm-166, both VMs on `main`: SC-04 5/5, SC-06 5/5, SC-07 6/10,
SC-05 6/10 (two evidence gaps, E2E-2); 0 errors, NO INTERFERENCE after every run.

**LANES-2, 2026-10-10 (`task/LANES-2-journal-rollup`):** 7 new tests in `tests/brain/test_brain.py` (red seen: no
`rollup`, no lint rule; the CI case reproduced with `GITHUB_HEAD_REF` set), all brain tests pass.

**T-0032 (phase 13), 2026-10-10 (`task/T-0032-prometheus-down`):** 3 tests in
`tests/test_t0032_prometheus_down.py` (both runners and the real adapter; red seen by removing the
`MetricsUnavailable` handling in each runner). On vm-095: UNDIAGNOSABLE for vm-095, HEALTHY for vm-166.

**T-0030 (phase 13), 2026-10-10 (`task/T-0030-pg-restart`):** 3 tests in `tests/test_t0030_pg_restart.py` (red seen: a
database error from `recover()` or the claim ended the worker's loop). Full suite on the laptop: green.

**T-0029 (SC-08), 2026-10-10 (`task/T-0029-sc08-nginx`):** 12 tests in `tests/test_t0029_sc08_nginx.py` (red seen
12/12: no probe, signal, class, alert, lab or inventory entries); 6 evaluation cases `tests/eval/cases/nginx-*.yaml`
(baseline 6/6, hard 0 0 0). Full suite on the laptop: green.

**OP-008, 2026-10-09 (`task/OP-008-backup-retention`):** three new retention/verification tests and the changed
snapshot-consistency test failed before implementation, then passed. `tests/test_db_backup.py`: 15 passed locally,
including two real Docker/PostgreSQL cases; one writes to the live throwaway database between snapshot export and
`pg_dump`, then restores successfully. The Windows full suite with Docker had one unrelated OD-3 timing-benchmark
failure (448.6 ms p95 overhead against 100 ms); every other executed test passed, with seven Linux/Postgres skips.
Linux CI and the VM dry run are pending. Review notes of PR #51 (2026-10-10): three new prune tests red seen (no
checksum gate, no `newest verified` line, leftovers not listed), then green: 16 passed, 2 real-Docker skipped. VM dry run done (OP-008 step 02).

**T-0027, 2026-10-09 (`task/T-0027-blind-spot`, the stack and `main` up to #53 merged in):** 10 tests in
`tests/test_t0027_blind_spot.py` (red seen: no class; a check of a host with node-exporter down ended `no_incident`),
5 evaluation cases `tests/eval/cases/blind-*.yaml` (baseline: 5/5, 0 model calls, hard 0 0 0), and
`test_every_registered_class_has_its_cases_or_is_listed_as_awaiting_them` (red seen without the cases;
`disk_pressure` listed as awaiting). Full suite on the laptop: green (Postgres tests skipped; the stack branches below
it passed with a throwaway Postgres). Stage 7: `inc_263f471e33e3` on vm-166, escalated as `monitoring_blind_spot`,
resolved after the exporter came back; NO INTERFERENCE.

**T-0026, 2026-10-09 (`task/T-0026-alert-resolution`):** 16 new tests in `tests/test_t0026_alert_resolution.py`
(red seen 14/16: a `resolved` notification was `ignored`; `active_alerts`, `resolve_absent` and `resolved_at` were
missing; the silenced-alert and the received-before guards were green from the start) and
`tests/test_postgres.py::test_alert_occurrence_resolution` (migration 005: forward only, column grant, no DELETE), plus
five `argus db check` lines. Full suite on the laptop with a throwaway `postgres:16-alpine`: **301 passed**, 3 skipped;
the OD-3 timing benchmark failed once in the full run and passed alone (the known Windows timing flake).
Stage 7 (2026-10-09, both VMs on `ea01c68`): `argus db check` 20/20; SC-03 `inc_ed6a85ccd28f`, both occurrences
resolved one pass after the alerts cleared, the incident unchanged; NO INTERFERENCE.

**OP-005, 2026-10-09 (`task/OP-005-young-restarts`):** three new unit tests were red against the old exporter/signal,
then passed. Five PromQL synthetic-series cases passed with Prometheus 3.5.0 `promtool test rules` (young, old with
scrape gap, old with continuous history, recreated same name, and missing creation metric). The full local Windows
worktree suite finished with 6 unrelated failures: 5 `tests/test_deploy.py` fixtures see their temporary `app` as an
existing Git clone; the OD-3 timing benchmark measured 155 ms p95 overhead against its 100 ms budget. Review of PR #41
(`main` merged in, + 1 test: the restart alert counts like the signal, red seen): 228 passed, 9 skipped on the laptop
(237); the only failure is the same timing-flaky benchmark (passes alone; green in CI). The VM checks follow.

**OP-004, 2026-10-09 (`task/OP-004-checkpoint-cleanup`):** six new tests pass against a throwaway PostgreSQL 16 and
the manual/timer wrapper. Three PostgreSQL cases were red before the command existed. VM dry run and CI are pending. 2026-10-10: the wrapper test now requires the container to run as the secret's
owner (red with `--user 0:0`, green after); VM dry run done (OP-004 step 02).

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
