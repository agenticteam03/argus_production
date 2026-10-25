## 2026-10-24 — T-0047 H4 paired evaluation report

Type: implementation
Who: juanbetancurm (+ Codex)
Context: H4's before/after model evaluation needs the same cases and trials summarized in a repeatable offline report.
Decision / result:
- Added `python -m argus.evaluation.compare` for two JSONL result files. It makes no model or network calls.
- It validates row shape, duplicate keys, `(case, trial)` coverage and matching model/strategy metadata.
- It re-grades each row with the current case label and groups class accuracy by the expected class label, not the
  model's predicted class.
- It sums hard failures, hypothesis problem kinds and model calls. Unrecognized H1 messages appear in `unclassified`
  with their original text counted separately.
- Each token total is unknown if any row lacks that token field; missing counts are reported. The p50 uses the same
  upper-middle order statistic as the existing evaluation summary.
Consequences: the tool reports measurements only; it does not choose whether H4's instruction change passes.

### Test state

- Red seen: the expected per-class report failed against an empty summary placeholder.
- Green: 26 synthetic paired-report tests passed; Ruff, Brain lint/audit and `git diff --check` are clean.
- Full offline suite (corrected workspace basetemp): 1 failed, 1,905 passed, 74 skipped, 1 deselected in 1,347.55 s.
  The sole failure is an unrelated timeout in
  `tests/skills/test_pr_review.py::test_a_later_changes_request_or_dismissal_cannot_leave_an_old_approval_active`.
- The first full-suite attempt used an in-worktree basetemp and caused seven `tests/test_deploy.py` clone-discovery
  failures; the corrected run moved basetemp outside all repositories, and those tests passed.

### Next step

S4 completed the pre-review with no findings. The PR draft records the unrelated full-suite timeout for S4's decision.
