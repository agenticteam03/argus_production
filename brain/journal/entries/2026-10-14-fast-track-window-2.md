## 2026-10-14 — A second fast-track window proposed (2026-10-14 to 2026-10-20)

Type: process proposal
Who: conantkd (+ agent)
Context: the fast-track of `REVIEW_PROTOCOL.md` expired on 2026-10-12. Since then, small changes (records, a
one-line gateway fix with its tests: #138, #141) wait a day or more for a review.
Decision / result: proposed a second window, 2026-10-14 to 2026-10-20 inclusive, with the same people and conditions.
The conditions:
- a task branch;
- CI green and up to date;
- the agent's review report posted;
- the PR's own line in `main-exceptions.txt`;
- never a safety principle, an ACR or the enforcement.

The window exists only if a teammate approves this pull request, which is not fast-tracked because it changes the
rule. Any teammate's objection ends it. Updated together: `REVIEW_PROTOCOL.md`, `GIT_WORKFLOW.md`, the header of
`main-exceptions.txt`, `PARALLEL_LANES.md`, `CURRENT_STATE.md`, T-0016's note.
Consequences: nothing in `brain.py` or CI changes (no date is coded there). Until the approval, #138 and #141 follow
the normal review.
References: [`REVIEW_PROTOCOL.md`](../../agents/REVIEW_PROTOCOL.md).

### Test state

No code change.

### Next step

A teammate approves (or objects) in the PR.
