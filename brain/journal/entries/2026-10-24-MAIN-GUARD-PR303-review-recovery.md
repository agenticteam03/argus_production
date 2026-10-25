## 2026-10-24 — MAIN-GUARD-PR303: prepare retrospective final-head review

Type: review recovery (no runtime or VM change)
Who: conantkd (+ Codex); teammate approval pending
Context: main-guard on main ada9fec reports that PR #303 merged without a valid review of its final protected-path
changes. PR #300 has corrected its original findings, but its integration remains blocked by that failure.
Decision / result:
- Prepared one retrospective record for #303, following REVIEW_PROTOCOL's follow-up-PR recovery procedure and the
  existing retrospective records. It is proposed only and must not reach main without a teammate's review.
- Recorded the approved head 7b6902a, manual resolution b8533b8, automatic merge d76f742 and merge commit d41b9ea.
- Specified the exact remaining review and the order for recovering main and then merging #300. No enforcement
  code, protection list, architecture, runtime configuration or VM state changes.
Consequences: The recovery PR requires a teammate's review of final #303 content; the author cannot provide it.
References: [task](../../tasks/current/MAIN-GUARD-PR303-review-recovery.md),
[PR #303](https://github.com/agenticteam03/argus_production/pull/303),
[main-guard log](https://github.com/agenticteam03/argus_production/actions/runs/40115433517/job/120935621714).

### Test state

- OBSERVED RED: current main-guard reports MAIN RULE BROKEN for #303's missing final-head teammate review.
- The b8533b8 remerge diff is nonempty; d76f742 has an empty remerge diff.
- This is a records-only recovery; runtime behavior is unchanged. Journal/status, Brain lint/audit and whitespace
  checks passed. The Brain policy suite passed: 109 passed in 161.93 seconds. No new full-suite or runtime RED/GREEN
  claim is made for this record.
- Separately for #300, its original 130 focused regressions passed. After repairing the local Python environment
  and moving pytest temporaries outside the worktree, the six files containing the earlier local failures passed:
  64 passed, 2 skipped. This does not constitute a new full-suite pass.

### Next step

A teammate reviews this recovery PR and PR #303's final protected-path changes. After approval and merge, require
main-guard to pass before resuming #300's update, exact-head checks, new approval and merge. Preserve both branches.
