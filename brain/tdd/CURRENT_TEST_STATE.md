# Current test state

**Last updated:** 2026-10-06 · **Commit:** `task/T-0015-ui-read-access` (steps 1-5, before commit); `main` `24d9bb0`

| Stage | Result | Where / when |
|---|---|---|
| 3. Offline suite | **81 passed**, 5 skipped on the T-0015 branch (+10 `test_ui_access.py`, +3 `test_ui_contract.py`) | laptop, in Docker `python:3.12` (Smart App Control blocks `uuid_utils` natively), 2026-10-06 |
| 3. Offline suite (main) | **68 passed** (40 Argus incl. 12 graph-runner + 19 `brain.py` + 9 `deploy.sh`), 5 skipped (the Postgres tests) | laptop, 2026-10-06 (lab baseline check) |
| 4. Postgres integration | **60 passed** on `661f904` (before merging main; incl. the restart test and the 15 db guarantees) against a throwaway `postgres:16-alpine`; not re-run after the merge (Docker was off) - the merge adds only the 6 offline `deploy.sh` tests | laptop, Docker Desktop, 2026-10-04 |
| 5. CI | first run on `9ccc61d`: audit, lint, gitleaks ✓; tests ✗ (runbook library not available in CI) → fixed in PR #1 (pinned runbooks checkout with a read-only deploy key) | GitHub, 2026-10-02 |
| 7. Deployment validation | T-0013 on vm-095 (2026-10-04): `argus db check` 15/15; H-1, SC-09, SC-01 on LangGraph, each checkpointed in Postgres; NO INTERFERENCE on both VMs. Earlier: `phase3_check` 28/28 (2026-10-01) | VMs |

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
