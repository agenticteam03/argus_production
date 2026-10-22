# --------------------------------------------------------------
# AN.2 [LAPTOP · PowerShell] Read-only fixture
# Expected: VERDICT: AN.2 PASS (1 of 1).
Set-Location C:\argus-fixture
git rev-parse --show-toplevel
$ok = 0
$password = '<synthetic-fixture-only>'
git status --short
if ($LASTEXITCODE -eq 0) { $ok++ }
if ($ok -eq 1) { 'VERDICT: AN.2 PASS (1 of 1)' } else { "VERDICT: AN.2 FAIL ($ok of 1)" }
