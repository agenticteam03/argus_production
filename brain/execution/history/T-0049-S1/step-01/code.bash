# ---------------------------------------------------------------------------------------------------------
# SK.1 [LAPTOP · PowerShell] T-0049 S1: commit the verified code-bash-step slice locally
# Goal / Why: checkpoint the reviewed skill, checker, templates, tests and journal; S0 and #255 still gate push/PR.
# MUTATES: the local task index/commit and archive of the used commit text. No remote or VM action.
# Undo (only before another commit or publication): git reset --soft 953331fd73ce3e55de08fe716cf2dc2a3149eaaa
# Text undo: Move-Item -LiteralPath ..\texts\archive\commit-T-0049-S1.txt -Destination ..\texts\commit-T-0049-S1.txt
# Text: ..\texts\commit-T-0049-S1.txt (running this block authorizes this commit message).
# Expected: 38 staged files, hooks Passed, 'Committed: <sha>', 'Commit text archived'; VERDICT: SK.1 PASS (2 of 2).
# If it fails: preserve the output; inspect the first Stopped/hook error. Do not re-run after a commit was made.
# Paste the complete output into this worktree's brain/execution/current/output.bash.
# ---------------------------------------------------------------------------------------------------------
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath 'C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\w-s1'
git rev-parse --show-toplevel
$ok = 0
$expectedFiles = @(
  '.claude/skills/code-bash-step/SKILL.md'
  '.claude/skills/code-bash-step/scripts/check_block.py'
  '.claude/skills/code-bash-step/templates/approve-on-head.ps1'
  '.claude/skills/code-bash-step/templates/comment.ps1'
  '.claude/skills/code-bash-step/templates/commit-push-open-pr.ps1'
  '.claude/skills/code-bash-step/templates/vm-readonly.sh'
  'brain/journal/entries/2026-10-21-T-0049-S1-code-bash-step.md'
  'tests/skills/fixtures/invalid-bash-heredoc.bash'
  'tests/skills/fixtures/invalid-braced-colon.bash'
  'tests/skills/fixtures/invalid-duplicate-labels.bash'
  'tests/skills/fixtures/invalid-ipv4.bash'
  'tests/skills/fixtures/invalid-location-tag.bash'
  'tests/skills/fixtures/invalid-missing-expected.bash'
  'tests/skills/fixtures/invalid-missing-label.bash'
  'tests/skills/fixtures/invalid-missing-ok-counter.bash'
  'tests/skills/fixtures/invalid-missing-repository-check.bash'
  'tests/skills/fixtures/invalid-missing-set-location.bash'
  'tests/skills/fixtures/invalid-missing-verdict.bash'
  'tests/skills/fixtures/invalid-native-quotes.bash'
  'tests/skills/fixtures/invalid-newline-else.bash'
  'tests/skills/fixtures/invalid-newline-elseif.bash'
  'tests/skills/fixtures/invalid-password-assignment.bash'
  'tests/skills/fixtures/invalid-powershell-here-string.bash'
  'tests/skills/fixtures/invalid-token-assignment.bash'
  'tests/skills/fixtures/invalid-unbraced-colon.bash'
  'tests/skills/fixtures/invalid-verdict-denominator.bash'
  'tests/skills/fixtures/invalid-verdict-label.bash'
  'tests/skills/fixtures/invalid-vm-exit.bash'
  'tests/skills/fixtures/invalid-vm-late-session.bash'
  'tests/skills/fixtures/invalid-vm-missing-session.bash'
  'tests/skills/fixtures/invalid-vm-reboot.bash'
  'tests/skills/fixtures/valid-approve-on-head.bash'
  'tests/skills/fixtures/valid-comment.bash'
  'tests/skills/fixtures/valid-commit-push-open-pr.bash'
  'tests/skills/fixtures/valid-nested-else.bash'
  'tests/skills/fixtures/valid-vm-readonly.bash'
  'tests/skills/fixtures/valid-whole-file.bash'
  'tests/skills/test_check_block.py'
)
try {
  $branch = git rev-parse --abbrev-ref HEAD
  if ($LASTEXITCODE -ne 0 -or $branch -ne 'task/T-0049-s1-code-bash-step') { throw 'Unexpected branch' }
  $base = git rev-parse HEAD
  if ($LASTEXITCODE -ne 0 -or $base -ne '953331fd73ce3e55de08fe716cf2dc2a3149eaaa') { throw 'HEAD moved; inspect before committing' }
  if (-not (Test-Path -LiteralPath '..\texts\commit-T-0049-S1.txt')) { throw 'Commit text missing' }
  if (Test-Path -LiteralPath '..\texts\archive\commit-T-0049-S1.txt') { throw 'Archive target exists; inspect before committing' }
  $staged = @(git diff --cached --name-only)
  if ($LASTEXITCODE -ne 0 -or $staged.Count -gt 0) { throw 'Index is not empty or cannot be inspected; preserve and review it' }
  $modified = @(git diff --name-only)
  if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect tracked changes' }
  if (@($modified | Where-Object { $_ -ne 'brain/execution/current/code.bash' }).Count -gt 0) { throw 'Unexpected tracked changes' }
  $untracked = @(git ls-files --others --exclude-standard)
  if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect new files' }
  if (@(Compare-Object $expectedFiles $untracked).Count -gt 0) { throw 'New files differ from the 38 reviewed paths' }
  git add -- $expectedFiles
  if ($LASTEXITCODE -ne 0) { throw 'Staging failed' }
  $staged = @(git diff --cached --name-only)
  if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect staged files' }
  if (@(Compare-Object $expectedFiles $staged).Count -gt 0) {
    git restore --staged -- $expectedFiles
    throw 'Staged paths differ from reviewed paths; slice unstaged'
  }
  git diff --cached --check
  if ($LASTEXITCODE -ne 0) { throw 'Staged whitespace check failed' }
  git diff --cached --stat
  if ($LASTEXITCODE -ne 0) { throw 'Cannot display staged summary' }
  $ok++
  git commit -q -F ..\texts\commit-T-0049-S1.txt
  if ($LASTEXITCODE -ne 0) { throw 'Commit failed; inspect hook output' }
  $newCommit = git rev-parse HEAD
  if ($LASTEXITCODE -ne 0) { throw 'Commit made but cannot read HEAD' }
  "Committed: $newCommit"
  $committed = @(git show --format= --name-only HEAD)
  if ($LASTEXITCODE -ne 0 -or @(Compare-Object $expectedFiles $committed).Count -gt 0) { throw 'Commit made; inspect its file list' }
  New-Item -ItemType Directory -Path '..\texts\archive' -Force | Out-Null
  Move-Item -LiteralPath '..\texts\commit-T-0049-S1.txt' -Destination '..\texts\archive\commit-T-0049-S1.txt'
  'Commit text archived'
  git status --short
  if ($LASTEXITCODE -ne 0) { throw 'Commit made but status check failed' }
  $ok++
} catch {
  "Stopped: $($_.Exception.Message)"
}
if ($ok -eq 2) { 'VERDICT: SK.1 PASS (2 of 2)' } else { "VERDICT: SK.1 FAIL ($ok of 2)" }
