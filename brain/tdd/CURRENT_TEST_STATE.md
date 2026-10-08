# Current test state

**Last updated:** 2026-10-08 · **Commit:** `task/T-0014-worker-scheduler` `169ca07` (T-0014 step 5)

| Stage | Result | Where / when |
|---|---|---|
| 3. Offline suite | **162 passed**, 1 skipped (163, Postgres tests included) on `task/T-0014-worker-scheduler` `169ca07`: + `test_a_running_worker_takes_back_a_claim_that_expires_later` (red seen: `recover_every_s` missing). Before: **161 passed**, 1 skipped (162, Postgres tests included with a throwaway `postgres:16-alpine`) on `task/T-0014-worker-scheduler` after merging `main`: + 8 `test_worker_lease.py`, 7 `test_worker_loop.py`, 16 `test_scheduler.py`, 4 `test_compose_split.py`, 1 `test_deploy.py` (T-0014 steps 1-4, red seen in each step). Before: **119 passed**, 6 skipped (125) on `task/T-0019-db-probe`: + 15 `test_db_probe.py` (red seen 15/15). Before: **104 passed**, 6 skipped (110) on `task/op-007-restarting-probe-fix`: + `test_exporter_keeps_the_probe_of_an_owner_in_a_restart_loop` (OP-007, red seen: `owner_active` missing). Before: **103 passed**, 6 skipped (109; the 5 Postgres tests and the real-Docker backup test): 89 before + 7 `test_sc07_network.py` + 7 `test_knowledge_runbook.py` (T-0018: `query_runbook` reads the library in-worker, refuses unknown/malformed ids, is limited by policy, and the context names the branch runbooks) | laptop, 2026-10-07 (OP-007 / T-0018) |
| 3. Frontend unit tests | **20 passed** (Vitest: `parseRunbook` 11, `routes` 4, `mockAuthAdapter` 5) and `vite build` OK | CI job `frontend` (T-0016, PR #24) |
| 4. Postgres integration | **95 passed, 0 skipped** (full suite with `ARGUS_TEST_PG_OWNER_DSN` against a throwaway `postgres:16-alpine` and `ARGUS_TEST_DOCKER=1`: the 5 Postgres tests and the real-Docker backup test included) on `task/T-0017-pg-backup-drill` after merging `main`; container removed afterwards | laptop, 2026-10-06 (T-0017, PR #25) |
| 5. CI | first run on `9ccc61d`: audit, lint, gitleaks ✓; tests ✗ (runbook library not available in CI) → fixed in PR #1 (pinned runbooks checkout with a read-only deploy key) | GitHub, 2026-10-02 |
| 7. Deployment validation | T-0014 on vm-095 (2026-10-08): api / worker / scheduler running; H-1 HEALTHY through the worker; worker killed mid-run (SC-02), run **resumed from its checkpoint** (`incident.resumed`) and DIAGNOSED; schedule submitted once per slot, not resubmitted after a scheduler restart, `schedule.coalesced` while busy; NO INTERFERENCE. T-0019 batch 1 on both VMs (2026-10-07): `phase3_check` **33/33** (5 new db-probe checks), `inspect_database_health` ok through the agent's code path, NO INTERFERENCE. T-0018 on both VMs (2026-10-07): H-1 on vm-166 `HEALTHY`; **SC-07 DIAGNOSED** (`inc_fb92d115abb2`), NO INTERFERENCE. T-0017 on vm-095 (2026-10-06): `BACKUP OK`, `VERIFY OK: 11 tables, 4603 rows match`, NO INTERFERENCE. T-0013 on vm-095 (2026-10-04): `argus db check` 15/15; H-1, SC-09, SC-01 on LangGraph, each checkpointed in Postgres; NO INTERFERENCE on both VMs. Earlier: `phase3_check` 28/28 (2026-10-01) | VMs |

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
