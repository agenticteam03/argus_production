---
name: pr-review
description: >-
  Review an Argus pull request, inspect changes since approval, check merge
  readiness, or verify journal roll-up preservation. Produces findings and a
  review text file; never approves, merges, pushes or runs VM commands.
---

# Review an Argus pull request

Read `brain/agents/REVIEW_PROTOCOL.md` and `brain/agents/AGENT_PROTOCOL.md` first.
For command handoff also read `brain/policies/CODE_BASH.md`. Those policies win.
These helpers inspect evidence and grant no execution or approval permission.
They load reviewed main's Brain module in-process as their trusted policy source.

1. Establish the task, PR author, exact reviewed head and fetched `origin/main`.
   Refresh refs through the authorized workflow; the helpers never fetch or
   change checkouts/refs. Read the whole diff and run the policy's local checks.
2. For a prior approval, run `scripts/since_approval.py --repo <worktree>
   --approved <sha> --head <sha>`. Read every first-parent commit and each merge's
   remerge diff. The helper delegates approval retention to fetched main's Brain;
   a conflict resolution, extra edit or rewritten history requires re-review.
3. For removed journal entries, run `scripts/rollup_check.py --repo <worktree>
   --base <sha> --head <sha>`. It uses Brain's section/link transformation and
   requires each complete payload to survive in its designated summary.
4. Run `scripts/merge_ready.py --repo <worktree> --pr <number>` for a preview.
   Read every review, conversation comment and inline comment it returns.
   Inspect the exact failing run's logs: record code, infrastructure or unknown
   with evidence. A proposed retry stays not ready until its result passes.
5. Assess unresolved findings and write the review using
   [the report format and evidence inputs](references/review-report.md).
   Recheck with `--discussions-read <digest> --findings-clear --keep-branch` only
   after reading that exact discussion and clearing the findings. A changed head
   or discussion invalidates the digest and needs another read.
6. Explain findings and the recommendation; save the English review text in the
   current approved text-file location. Hand any authorized posting/merge action
   to the developer through the current code.bash workflow. Never execute it here.

Readiness measures ancestry with `git merge-base --is-ancestor`, exact-head CI,
current main-guard, and protected paths through fetched main's `brain.py:is_protected`,
including rename sources. Brain also judges self-merge eligibility when a teammate
has not approved; an ordinary path does not by itself make a PR eligible.
Missing evidence refuses readiness. Exit 0 means the
reported conditions pass; exit 1 means not ready; exit 2 means evidence unavailable.
Recorded `--snapshot` input describes its captured state; refresh live evidence for
a current decision. Human review still judges scope, test quality and concerns.

Use a merge commit and preserve the source branch after merge. Never include
`--delete-branch`: `verify-main` needs the branch. A helper verdict never approves
or merges anything and never accesses a VM.
