# =====================================================================================
# T-0022 step 04 — vm-166: Argus-owned Alertmanager, node-exporter, cAdvisor; tunnel permitopen 18091  [~5 min]
# Why: phase 7 on the target host. Prometheus starts sending its alerts to its own Alertmanager (bound to
#      127.0.0.1:18091, read later through the tunnel) and scrapes host and container metrics.
# MUTATES (vm-166 only):
#   - checkout task/T-0022-alerting (it contains T-0020: the same target code that runs now);
#   - 3 new containers argus-v18-alertmanager/-node-exporter/-cadvisor (images already present), volume
#     argus-v18-alertmanager; argus-v18-prometheus recreated (new config; its data volume is kept);
#   - the tunnel account's authorized_keys: one more permitopen="127.0.0.1:18091" (a backup is kept).
# Undo (U.1 below): remove the 3 containers and the volume, restore authorized_keys from the backup, checkout
#      task/T-0020-sc04-pg-connections and recreate Prometheus.
# Lease: conantkd (session d77b4b79ab5a).
# =====================================================================================

# --- M.1 [VM vm-166 · bash] (ssh argus-vm166) -------------------------------------------------------------------------
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh task/T-0022-alerting --as $ME | tail -3
K=/var/lib/argus-v18-tunnel/.ssh/authorized_keys
sudo test -f $K.pre-T0022 || sudo cp -p $K $K.pre-T0022
sudo grep -q 'permitopen="127.0.0.1:18091"' $K || sudo sed -i 's#permitopen="127.0.0.1:18090"#permitopen="127.0.0.1:18090",permitopen="127.0.0.1:18091"#' $K
echo "permitopen now: $(sudo grep -oE 'permitopen="[^"]+"' $K | sort | tr '\n' ' ')"
cd /opt/argus-v18/app/deploy/monitoring && sudo docker compose --env-file vm-166.env -f compose.monitoring.yml -f compose.loopback.yml up -d 2>&1 | tail -5
sudo docker compose --env-file vm-166.env -f compose.monitoring.yml -f compose.loopback.yml up -d --force-recreate --no-deps argus-v18-prometheus 2>&1 | tail -2; cd ~
# Expected: SESSION OK; NO INTERFERENCE (before); DEPLOY OK; permitopen 18090 18091 18701-18704; 3 containers created,
#           Prometheus recreated.

# --- M.2 [VM vm-166 · bash] verify (wait ~60 s after M.1: first scrapes and rule evaluations) -------------------------
q() { curl -s --get http://127.0.0.1:18090/api/v1/query --data-urlencode "query=$1" | python3 -c 'import json,sys
r=json.load(sys.stdin)["data"]["result"]
print(" ".join(x["metric"].get("job", x["metric"].get("argus_host", "")) + "=" + x["value"][1][:6] for x in r) or "none")'; }   # no f-string: Python 3.10 on the VMs
sudo docker ps --format '{{.Names}} {{.Status}}' | grep -E 'argus-v18-(alertmanager|node-exporter|cadvisor|prometheus)'
echo "up: $(q 'up{job=~"argus-v18-.*"}')"
echo "root fs size: $(q 'node_filesystem_size_bytes{mountpoint="/"}')"
echo "host_disk_used_ratio: $(q '1 - node_filesystem_avail_bytes{argus_host="vm-166",mountpoint="/"} / node_filesystem_size_bytes{argus_host="vm-166",mountpoint="/"}')"
echo "cadvisor lab-api cpu periods: $(q 'count(container_cpu_cfs_periods_total{name="argus-lab-api"})')"
echo "alertmanagers seen by prometheus: $(curl -s http://127.0.0.1:18090/api/v1/alertmanagers | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["data"]["activeAlertmanagers"]))')"
echo "alertmanager: $(curl -s http://127.0.0.1:18091/api/v2/status | python3 -c 'import json,sys; print(json.load(sys.stdin)["cluster"]["status"])') · firing now: $(curl -s 'http://127.0.0.1:18091/api/v2/alerts?active=true' | python3 -c 'import json,sys; print([a["labels"]["alertname"] for a in json.load(sys.stdin)])')"
sudo docker stats --no-stream --format '{{.Name}} {{.MemUsage}} {{.CPUPerc}}' | grep -E 'argus-v18-(alertmanager|node-exporter|cadvisor|prometheus)'
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: 4 containers Up; every argus-v18-* job up=1; the root filesystem has a size; disk ratio ~0.28;
#           cadvisor sees argus-lab-api; 1 alertmanager; alertmanager "disabled" (no cluster) and [] firing (lab
#           baseline healthy); small memory; ref=task/T-0022-alerting; LAB BASELINE OK; nonint: the ONLY difference is
#           the new listener tcp 127.0.0.1:18091 (Argus's own Alertmanager; expected).
# VERDICT: all as expected -> OK · any job down, no root filesystem, or any other nonint difference -> STOP.

# --- U.1 [VM vm-166 · bash] UNDO (only if needed) ------------------------------------------------------------------------
# sudo docker rm -f argus-v18-alertmanager argus-v18-node-exporter argus-v18-cadvisor && sudo docker volume rm argus-v18-alertmanager
# K=/var/lib/argus-v18-tunnel/.ssh/authorized_keys; sudo cp -p $K.pre-T0022 $K
# sudo bash /opt/argus-v18/app/ops/deploy.sh task/T-0020-sc04-pg-connections --as conantkd
# cd /opt/argus-v18/app/deploy/monitoring && sudo docker compose --env-file vm-166.env -f compose.monitoring.yml -f compose.loopback.yml up -d --force-recreate --no-deps argus-v18-prometheus
