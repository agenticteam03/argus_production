# LANES-2 — Journal entries as files and `brain.py rollup`

| Field | Value |
|---|---|
| Status | `done` offline (2026-10-10); in use after its pull request merges |
| Policy | [`../../policies/PARALLEL_LANES.md`](../../policies/PARALLEL_LANES.md), change 2 (accepted in PR #52) |
| Architecture | no change (no ACR): the developer workflow, not Argus |
| Branch | `task/LANES-2-journal-rollup` (from `main`) |
| Owner | `juanbetancurm` (+ agent), quality lane |
| Needs the VM lease | no |

## Goal (plain language)

Every task PR appended to the same three files (`journal/logbook.md`, `tdd/CURRENT_TEST_STATE.md`, `NEXT_STEP.md`),
so two PRs merged the same day always conflicted. On 2026-10-10 every PR of the merge queue (#42, #51, #60, #62)
needed a by-hand fix of exactly those files, one after the other. Now a task writes its own entry file, and one small
roll-up PR folds the entries in after the merges.

## Design

- **An entry file** `brain/journal/entries/<YYYY-MM-DD>-<task>.md`: it starts with `## <date> — <title>` (the logbook
  fields, as before) and may end with two sections: `### Test state` (what used to go into `CURRENT_TEST_STATE.md`)
  and `### Next step` (what used to go into `NEXT_STEP.md`).
- **`brain.py rollup`** (on a `task/rollup-<date>` branch): appends each entry's journal part to the logbook, oldest
  first; puts each section at the top of its file (newest on top, under `**Last updated:**` for the test state);
  rewrites relative links (and a shown path equal to its link) for the new folder; removes the entry files. It checks
  every entry before writing anything; an entry without its heading stops it with nothing changed.
- **The lint rule** (`brain.py lint`, the pre-commit hook): a `task/*` branch whose base has the roll-up must not
  edit those three files. Exempt: `task/rollup-*`, `main`, and branches made before the rule (their base has no
  `cmd_rollup`: the PARALLEL_LANES transition). In CI the branch name comes from `GITHUB_HEAD_REF`; a shallow checkout
  without `origin/main` skips the rule (the local hook enforces it).
- `CURRENT_STATE.md` and `IMPLEMENTATION_PLAN.md` stay editable on a task branch: they rarely conflict and the roll-up
  cannot produce them yet.

## Tests (`tests/brain/test_brain.py`)

6 new tests, red seen (4 failing at first: no `rollup`, no lint rule; the 2 "nothing changes" checks passed from the
start, as expected): the roll-up folds two entries into the three files in order, rebases the links, keeps absolute
links, removes the files; nothing to do changes nothing; a bad entry stops it with nothing changed; lint refuses a task
branch editing `NEXT_STEP.md`, lets `main` and a roll-up branch edit it, and keeps a branch made before the rule.

Review fix (`conantkd`, 2026-10-10): CI's `pull_request` run failed `test_lint_lets_a_rollup_branch_and_main_edit_the_summaries`,
because the rule reads the branch from `GITHUB_HEAD_REF` (right for CI's detached merge commit) and CI sets it to this
PR's branch inside the test's own repository. The `repos` fixture now clears it, and a 7th test pins the CI case: a
detached HEAD with `GITHUB_HEAD_REF=task/…` editing `NEXT_STEP.md` is refused. Red seen: the failure reproduced
locally with the variable set; with the fix all brain tests pass with and without it.

Checked by hand: on a clean copy of `main` the roll-up folded the two existing entries (E2E-1, LANES-1) into the
logbook with working links, and `brain.py lint` stayed clean.

## After the merge

Docs updated: `AGENT_PROTOCOL.md`, `REVIEW_PROTOCOL.md`, `TDD.md`, `README.md`, `PARALLEL_LANES.md`. Branches opened
before the merge keep working as they are. The first roll-up folds today's entries (E2E-1, LANES-1, E2E-1 batch).
