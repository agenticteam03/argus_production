# (archived) OP-007 step 01, run 2026-10-07 by the agent over SSH (session 3307114120d3)
# =====================================================================================
# OP-007 step 01 — redeploy the target services on vm-166 with the restarting-owner fix           [~3 min]
# Why: the exporter must keep a dependency probe while its owner is restarting (crash loop on a down dependency).
#      The 4 target services share one image (argus-v18-target:1), so all 4 are recreated (seconds each).
# MUTATES: the checkout on vm-166 + DEPLOYED marker; recreates argus-v18-read-gateway, -host-probe, -network-probe,
#          -exporter. No lab container changes. vm-095 is not touched.
# Undo: sudo bash /opt/argus-v18/app/ops/deploy.sh main --as conantkd, then the same `up -d --build` line.
# Needs: the branch pushed to GitHub (deploy.sh fetches it); lease conantkd, session 3307114120d3.
# =====================================================================================

# --- O.1 [VM vm-166 · bash] (ssh argus-vm166) checkout + rebuild + check the probes (MUTATES) ------------------------
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || echo "NOT YOUR SESSION - stop here"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh task/op-007-restarting-probe-fix --as $ME | tail -3
cd /opt/argus-v18/app/deploy/target && sudo docker compose --env-file vm-166.env -f compose.target.yml -f compose.loopback.yml up -d --build 2>&1 | tail -6; cd ~
sleep 30
sudo docker ps --format '{{.Names}}\t{{.Status}}' | grep -E '^argus-(v18|lab)-' | sort
sudo docker exec argus-v18-exporter grep -c owner_active /app/service.py 2>/dev/null || echo "owner_active not found in image"
for q in 'argus_probe_success{owner="argus-lab-api"}' 'count(argus_probe_success{owner="argus-lab-client"}) or vector(0)'; do
  curl -s --data-urlencode "query=$q" http://127.0.0.1:18090/api/v1/query | python3 -c 'import json,sys; r=json.load(sys.stdin)["data"]["result"]; print(sys.argv[1], "=", r[0]["value"][1] if r else "none")' "$q"
done
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: SESSION OK; "DEPLOY OK: <branch head> (task/op-007-restarting-probe-fix)"; 4 target services Up (seconds),
#           argus-lab-api / -cache untouched; owner_active found (count >= 1); api->cache probe = 1 (healthy owner keeps
#           its probe); client probe count = 0 (SC-07 client absent: no false alarm); ref=task/op-007-...;
#           LAB BASELINE OK; NO INTERFERENCE.
# The restarting case itself is covered by test_exporter_keeps_the_probe_of_an_owner_in_a_restart_loop; a live crash
# loop is not provoked here (it would need breaking argus-lab-cache: a scenario, not a deploy check).
