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
# T-0020 step 03 — SC-04 on vm-166: a worker leaks database sessions                                 [~15 min]
# Why: prove Argus detects connection exhaustion from the metric, reads the database's health and names the leaker
#      as the root cause, without proposing to restart the database.
# MUTATES: starts argus-lab-leaker (sc04) for the run, then removes it (its sessions close with it). The lab DB is
#          only filled with idle sessions of the lab app role (16 of 17 usable slots).
# Undo / reset: sudo docker rm -f argus-lab-leaker (S.3). NEVER `compose down`: it would remove the whole lab.
# Lease: conantkd (session 3307114120d3).
# =====================================================================================

# --- S.1 [VM vm-166 · bash] (ssh argus-vm166) start the leaker + readiness gate (MUTATES) ----------------------------
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc04 up -d argus-lab-leaker 2>&1 | tail -2; cd ~
sleep 25; sudo docker logs --tail 2 argus-lab-leaker 2>&1
Q() { curl -s --data-urlencode "query=$1" http://127.0.0.1:18090/api/v1/query | python3 -c 'import json,sys; r=json.load(sys.stdin)["data"]["result"]; print(r[0]["value"][1] if r else "none")'; }
U='min_over_time((argus_db_connections_used{argus_host="vm-166",container="argus-lab-db"} / (argus_db_connections_usable{argus_host="vm-166",container="argus-lab-db"} > 0))[5m:30s])'
A='count(ALERTS{alertname="DbConnectionsExhausted",alertstate="firing",container="argus-lab-db"}) or vector(0)'
for i in $(seq 1 50); do u=$(Q "$U"); a=$(Q "$A"); echo "$(date -u +%H:%M:%S) used=$(Q 'argus_db_connections_used{container="argus-lab-db"}') usage_5m=$u alert_firing=$a"; [ "$a" = 1 ] && python3 -c "import sys; sys.exit(0 if float('$u') >= 0.9 else 1)" 2>/dev/null && break; sleep 15; done
[ "$a" = 1 ] && echo "VERDICT S.1 OK: usage >= 0.9 for 5 min, DbConnectionsExhausted firing" || echo "VERDICT S.1 STOP: gate not reached"
# Expected: "leaker: opened 16 sessions …"; used=16; usage_5m reaches 0.941 after ~5 min; alert_firing=1;
#           VERDICT S.1 OK.

# --- S.2 [VM vm-095 · bash] (ssh argus-vm095) diagnose the database (READ-ONLY; calls the model; asks YOUR password) --
ME=conantkd
read -rsp "Argus password for $ME: " ARGUS_PASSWORD; echo; export ARGUS_PASSWORD
ARGUS="sudo --preserve-env=ARGUS_PASSWORD docker exec -i -e ARGUS_USER=$ME -e ARGUS_PASSWORD argus-v18-agent argus"
$ARGUS diagnose vm-166/container:argus-lab-db --reason "clients cannot get a database connection" --no-color < /dev/null | tee /tmp/sc04-run1.txt | tail -40
grep -qi 'diagnosed' /tmp/sc04-run1.txt && grep -q 'postgresql_connection_exhaustion' /tmp/sc04-run1.txt && grep -q 'argus-lab-leaker' /tmp/sc04-run1.txt && echo "VERDICT S.2 OK: diagnosed, the leaker named" || echo "VERDICT S.2 CHECK: read the diagnosis"
unset ARGUS_PASSWORD
# Expected: DETECT postgresql_connection_exhaustion (94 % of the usable slots for 5 min) → RECALL RB-004 →
#           inspect_database_health on vm-166 (16 idle in transaction from argus-lab-leaker/argus_lab_app) → RECORD
#           DIAGNOSED: root cause the leaker (sessions held idle in transaction), no restart of the database.

# --- S.3 [VM vm-166 · bash] (ssh argus-vm166) reset: remove the leaker; its sessions close (MUTATES) -----------------
sudo docker rm -f argus-lab-leaker
sleep 40
curl -s --data-urlencode 'query=argus_db_connections_used{container="argus-lab-db"}' http://127.0.0.1:18090/api/v1/query | python3 -c 'import json,sys; r=json.load(sys.stdin)["data"]["result"]; print("used after reset =", r[0]["value"][1] if r else "none")'
sudo docker ps -a --format '{{.Names}}' | grep -x argus-lab-leaker || echo "leaker gone"
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E 'LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
echo "T-0020.3 SC-04 DONE"
# Expected: leaker gone; used after reset = 0; LAB BASELINE OK; NO INTERFERENCE; T-0020.3 SC-04 DONE.
