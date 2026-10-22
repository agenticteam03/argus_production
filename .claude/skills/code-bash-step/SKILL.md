---
name: code-bash-step
description: >-
  Prepare the current step's code.bash when asked to "write the block", give the
  "next step", or "prepare the commands" for Argus. Use for command preparation,
  not executing commands or making VM changes without a lease.
---

# Prepare one Argus step

Read `brain/policies/CODE_BASH.md` first, from the task worktree. It wins over
this skill. Read `brain/agents/AGENT_PROTOCOL.md` for the current session rules;
for reviews or pull requests, also read `brain/agents/REVIEW_PROTOCOL.md`.
This skill grants no permission to approve, commit, push, post, merge or access a VM.

1. Establish the task worktree, intended action and existing developer authorization.
   Preserve unrelated files and keep only this step's blocks in
   `brain/execution/current/code.bash`. Archive completed evidence as the policy requires.
2. Choose the relevant template, reading only that file:
   - [approve-on-head.ps1](templates/approve-on-head.ps1): a developer-authorized
     review of another author's PR, on its reviewed head with completed checks.
   - [comment.ps1](templates/comment.ps1): a developer-authorized comment from a text file.
   - [commit-push-open-pr.ps1](templates/commit-push-open-pr.ps1): an authorized
     commit/push/PR sequence; omit actions the developer has not authorized.
   - [vm-readonly.sh](templates/vm-readonly.sh): reads on the specified VM, inside
     its SESSION guard. Check the lease first; this skill never connects to a VM.
3. Fill every `__PLACEHOLDER__`, choose a unique block label, and update every
   occurrence of that label and its verdict counts. Use the team's current text-file
   location for commit messages, reviews and PR bodies; do not embed their bodies in a block.
   Write expected results and, for mutations, the exact undo before handing it over.
4. From the task worktree, run the read-only checker on the prepared file:
   `python .claude/skills/code-bash-step/scripts/check_block.py brain/execution/current/code.bash`.
   Resolve every labelled diagnostic; status 0 means no listed trap was found.
   Parse laptop blocks with PowerShell's parser without executing them as well.
5. Explain what to run, why and the expected verdict; wait for the developer's output
   before treating the step as executed. Follow CODE_BASH.md's economical output review.

The checker covers these templates' static conventions, not all shell syntax or
runtime safety. PowerShell strings/comments do not affect brace depth: newline
`else`/`elseif` is rejected at console top level, but allowed inside an enclosing block.
The native-command argument check applies to laptop blocks; bash quoting is different.

For the team's current blocks, the checker deliberately enforces stricter conventions
than the older Brain examples: use a positive quiet `if grep ... /opt/argus-v18/SESSION; then ... fi`,
and omit `exit` in VM blocks so a failed check does not close the developer's SSH session.
The legacy `grep ... || { ...; exit 1; }` guard therefore fails this template checker.
Every IPv4 literal is rejected, including otherwise permitted lab addresses; use inventory
names. These diagnostics describe the template contract. Report policy mismatches;
this skill cannot change the policy.

The marker contains both `holder=<who> session=<id>` on one line. Match the holder's
boundary as the VM template does; bare `holder=<who>` substring guards are refused.
Anchored `^holder=<who> ` patterns and `-x` guards matching the full marker are supported.
When an existing lease authorizes initialization, exactly one literal
`echo 'holder=<who> session=<id>' | sudo tee /opt/argus-v18/SESSION` may be the first
command of a VM block, with at most one optional stdout redirect `>/dev/null`.
Fill the holder and session id from the authorized lease before checking; literal placeholders are refused.
This exception covers only that line; every later mutation
still needs the successful SESSION guard. It grants no lease or execution permission.
