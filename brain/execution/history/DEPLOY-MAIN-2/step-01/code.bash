# DEPLOY-MAIN-2 — both VMs from the proof branches to `main` ebbe9c9 (2026-10-10, conantkd, session 4ef1e84354ce).
# Run by the agent over SSH. Why: #48, #54, #55, #59, #60, #62, #42, #51 merged; main contains everything the proof
# branches ran (checked line by line) and no new migration (004, 005 already applied on vm-095).
# M.1 [vm-166, then vm-095] session marker, nonint before, (vm-095) backup, deploy.sh main -> rebuild hints.
# MUTATES: SESSION; the git checkout + DEPLOYED marker; vm-095: one backup file. Nothing is restarted.
# ROLLBACK: sudo bash /opt/argus-v18/app/ops/deploy.sh task/T-0029-vm-proof (vm-166) | task/T-0030-vm-proof (vm-095).
echo 'holder=conantkd session=4ef1e84354ce' | sudo tee /opt/argus-v18/SESSION >/dev/null
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
[ "$(hostname)" = argus-vm095 ] && sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as conantkd | tail -2
sudo bash /opt/argus-v18/app/ops/deploy.sh main --as conantkd
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'

# M.2 [vm-166, then vm-095] rebuild what deploy.sh listed. MUTATES: recreates argus-v18-* containers (target services,
# monitoring, and on vm-095 agent/worker/scheduler); an interrupted run resumes from its checkpoint (T-0014).
# ROLLBACK: deploy.sh <proof branch> as in M.1, then the same compose commands.
# EXPECT: containers up, Prometheus rules include HttpGatewayErrors + ArgusScrapeTargetDown, (vm-095) db check all
# passed, healthz ok, LAB BASELINE OK, NO INTERFERENCE.
H=$(hostname | sed 's/argus-//'); H=vm-${H#vm}; OV=$([ "$H" = vm-095 ] && echo compose.core-join.yml || echo compose.loopback.yml)
echo "== $H ($OV)"
if [ "$H" = vm-095 ]; then
  cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml \
    up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E 'Started|Recreated|Error' | tail -4
fi
cd /opt/argus-v18/app/deploy/target && sudo docker compose --env-file $H.env -f compose.target.yml -f $OV up -d --build </dev/null 2>&1 | grep -E 'Started|Recreated|Error' | tail -8
cd /opt/argus-v18/app/deploy/monitoring && sudo docker compose --env-file $H.env -f compose.monitoring.yml -f $OV up -d </dev/null 2>&1 | grep -E 'Started|Recreated|Error' | tail -6
sudo docker compose --env-file $H.env -f compose.monitoring.yml -f $OV up -d --force-recreate --no-deps argus-v18-prometheus </dev/null 2>&1 | tail -1; cd ~
sleep 30
sudo docker ps --format '{{.Names}} {{.Status}}' | grep -E '^argus-v18-' | sort
P=$(sudo docker port argus-v18-prometheus 9090 2>/dev/null | head -1)
[ -n "$P" ] && curl -s "http://$P/api/v1/rules" | grep -oE '"name":"(HttpGatewayErrors|ArgusScrapeTargetDown|ContainerCpuThrottled)"' | sort -u
if [ "$H" = vm-095 ]; then
  sudo docker exec argus-v18-agent argus db check </dev/null | tail -1
  curl -s http://127.0.0.1:18000/healthz; echo
  for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c restarts=$(sudo docker inspect -f '{{.RestartCount}}' $c)"; done
fi
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E 'LAB BASELINE|lab:' | tail -3
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
