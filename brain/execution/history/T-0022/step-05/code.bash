# =====================================================================================
# T-0022 step 05 — vm-095: Argus-owned Alertmanager, node-exporter, cAdvisor; tunnel forward 18091; the scheduler
# pulls firing alerts (ACR-0003, restricted-ssh). Also vm-166's checkout aligned to the same ref (no rebuild).
# Ref: task/OP-010-reserved-slot (= T-0022 + OP-010 + main with #41). Lease: conantkd (session 21a9ce710773).
# MUTATES vm-095: 3 new containers (argus-v18-alertmanager/-node-exporter/-cadvisor), Prometheus recreated, the tunnel
#   and agent/worker/scheduler rebuilt. vm-166: the checkout only.
# UNDO vm-095: sudo docker rm -f argus-v18-alertmanager argus-v18-node-exporter argus-v18-cadvisor &&
#   sudo docker volume rm argus-v18-alertmanager; deploy b26effa and rebuild tunnel, agent, Prometheus as below.
# =====================================================================================

# --- A.1 [VM vm-166 · bash] checkout aligned (same code as 4247dc8) ---------------------------------------------------
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh task/OP-010-reserved-slot --as $ME | tail -1
sudo grep -oE 'permitopen="[^"]+"' /var/lib/argus-v18-tunnel/.ssh/authorized_keys | sort | tr '\n' ' '; echo
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: SESSION OK; DEPLOY OK (task/OP-010-reserved-slot); permitopen includes 18090 and 18091; NO INTERFERENCE.

# --- B.1 [VM vm-095 · bash] deploy and rebuild ---------------------------------------------------------------------------
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh task/OP-010-reserved-slot --as $ME | tail -1
cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-tunnel argus-v18-agent argus-v18-worker argus-v18-scheduler 2>&1 | grep -E "Started|Recreated|Error" | tail -6
cd /opt/argus-v18/app/deploy/monitoring && sudo docker compose --env-file vm-095.env -f compose.monitoring.yml -f compose.core-join.yml up -d 2>&1 | grep -E "Created|Started|Error" | tail -6
sudo docker compose --env-file vm-095.env -f compose.monitoring.yml -f compose.core-join.yml up -d --force-recreate --no-deps argus-v18-prometheus 2>&1 | tail -1; cd ~
# Expected: SESSION OK; baseline saved; DEPLOY OK; tunnel, agent, worker, scheduler recreated; 3 monitoring containers
#           created; Prometheus recreated.

# --- B.2 [VM vm-095 · bash] verify (~60 s after B.1) ---------------------------------------------------------------------
sudo docker ps --format '{{.Names}} {{.Status}}' | grep -E 'argus-v18-(tunnel|alertmanager|node-exporter|cadvisor|prometheus|scheduler)'
sudo docker exec argus-v18-agent python -c '
import json, urllib.request, urllib.parse
def get(u): return json.load(urllib.request.urlopen(u, timeout=10))
def q(e):
    r = get("http://argus-v18-prometheus:9090/api/v1/query?" + urllib.parse.urlencode({"query": e}))["data"]["result"]
    return " ".join(x["metric"].get("job", "") + "=" + x["value"][1][:6] for x in r) or "none"
print("vm-095 up:", q("up{job=~\"argus-v18-.*\"}"))
print("vm-095 alertmanagers seen by prometheus:", len(get("http://argus-v18-prometheus:9090/api/v1/alertmanagers")["data"]["activeAlertmanagers"]))
for name, url in (("vm-095", "http://argus-v18-alertmanager:9093"), ("vm-166 via tunnel", "http://argus-v18-tunnel:18091")):
    print(name, "alertmanager:", get(url + "/api/v2/status")["cluster"]["status"], "firing:",
          [a["labels"]["alertname"] for a in get(url + "/api/v2/alerts?active=true")])
'
sudo docker logs --since 3m argus-v18-scheduler 2>&1 | grep -iE "reconcil|alert" | tail -5
sudo docker exec argus-v18-worker python -m argus.tooling.isolation_check 2>&1 | tail -1
sudo docker stats --no-stream --format '{{.Name}} {{.MemUsage}} {{.CPUPerc}}' | grep -E 'argus-v18-(alertmanager|node-exporter|cadvisor|prometheus)'
free -m | awk 'NR==2{print "mem available MiB:", $7}'
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -3
# Expected: every container Up; every argus-v18-* job up=1; 1 alertmanager seen; both Alertmanagers "disabled" (no
#           cluster) with [] firing (lab baseline healthy); scheduler logs a reconciliation pass with 0 new incidents;
#           TOOLS ISOLATION OK; small memory; LAB BASELINE OK; NO INTERFERENCE.
# VERDICT: all as expected -> OK · a job down, the tunnel Alertmanager unreachable, or a nonint difference -> STOP.
