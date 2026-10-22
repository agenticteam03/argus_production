# ---------------------------------------------------------------------------------------------------------
# SK.2 [LAPTOP · PowerShell] T-0049 S1: commit the reviewed corrections and completed SK.1 archive locally
# Validation: 1571 passed, 62 skipped, 1 CI-only case deselected; final peer re-review clear.
# Goal / Why: preserve the verified SESSION fixes and completed-step evidence as a new local checkpoint.
# MUTATES: local task index/commit and archive of the used commit text. No remote or VM action.
# Undo (only before another commit or publication): git reset --soft dbffd03787eead45f8939e45ebfcc7fa86108906
# Text undo: Move-Item -LiteralPath ..\texts\archive\commit-T-0049-S1-review-fix.txt -Destination ..\texts\commit-T-0049-S1-review-fix.txt
# Text: ..\texts\commit-T-0049-S1-review-fix.txt (running this block authorizes this commit message).
# Expected: 9 staged files, hooks Passed, 'Committed: <sha>', 'Commit text archived'; VERDICT: SK.2 PASS (2 of 2).
# If it fails after a commit: preserve output; do not rerun. Push/PR still waits for S0 to merge.
# Output: S1 relays the central run file's output to this worktree's output.bash.
# ---------------------------------------------------------------------------------------------------------
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath 'C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\w-s1'
git rev-parse --show-toplevel
$ok = 0
$handoffReady = $true
$expectedFiles = @(
  '.claude/skills/code-bash-step/SKILL.md'
  '.claude/skills/code-bash-step/scripts/check_block.py'
  '.claude/skills/code-bash-step/templates/vm-readonly.sh'
  'brain/execution/history/T-0049-S1/step-01/code.bash'
  'brain/execution/history/T-0049-S1/step-01/evidence.md'
  'brain/journal/entries/2026-10-21-T-0049-S1-code-bash-step.md'
  'tests/skills/fixtures/invalid-vm-single-quote-backslash.bash'
  'tests/skills/fixtures/valid-vm-readonly.bash'
  'tests/skills/test_check_block.py'
)
try {
  if (-not $handoffReady) { throw 'HOLD: full regression or peer re-review is pending' }
  $branch = git rev-parse --abbrev-ref HEAD
  if ($LASTEXITCODE -ne 0 -or $branch -ne 'task/T-0049-s1-code-bash-step') { throw 'Unexpected branch' }
  $base = git rev-parse HEAD
  if ($LASTEXITCODE -ne 0 -or $base -ne 'dbffd03787eead45f8939e45ebfcc7fa86108906') { throw 'HEAD moved; inspect before committing' }
  if (-not (Test-Path -LiteralPath '..\texts\commit-T-0049-S1-review-fix.txt')) { throw 'Commit text missing' }
  if (Test-Path -LiteralPath '..\texts\archive\commit-T-0049-S1-review-fix.txt') { throw 'Text archive target exists; inspect before committing' }
  $staged = @(git diff --cached --name-only)
  if ($LASTEXITCODE -ne 0 -or $staged.Count -gt 0) { throw 'Index is not empty or cannot be inspected' }
  $modified = @(git diff --name-only)
  if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect tracked changes' }
  $untracked = @(git ls-files --others --exclude-standard)
  if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect new files' }
  $changes = @($modified + $untracked | Where-Object { $_ -ne 'brain/execution/current/code.bash' })
  if (@(Compare-Object $expectedFiles $changes).Count -gt 0) { throw 'Changes differ from the nine reviewed paths' }
  git add -- $expectedFiles
  if ($LASTEXITCODE -ne 0) { throw 'Staging failed' }
  $staged = @(git diff --cached --name-only)
  if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect staged files' }
  if (@(Compare-Object $expectedFiles $staged).Count -gt 0) {
    git restore --staged -- $expectedFiles
    throw 'Staged paths differ from reviewed paths; slice unstaged'
  }
  git --no-pager diff --cached --check
  if ($LASTEXITCODE -ne 0) { throw 'Staged whitespace check failed' }
  git --no-pager diff --cached --stat
  if ($LASTEXITCODE -ne 0) { throw 'Cannot display staged summary' }
  $ok++
  git commit -q -F ..\texts\commit-T-0049-S1-review-fix.txt
  if ($LASTEXITCODE -ne 0) { throw 'Commit failed; inspect hook output' }
  $createdCommit = git rev-parse HEAD
  if ($LASTEXITCODE -ne 0) { throw 'Commit made but cannot read HEAD' }
  "Committed: $createdCommit"
  $committed = @(git --no-pager show --format= --name-only HEAD)
  if ($LASTEXITCODE -ne 0 -or @(Compare-Object $expectedFiles $committed).Count -gt 0) { throw 'Commit made; inspect its file list' }
  New-Item -ItemType Directory -Path '..\texts\archive' -Force | Out-Null
  Move-Item -LiteralPath '..\texts\commit-T-0049-S1-review-fix.txt' -Destination '..\texts\archive\commit-T-0049-S1-review-fix.txt'
  'Commit text archived'
  git --no-pager status --short
  if ($LASTEXITCODE -ne 0) { throw 'Commit made but status check failed' }
  $ok++
} catch {
  "Stopped: $($_.Exception.Message)"
}
Set-StrictMode -Off
$ErrorActionPreference = 'Continue'
if ($ok -eq 2) { 'VERDICT: SK.2 PASS (2 of 2)' } else { "VERDICT: SK.2 FAIL ($ok of 2)" }
