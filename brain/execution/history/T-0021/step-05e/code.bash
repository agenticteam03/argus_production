# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
#
# Every block says WHERE to run it:
#   [VM vm-095 · bash]      ssh argus-vm095
#   [LAPTOP · PowerShell]   a PowerShell window on your laptop
# Paste what the terminal printed into brain/execution/current/output.bash (gitignored, never committed)
# and tell the agent "output.bash updated".
# =====================================================================================

# =====================================================================================
# T-0021 step 5e — vm-095: the fixed launcher (review of PR #36)  [~6 min]
# Ran 2026-10-09 with the review fixes 6f45218 (task/T-0021-tool-isolation). Kept as the record of step 5e.
# Story: redeploy the branch and rebuild the three programs, so the worker's image has the launcher with `cd /` and
#   `python -I`. Then the isolation check, now with the planted-package probe: it must print
#   "ok   the launcher ignores code planted in the caller's folder" and TOOLS ISOLATION OK.
# The worker stays mcp, the tokens stay argus-tools. vm-166 is NOT touched (conantkd's T-0020 branch).
# READ-ONLY on the lab. MUTATES Argus only: checkout + rebuild of the three Argus programs on vm-095.
# =====================================================================================

# --- L.1 [LAPTOP · PowerShell] the lease: take it ONLY if conantkd has released it or it has expired -----------------
cd C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\argus_production
git stash push brain/execution/current/code.bash
python brain\tools\brain.py status
python brain\tools\brain.py start --task T-0021
git stash pop
git fetch -q origin '+refs/heads/session:refs/remotes/origin/session'
$L = git show origin/session:session.json | ConvertFrom-Json
ssh -o BatchMode=yes argus-vm095 "echo 'holder=$($L.holder) session=$($L.session_id)' | sudo tee /opt/argus-v18/SESSION"
if (($L.holder -eq 'juanbetancurm') -and (-not $L.released)) { 'VERDICT L.1 OK' } else { 'VERDICT L.1 STOP: lease not yours' }
# Expected: status shows conantkd's lease released or expired; "Lease CLAIMED by juanbetancurm until ...";
#   vm-095 prints holder=juanbetancurm session=...; VERDICT L.1 OK.
# VERDICT: STOP (conantkd still holds it) → do NOT force it: ask him to release it (brain.py handoff), then run L.1 again.

# --- V.1 [VM vm-095 · bash] deploy, rebuild, isolation check with the new probe (asks nothing) -----------------------
grep -q "^holder=juanbetancurm " /opt/argus-v18/SESSION && echo "SESSION OK" || echo "NOT YOUR SESSION - stop here"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh task/T-0021-tool-isolation --as juanbetancurm | tail -1
cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler 2>&1 | tail -3; cd ~
sleep 15
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^commit=|LAB BASELINE|^argus:'
sudo docker exec argus-v18-worker sh -c 'echo "catalogue=${ARGUS_TOOL_CATALOGUE}"'
sudo docker exec argus-v18-worker grep -E '^(cd|exec) ' /usr/local/bin/argus-tools-server
sudo docker exec argus-v18-worker python -m argus.tooling.isolation_check
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: SESSION OK; NO INTERFERENCE baseline; DEPLOY OK: <the new commit>; 3 argus: lines; LAB BASELINE OK;
#   catalogue=mcp; "cd / || exit 1" and "exec /usr/local/bin/python -I -u -m argus.tooling.mcp.tools_server";
#   7 lines "ok ..." including "ok   the launcher ignores code planted in the caller's folder: the fake argus
#   package did not run" and "... lists its reads: 16 capabilities"; TOOLS ISOLATION OK; NO INTERFERENCE.
# VERDICT: TOOLS ISOLATION OK + NO INTERFERENCE → step 5e done (the agent records it and asks for the re-review)
#   · any FAIL / STOP → paste everything; do not change anything else.
