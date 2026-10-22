## 2026-10-21 — T-0049 S1: prepare and statically check code.bash steps

Type: implementation
Who: juanbetancurm (+ S2 agent)
Status: implemented and locally verified; push/PR held for governance prerequisites.
Context: T-0049's S1 slice, isolated from S1's coordinator work in `w-s1` on
`task/T-0049-s1-code-bash-step`, created from `origin/main` at `953331f`.

Decision / result:
- Add a short `.claude/skills/code-bash-step/SKILL.md` that reads the current Brain policies first,
  selects one template, fills the current step, and checks it before developer execution.
- Supply PowerShell templates for a comment, approval of another author's reviewed head, and a
  guarded commit/push/PR sequence; supply a read-only Bash template inside the VM SESSION guard.
- Add a stdlib-only CLI checker for headers, location/expected markers, laptop setup and verdict
  counts, native argument quotes, interpolation, depth-aware console `else`/`elseif`, heredocs,
  VM exit/reboot/session ordering, duplicate labels, addresses and secret assignments.
- The lexer ignores strings/comments when counting braces. S1 clarified that the original approval
  block's newline branches are valid inside `foreach`; all three real blocks are preserved verbatim.
- VM commands outside the successful SESSION branch require a guard when mutating or unrecognized;
  redirections and command expansion are checked too. This static checker is not a shell sandbox.
- Add 30 fixtures and 63 CLI tests. Negative data uses explicit synthetic values; the documentation
  address is assembled only during tests. No real address or credential is stored in the fixtures.
- Following S1's review, detect headers only at rule lines and ignore the standard banner and status
  comments as free text. Also accept CODE_BASH.md's inline rule/header form. A copy of S1's whole real
  file is a positive fixture; all three original isolated blocks remain unchanged.

### Test state

- **Red seen:** `test_rejects_known_traps[native-quotes]` asserted status 1 and observed status 0 with
  the no-op entry point. This was a behavior assertion, not a missing import or syntax failure.
- **Red seen:** six `test_rejects_unguarded_vm_mutation_in_read_looking_commands` cases likewise
  observed status 0 before checks for write-capable tools, expansion and redirection were tightened.
- **Red seen:** the whole-file fixture reproduced S1's 12 false positives before header discovery was fixed.
- **Green:** shared-venv `python -m pytest tests/skills -q -o addopts=`: **63 passed in 9.95s**.
- The checker also returns status 0 on S1's current whole `code.bash`, without executing it.
- `ruff check .claude tests/skills`: clean. Skill frontmatter validation: valid.
- All three PowerShell templates parse without execution; the Bash template passes `bash -n`.
- `python brain/tools/brain.py lint`: clean; final lint also covers the completed commit block and entry.
- Brain secret/address audit: clean.
- Full offline suite: interrupted at 42% after S1's 21:16 instruction that this new-file-only slice needs
  only skill tests, Ruff and Brain lint. No failure appeared before interruption; this is not a full-suite pass.
- No runtime, database, CI or shared Brain summary changes; no VM command or external action executed.

### Next step

The developer runs the local-commit-only block with the exact 38-file list after reviewing the commit text.
The current execution block and raw output are excluded from that commit. Wait for the developer's
output before reporting this slice DONE to S1. Hold push/PR until S0 protects `.claude/skills/`
and #255's review completes; `conantkd` reviews the resulting skill PR.
