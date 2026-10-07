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

# =====================================================================================
# T-0015 step 6 — prove the read-only token on the deployed agent (vm-095)                         [~3 min]
# Why: T-0015 steps 1-5 are merged (PR #22); the running agent image already carries them (rebuilt by conantkd
#      for T-0019/T-0020), so NO deploy and NO rebuild: only API calls on the loopback port.
# MUTATES: nothing (logins + GETs; the refused POST creates nothing). Lease: juanbetancurm (DEMO session, still active;
#          renew it first). The token is never printed.
# =====================================================================================

# --- U.0 [LAPTOP · PowerShell] renew the lease -------------------------------------------------------------------------
cd C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\argus_production
git stash push brain/execution/current/code.bash
python brain\tools\brain.py renew
git stash pop
# Expected: "Lease renewed until ..." (60 min from now)

# --- U.1 [VM vm-095 · bash] (ssh argus-vm095) read token: reads work, a write is refused ------------------------------
grep -q "^holder=juanbetancurm " /opt/argus-v18/SESSION && echo "SESSION OK" || echo "NOT YOUR SESSION - stop here"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
read -rsp "Argus password for juanbetancurm: " ARGUS_PASSWORD; echo
A=http://127.0.0.1:18000/api/v1
TOK=$(curl -s -X POST $A/auth/token --data-urlencode username=juanbetancurm --data-urlencode "password=$ARGUS_PASSWORD" -d scope=read | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("access_token","")) if d.get("access")=="read" else print("")')
unset ARGUS_PASSWORD
[ -n "$TOK" ] && echo "login scope=read: token with access=read" || echo "login scope=read: FAILED"
curl -s -H "Authorization: Bearer $TOK" $A/me | python3 -c 'import json,sys; d=json.load(sys.stdin); print("me:", d.get("user"), d.get("role"), "access="+str(d.get("access")), "actions="+",".join(d.get("actions",[])))'
echo "GET  incidents with the read token -> $(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOK" "$A/incidents?limit=3")"
echo "POST investigations with the read token -> $(curl -s -o /dev/null -w '%{http_code}' -X POST -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' -d '{"target":"vm-095/container:argus-lab-api","reason":"T-0015 step 6 proof","request_kind":"check"}' $A/investigations)"
echo "GET  incidents without a token -> $(curl -s -o /dev/null -w '%{http_code}' "$A/incidents?limit=3")"
unset TOK
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: SESSION OK; login scope=read: token with access=read; me: juanbetancurm <role> access=read actions=view_...;
#           GET 200; POST 403; without a token 401; NO INTERFERENCE.
# VERDICT: 200 / 403 / 401 → OK · a POST answer of 200/201/202 → STOP (a read token must never start an investigation)
