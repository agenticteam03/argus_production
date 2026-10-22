# ---------------------------------------------------------------------------------------------------------
# CB.1 [LAPTOP · PowerShell] Post the reviewed comment from its text file
# MUTATES: one PR comment. Undo: gh api repos/__OWNER__/__REPO__/issues/comments/__COMMENT_ID__ --method DELETE
# Text: ..\texts\__COMMENT_TEXT__.md (running this block authorizes posting it).
# Expected: a comment URL; VERDICT: CB.1 PASS (1 of 1).
# ---------------------------------------------------------------------------------------------------------
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath '__REPO_ROOT__'
git rev-parse --show-toplevel
$ok = 0
gh pr comment __PR_NUMBER__ --body-file ..\texts\__COMMENT_TEXT__.md
if ($LASTEXITCODE -eq 0) { $ok++ }
if ($ok -eq 1) { 'VERDICT: CB.1 PASS (1 of 1)' } else { "VERDICT: CB.1 FAIL ($ok of 1)" }
