# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
#
# Every block says WHERE to run it:
#   [LAPTOP · PowerShell]   a PowerShell window on your laptop
#   [VM vm-095 · bash]      ssh argus-vm095   (prompt: ubuntu@vm-appsvnic)
#   [VM vm-166 · bash]      ssh argus-vm166   (prompt: ubuntu@agent-test-vnic)
# Paste what the terminal printed into brain/execution/current/output.bash (gitignored, never committed)
# and tell the agent "output.bash updated".
# =====================================================================================

# =====================================================================================
# DEPLOY-MAIN — Put both VMs on `main`, rebuild the agent, re-verify H-1 and SC-03        [~25 min]
# Why: vm-095 runs c87d76c (T-0013 branch). `main` has since added the T-0013 review fix (one read per graph step),
#   OP-006 (recursion limit from the budgets) and the `langgraph` compose default. vm-166 runs 8eff994: no target-
#   service code changed since, so it only moves its checkout to `main` (no rebuild).
#   SC-03 is re-run WITH archived output: it upgrades the 2026-10-05 class demo from "reported" to "verified".
# MUTATES: the git checkout on both VMs (+ DEPLOYED marker); rebuilds argus-v18-agent on vm-095; stops/starts
#   argus-lab-cache on vm-166 (SC-03).
# Undo (vm-095): sudo bash /opt/argus-v18/app/ops/deploy.sh c87d76c --as <you>, then rebuild the agent as in D.2.
# Written for conantkd: if someone else runs it, replace conantkd with your handle in D.0 and in each ME= line.
# =====================================================================================

# =====================================================================================
# PROGRESS (conantkd, session 6b413ecc1488, lease until 08:23 UTC = 03:23 local)
#   D.0 OK · D.1 OK (vm-166 on 09f5ab1) · D.2 OK (vm-095 on 09f5ab1, agent rebuilt, langgraph, db 15/15;
#     re-checked at 05:24 UTC after the second D.2 run recreated the container)
#   D.2 incident: `db-migrate.sh | tail -3` hung on `docker exec -i` (it read the terminal); fixed with `< /dev/null`.
#   D.3: H-1 returned "DIAGNOSED · class dependency_unavailable" (inc_bee874c1898e) instead of HEALTHY.
#   D.3b-1 EXPLAINS IT: argus-lab-cache "Exited (0) 7 hours ago" (left stopped after the DEMO-SC03 class demo),
#     argus-lab-api unhealthy, Prometheus argus_container_running{cache}=0. Argus was RIGHT: the lab was broken.
#   Consequence: the SC-03 condition (cache down, api unhealthy) is ALREADY in place -> D.4 is SKIPPED.
#   D.5 OK (vm-095): DIAGNOSED dependency_unavailable, root cause vm-166/container:argus-lab-cache, confidence high,
#     api = victim; reads on vm-166 only (container.status x2, dns + tcp to the cache); no mutation recommended.
#   D.6 OK: cache started, api healthy, NO INTERFERENCE on vm-166; Prometheus: api_unhealthy=0,
#     no firing alerts.
#   >>> NEXT: D.6b (conantkd, vm-095, the SAME shell as D.5 - prompt ubuntu@argus-vm095). <<<
# =====================================================================================

# --- D.5 [VM vm-095 · bash] SC-03: diagnose the api with the cache down (READ-ONLY; calls the model) --------------
ME=conantkd
read -rsp "Shared Argus password: " ARGUS_PASSWORD; echo; export ARGUS_PASSWORD
ARGUS="sudo --preserve-env=ARGUS_PASSWORD docker exec -i -e ARGUS_USER=$ME -e ARGUS_PASSWORD argus-v18-agent argus"
$ARGUS diagnose vm-166/container:argus-lab-api --reason "api returns errors" --no-color < /dev/null | tee /tmp/sc03.txt | tail -30
grep -qi 'diagnosed' /tmp/sc03.txt && grep -i 'root cause' /tmp/sc03.txt | grep -q 'argus-lab-cache'   && echo "VERDICT D.5 OK: root cause = vm-166/container:argus-lab-cache (the api is the victim)" || echo "VERDICT D.5 STOP"
rm -f /tmp/sc03.txt
# Keep this shell open (ARGUS_PASSWORD stays set) for D.6b. Paste everything below the password prompt.
# Expected: DETECT dependency_unavailable -> RECALL RB-003 -> reads on vm-166 only -> RECORD diagnosed, root cause the cache.

# --- D.6 [VM vm-166 · bash] Start the cache again, wait for the api to be healthy (MUTATES: argus-lab-cache) ------
sudo docker start argus-lab-cache
for i in $(seq 1 8); do s=$(sudo docker inspect -f '{{.State.Health.Status}}' argus-lab-api); echo "api health=$s"; [ "$s" = healthy ] && break; sleep 10; done
sudo docker ps -a --filter name=argus-lab- --format '{{.Names}} | {{.Status}}'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1             # expected: NO INTERFERENCE
[ "$s" = healthy ] && echo "VERDICT D.6 OK: api healthy again" || echo "VERDICT D.6 STOP"

# --- D.6b [VM vm-095 · bash] (same shell as D.5) H-1 again: now it must be HEALTHY (READ-ONLY, no model call) -------
$ARGUS diagnose vm-166/container:argus-lab-api --check --reason "DEPLOY-MAIN H-1 after the cache is back" --no-color < /dev/null | grep -E '^incident|outcome'
unset ARGUS_PASSWORD
# Expected: outcome HEALTHY.

# --- D.7 / D.8: non-interference on vm-095, then archive (original blocks below).

# =====================================================================================
# ORIGINAL DEPLOY-MAIN BLOCKS (kept for the record; status in each title)
# =====================================================================================

# --- [DONE OK] D.0 [LAPTOP · PowerShell] Lease + session marker on both VMs (MUTATES the session branch + SESSION files) -----
cd C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\argus_production
python brain\tools\brain.py start --task DEPLOY-MAIN
git fetch -q origin "+refs/heads/session:refs/remotes/origin/session"
$L = git show origin/session:session.json | ConvertFrom-Json
foreach ($vm in "argus-vm095", "argus-vm166") { ssh -o BatchMode=yes $vm "echo 'holder=$($L.holder) session=$($L.session_id)' | sudo tee /opt/argus-v18/SESSION" }
if (($L.holder -eq "conantkd") -and (-not $L.released)) { "VERDICT D.0 OK" } else { "VERDICT D.0 STOP: lease not yours/active" }
# Expected: "Lease CLAIMED by conantkd until ...", both VMs print the same holder/session line, "VERDICT D.0 OK".

# --- [DONE OK] D.1 [VM vm-166 · bash] (ubuntu@agent-test-vnic) Move the checkout to main (MUTATES files only) --------------
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "session marker: mine" || echo "NOT YOUR SESSION - stop here"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh main --as $ME | tail -8
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)='
# Expected: "DEPLOY OK: <main commit> (main) on ..."; the rebuild hints list nothing for vm-166's services
# (if they list a target service, STOP and tell the agent: that would contradict the code comparison).

# --- [DONE OK, do not re-run] D.2 [VM vm-095 · bash] (ubuntu@vm-appsvnic) Deploy main + rebuild the agent (MUTATES: argus-v18-agent) -------
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "session marker: mine" || echo "NOT YOUR SESSION - stop here"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh main --as $ME | tail -8
sudo bash /opt/argus-v18/app/ops/db-migrate.sh < /dev/null   # < /dev/null: without it `docker exec -i` reads the terminal and hangs
cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml \
  up -d --build --no-deps argus-v18-agent && cd ~
sleep 15
RUNNER=$(sudo docker exec argus-v18-agent python -c "from argus.infrastructure.wiring import Settings; print(Settings().runner)")
echo "agent runner: $RUNNER"
sudo docker exec argus-v18-agent argus db check | grep -q '^15/15 database checks passed' && [ "$RUNNER" = langgraph ] \
  && echo "VERDICT D.2 OK: vm-095 on main, agent rebuilt on LangGraph, db check 15/15" || echo "VERDICT D.2 STOP"
# Expected: "DEPLOY OK: <main commit> (main)", migrations "(already applied)", "agent runner: langgraph".

# --- [DONE, unexpected: see PROGRESS] D.3 [VM vm-095 · bash] H-1: healthy check, no model call (READ-ONLY). Keep this shell open for D.5 ----------
read -rsp "Shared Argus password: " ARGUS_PASSWORD; echo; export ARGUS_PASSWORD
ARGUS="sudo --preserve-env=ARGUS_PASSWORD docker exec -i -e ARGUS_USER=$ME -e ARGUS_PASSWORD argus-v18-agent argus"
$ARGUS diagnose vm-166/container:argus-lab-api --check --reason "DEPLOY-MAIN H-1" < /dev/null | grep -E '^incident|outcome'
# Expected: outcome HEALTHY.

# --- [SKIPPED: cache was already down] D.4 [VM vm-166 · bash] SC-03: stop the cache (MUTATES: argus-lab-cache only; undo: D.6) ----------------------
sudo docker stop argus-lab-cache
for i in $(seq 1 12); do s=$(sudo docker inspect -f '{{.State.Health.Status}}' argus-lab-api); echo "api health=$s"; [ "$s" = unhealthy ] && break; sleep 10; done
sleep 30                                                    # let Prometheus scrape the failure
[ "$s" = unhealthy ] && echo "VERDICT D.4 OK: api unhealthy" || echo "VERDICT D.4 STOP"

# --- D.5 [VM vm-095 · bash] (same shell as D.3) SC-03: diagnose the api (READ-ONLY; calls the model) -------------
$ARGUS diagnose vm-166/container:argus-lab-api --reason "api returns errors" < /dev/null | tee /tmp/sc03.txt | tail -25
grep -qi 'diagnosed' /tmp/sc03.txt && grep -i 'root cause' /tmp/sc03.txt | grep -q 'argus-lab-cache' \
  && echo "VERDICT D.5 OK: root cause = vm-166/container:argus-lab-cache (the api is the victim)" || echo "VERDICT D.5 STOP"
rm -f /tmp/sc03.txt; unset ARGUS_PASSWORD
# Expected: DETECT dependency_unavailable -> RECALL RB-003 -> reads on vm-166 only -> RECORD diagnosed, root cause the cache.

# --- D.6 [VM vm-166 · bash] Start the cache again + non-interference -----------------------------------------------
sudo docker start argus-lab-cache
for i in $(seq 1 8); do s=$(sudo docker inspect -f '{{.State.Health.Status}}' argus-lab-api); echo "api health=$s"; [ "$s" = healthy ] && break; sleep 10; done
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1             # expected: NO INTERFERENCE
[ "$s" = healthy ] && echo "VERDICT D.6 OK: api healthy again" || echo "VERDICT D.6 STOP"

# --- D.7 [VM vm-095 · bash] Non-interference ---------------------------------------------------------------------
sudo docker ps --filter name=argus- --format '{{.Names}} {{.Status}}'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1             # expected: NO INTERFERENCE

# --- D.8 [LAPTOP · PowerShell] Release the lease ------------------------------------------------------------------
python brain\tools\brain.py release
# >>> Paste everything (no password) into output.bash and tell the agent "output.bash updated". <<<
