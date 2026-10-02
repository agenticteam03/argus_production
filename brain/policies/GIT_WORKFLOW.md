# Policy — Git workflow

## Branches

| Branch | Purpose | Who writes |
|---|---|---|
| `main` | the latest **verified** shared state (code + Brain) | only merged pull requests |
| `task/T-xxxx-<slug>` | one short-lived branch per task, e.g. `task/T-0013-langgraph-skeleton` | the developer holding the task |
| `session` | `session.json`: the session lease and the handoff note | `brain.py` only |

## The flow

1. `brain.py start` (clean tree, fetch, fast-forward `main`, claim the lease).
2. `git checkout -b task/T-xxxx-<slug> main` — or continue the branch named in the handoff.
3. Small commits ("checkpoints") after each verified step; push the branch after each commit, so CI runs and the work
   is never only on one laptop.
4. Task complete → pull request into `main` (the agent writes the description).
5. The **next developer** reviews and merges ([`../agents/REVIEW_PROTOCOL.md`](../agents/REVIEW_PROTOCOL.md)).
   Merge method: **merge commit**.
6. Session end → `brain.py release`, or `brain.py handoff "…"` if the task is unfinished.

Pushing a branch shares *work in progress*. Only **merging into `main`** makes it the project state.

## Commit messages

```text
T-0013: add LangGraph skeleton with Postgres checkpointer

What changed and why, in 1–5 lines. Tests: 34 passed (red seen: test_resume_after_crash).
```

- Start with the task id. Present tense. Say *why*, not only *what*.
- One logical change per commit; the Brain update for that change goes in the same commit.

## Never

- commit to or push `main` directly; force-push `main`, `session` or someone else's branch;
- merge your own pull request, or bypass branch protection (all three developers are organization owners: the rule
  "do not allow bypassing" exists because of that);
- modify another developer's task branch without talking to them (after an expired lease: wait for them, or start a
  fresh branch from `main`);
- commit secrets, `output*.bash`, `*.db`, `.env`, `hosts.env`, `secrets/` — see [`SECURITY.md`](SECURITY.md).

## Line endings

The repository is LF-only (`.gitattributes`). On Windows set `git config core.autocrlf input`. Files deployed to Linux
must never contain CRLF — a test enforces it.
