# Current test state

**Last updated:** 2026-10-02 · **Commit:** `bf24fac` (main) + branch `task/T-0013-langgraph-skeleton`

| Stage | Result | Where / when |
|---|---|---|
| 3. Offline suite | **54 passed** (35 Argus incl. 7 graph-runner + 19 `brain.py`), 4 skipped (the Postgres tests) | laptop, 2026-10-03 |
| 4. Postgres integration | **32 passed** (28 + 4) against a throwaway `postgres:16-alpine` | laptop, Docker Desktop, 2026-10-02 |
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
- `tests/test_graph_runner.py` (T-0013) — LangGraph runner = plain runner in 5 scenarios; resume after a crash without
  repeating completed reads; the `ARGUS_RUNNER` switch. Red seen: the runner was still `SkeletonRunner`.
