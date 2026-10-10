# =====================================================================================
# T-0032 step 02 — Prometheus down on vm-095: a partition of that host only (phase 13)              [~15 min]
# Why: the plan's phase 13 asks "partition => escalation for one host only". With vm-095's Prometheus stopped, a
#   check of a vm-095 target must end UNDIAGNOSABLE (no model call; unknown is never healthy) and a check of a
#   vm-166 target, read through vm-166's Prometheus over the tunnel, must still be HEALTHY.
# Lease: vm-095 only (Prometheus is vm-095 monitoring, not the agent; vm-166 is only read).
# MUTATES: stops then starts argus-v18-prometheus on vm-095 (its TSDB is the named volume argus-v18-prometheus:
#   nothing is lost, the metrics get a gap of a few minutes). Nothing else.
# ROLLBACK (always, also after any failure): sudo docker start argus-v18-prometheus
# Outage window: P.1 -> P.4, about 5 minutes. Alertmanager resolves an alert it stops hearing about after 5 min,
#   so P.0 records the active alerts first: with none active, nothing can be wrongly resolved.
# Who runs what: P.0, P.1, P.3, P.4 the agent over SSH; P.2 and P.5 conantkd (the shared password).
# =====================================================================================

# --- P.0 [vm-095 · agent] state probe (READ-ONLY) -------------------------------------------------------------------
echo 'holder=conantkd session=ecee514c2421' | sudo tee /opt/argus-v18/SESSION >/dev/null   # first block of the session
grep -q '^holder=conantkd ' /opt/argus-v18/SESSION && echo "session marker: mine" || echo "NOT YOUR SESSION - stop"
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo docker inspect -f '{{.Name}} {{.State.Status}} started={{.State.StartedAt}} restarts={{.RestartCount}}' \
  argus-v18-prometheus argus-v18-agent argus-v18-worker argus-v18-scheduler
sudo docker exec argus-v18-alertmanager wget -qO- 'http://localhost:9093/api/v2/alerts?active=true' | grep -o '"alertname":"[^"]*"' | sort | uniq -c
echo "active alerts listed above (none expected)"
# Expect: session mine, ref=main, LAB BASELINE OK, prometheus running, no active alert.

# --- P.1 [vm-095 · agent] stop Prometheus (MUTATES) ------------------------------------------------------------------
sudo docker stop argus-v18-prometheus
date -u +"stopped at %H:%M:%SZ"; sudo docker inspect -f '{{.State.Status}}' argus-v18-prometheus
# Expect: exited.

# --- P.2 [vm-095 · conantkd] the two checks (READ-ONLY; no model call) -----------------------------------------------
read -rsp "Shared Argus password: " ARGUS_PASSWORD; echo; export ARGUS_PASSWORD
ARGUS="sudo --preserve-env=ARGUS_PASSWORD docker exec -i -e ARGUS_USER=conantkd -e ARGUS_PASSWORD argus-v18-agent argus"
$ARGUS diagnose vm-095/container:argus-lab-api --check --reason "T-0032 Prometheus down on vm-095" --no-color < /dev/null | grep -E '^incident|outcome|metrics|prometheus'
$ARGUS diagnose vm-166/container:argus-lab-api --check --reason "T-0032 vm-166 while vm-095's Prometheus is down" --no-color < /dev/null | grep -E '^incident|outcome'
# Keep this shell open for P.5. Expect: vm-095 -> UNDIAGNOSABLE (metrics unavailable: prometheus ... ConnectError);
#   vm-166 -> HEALTHY.

# --- P.3 [vm-095 · agent] what the services did during the outage (READ-ONLY) ---------------------------------------
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c restarts=$(sudo docker inspect -f '{{.RestartCount}}' $c) status=$(sudo docker inspect -f '{{.State.Status}}' $c)"; done
sudo docker logs --since 10m argus-v18-worker 2>&1 | grep -iE 'error|traceback|failed' | tail -5
sudo docker logs --since 10m argus-v18-scheduler 2>&1 | grep -iE 'error|traceback|failed' | tail -5
curl -s http://127.0.0.1:18000/healthz; echo
# Expect: restarts unchanged (0), all running; no traceback; healthz ok.

# --- P.4 [vm-095 · agent] start Prometheus again (MUTATES; the rollback) --------------------------------------------
sudo docker start argus-v18-prometheus
for i in $(seq 1 12); do sudo docker exec argus-v18-prometheus wget -qO- http://localhost:9090/-/ready >/dev/null 2>&1 && break; sleep 5; done
date -u +"ready at %H:%M:%SZ"; sleep 45                                    # one scrape interval for fresh samples
sudo docker exec argus-v18-prometheus wget -qO- 'http://localhost:9090/api/v1/query?query=count(up==0)' | grep -oE '"result":\[[^]]*\]'
sudo docker exec argus-v18-prometheus wget -qO- 'http://localhost:9090/api/v1/query?query=up{job="argus-v18-exporter"}' | grep -oE '"value":\[[^]]*\]'
sudo docker exec argus-v18-alertmanager wget -qO- 'http://localhost:9093/api/v2/alerts?active=true' | grep -o '"alertname":"[^"]*"' | sort | uniq -c
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E 'LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expect: ready; count(up==0) empty; the exporter's up = 1; no active alert; LAB BASELINE OK; NO INTERFERENCE.

# --- P.5 [vm-095 · conantkd] the vm-095 check again (same shell as P.2) ---------------------------------------------
$ARGUS diagnose vm-095/container:argus-lab-api --check --reason "T-0032 after Prometheus is back" --no-color < /dev/null | grep -E '^incident|outcome'
unset ARGUS_PASSWORD
# Expect: HEALTHY.
