# ---------------------------------------------------------------------------------------------------------
# CB.1 [LAPTOP · PowerShell] Commit the reviewed file list, push the task branch and open its PR
# MUTATES: local commit, task branch on origin, PR. Undo: gh pr close __PR_NUMBER__; git revert __CREATED_COMMIT__; git push origin __BRANCH__
# Texts: ..\texts\__COMMIT_TEXT__.txt, ..\texts\__PR_TEXT__.md (running this block authorizes them).
# Expected: hooks Passed, 'committed', 'pushed', 'PR: <url>'; VERDICT: CB.1 PASS (3 of 3).
# ---------------------------------------------------------------------------------------------------------
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath '__REPO_ROOT__'
git rev-parse --show-toplevel
$ok = 0
$expectedFiles = @('__REVIEWED_FILE__')
try {
  $branch = git rev-parse --abbrev-ref HEAD
  if ($LASTEXITCODE -ne 0 -or $branch -ne '__BRANCH__') { throw 'Unexpected branch' }
  $staged = @(git diff --cached --name-only)
  if ($LASTEXITCODE -ne 0 -or $staged.Count -gt 0) { throw 'Inspect the existing index first' }
  git add -- $expectedFiles
  if ($LASTEXITCODE -ne 0) { throw 'Staging failed' }
  $staged = @(git diff --cached --name-only)
  if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect staged files' }
  if (@(Compare-Object $expectedFiles $staged).Count -gt 0) {
    git restore --staged -- $expectedFiles
    throw 'Staged list differs from reviewed files; slice unstaged'
  }
  git diff --cached --check
  if ($LASTEXITCODE -ne 0) { throw 'Staged whitespace check failed' }
  git diff --cached --stat
  git commit -q -F ..\texts\__COMMIT_TEXT__.txt
  if ($LASTEXITCODE -ne 0) { throw 'Commit failed; inspect hook output' }
  'committed'; $ok++
  git push -q -u origin __BRANCH__
  if ($LASTEXITCODE -ne 0) { throw 'Push failed' }
  'pushed'; $ok++
  $url = gh pr create --base main --head __BRANCH__ --title '__PR_TITLE__' --body-file ..\texts\__PR_TEXT__.md --reviewer __REVIEWER__
  if ($LASTEXITCODE -ne 0 -or $url -notmatch '/pull/\d+') { throw 'PR creation failed' }
  "PR: $url"; $ok++
} catch {
  "Stopped: $($_.Exception.Message)"
}
if ($ok -eq 3) { 'VERDICT: CB.1 PASS (3 of 3)' } else { "VERDICT: CB.1 FAIL ($ok of 3)" }
