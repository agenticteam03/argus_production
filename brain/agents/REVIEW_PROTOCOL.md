# Review protocol — the next developer reviews, with AI help

A pull request by developer A is reviewed and approved by **the next developer (B) who works**, at the **start** of
B's session, with B's AI agent. Reviewing comes before new work, because new work must start from the merged state.

## Steps

1. `brain.py start` lists the pull requests waiting for review.
2. **Explain.** The agent fetches the branch and explains the pull request to B in plain language:
   the goal (linked task), what changed file by file, why, and what the tests and evidence show.
3. **Check locally** — do not just trust CI:
   - [ ] the full test suite passes on the PR branch (`pytest -q`; Postgres tests if persistence changed);
   - [ ] new behaviour has a "red seen" record (`tdd/CURRENT_TEST_STATE.md` or the task file);
   - [ ] the Brain matches the code: the task file and its journal entry file (`journal/entries/`, with its
     `### Test state` / `### Next step` sections), `CURRENT_STATE.md` if the deployment changed;
   - [ ] no secrets, IP addresses, personal names or local paths (Windows user-profile paths) in the diff;
   - [ ] the scope matches the task (no unrelated changes);
   - [ ] if the architecture changed: an ACR exists, `ARCHITECTURE.md` version and changelog are updated, and a
         safety-principle change has a second approval;
   - [ ] if the VMs changed: the archived evidence shows `NO INTERFERENCE` and the deployed commit.
4. **Report.** The agent writes a short review report: what passes, concerns, questions for A.
5. **B decides:**
   - **Approve + merge** (merge commit). The approval is B's own GitHub approval, so it is attributable.
   - **Request changes.** Small fixes: B makes them on the same branch during the session (journaled). Larger ones:
     hand back to A with clear PR comments.
6. **After the merge:** `git checkout main && git pull`; the reviewed work is now the shared state. Continue with
   `NEXT_STEP.md`.

## How the rule is enforced (free GitHub plan: no branch protection on private repos)

GitHub cannot block a merge for us, so the rule is enforced by the team and checked by tools:
- **before merging** (the reviewer checks it in the PR page): the PR has an **Approve** from someone other than its
  author, given **after the last push**; CI is green; the branch is up to date with `main` ("Update branch" if not);
- **on your laptop:** the pre-push hook refuses `git push` to `main`;
- **after merging:** `brain.py verify-main` checks every commit on `main` came from a PR approved on its last push by
  someone other than its author — CI runs it on every push to `main` (job `main-guard`, red = rule broken) and
  `brain.py start` warns at the start of every session;
- the only exceptions are listed in [`../policies/main-exceptions.txt`](../policies/main-exceptions.txt).

If `main-guard` is red: stop and tell the team; the fix is a follow-up PR that gets the missing review (never a
force push). Nobody merges their own pull request (except under the temporary fast-track below). If A works again
before anyone reviewed, A continues on the same branch.

## Temporary fast-track (until 2026-10-12, then it expires by itself)

**Why:** the course presentation came earlier than planned; waiting for a review on every pull request would block
the work. Decided by `juanbetancurm` on 2026-10-05 (journal). Teammates may object in any PR; an objection ends it.

**Who:** `juanbetancurm`, `conantkd` (added 2026-10-06 by PR #16, approved by `juanbetancurm`), `juanes6554` (added
2026-10-06 for the frontend, T-0016, once his onboarding is done; approved by `conantkd`). **Until:** 2026-10-12
inclusive. After that date no new fast-track line may be added.

A fast-track pull request may be merged by its author when **all** of these hold:
- it is still a pull request from a task branch (no direct push to `main`; the pre-push hook stays);
- CI `test` is green on its last push and the branch is up to date with `main`;
- the agent did the review checklist above on it and posted the report as a PR comment;
- **the PR adds its own line** to [`../policies/main-exceptions.txt`](../policies/main-exceptions.txt)
  (`pr <n>  <date>  <who>  fast-track: <what>`) in a commit on the PR branch, so `main-guard` stays green and every
  self-merge stays visible;
- it does **not** touch a safety principle (read-only, write gate, host isolation, evidence integrity, secrets),
  `policies/SECURITY.md`, an ACR, or the enforcement itself (`brain.py verify-main`, CI `main-guard`, the hooks,
  anything under `.github/workflows/`). Those still need a teammate's approval. For the frontend this means: the PR
  that adds the CI job `frontend` and any change to `contracts/` need a teammate; frontend PRs after that need the
  job `frontend` green as well (tests first, `tasks/current/T-0016-frontend.md`).

**After the merge:** a teammate reviews the merged PR at the start of their next session (same checklist); findings
become a follow-up PR. Nothing here changes `brain.py`, CI or the hooks.
