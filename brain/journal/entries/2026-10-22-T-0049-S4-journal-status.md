## 2026-10-22 — T-0049 S4: journal and task status skill

Type: implementation (development tooling only)
Who: juanbetancurm (+ agent); review: conantkd
Context: T-0049 S4 calls for a repeatable journal entry and task status procedure. The Brain roll-up moves
`### Test state` and `### Next step` into shared summaries, while task branches keep those summaries untouched.
The branch was fast-forwarded to current main `6a72339` (#275) before final validation.

Decision / result:
- Add a short skill that reads the current Brain policies, uses the journal roll-up format, and keeps a task status
  linked to evidence. A `done` state requires a merged, linked PR; local test success alone cannot establish it.
- Add a read-only validator for the journal headings, nonempty roll-up sections, status row, evidence link, and
  linked PR when the status is `done`. It does not verify the truth of a PR's state; that remains a review check.
- Keep this PR to the skill, its validator and tests, and this entry. The shared T-0049 task row is owned by S1
  until S2's parallel T-0049 S3 PR and this PR have merged.

Consequences: the skill packages an existing documentation workflow. It changes no Argus runtime, Brain policy,
VM state or review permission.

References: [T-0049](../../tasks/current/T-0049-agent-skills.md),
[parallel lanes](../../policies/PARALLEL_LANES.md), [agent protocol](../../agents/AGENT_PROTOCOL.md).

### Test state

- RED seen before implementation: the five focused tests failed because the validator was absent.
- GREEN after S3's paired review fixes: seventeen focused tests passed (missing/empty sections, unlinked status,
  missing row, linked versus unlinked completion in table, plain and marked-up forms, and three real task shapes).
  Brain lint/audit, Ruff and diff whitespace checks clean.
- Full offline suite on integrated main `6a72339`, after the final `done` guard: 1649 passed, 62 skipped,
  1 deselected (the known detached-CI Brain test), exit 0. S1 re-ran the 17 focused tests, Ruff and Brain lint
  on the final tree: clean. S1 reviewed the final `done` guard (S4 hit its quota before S3's clearance).

### Next step

Conantkd's GitHub review of this protected skill PR. S1 updates the shared T-0049 status row after both parallel
skill PRs merge.
