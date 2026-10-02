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
   - [ ] the Brain matches the code: `CURRENT_STATE.md`, `NEXT_STEP.md`, `tdd/`, the task file, the journal;
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

## Enforced by GitHub (branch protection on `main`)

- a pull request is required, with 1 approval;
- the most recent push must be approved by someone other than its author;
- CI must be green; the branch must be up to date with `main`;
- **no bypass**, also for organization owners.

Nobody merges their own pull request. If A works again before anyone reviewed, A continues on the same branch.
