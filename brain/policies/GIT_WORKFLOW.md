# Policy — Git workflow

## Branches

| Branch | Purpose | Who writes |
|---|---|---|
| `main` | the latest **verified** shared state (code + Brain) | only merged pull requests |
| `task/T-xxxx-<slug>` | one short-lived branch per task, e.g. `task/T-0013-langgraph-skeleton` | the developer holding the task |
| `session` | `session.json`: one lease per VM and the handoff notes | `brain.py` only |

## The flow

1. `brain.py start` (clean tree, fetch, fast-forward `main`, claim the lease). `--vm vm-095` or `--vm vm-166` claims
   one VM, so two developers can work on the VMs at the same time; without `--vm` it claims both. A change to the
   agent on vm-095 (deploy, rebuild, `hosts.env`, a migration or a restore) needs both
   ([`PARALLEL_LANES.md`](PARALLEL_LANES.md)).
2. `git checkout -b task/T-xxxx-<slug> main` — or continue the branch named in the handoff.
3. Small commits ("checkpoints") after each verified step; push the branch after each commit, so CI runs and the work
   is never only on one laptop. **Every task branch has a pull request from its first push:** open it as a draft
   (`gh pr create --draft`); CI runs on the pull request, once per push (a push to a branch without one runs no CI).
4. Task complete → mark the pull request ready for review (`gh pr ready`; the agent writes the description).
5. The **next developer** reviews and merges ([`../agents/REVIEW_PROTOCOL.md`](../agents/REVIEW_PROTOCOL.md)).
   Merge method: **merge commit**.
6. Session end → `brain.py release`, or `brain.py handoff "…"` if the task is unfinished (both release every VM
   you hold; `--vm` releases one).

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
- merge a pull request that has neither an approval of its last push by another developer nor every self-merge
  condition (`../agents/REVIEW_PROTOCOL.md`, "Self-merge": required checks green on the last push, no protected
  path), or skip the hooks (`--no-verify`). The organization is on GitHub's free plan, so **nothing on GitHub stops
  an owner** from doing it: the rule is enforced by us, and checked by the pre-push hook, CI job `main-guard` and
  `brain.py start` (`brain.py verify-main`; other exceptions only in `main-exceptions.txt`);
- modify another developer's task branch without talking to them (after an expired lease: wait for them, or start a
  fresh branch from `main`);
- commit secrets, `output*.bash`, `*.db`, `.env`, `hosts.env`, `secrets/` — see [`SECURITY.md`](SECURITY.md).

## Line endings

The repository is LF-only (`.gitattributes`). On Windows set `git config core.autocrlf input`. Files deployed to Linux
must never contain CRLF — a test enforces it.
