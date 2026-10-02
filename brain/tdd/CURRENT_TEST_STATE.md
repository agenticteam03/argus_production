# Current test state

**Last updated:** 2026-10-02 · **Commit:** (before the first commit)

| Stage | Result | Where / when |
|---|---|---|
| 3. Offline suite | **43 passed** (28 Argus + 15 `brain.py`), 4 skipped (the Postgres tests) | laptop, 2026-10-02 |
| 4. Postgres integration | **32 passed** (28 + 4) against a throwaway `postgres:16-alpine` | laptop, Docker Desktop, 2026-10-02 |
| 5. CI | `.github/workflows/ci.yml` written (audit, lint, gitleaks, tests with a Postgres service); first run at the B6 push | — |
| 7. Deployment validation | `phase3_check` 28/28 (2026-10-01); `argus db check` 13/13 (2026-10-02); scenarios in `CURRENT_STATE.md` §4; NO INTERFERENCE on both VMs (2026-10-02, Task 12c) | VMs |

## Currently red

Nothing.

## Notable tests

- `test_deployable_files_have_unix_line_endings` — blocks CRLF in files that go to Linux.
- `test_runbooks_lock_matches_compose_default` — `config/runbooks.lock` and the compose default point to the same commit.
- `test_provider_error_escalates_at_once`, the freshness-gate and identity tests — see `tests/test_core.py`.
- `tests/brain/test_brain.py` — lease claim/refusal/race/expiry/renew/handoff/release, audit (planted secrets,
  addresses, files), lint, archive-step, checkpoint. Red seen: every lease test failed first (a Windows text-mode
  pipe turned LF into CRLF in the `git mktree` input) → fixed by feeding git bytes.
- `tests/test_postgres.py` — contract, forward-only states, SQLite import, a full run on Postgres (needs
  `ARGUS_TEST_PG_OWNER_DSN`).
