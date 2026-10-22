# ---------------------------------------------------------------------------------------------------------
# CB.1 [LAPTOP · PowerShell] Approve another author's PR on its reviewed head
# MUTATES: one approval. Undo: gh pr review __PR_NUMBER__ --request-changes --body-file ..\texts\__UNDO_REVIEW_TEXT__.md
# Text: ..\texts\__REVIEW_TEXT__.md (running this block authorizes the review).
# Expected: 'approved __PR_NUMBER__'; VERDICT: CB.1 PASS (1 of 1).
# ---------------------------------------------------------------------------------------------------------
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath '__REPO_ROOT__'
git rev-parse --show-toplevel
$ok = 0
$reviewed = '__REVIEWED_FULL_HEAD_SHA__'
foreach ($n in @('__PR_NUMBER__')) {
  $head = gh pr view $n --json headRefOid --jq '.headRefOid'
  $headOk = $LASTEXITCODE -eq 0
  $buckets = gh pr checks $n --json bucket --jq '.[].bucket'
  $checksOk = $LASTEXITCODE -eq 0
  $author = gh pr view $n --json author --jq '.author.login'
  $authorOk = $LASTEXITCODE -eq 0
  $me = gh api user --jq '.login'
  $meOk = $LASTEXITCODE -eq 0
  $bad = @($buckets | Where-Object { $_ -eq 'fail' -or $_ -eq 'pending' -or $_ -eq 'cancel' }).Count
  if (-not ($headOk -and $checksOk -and $authorOk -and $meOk)) { "skip $n : metadata or checks unavailable" }
  elseif ([string]::IsNullOrWhiteSpace($me) -or $author -eq $me) { "skip $n : reviewer must be another author" }
  elseif ($head -ne $reviewed) { "skip $n : head differs from reviewed commit" }
  elseif ($bad -gt 0 -or @($buckets).Count -eq 0) { "skip $n : checks failed, pending, cancelled or absent" }
  else {
    gh pr review $n --approve --body-file ..\texts\__REVIEW_TEXT__.md
    if ($LASTEXITCODE -eq 0) { "approved $n"; $ok++ } else { "approve $n failed" }
  }
}
if ($ok -eq 1) { 'VERDICT: CB.1 PASS (1 of 1)' } else { "VERDICT: CB.1 FAIL ($ok of 1)" }
