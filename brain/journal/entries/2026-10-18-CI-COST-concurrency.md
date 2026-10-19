## 2026-10-18 — CI-COST: main runs main-guard alone; a new push cancels the PR's run in progress

Type: decision
Who: conantkd (+ agent)
Context: the organisation's GitHub Actions minutes went past the plan's 3000 included minutes in October (about 3700
used). Each PR push costs about 6 minutes (`test` and `frontend`) and each merge about 9 more on `main` (the same two
jobs again, plus `main-guard`); 38 runs on 2026-10-18 alone, several of them for a PR pushed twice in a row.
Decision / result: two changes in `.github/workflows/ci.yml`.
- **`test` and `frontend` run on pull requests only.** A merge already needs both green on the PR's last push with the
  branch up to date with `main` (REVIEW_PROTOCOL.md), so the run on `main` tested the same code. A push to `main` now
  runs `main-guard` alone (about 3 minutes instead of 9).
- **`concurrency`:** one group per pull request; a new push cancels that PR's run still in progress (its result no
  longer counts, only the last push does). Runs on `main` are never cancelled, so every merge gets its `main-guard`.
Consequences: about 6 minutes saved per merge, plus the unfinished part of every superseded PR run. A cancelled run
shows "cancelled", not failed. What `main` no longer gets is a second run of the tests after the merge commit; a
check on `main` itself stays available with `python ops/local_ci.py --main`. Changing `.github/` is a protected path:
this needs a teammate's approval.
References: [REVIEW_PROTOCOL.md](../../agents/REVIEW_PROTOCOL.md).

### Test state

No code change. The workflow is checked by its own run on this PR (`test` and `frontend` start; `main-guard` is
skipped). `brain.py lint` green.

### Next step

After the merge, check the push to `main` runs `main-guard` only.
