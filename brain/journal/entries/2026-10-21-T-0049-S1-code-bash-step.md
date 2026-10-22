## 2026-10-21 — T-0049 S1: prepare and statically check code.bash steps

Type: implementation
Who: juanbetancurm (+ agent)
Status: initial and corrective commits are local; governance merged; final publication record under validation.
Context: T-0049 step S1, isolated in `w-s1` on
`task/T-0049-s1-code-bash-step`, created from `origin/main` at `953331f`.
On 2026-10-22, local merge `dbffd037` integrated reviewed main `9d65e1e` without conflicts;
the five pending correction files and completed private SK.1 block were preserved exactly.
The developer committed the correction as `8f40d31`. After governance #268 merged,
local merge `86bd0d19` integrated main `e4b9869` without conflicts or skill-code changes, and
local merge `808d46a` integrated main `096bf90` (#270, a journal entry only).

Decision / result:
- Add a short `.claude/skills/code-bash-step/SKILL.md` that reads the current Brain policies first,
  selects one template, fills the current step, and checks it before developer execution.
- Supply PowerShell templates for a comment, approval of another author's reviewed head, and a
  guarded commit/push/PR sequence; supply a read-only Bash template inside the VM SESSION guard.
- Add a stdlib-only CLI checker for headers, location/expected markers, laptop setup and verdict
  counts, native argument quotes, interpolation, depth-aware console `else`/`elseif`, heredocs,
  VM exit/reboot/session ordering, duplicate labels, addresses and secret assignments.
- The lexer ignores strings/comments when counting braces. The coordinating review clarified that the original approval
  block's newline branches are valid inside `foreach`; all three real blocks are preserved verbatim.
- VM commands outside the successful SESSION branch require a guard when mutating or unrecognized;
  redirections and command expansion are checked too. This static checker is not a shell sandbox.
- Add 31 fixtures and 64 CLI tests. Negative data uses explicit synthetic values; the documentation
  address is assembled only during tests. No real address or credential is stored in the fixtures.
- Following review, detect headers only at rule lines and ignore the standard banner and status
  comments as free text. Also accept CODE_BASH.md's inline rule/header form. A copy of the coordinator's whole real
  file is a positive fixture; all three original isolated blocks remain unchanged.
- Fix the peer-reported Bash single-quote bug: a backslash is literal inside single quotes, so it cannot
  consume the closing quote and hide a later unguarded VM mutation. The regression fixture is parsed
  without executing its commands.
- Document the checker's deliberately stricter current template conventions: an `if` SESSION guard,
  no VM `exit` (which closes the SSH session), and no IPv4 literal, including permitted lab ranges.
  The older CODE_BASH example differs; policy still wins, and policy alignment is a separate change.
- Fix the VM template and its fixture to match the actual two-field `holder=<who> session=<id>` marker.
  The anchored holder boundary admits the right holder and refuses a different holder or a prefix collision.
  Accept the established anchored quiet-grep guard form; inverted and files-without-match options do not
  establish a positive SESSION guard.
- As the coordinating session explicitly authorized, exempt exactly one literal SESSION marker pipeline
  only when it is the first command of a VM block. A second/later write, another path, extra options,
  expansion or another command on that line still requires the normal successful guard. Only one optional
  stdout redirect to `/dev/null` is allowed on that first line, as the coordinating session confirmed.
- Preserve the developer-completed SK.1 block and sanitized successful evidence under
  `brain/execution/history/T-0049-S1/step-01/`, as authorized. Keep raw terminal output private.
- Preserve completed SK.2 and its sanitized local-commit evidence under the approved `step-02/` archive.
  The final publication record changes only that archive and this journal; the skill code stays as reviewed.

### Test state

- **Red seen:** `test_rejects_known_traps[native-quotes]` asserted status 1 and observed status 0 with
  the no-op entry point. This was a behavior assertion, not a missing import or syntax failure.
- **Red seen:** six `test_rejects_unguarded_vm_mutation_in_read_looking_commands` cases likewise
  observed status 0 before checks for write-capable tools, expansion and redirection were tightened.
- **Red seen:** the whole-file fixture reproduced 12 false positives before header discovery was fixed.
- **Red seen after peer review:** `test_rejects_known_traps[vm-single-quote-backslash]` expected refusal
  (status 1) but observed status 0: **1 failed, 63 deselected in 1.66s**.
- **Green:** shared-venv `python -m pytest tests/skills -q -o addopts=`: **64 passed in 14.86s**.
- **Red seen for the current SESSION correction:** **9 failed, 16 passed, 64 deselected in 4.36s**.
  Two anchored guards and three allowed first-marker cases were refused; three inverted guards were
  wrongly accepted; the real two-field marker failed the local read-only template simulation.
- **Green for the current correction:** **89 passed in 11.81s**, including wrong-holder/prefix-collision
  simulation cases and 14 rejected variants of the marker exception. The simulation replaces both VM
  paths with local temporary files and intercepts `sudo`; no VM command or connection runs.
- **Red seen after the second peer review:** bare holder guards were wrongly accepted (**3 failed,
  2 passed, 89 deselected in 1.17s**); the real marker's `/dev/null` stdout redirect was wrongly refused
  (**2 failed, 98 deselected in 0.74s**). Require a holder boundary or a full-line two-field match,
  and admit only the authorized optional stdout redirect. Final focused result: **100 passed in 14.22s**.
- The whole-file and three original isolated fixtures still pass without executing their commands.
- `ruff check .claude tests/skills`: clean. Skill frontmatter validation: valid.
- All three PowerShell templates parse without execution; the Bash template passes `bash -n`.
- Brain lint, secret/address audit and whitespace checks are clean for the correction and approved archive.
- Full offline suite on unchanged `b997395`: **7 failed, 1474 passed, 62 skipped, 1 deselected in 1167.34s**.
  All seven failures selected the Windows WSL launcher, whose `/bin/bash` is unavailable, in
  `tests/test_t0033_rotate_token_script.py`. Selecting installed Git Bash only in the test process makes
  those seven tests pass (**7 passed in 8.18s**, verified in the governance worktree).
- The first peer correction passed its original-base full suite: **1482 passed, 62 skipped, 1 deselected
  in 965.03s**, exit 0.
- The first current-main run was intentionally interrupted for the second peer review's source fixes;
  it is not a full pass. The final-source run replaces it.
- Full offline regression of the final correction on integrated main `9d65e1e`: **1571 passed,
  62 skipped, 1 deselected in 742.16s**, exit 0. It uses process-local Git Bash selection and a Git
  discovery ceiling for temporary repositories. Only the known detached-CI lint case is deselected.
- Integrated-main validation on `808d46a` (main `096bf90`) with the final three-file record: full offline
  suite passed, 0 failed (1654 collected, only the known detached-CI lint case deselected); run by S1
  after S2's session ended.
- No runtime, database, CI or shared Brain summary changes; no VM command or external action executed.

### Next step

The developer made initial commit `b997395` and corrective commit `8f40d31`; neither is amended.
The final peer re-review is clear and the real OP-013 file passes the checker. Plans #255 and governance
#268 are approved and merged, so `.claude/skills/` is protected before publication. After integrated-main
validation, SK.3 commits the exact three-file publication record, pushes the skill task branch and opens
the PR requesting `conantkd` through the central command workflow. Current execution files and raw output
stay outside the commit. Wait for actual developer output before claiming publication; no self-merge,
and preserve the source branch.
