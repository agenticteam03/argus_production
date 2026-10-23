# ---------------------------------------------------------------------------------------------------------
# AN.3 [LAPTOP · PowerShell]  commit, push and open the T-0049 plan PR (agent skills, phase 24; conantkd reviews)
# Texts: ..\commit-t0049-plan.txt, ..\pr-t0049-plan.md (running this block approves them).
# Expected: the hooks Passed, 'pushed', 'PR: <url>'; VERDICT: AN.3 PASS (2 of 2).
# ---------------------------------------------------------------------------------------------------------
Set-Location C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\w-skills
git rev-parse --show-toplevel
git rev-parse --abbrev-ref HEAD
$ok = 0
git add brain/IMPLEMENTATION_PLAN.md brain/tasks/current/T-0049-agent-skills.md brain/journal/entries/2026-10-21-T-0049-skills-plan.md
git commit -q -F ..\commit-t0049-plan.txt
git push -q -u origin task/T-0049-skills-plan
if ($LASTEXITCODE -eq 0) { 'pushed'; $ok++ } else { 'push failed' }
$url = gh pr create --base main --head task/T-0049-skills-plan --title 'T-0049 proposed: agent skills (phase 24)' --body-file ..\pr-t0049-plan.md --reviewer conantkd
"PR: $url"
if ($url -match '/pull/\d+') { $ok++ }
Set-Location ..\argus_production
if ($ok -eq 2) { 'VERDICT: AN.3 PASS (2 of 2)' } else { "VERDICT: AN.3 FAIL ($ok of 2)" }
