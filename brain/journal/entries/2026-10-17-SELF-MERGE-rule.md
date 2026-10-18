## 2026-10-17 — SELF-MERGE: authors may merge their own pull requests when the required checks are green

Type: decision
Who: juanbetancurm (+ agent)
Context: the temporary fast-track windows (2026-10-05 to 2026-10-12, 2026-10-14 to 2026-10-16) showed that small,
well-tested pull requests waited a day or more for a review. The team wants a standing rule instead of windows.
Decision / result: a standing **self-merge** rule in `agents/REVIEW_PROTOCOL.md`: the author may approve and merge
their own pull request when the CI jobs `test` and `frontend` are green on its last push (or a `LOCAL CI PASS`
comment names that commit), the branch is up to date with `main`, and it changes none of the protected paths
(architecture and ACRs, the security and review rules, the enforcement, `config/policy.yaml`, `config/inventory.yaml`,
the public edge, the UI contract). `brain.py verify-main` (`main-guard`) now checks those conditions through the
GitHub API (`self_merge_problem`, `SELF_MERGE_PROTECTED`), so a valid self-merge needs no `main-exceptions.txt` line.
The rule starts when a teammate approves this pull request: it changes the enforcement, so it cannot be self-merged.
Consequences: the review protocol, `GIT_WORKFLOW.md`, `AGENT_PROTOCOL.md`, `PARALLEL_LANES.md`, `HOW_WE_WORK.md`,
`START_HERE.md` and the Brain README say the same. The gaps where a green CI does not yet mean "safe to merge", and
the checks to add, are OP-014; the first three (Docker tests in CI, prompt-injection cases, the flaky timing test) go
in `task/TEST-HARDEN-1`. VM changes still need their lease, `code.bash` and `nonint-check.sh`.
References: [review protocol](../../agents/REVIEW_PROTOCOL.md), [OP-014](../../OPEN_PROBLEMS.md).

### Test state

`tests/brain/test_brain.py`: 6 new test functions (19 cases) for the self-merge check (green checks and ordinary files accepted; each
required check missing or not `success` refused; every protected path refused; 100 or more files refused; a
`LOCAL CI PASS` for the last push accepted, for an earlier push or a `FAIL` refused; `check_main` reports why).

### Next step

A teammate reviews and approves this pull request; then `task/TEST-HARDEN-1` (OP-014 steps 1-3).
