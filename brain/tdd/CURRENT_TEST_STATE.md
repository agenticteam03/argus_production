# Current test state

**Last updated:** 2026-10-04 · **Commit:** `8eff994` (main) merged into branch `task/T-0013-langgraph-skeleton`

| Stage | Result | Where / when |
|---|---|---|
| 3. Offline suite | **61 passed** (36 Argus incl. 8 graph-runner + 19 `brain.py` + 6 `deploy.sh`), 5 skipped (the Postgres tests) | laptop, 2026-10-04 |
| 4. Postgres integration | **60 passed** on `661f904` (before merging main; incl. the restart test and the 15 db guarantees) against a throwaway `postgres:16-alpine`; not re-run after the merge (Docker was off) - the merge adds only the 6 offline `deploy.sh` tests | laptop, Docker Desktop, 2026-10-04 |
| 5. CI | first run on `9ccc61d`: audit, lint, gitleaks ✓; tests ✗ (runbook library not available in CI) → fixed in PR #1 (pinned runbooks checkout with a read-only deploy key) | GitHub, 2026-10-02 |
| 7. Deployment validation | `phase3_check` 28/28 (2026-10-01); `argus db check` 13/13 (2026-10-02); scenarios in `CURRENT_STATE.md` §4; NO INTERFERENCE on both VMs (2026-10-02, Task 12c) | VMs |

## Currently red

Nothing (CI on `main` `bf24fac`: test + main-guard green).

## Notable tests

- `test_deployable_files_have_unix_line_endings` — blocks CRLF in files that go to Linux.
- `test_runbook_library_lives_in_the_repository` — D-002: 21 runbooks + index + conventions load from `argus/runbooks/`, the
  default location; no `/opt/argus-runbooks` mount, no `runbooks.lock`. Red seen: the default still pointed to the old
  sibling folder.
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
- `tests/test_graph_runner.py` (T-0013) — LangGraph runner = plain runner in 5 scenarios; resume after a crash without
  repeating completed reads; the `ARGUS_RUNNER` switch. Red seen: the runner was still `SkeletonRunner`.
- `test_graph_runner_resumes_from_postgres_after_a_restart` (T-0013) — a new app resumes a crashed run from the Postgres
  checkpoint without repeating reads; `test_checkpoint_migration_covers_every_library_migration` guards library upgrades.
