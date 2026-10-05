# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
#   [LAPTOP · PowerShell]   [VM vm-095 · bash] = ssh argus-vm095   [VM vm-166 · bash] = ssh argus-vm166
# Paste what the terminal printed into brain/execution/current/output.bash (gitignored, never committed)
# and tell the agent "output.bash updated". Every block ends with a VERDICT line.
# =====================================================================================

# =====================================================================================
# T-0013 STEP 5 (verification run by conantkd, the reviewer) — LangGraph + Postgres checkpoints on the real VMs  [~40 min]
# Why: the PR review needs evidence that the branch works on the VMs: same diagnoses as before, runs checkpointed.
# Already done by the task owner (DEPLOYED markers on both VMs): deploy.sh init (old steps S5.1-S5.3). Not repeated.
# What changes: vm-095 Postgres gets migration 002 (idempotent) and the agent image is rebuilt with
#   ARGUS_RUNNER=langgraph; vm-166 gets the SC-01 lab worker started, then removed.
# Rollback (vm-095): cd /opt/argus-v18/app/deploy/vm-095 && sudo ARGUS_RUNNER=plain docker compose --env-file
#   /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent   (002 tables stay, unused)
# =====================================================================================

# --- S5.A [LAPTOP · PowerShell] Renew the lease for 2 hours (MUTATES the session branch) ---------------------------
python brain\tools\brain.py renew --minutes 120
# Expected: "Lease renewed until ..." (about 2 hours from now). If it says the lease is not yours: STOP.

# --- S5.B [VM vm-095 · bash] (ssh argus-vm095) Marker check, baseline, migration 002, rebuild the agent (MUTATES) ---
grep -q '^holder=conantkd ' /opt/argus-v18/SESSION || { echo "NOT YOUR SESSION"; exit 1; }
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|checkout:|local modifications'
cd /opt/argus-v18/app && sudo bash ops/db-migrate.sh
cd /opt/argus-v18/app/deploy/vm-095 && sudo ARGUS_RUNNER=langgraph docker compose --env-file /opt/argus-v18/hosts.env \
  -f compose.core.yml up -d --build --no-deps argus-v18-agent && cd ~
sleep 15
RUNNER=$(sudo docker exec argus-v18-agent python -c "from argus.infrastructure.wiring import Settings; print(Settings().runner)")
echo "agent runner: $RUNNER"
sudo docker exec argus-v18-agent argus db check | tail -4
sudo docker exec argus-v18-agent argus db check | grep -q '^15/15 database checks passed' && [ "$RUNNER" = langgraph ] \
  && echo "VERDICT S5.B OK: 002 applied, agent on LangGraph, db check 15/15" || echo "VERDICT S5.B STOP"
# Expected: "+ 002_checkpoints applied" (or "= 002_checkpoints (already applied)"), "agent runner: langgraph", 15/15.
# The first build takes a few minutes (it downloads LangGraph).

# --- S5.C [VM vm-095 · bash] H-1 (healthy, no model call) and SC-09 (unsupported, evidence pack) --------------------
read -rsp "Shared Argus password: " ARGUS_PASSWORD; echo; export ARGUS_PASSWORD
argus() { sudo --preserve-env=ARGUS_PASSWORD docker exec -i -e ARGUS_USER=conantkd -e ARGUS_PASSWORD argus-v18-agent argus "$@"; }
ckpt() { sudo docker exec argus-v18-postgres psql -U argus_owner -d argus -At -c "SELECT count(DISTINCT thread_id) FROM checkpoints"; }
BEFORE=$(ckpt)
H1=$(argus diagnose vm-166/container:argus-lab-api --check --reason "T-0013 review H-1" | grep -E '^incident|outcome'); echo "$H1"
S9=$(argus diagnose vm-095/container:argus-lab-api --reason "users see stale data" | grep -E '^incident|outcome'); echo "$S9"
AFTER=$(ckpt); echo "checkpointed investigations: $BEFORE -> $AFTER"
echo "$H1" | grep -q 'HEALTHY' && echo "$S9" | grep -qi 'unsupported' && [ "$AFTER" -ge $((BEFORE + 2)) ] \
  && echo "VERDICT S5.C OK: same outcomes as before, both runs checkpointed in Postgres" || echo "VERDICT S5.C STOP"
# Keep this shell open (the password stays in ARGUS_PASSWORD) for S5.E.

# --- S5.D [VM vm-166 · bash] (ssh argus-vm166) Start SC-01 (OOM restart loop) (MUTATES: lab worker only) -------------
# Undo: cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc01 rm -sf argus-lab-worker-oom
grep -q '^holder=conantkd ' /opt/argus-v18/SESSION || { echo "NOT YOUR SESSION"; exit 1; }
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc01 up -d argus-lab-worker-oom && cd ~
for i in $(seq 1 18); do r=$(sudo docker inspect -f '{{.RestartCount}}' argus-lab-worker 2>/dev/null || echo 0); echo "restarts=$r"; [ "$r" -ge 3 ] && break; sleep 10; done
[ "$r" -ge 3 ] && echo "VERDICT S5.D OK: SC-01 worker is crash-looping" || echo "VERDICT S5.D STOP: fewer than 3 restarts"

# --- S5.E [VM vm-095 · bash] (same shell as S5.C) SC-01: Argus diagnoses it on LangGraph -----------------------------
BEFORE=$(ckpt)
argus diagnose vm-166/container:argus-lab-worker --reason "keeps restarting" | tee /tmp/sc01.txt | tail -25
AFTER=$(ckpt); echo "checkpointed investigations: $BEFORE -> $AFTER"
grep -qi 'outcome.*diagnosed' /tmp/sc01.txt && grep -q 'RB-001' /tmp/sc01.txt && [ "$AFTER" -gt "$BEFORE" ] \
  && echo "VERDICT S5.E OK: SC-01 diagnosed (RB-001) on LangGraph, checkpointed in Postgres" || echo "VERDICT S5.E STOP"
rm -f /tmp/sc01.txt; unset ARGUS_PASSWORD
# Expected: DETECT -> RECALL RB-001 -> INVESTIGATE/ACT on vm-166 only -> RECORD: diagnosed (OOM). This one calls the model.

# --- S5.F [VM vm-166 · bash] Remove SC-01, prove non-interference ------------------------------------------------------
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc01 rm -sf argus-lab-worker-oom && cd ~
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after
# Expected: NO INTERFERENCE: non-Argus objects unchanged

# --- S5.G [VM vm-095 · bash] Prove non-interference ---------------------------------------------------------------------
sudo docker ps --filter name=argus- --format '{{.Names}} {{.Status}}'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after
# Expected: every argus-* container Up (argus-v18-agent recently restarted), NO INTERFERENCE.
# >>> Paste everything (no password) into output.bash and tell the agent "output.bash updated". <<<
