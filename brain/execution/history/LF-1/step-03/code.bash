#!/usr/bin/env bash
# STEP LF-1.04 — Fresh baseline under the user-authorized shared lease [VM vm-095]
# READ-ONLY. Expected: deployed status explained, LAB BASELINE OK, /healthz 200, NO INTERFERENCE.
set -euo pipefail
grep -q 'holder=conantkd session=dc432c3ff537' /opt/argus-v18/SESSION
sudo -n bash /opt/argus-v18/app/ops/deploy.sh status </dev/null
free -m
df -m /opt/argus-v18
vmstat 1 5 </dev/null
for name in argus-v18-agent argus-v18-worker argus-v18-scheduler argus-v18-postgres argus-v18-ui; do
 sudo -n docker inspect -f '{{.Name}} restarts={{.RestartCount}} status={{.State.Status}} oom={{.State.OOMKilled}}' "$name" </dev/null
done
for i in $(seq 1 10); do
 curl --max-time 5 -s -o /dev/null -w 'argus_healthz=%{http_code} latency_s=%{time_total}\n' http://127.0.0.1:18000/healthz </dev/null
 sleep 1
done
sudo -n bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -n 2
echo 'LF-1 SHARED BASELINE COMPLETE'