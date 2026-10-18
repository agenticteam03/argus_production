# Policy — tests run continuously

Tests run **all the time**, not only at approval. The pull-request check is the *last* gate, not the only one.

| Stage | What runs | Who / where | When |
|---|---|---|---|
| 1. Red | the new or changed test alone (`pytest tests/test_x.py::test_new`) | agent, laptop | before writing code; it **must fail for the right reason** — record it as "red seen" |
| 2. Green | the same test | agent, laptop | after each small code change |
| 3. Suite | the full offline suite (`pytest -q`, seconds) | agent, laptop | after every green, and before every commit |
| 4. Integration | Postgres tests (`ARGUS_TEST_PG_OWNER_DSN`, a throwaway Postgres in Docker Desktop) | agent, laptop | before committing anything that touches persistence |
| 5. CI on every push | offline suite + Postgres service + LF check + secret scan + Brain lint | GitHub Actions (when it does not run: `ops/local_ci.py`, laptop) | **every push to a task branch (each has a pull request, a draft until it is ready: `GIT_WORKFLOW.md`), and every push to `main`**, once each |
| 6. Merge gate | the same CI, green on the pull request's latest commit (or a `LOCAL CI PASS` comment for it, [`../agents/REVIEW_PROTOCOL.md`](../agents/REVIEW_PROTOCOL.md)) | GitHub / the reviewer | before merging into `main` |
| 7. Deployment validation | `phase3_check`, `argus db check`, scenario runs, `nonint-check.sh` | developer runs `code.bash` on the VMs | after every deployment step |

## Rules

- **Red first.** A test that never failed proves nothing. Record "red seen" (test name + the failing line) in the task
  file or `tdd/CURRENT_TEST_STATE.md`.
- **Fail for the right reason.** An `ImportError` or a typo is not the right reason; the assertion about the new
  behaviour is.
- **Infrastructure steps** (where unit tests do not apply): the `Expected:` lines of the step are written **before**
  running — stage 7 replaces stages 1–3.
- **Never weaken a test to make it pass.** If the test is wrong, say so, fix it in a separate, explained change.
- **Postgres tests locally** (needs Docker Desktop):
  ```powershell
  docker run -d --rm --name argus-pgtest -e POSTGRES_USER=argus_owner -e POSTGRES_DB=argus `
    -e POSTGRES_PASSWORD=<throwaway> -p 127.0.0.1:55432:5432 postgres:16-alpine
  $env:ARGUS_TEST_PG_OWNER_DSN = "host=127.0.0.1 port=55432 dbname=argus user=argus_owner password=<throwaway>"
  .\.venv\Scripts\python -m pytest -q
  docker stop argus-pgtest
  ```
  The fixture drops and recreates the `public` schema: **never** point it at a real database.
- After stage 3–7 results change, write them in the `### Test state` section of the task's journal entry file
  (`journal/entries/`); `brain.py rollup` moves them into
  [`../tdd/CURRENT_TEST_STATE.md`](../tdd/CURRENT_TEST_STATE.md) after the merge.
