# (archived) AFTER-MERGE of #88-#90, run 2026-10-12 by juanbetancurm; both leases, session f3734af7cf36
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
# 2026-10-12, juanbetancurm. AFTER-MERGE of #88-#90: both VMs from task/T-0019-batch2-host-probe 040b827 to main 45dda69.
# main CI is all green (main-guard too). Code difference 040b827 → 45dda69: argus/evaluation/replay.py (evaluation only)
# and tests; the target services' code is the same. So this is mostly the checkout on main + one agent image from main.
# Modelled on conantkd's S3.5 (brain/execution/history/T-0019/step-06/code.bash). No model call.
# Order: L.1 → M.1 → A.1 on vm-166 → A.1 on vm-095 → R.1.   [~20 min]
# Your laptop checkout is on main 45dda69. #87 (PRODUCT-MOCK, added by mistake) is closed and its branch deleted.
# =====================================================================================

# --- L.1 [LAPTOP · PowerShell] both leases ------------------------------------------------------------------------------
cd C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\argus_production
git stash push brain/execution/current/code.bash
python brain\tools\brain.py start --task AFTER-MERGE-T-0019 --vm both
git stash pop
python brain\tools\brain.py renew --vm both --minutes 60
# Expected: the lease taken on vm-095 and vm-166, a session id and two "VM marker" lines; code.bash back; renewed.
# VERDICT: lease taken → paste it, say "output updated" (the agent fills M.1). "held by" someone else → STOP, paste it.

# --- M.1 [LAPTOP · PowerShell] the session marker on both VMs (session f3734af7cf36, lease until 16:01 UTC) --------
ssh argus-vm166 'echo holder=juanbetancurm session=f3734af7cf36 | sudo tee /opt/argus-v18/SESSION >/dev/null; cat /opt/argus-v18/SESSION'
ssh argus-vm095 'echo holder=juanbetancurm session=f3734af7cf36 | sudo tee /opt/argus-v18/SESSION >/dev/null; cat /opt/argus-v18/SESSION'
# Expected: twice  holder=juanbetancurm session=f3734af7cf36
# VERDICT: both → A.1: type  ssh argus-vm166 , paste the whole A.1 block, check it, type  exit ;
#          then  ssh argus-vm095 , paste the SAME A.1 block again, check it, type  exit .

# --- A.1 [VM vm-166 · bash] then [VM vm-095 · bash]: the same block on each (MUTATES) ---------------------------------
# MUTATES: the checkout + DEPLOYED marker; target services up -d --build (same code: little or nothing recreated);
#   on vm-095 one backup and agent, worker and scheduler recreated TOGETHER (S3.3's lesson).
# ROLLBACK: deploy.sh task/T-0019-batch2-host-probe --as juanbetancurm, then the same compose commands.
ME=juanbetancurm
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
H=$(hostname | sed 's/^argus-//'); case $H in vm095) V=vm-095; O=compose.core-join.yml;; *) V=vm-166; O=compose.loopback.yml;; esac
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
[ $V = vm-095 ] && sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as $ME | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh main --as $ME | tail -1
cd /opt/argus-v18/app/deploy/target && sudo docker compose --env-file $V.env -f compose.target.yml -f $O up -d --build 2>&1 | grep -c -E "Started|Running" | sed 's/^/target services up: /'
if [ $V = vm-095 ]; then
  cd /opt/argus-v18/app/deploy/vm-095
  sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler 2>&1 | grep -E "Recreated|Started" | tr '\n' ' '; echo
  for i in $(seq 1 24); do c=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18000/healthz); [ "$c" = 200 ] && break; sleep 5; done; echo "health $c"
  for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c image=$(sudo docker inspect -f '{{.Image}}' $c | cut -c8-19) $(sudo docker inspect -f '{{.State.Status}} restarts={{.RestartCount}}' $c)"; done
  sudo docker logs --tail 5 argus-v18-worker 2>&1 | grep -i -E "startup validation|missing credential|error" || echo "worker: no startup errors"
  sudo docker exec argus-v18-agent argus db check </dev/null | tail -1
  sudo docker run --rm --network argus-v18-core -v /opt/argus-v18/secrets/agent:/s:ro -v /opt/argus-v18/app/ops/phase3_check.py:/c.py:ro python:3.12-alpine python /c.py | grep -E "checks passed|FAIL"
  sudo docker exec argus-v18-worker python -c "from argus.detectors.classes import CLASSES; from argus.tooling.model_harness import SYSTEM_PROMPT as P; print('disk_pressure strategy:', next(c.strategy for c in CLASSES if c.name == 'disk_pressure'), '| prompt rules present:', 'where the space went' in ' '.join(P.split()), 'host-level symptom' in P)"
  sudo bash /opt/argus-v18/app/ops/write-gate-check.sh | tail -1
fi
cd ~
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: SESSION OK; NO INTERFERENCE (before); [vm-095: BACKUP OK]; DEPLOY OK 45dda69 (main); target services up: N;
#   vm-095: agent, worker, scheduler on ONE image, running restarts=0, health 200, no startup errors, 20/20 db checks,
#   phase3_check "55/55 checks passed", "disk_pressure strategy: confirm_then_reason | prompt rules present: True True",
#   WRITE GATE CLOSED; commit=45dda69... ref=main; LAB BASELINE OK; NO INTERFERENCE.
# VERDICT: both VMs → R.1. Anything else → STOP (rollback above) and paste it.

# --- R.1 [LAPTOP · PowerShell] release both leases ----------------------------------------------------------------------
git stash push brain/execution/current/code.bash
python brain\tools\brain.py release --vm both
git stash pop
# Expected: "Lease released on vm-095 and vm-166."; code.bash back.
# VERDICT: paste L.1 to R.1, say "output updated". The agent then writes the record PR (AFTER-MERGE + E2E-5 step 2).
