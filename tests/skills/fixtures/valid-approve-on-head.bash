# ---------------------------------------------------------------------------------------------------------
# AN.1b [LAPTOP · PowerShell]  approve conantkd's #250 (H4 observed allowlist) once its test job is done
# Text: ..\review-250.md (running this block approves it).
# Approved only if the head is the reviewed one and its CI has no failed or pending check.
# Expected: 'approved 250'; VERDICT: AN.1b PASS (1 of 1).
# ---------------------------------------------------------------------------------------------------------
Set-Location C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\argus_production
git rev-parse --show-toplevel
$ok = 0
$reviewed = @{ 250 = '3d46fad' }
foreach ($n in @(250)) {
  $head = gh pr view $n --json headRefOid --jq '.headRefOid'
  $buckets = gh pr checks $n --json bucket --jq '.[].bucket'
  $bad = @($buckets | Where-Object { $_ -eq 'fail' -or $_ -eq 'pending' }).Count
  if (-not $head.StartsWith($reviewed[$n])) { "skip $n : head is $head, reviewed $($reviewed[$n])" }
  elseif ($bad -gt 0) { "skip $n : $bad check(s) failed or pending" }
  else {
    gh pr review $n --approve --body-file ..\review-$n.md
    if ($LASTEXITCODE -eq 0) { "approved $n"; $ok++ } else { "approve $n failed" }
  }
}
if ($ok -eq 1) { 'VERDICT: AN.1b PASS (1 of 1)' } else { "VERDICT: AN.1b FAIL ($ok of 1)" }
