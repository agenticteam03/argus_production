# --------------------------------------------------------------
# AN.2 [LAPTOP · PowerShell] Read-only fixture
# Expected: VERDICT: AN.2 PASS (1 of 1).
Set-Location C:\argus-fixture
$ok = 0
git status --short
if ($LASTEXITCODE -eq 0) { $ok++ }
if ($ok -eq 1) { 'VERDICT: AN.2 PASS (1 of 1)' } else { "VERDICT: AN.2 FAIL ($ok of 1)" }
