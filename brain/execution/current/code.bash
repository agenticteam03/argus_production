# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
#   [LAPTOP · PowerShell]   [VM vm-095 · bash] = ssh argus-vm095   [VM vm-166 · bash] = ssh argus-vm166
# Paste what the terminal printed into brain/execution/current/output.bash (gitignored, never committed)
# and tell the agent "output.bash updated". Every block ends with a VERDICT line.
# =====================================================================================

# =====================================================================================
# T-0013 REVIEW — repeat only SC-01 (diagnosed, RB-001) on LangGraph                              [~10 min]
# Why: the first run (S5.E) ended UNSUPPORTED because Prometheus still showed restarts_10m=2 (the detector needs 3;
#   the metric lags Docker by one scrape, 15 s). This time we wait until Prometheus itself shows >= 3.
# MUTATES: starts the SC-01 lab worker on vm-166, then removes it. This run calls the model (small cost).
# Undo: cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc01 rm -sf argus-lab-worker-oom
# =====================================================================================

# --- R.1 [LAPTOP · PowerShell] Renew the lease (MUTATES the session branch) ----------------------------------------
python brain\tools\brain.py renew --minutes 60
# Expected: "Lease renewed until ...". If it says the lease is not yours: STOP.

# --- R.2 [VM vm-166 · bash] (ssh argus-vm166) Start SC-01 and wait until PROMETHEUS shows >= 3 restarts (MUTATES) -----
grep -q '^holder=conantkd ' /opt/argus-v18/SESSION || { echo "NOT YOUR SESSION"; exit 1; }
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc01 up -d argus-lab-worker-oom && cd ~
Q='max_over_time(argus_container_restart_count{argus_host="vm-166",container="argus-lab-worker"}[10m]) - min_over_time(argus_container_restart_count{argus_host="vm-166",container="argus-lab-worker"}[10m])'
V=0
for i in $(seq 1 36); do
  V=$(curl -s -G http://127.0.0.1:18090/api/v1/query --data-urlencode "query=$Q" \
      | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; print(int(float(r[0]["value"][1])) if r else 0)' 2>/dev/null || echo 0)
  echo "docker restarts=$(sudo docker inspect -f '{{.RestartCount}}' argus-lab-worker 2>/dev/null)  prometheus restarts_10m=$V"
  [ "$V" -ge 3 ] && break; sleep 10
done
[ "$V" -ge 3 ] && echo "VERDICT R.2 OK: Prometheus sees $V restarts (detector threshold is 3)" || echo "VERDICT R.2 STOP: Prometheus still below 3 after 6 min"
# Expected: restarts_10m climbs 0 -> 3 within about 1-3 minutes. If STOP: do R.4 (cleanup) and tell the agent.

# --- R.3 [VM vm-095 · bash] (ssh argus-vm095) Diagnose SC-01 on LangGraph (calls the model) ----------------------------
ckpt() { sudo docker exec argus-v18-postgres psql -U argus_owner -d argus -At -c "SELECT count(DISTINCT thread_id) FROM checkpoints"; }
read -rsp "Shared Argus password: " ARGUS_PASSWORD; echo; export ARGUS_PASSWORD
BEFORE=$(ckpt)
sudo --preserve-env=ARGUS_PASSWORD docker exec -i -e ARGUS_USER=conantkd -e ARGUS_PASSWORD argus-v18-agent \
  argus diagnose vm-166/container:argus-lab-worker --reason "keeps restarting" | tee /tmp/sc01.txt | tail -30
AFTER=$(ckpt); echo "checkpointed investigations: $BEFORE -> $AFTER"
grep -qi 'outcome.*diagnosed' /tmp/sc01.txt && grep -q 'RB-001' /tmp/sc01.txt && [ "$AFTER" -gt "$BEFORE" ] \
  && echo "VERDICT R.3 OK: SC-01 diagnosed (RB-001) on LangGraph, checkpointed in Postgres" || echo "VERDICT R.3 STOP"
rm -f /tmp/sc01.txt; unset ARGUS_PASSWORD
# Expected: class container_restart_loop -> RECALL RB-001 -> reads on vm-166 only -> outcome: diagnosed (OOM).

# --- R.4 [VM vm-166 · bash] Remove SC-01 and prove non-interference ------------------------------------------------------
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc01 rm -sf argus-lab-worker-oom && cd ~
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after
# Expected: NO INTERFERENCE: non-Argus objects unchanged

# --- R.5 [VM vm-095 · bash] Prove non-interference ------------------------------------------------------------------------
sudo docker ps --filter name=argus- --format '{{.Names}} {{.Status}}'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after
# Expected: every argus-* container Up, NO INTERFERENCE.
# >>> Paste everything (no password) into output.bash and tell the agent "output.bash updated". <<<
