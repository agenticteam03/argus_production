# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
#
# Every block says WHERE to run it:
#   [LAPTOP · PowerShell]   a PowerShell window on your laptop
#   [VM vm-095 · bash]      ssh argus-vm095
#   [VM vm-166 · bash]      ssh argus-vm166
# Paste what the terminal printed into brain/execution/current/output.bash (gitignored, never committed)
# and tell the agent "output.bash updated".
# =====================================================================================


# AN.1 approved #251; AN.2 commented on #254; AN.3 opened #255 (T-0049 plan). #250's tests are now green.
# main-guard stays red until #253 or #254 merges: approvals and new PRs are fine, no merges.

# ---------------------------------------------------------------------------------------------------------
# AN.1b [LAPTOP · PowerShell]  approve conantkd's #250 (H4 observed allowlist) once its test job is done
# Text: ..\texts\review-250.md (running this block approves it).
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
    gh pr review $n --approve --body-file ..\texts\review-$n.md
    if ($LASTEXITCODE -eq 0) { "approved $n"; $ok++ } else { "approve $n failed" }
  }
}
if ($ok -eq 1) { 'VERDICT: AN.1b PASS (1 of 1)' } else { "VERDICT: AN.1b FAIL ($ok of 1)" }
