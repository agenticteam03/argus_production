---
name: journal-and-task-status
description: >-
  Prepare an Argus task's journal entry and linked status row for a task PR or
  handoff. Use when recording test evidence and the next step for Brain roll-up;
  not for changing shared summaries, opening PRs, or approving completion.
---

# Journal and task status

Read `brain/agents/AGENT_PROTOCOL.md`, `brain/policies/PARALLEL_LANES.md`,
and `brain/policies/CODE_BASH.md` first. They win over this skill. Read the
specific task and its evidence before writing. Use the current branch and
reviewed PR state; do not infer completion from a clean local diff.

1. Add one `brain/journal/entries/YYYY-MM-DD-<task>.md` entry. Start with
   `## YYYY-MM-DD — title` and record Type, Who, Context, Decision / result,
   Consequences and References. Add `### Test state` with actual RED/GREEN,
   full-suite and CI evidence, and `### Next step` with what remains after the
   merge. Say "pending" where a check has not run. Brain treats those sections
   as optional; this skill requires both for a useful handoff. The roll-up moves
   them into the test and next-step summaries.
2. Update only this task's `| Status | ... |` row (or existing `**Status:**`
   or `Status:` line). Start a table row with a backticked state and cite the relevant PR
   or evidence. Existing tasks use Markdown links or `#NNN` PR references.
   Use `proposed`, `in progress`,
   or `in review` while work awaits review or merge. Say `done` only after its
   PR has merged; include a link to that PR. A journal draft or local tests
   never establish that state.
3. Run `python .claude/skills/journal-and-task-status/scripts/check_status.py
   --entry <entry-path> --task <task-path>`. Then run `python brain/tools/brain.py
   lint` and `audit`. The helper checks format only. Verify link targets,
   test claims, PR state and scope against the actual evidence. Keep
   `NEXT_STEP.md`, `tdd/CURRENT_TEST_STATE.md` and `journal/logbook.md` for the
   roll-up branch.

The helper reads two files and prints a verdict; it never writes, commits,
pushes, reviews, merges, deploys or connects to a VM. Follow the current
`code.bash` handoff policy for any developer action.
