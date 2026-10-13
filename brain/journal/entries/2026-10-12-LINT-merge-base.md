## 2026-10-12 — brain.py lint lets a task branch merge main after a roll-up (LINT-merge-base)

Type: fix
Who: conantkd (+ agent)
Context: merging `main` into #101 and #103 (after the roll-up #97) was refused by the pre-commit lint: "a task branch
does not edit the shared summaries" for `logbook.md`, `CURRENT_TEST_STATE.md` and `NEXT_STEP.md`. While `git merge`
is in progress HEAD is still the branch's old tip, so `merge-base(HEAD, origin/main)` is the old base and the
summaries changed by main's roll-up looked like the branch's own edits. Any task branch merging `main` after a
roll-up hits it.
Decision / result: `summary_edits` judges from `MERGE_HEAD` when a commit of `main` is being merged: only what the
branch changes on top of it counts. A summary edited by the branch during the merge is still refused. Not skipped with
`--no-verify`: the merges of #101 and #103 wait for this fix.
Consequences: touches the enforcement (`brain.py`): needs a teammate's approval. After the merge, `main` is merged into
#103 and #101.
References: `brain/tools/brain.py` (`summary_edits`), `tests/brain/test_brain.py`.

### Test state

`tests/brain/test_brain.py`: 2 tests added (red seen: the merge of main after a roll-up refused; a summary edited during
the merge still refused).

### Next step

After approval and merge: merge `main` into #103 (3b), then #101 (3c; also resolves `T-0019-db-probe.md`, both sections
kept).
