## 2026-10-19 — Review rule: an update that only brings in main keeps the approval

Type: decision
Who: juanbetancurm (+ agent)
Context: a pull request merges only when it is up to date with `main` and approved on its last push. Every merge puts
the other open pull requests behind, and "Update branch" is a new push, so their approvals stopped counting. #174 and
#176 were approved and fell behind when #178 merged; updating them would have needed a new review although their code
had not changed (in the end they were merged without the update).
The T-0045 steps all touch `contracts/`, a protected path, so the self-merge rule does not help them.
Decision / result:
- An approval stays valid after later pushes when each commit after the approved one is a merge with `main` that git
  made without a conflict (its tree is git's automatic merge of its parents). A resolved conflict, any extra edit, any
  other commit or a rewritten branch needs a new approval. CI green on the last push and up to date are unchanged.
- `brain.py verify-main` (CI `main-guard`, `brain.py start`) checks it with `only_main_merged_since` and
  `git merge-tree --write-tree`; `check_main` takes it as `keeps_approval`.
- `REVIEW_PROTOCOL.md`: the rule, why, and how it is enforced; `GIT_WORKFLOW.md`: the "Never" line refers to it.
Consequences: the reviewer can update an approved pull request and merge it without a new review round. It changes
the enforcement, so it starts when a teammate approves this pull request.
References: `brain/agents/REVIEW_PROTOCOL.md`, `brain/tools/brain.py`.

### Test state

Six new tests in `tests/brain/test_brain.py`, red seen first (the function did not exist): `check_main` keeps an
approval only through `keeps_approval` and never the author's own; with real git repositories, a clean merge of main
keeps it; a later commit, an edit inside the merge, a resolved conflict and a rewritten branch do not.

### Next step

A teammate's approval; then updating an approved pull request with `main` no longer needs a new review.
