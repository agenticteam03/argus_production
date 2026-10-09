# =====================================================================================
# OP-010 step 02 — SC-04 at 100 % DIAGNOSED from the pulled alert (2026-10-09, conantkd, session 21a9ce710773)
# Both VMs on task/OP-010-reserved-slot 50f33ae (T-0022 step 5). Run by the agent over SSH; no password needed: the
# alert opens the incident (T-0022). MUTATES: the lab only (the leaker) and incident rows.
# =====================================================================================

# --- S.1 [VM vm-166 · bash] the leaker at 100 % and the alert -----------------------------------------------------------
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
cd /opt/argus-v18/app/deploy/lab && sudo SC04_SESSIONS=16 docker compose -f compose.lab.yml --profile sc04 up -d argus-lab-leaker; cd ~
# every 10 s until DbConnectionsExhausted is active in http://127.0.0.1:18091/api/v2/alerts?active=true; every
# minute: argus_db_up, _connections_used, _connections_usable, _monitor_slot_reserved for argus-lab-db

# --- S.2 [VM vm-095 · bash] the incident opened by the scheduler from the alert -----------------------------------------
# inside argus-v18-worker: make_store(Settings()) until an alert-triggered incident on vm-166/container:argus-lab-db is
# closed or escalated; print its outcome, class, root cause, reads and diagnosis
sudo docker logs --since 4m argus-v18-scheduler 2>&1 | grep "reconcile firing" | tail -3

# --- S.3 [VM vm-166 · bash] reset ---------------------------------------------------------------------------------------
sudo docker rm -f argus-lab-leaker
# every 10 s until no alert is active
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep "LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
