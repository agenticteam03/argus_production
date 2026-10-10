# =====================================================================================
# T-0022 step 06 — pulled alerts end to end: SC-03 on vm-166, SC-02 on vm-095 (2026-10-09, conantkd, session
# 21a9ce710773). Run by the agent over SSH. Incidents are read from the store inside the worker (no password).
# MUTATES: the lab only (cache stopped then started; argus-lab-worker created then removed); incident rows.
# =====================================================================================

# --- S.1 [VM vm-166 · bash] SC-03: stop the cache, wait for the alert ---------------------------------------------------
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo docker stop argus-lab-cache
# poll http://127.0.0.1:18091/api/v2/alerts?active=true until something fires (every 10 s, max 4 min)

# --- S.2 [VM vm-095 · bash] the incident the scheduler opens from the pulled alert -----------------------------------
# inside argus-v18-worker: make_store(Settings()).list_incidents(10) until an alert-triggered incident on
#   vm-166/container:argus-lab-api is closed or escalated (every 15 s, max 7 min); then the scheduler log lines
sudo docker logs --since 6m argus-v18-scheduler 2>&1 | grep "reconcile firing" | tail -4

# --- S.3 [VM vm-166 · bash] reset ---------------------------------------------------------------------------------------
sudo docker start argus-lab-cache
# poll until no alert is active; then
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep "LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1

# --- S.4 [VM vm-095 · bash] SC-02 on vm-095: the same path for a vm-095 alert -------------------------------------------
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc02 up -d argus-lab-worker-crash; cd ~
# inside argus-v18-worker: wait for an alert-triggered incident on vm-095/container:argus-lab-worker, closed
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc02 rm -sf argus-lab-worker-crash; cd ~
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep "LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# then the next scheduler pass: no new incident
