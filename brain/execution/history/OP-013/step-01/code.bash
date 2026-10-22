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


# ---------------------------------------------------------------------------------------------------------
# OP13.1 [LAPTOP · PowerShell]  commit, push and open the OP-013 held-out set PR (conantkd reviews)
# HOLD: run only after S1's pre-review says OK on SESSIONS.md.
# Texts: ..\texts\commit-OP-013.txt, ..\texts\pr-OP-013.md (running this block approves them).
# MUTATES: one local commit, the task branch on origin, one PR. Undo: gh pr close <n>; the branch stays.
# Expected: the hooks Passed, 'pushed', 'PR: <url>'; VERDICT: OP13.1 PASS (2 of 2).
# ---------------------------------------------------------------------------------------------------------
Set-Location C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\w-op013
git rev-parse --show-toplevel
git rev-parse --abbrev-ref HEAD
$ok = 0
git add tests/eval/heldout/cases tests/test_op013_heldout_cases.py brain/tasks/current/OP-013-held-out-set.md brain/journal/entries/2026-10-21-OP-013-held-out-set.md
git --no-pager diff --cached --stat
git commit -q -F ..\texts\commit-OP-013.txt
git push -q -u origin task/OP-013-held-out-set
if ($LASTEXITCODE -eq 0) { 'pushed'; $ok++ } else { 'push failed' }
$url = gh pr create --base main --head task/OP-013-held-out-set --title 'OP-013: a held-out evaluation set for the two classes under the baseline' --body-file ..\texts\pr-OP-013.md --reviewer conantkd
"PR: $url"
if ($url -match '/pull/\d+') { $ok++; Move-Item ..\texts\commit-OP-013.txt, ..\texts\pr-OP-013.md ..\texts\archive\ }
if ($ok -eq 2) { 'VERDICT: OP13.1 PASS (2 of 2)' } else { "VERDICT: OP13.1 FAIL ($ok of 2)" }
