# Review protocol — the next developer reviews, with AI help

A pull request by developer A is reviewed and approved by **the next developer (B) who works**, at the **start** of
B's session, with B's AI agent. Reviewing comes before new work, because new work must start from the merged state.
A pull request that meets the **self-merge** conditions below may instead be merged by its author.

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
         safety-principle change has a second approval (any team member's approval, the author's
         included),
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
- **before merging** (the reviewer, or the author under the self-merge rule, checks it in the PR page): the PR has an
  **Approve** from someone other than its author, given **after the last push** (or before pushes that only brought
  in `main`: see "An update that only brings in main" below), or it meets every self-merge condition below; CI is
  green (or, when CI does not run, a `LOCAL CI PASS` comment for that push: see below); the branch is up to date with
  `main` ("Update branch" if not);
- **on your laptop:** the pre-push hook refuses `git push` to `main`;
- **after merging:** `brain.py verify-main` checks that every commit on `main` came from a PR approved on its last push
  (or before pushes that only brought in `main`) by someone other than its author, or from a valid self-merge (its
  required checks green on its last push and no protected path changed) — CI runs it on every push to `main` (job
  `main-guard`, red = rule broken) and `brain.py start` warns at the start of every session;
- the only other exceptions are listed in [`../policies/main-exceptions.txt`](../policies/main-exceptions.txt).

If `main-guard` is red: stop and tell the team; the fix is a follow-up PR that gets the missing review (never a
force push). Nobody merges their own pull request unless it meets the self-merge rule below. If A works again before
anyone reviewed, A continues on the same branch.

## An update that only brings in main (standing rule, proposed 2026-10-19)

**Why:** a pull request must be up to date with `main` when it merges, so every merge puts the other open pull
requests behind; updating them was a new push, and their approvals no longer counted. With several approved pull
requests open, each merge sent the others back for a new review, although nobody changed their code.

**The rule:** an approval stays valid after later pushes when **each commit after the approved one is a merge with
`main` that git made without a conflict**, so the author's code is still the code that was approved. "Update branch"
on the PR page makes exactly such a commit. CI must still be green on the last push, and the branch up to date.

**Needs a new approval:** any other commit after the approval; a merge in which a conflict was resolved (by anyone,
the author or the reviewer); a merge with any edit beyond git's automatic merge; a rewritten branch (force push).

**How it is enforced:** `brain.py verify-main` accepts an approval of an earlier commit only when that commit is still
in the branch and every later commit not on `main` has two parents, one of them on `main`, and a tree equal to git's
automatic merge of the two (`git merge-tree --write-tree`), which fails on any conflict. Otherwise the pull request
counts as unapproved, as before.

**Decided by** `juanbetancurm` on 2026-10-19. It changes the enforcement, so it starts when a teammate approves the
pull request that adds it.

## When CI does not run (local CI)

Sometimes GitHub Actions does not run the jobs: the run shows them "not started" (an annotation says why), or Actions
is turned off. The checks do not go away; they move to a laptop. `ops/local_ci.py` runs the steps of
`.github/workflows/ci.yml` (Brain audit and lint, the secret scan, the full pytest suite with a throwaway Postgres,
the PromQL cases, the frontend's tests and build) on an exact commit and prints one result block that starts with
`LOCAL CI PASS <commit>` or `LOCAL CI FAIL <commit>`. It needs the repository's virtual environment, Docker Desktop,
Node/npm and `gh`; a missing tool makes its step `skipped`, and the result says so.

- **The author**, before asking for a review: `python ops/local_ci.py` on the pushed commit (a clean working tree),
  and says in the PR body that it passed.
- **The reviewer** runs it again on the PR's last push, in a clean temporary copy:
  `python ops/local_ci.py --pr <n> --post`. The posted comment replaces the green CI in the merge check above: it must
  be `LOCAL CI PASS`, for the **same commit** the approval is on (a new push needs a new run), with no step `fail`. A
  `flaky` test (failed in the full run, passed alone) is allowed once; name it in the review so it gets fixed. A
  `known-local` test fails only for a reason of the laptop and passes on CI's runner (the `KNOWN_LOCAL` list in the
  script, each line with its reason; adding one needs a reviewer's approval, like any change). A
  `skipped` step is allowed only when the PR does not touch what it checks (for example `frontend` for a PR without
  `frontend/` changes); persistence changes need the Postgres tests.
- **After merging**, the reviewer runs `python ops/local_ci.py --main`: the same steps on `origin/main` plus
  `brain.py verify-main` (the `main-guard` job). A `FAIL` there is handled like a red `main-guard`.
- **The agent** runs these commands for its developer when asked to review or merge, reports the result block as it
  is, and never presents a local run as a GitHub CI result.

When GitHub Actions runs again, its CI is the merge check again; nothing needs re-running for what was merged.

## Self-merge (standing rule, from 2026-10-17)

**Why:** most pull requests are small and well covered by tests; waiting a day for a teammate slowed the work, and
the fast-track windows below showed that self-merging with green tests worked. Decided by `juanbetancurm` on
2026-10-17. This rule starts when a teammate approves the pull request that adds it (it changes the enforcement, so
it cannot be self-merged). A teammate may object in any PR; an objection goes to the team.

**Who:** every developer of the team.

**The author may approve and merge their own pull request when all of these hold:**
1. it is a pull request from a task branch (no direct push to `main`; the pre-push hook stays);
2. **every required check is green on its last push:** CI jobs `test` and `frontend`. When CI does not run, a
   `LOCAL CI PASS` comment for **that exact commit**, **posted by another developer** (`python ops/local_ci.py --pr
   <n> --post`, no step `fail`), replaces them, as in "When CI does not run"; the author's own run does not count;
3. the branch is up to date with `main` when it is merged ("Update branch", then wait for the checks again);
4. it changes **none of the protected paths** below, under its new name or, for a renamed file, its old one. Those
   still need a teammate's approval on the last push:
   - `brain/architecture/` (ARCHITECTURE.md and every ACR; a safety-principle change still needs its second approval,
     AGENT_PROTOCOL §4);
   - `brain/policies/` and `brain/agents/` (the security, git and review rules; the agents' stop conditions and rails);
   - `.claude/skills/` (agent procedures, executable helpers and templates);
   - the enforcement: `brain/tools/brain.py`, `.github/`, `.pre-commit-config.yaml`;
   - `ops/` (`deploy.sh`, `nonint-check.sh`, `write-gate-check.sh` run as root on the VMs; `local_ci.py`);
   - safety data: `config/policy.yaml` (write gate, scope), `config/inventory.yaml` (host isolation);
   - every deployed stack's compose file (`deploy/*/compose*.yml`: mounts, secrets, ports) and
     `deploy/migrations/` (database roles);
   - the public surface: `deploy/ui/nginx/`, `contracts/`;
   - the code that enforces the write gate and the rails (`argus/policy/`, `argus/application/invoke_capability.py`,
     `argus/infrastructure/gate_report.py`, `argus/tooling/isolation_check.py`) and their tests (`tests/brain/`,
     `tests/test_write_gate_standing.py`, `tests/test_write_gate_check.py`, `tests/test_tool_isolation.py`,
     `tests/test_op014_prompt_injection.py`): a weakened rail test would keep CI green;
   - the action path, protected before it is built (phase 15, ACR-0019): `config/actions/` (action cards),
     `config/risk.yaml` (risk colours), `config/ranking.yaml` (ACR-0024's weights),
     `argus/capabilities/write_contract.py` (§14.8), and the reserved names of the dispatch module (`argus/actions/`)
     and the action gateway (`services/action-gateway/`), which the first PR that builds them keeps;
5. it is merged with a merge commit, and the branch is not deleted (`GIT_WORKFLOW.md`).

The author's agent should still run the review checklist above and post its report as a PR comment before the merge:
the tests check behaviour, the report catches scope, Brain and wording problems the tests cannot.

**What it does not change:** a change on the VMs (deploy, rebuild, migration, scenario run) still needs its lease, a
`code.bash` step and `nonint-check.sh` before and after; a merge never deploys anything by itself.

**How it is enforced:** `brain.py verify-main` (CI `main-guard`, `brain.py start`) accepts a PR without another
developer's approval only when all five conditions are measured true: the GitHub check runs of its last push show
`test` and `frontend` as `success` (or another developer's `LOCAL CI PASS` comment names that commit); none of its
files, new or old name, is under a protected path; its merge commit has two parents and main's commit before the merge
is contained in the merged branch (up to date); and its branch still exists. The list lives in `brain.py`
(`SELF_MERGE_PROTECTED`, `SELF_MERGE_PROTECTED_GLOBS`) and must match this section. A PR with 100 files or more is
never a valid self-merge (too many to check). No `main-exceptions.txt` line is needed.

**After the merge:** any teammate may review a merged PR with the same checklist; findings become a follow-up PR.

**The tests this rule relies on:** the known gaps, and the checks to add so that green tests mean more, are in
[`../OPEN_PROBLEMS.md`](../OPEN_PROBLEMS.md) (OP-014). Until a gap is closed, ask for a teammate's review when your
change sits in it (for example a prompt or strategy change, which CI's offline evaluation does not judge).

## Temporary fast-track (history: windows 2026-10-05 – 2026-10-12 and 2026-10-14 – 2026-10-16, both expired; replaced by the self-merge rule above)

**Why:** the course presentation came earlier than planned; waiting for a review on every pull request would block
the work. Decided by `juanbetancurm` on 2026-10-05 (journal). Teammates may object in any PR; an objection ends it.

**Who:** `juanbetancurm`, `conantkd` (added 2026-10-06 by PR #16, approved by `juanbetancurm`), `juanes6554` (added
2026-10-06 for the frontend, T-0016, once his onboarding is done; approved by `conantkd`). **Until:** 2026-10-12
inclusive (first window).

**Second window, 2026-10-14 to 2026-10-16 inclusive:**
- Proposed by `conantkd` on 2026-10-14 in the pull request that adds this paragraph. It exists only if a teammate
  approves that pull request, which is not itself fast-tracked because it changes this rule.
- **Why:** after the first window, small changes (records, one-line fixes with their tests) waited a day or more for
  a review while the team was on other work.
- **Same people and conditions as above, unchanged.** A teammate's objection in any PR ends it, as in the first
  window.

Outside a window no fast-track line may be added; a line's date must fall inside one.

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
