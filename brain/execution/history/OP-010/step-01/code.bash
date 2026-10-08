# (archived) OP-010 step 01, run 2026-10-08 by the agent over SSH (go: conantkd)
# =====================================================================================
# OP-010 — vm-166: the db-probe keeps a slot of its own; SC-04 at 100 %                              [~15 min]
# Why: a leak of every ordinary slot must not blind the db-probe (unknown at the worst moment).
# MUTATES (vm-166 only):
#   - checkout task/OP-010-reserved-slot (= T-0022 + OP-010);
#   - target services rebuilt (service.py changed: every argus-v18 target container is recreated, same config);
#   - argus-lab-db recreated with reserved_connections=1 (tmpfs: it starts empty, the init script grants
#     argus_monitor pg_use_reserved_connections);
#   - for the run: argus-lab-leaker with SC04_SESSIONS=16 (every ordinary slot), then removed.
# Undo: deploy.sh task/T-0022-alerting, rebuild the target services, recreate argus-lab-db (same commands).
# Not here: the diagnosis on vm-095 (its agent runs T-0021 without the SC-04 class): with T-0022 step 5.
# Lease: conantkd (session d77b4b79ab5a).

# --- M.1 [VM vm-166 · bash] (ssh argus-vm166) deploy, rebuild the target services, recreate the lab DB ---------------
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh task/OP-010-reserved-slot --as $ME | tail -1
cd /opt/argus-v18/app/deploy/target && sudo docker compose --env-file vm-166.env -f compose.target.yml -f compose.loopback.yml up -d --build 2>&1 | grep -E 'Started|Recreated|Error' | tail -8
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile base-166 up -d --no-deps argus-lab-db 2>&1 | tail -2; cd ~
# Expected: SESSION OK; baseline saved; DEPLOY OK (task/OP-010-reserved-slot); target containers started;
#           argus-lab-db recreated.

# --- M.2 [VM vm-166 · bash] verify the probe's slot (wait ~60 s: the DB init and two scrapes) ------------------------
Q() { curl -s --get http://127.0.0.1:18090/api/v1/query --data-urlencode "query=$1" | python3 -c 'import json,sys
r=json.load(sys.stdin)["data"]["result"]
print(r[0]["value"][1] if r else "none")'; }
sudo docker ps --format '{{.Names}} {{.Status}}' | grep -E 'argus-lab-db|argus-v18-db-probe'
for m in argus_db_up argus_db_connections_usable argus_db_connections_used argus_db_monitor_slot_reserved; do echo "$m=$(Q "$m{container=\"argus-lab-db\"}")"; done
# Expected: both Up (db healthy); argus_db_up=1, usable=16, used=0, monitor_slot_reserved=1.

# --- S.1 [VM vm-166 · bash] SC-04 at 100 %: every ordinary slot taken (MUTATES: starts the leaker) -------------------
cd /opt/argus-v18/app/deploy/lab && sudo SC04_SESSIONS=16 docker compose -f compose.lab.yml --profile sc04 up -d argus-lab-leaker 2>&1 | tail -1; cd ~
sleep 30; sudo docker logs --tail 1 argus-lab-leaker 2>&1
U='min_over_time((argus_db_connections_used{argus_host="vm-166",container="argus-lab-db"} / (argus_db_connections_usable{argus_host="vm-166",container="argus-lab-db"} > 0))[5m:30s])'
for i in $(seq 1 50); do u=$(Q "$U"); a=$(Q 'count(ALERTS{alertname="DbConnectionsExhausted",alertstate="firing"}) or vector(0)'); echo "$(date -u +%H:%M:%S) up=$(Q 'argus_db_up{container="argus-lab-db"}') used=$(Q 'argus_db_connections_used{container="argus-lab-db"}') usage_5m=$u alert=$a"; [ "$a" = 1 ] && [ "$u" = 1 ] && break; sleep 15; done
echo "in vm-166's Alertmanager: $(curl -s 'http://127.0.0.1:18091/api/v2/alerts?active=true' | python3 -c 'import json,sys; print([a["labels"].get("alertname") for a in json.load(sys.stdin)])')"
# Expected: "leaker: opened 16 sessions"; up=1 all along (the probe gets its reserved slot); used=16; usage_5m
#           reaches 1 after ~5 min; alert=1; DbConnectionsExhausted in the Alertmanager (T-0022 path).
# VERDICT: up=1 and usage_5m=1 -> OK (OP-010 fixed) · up=0 or none -> STOP (the probe is still locked out).

# --- S.2 [VM vm-166 · bash] reset: remove the leaker (MUTATES) -------------------------------------------------------
sudo docker rm -f argus-lab-leaker
sleep 40; echo "used after reset=$(Q 'argus_db_connections_used{container="argus-lab-db"}')"
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^ref=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -3
# Expected: used after reset=0; ref=task/OP-010-reserved-slot; LAB BASELINE OK; nonint: the only difference may be
#           the listener 127.0.0.1:18091 if the baseline predates T-0022 step 4 — otherwise NO INTERFERENCE.
