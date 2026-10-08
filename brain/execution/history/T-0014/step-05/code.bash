# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
#
# Every block says WHERE to run it:
#   [VM vm-095 · bash]      ssh argus-vm095
#   [LAPTOP · PowerShell]   a PowerShell window on your laptop
# Paste what the terminal printed into brain/execution/current/output.bash (gitignored, never committed)
# and tell the agent "output.bash updated".
# =====================================================================================

# =====================================================================================
# T-0014 step 5c — vm-095: the scheduler, for real  [~15 min, mostly waiting]
# Story: one schedule is enabled TEMPORARILY (every 5 min, a health check of the healthy lab twin
#        vm-095/container:argus-lab-api; a healthy check makes no model call). We prove:
#   C.1 the scheduler submits the slot and the worker runs it (HEALTHY);
#   C.2 with the worker stopped, the next slot waits queued;
#   C.3 a restarted scheduler does NOT submit that slot a second time (identity schedule id + slot);
#   C.4 the following slot finds the target busy: "coalesced" (audit schedule.coalesced), no second run;
#   C.5 the worker comes back and runs the queued check (HEALTHY).
#   C.6 UNDO: the shipped file back (enabled: false), scheduler restarted, worker running, NO INTERFERENCE.
# MUTATES (vm-095 Argus only): deploy/scheduler/schedules.yaml in the VM checkout (restored in C.6), the scheduler
#   restarted 3 times, the worker stopped ~10 min. Lab containers are only READ. vm-166 untouched.
# If anything looks wrong at any point: run C.6 straight away (it also starts the worker).
# =====================================================================================

# --- C.0 [LAPTOP · PowerShell] renew the lease -------------------------------------------------------------------------
cd C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\argus_production
git stash push brain/execution/current/code.bash
python brain\tools\brain.py renew
git stash pop
# Expected: "Lease renewed until ..."

# --- C.1 [VM vm-095 · bash] enable the test schedule, restart the scheduler, the first slot runs (MUTATES) ----------
F=/opt/argus-v18/app/deploy/scheduler/schedules.yaml
Q="sudo docker exec argus-v18-postgres psql -X -At -U argus_owner -d argus -c"
LIST="SELECT id, status, body->>'outcome', body->>'trigger_id', to_char(opened_at, 'HH24:MI:SS') FROM incident WHERE body->>'trigger_id' LIKE 'sched:t14-step5c:%' ORDER BY opened_at"
sudo sed -i -e 's|id: lab-worker-health|id: t14-step5c|' -e 's|cron: "\*/15 \* \* \* \*"|cron: "*/5 * * * *"|' -e 's|vm-166/container:argus-lab-worker|vm-095/container:argus-lab-api|' -e 's|enabled: false|enabled: true|' "$F"
grep -nE '^ *(- id|cron|target|enabled):' "$F"
T1=$(date -u +%Y-%m-%dT%H:%M:%SZ); sudo docker restart argus-v18-scheduler; sleep 10
sudo docker logs --since "$T1" argus-v18-scheduler 2>&1 | grep -E "schedules,|t14-step5c|Error|rror:"
for i in $(seq 1 30); do sudo docker logs --since "$T1" argus-v18-worker 2>&1 | grep -q "running inc_.*argus-lab-api" && break; sleep 2; done; sleep 20
sudo docker logs --since "$T1" argus-v18-worker 2>&1 | grep "running inc_"
$Q "$LIST" < /dev/null
# Expected: the 4 lines show id t14-step5c, cron "*/5 * * * *", target vm-095/container:argus-lab-api, enabled true;
#   "1 schedules, 1 enabled"; "t14-step5c <slot>: submitted inc_..."; the worker "running inc_... on ...argus-lab-api";
#   one row: inc_...|closed|healthy|sched:t14-step5c:<slot>|...
# VERDICT: 1 enabled + submitted + closed/healthy → OK, go on · an error or "0 enabled" → STOP, run C.6

# --- C.2 [VM vm-095 · bash] stop the worker; the next slot waits queued (up to ~5 min) ------------------------------
sudo docker stop argus-v18-worker
T2=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo "worker stopped at $T2; waiting for the next */5 slot ..."
for i in $(seq 1 40); do sudo docker logs --since "$T2" argus-v18-scheduler 2>&1 | grep -q "submitted" && break; sleep 10; done
sudo docker logs --since "$T2" argus-v18-scheduler 2>&1 | grep t14-step5c
$Q "$LIST" < /dev/null
# Expected: "t14-step5c <next slot>: submitted inc_..."; two rows, the new one "queued" (no worker to run it).
# VERDICT: a second row, queued → OK · no "submitted" after 6.5 min → STOP, run C.6

# --- C.3 [VM vm-095 · bash] restart the scheduler: the same slot must NOT be submitted again ------------------------
T3=$(date -u +%Y-%m-%dT%H:%M:%SZ); sudo docker restart argus-v18-scheduler; sleep 20
sudo docker logs --since "$T3" argus-v18-scheduler 2>&1 | grep -E "schedules,|t14-step5c"
$Q "$LIST" < /dev/null
# Expected: "1 schedules, 1 enabled" and NO new "submitted" line; still exactly the same two rows.
# VERDICT: still two rows → OK · a third row for the same slot → STOP, run C.6

# --- C.4 [VM vm-095 · bash] the following slot finds the target busy: coalesced (up to ~5 min) ----------------------
for i in $(seq 1 40); do sudo docker logs --since "$T3" argus-v18-scheduler 2>&1 | grep -q "coalesced" && break; sleep 10; done
sudo docker logs --since "$T3" argus-v18-scheduler 2>&1 | grep t14-step5c
$Q "SELECT incident_id, to_char(at, 'HH24:MI:SS'), body->>'event', body->>'detail' FROM audit WHERE body->>'event' = 'schedule.coalesced' AND at > now() - interval '15 minutes'" < /dev/null
$Q "$LIST" < /dev/null
# Expected: "t14-step5c <slot>: vm-095/container:argus-lab-api is busy (inc_<the queued one>), coalesced";
#   one audit row schedule.coalesced on that queued incident; still two rows (no third run).
# VERDICT: coalesced on the queued incident, still two rows → OK · no "coalesced" after 6.5 min → STOP, run C.6

# --- C.5 [VM vm-095 · bash] start the worker: it runs the queued check -------------------------------------------------
T5=$(date -u +%Y-%m-%dT%H:%M:%SZ); sudo docker start argus-v18-worker
for i in $(seq 1 30); do sudo docker logs --since "$T5" argus-v18-worker 2>&1 | grep -q "running inc_" && break; sleep 2; done; sleep 20
sudo docker logs --since "$T5" argus-v18-worker 2>&1 | grep -E "running inc_|skipped"
$Q "$LIST" < /dev/null
# Expected: "running inc_<the queued one>"; both rows closed|healthy (the queued one waited < 900 s, so not stale).
# VERDICT: both closed/healthy → OK (step 5c done) · anything else → note it, still run C.6

# --- C.6 [VM vm-095 · bash] UNDO: the shipped file back, scheduler restarted, worker running, after-check (always) --
sudo git -c safe.directory=/opt/argus-v18/app -C /opt/argus-v18/app checkout -- deploy/scheduler/schedules.yaml
sudo git -c safe.directory=/opt/argus-v18/app -C /opt/argus-v18/app status --short
T6=$(date -u +%Y-%m-%dT%H:%M:%SZ); sudo docker restart argus-v18-scheduler; sudo docker start argus-v18-worker; sleep 10
sudo docker logs --since "$T6" argus-v18-scheduler 2>&1 | grep "schedules,"
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E 'LAB BASELINE|^argus:'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: git status prints nothing (checkout clean); "1 schedules, 0 enabled"; 3 "argus:" lines running;
#   LAB BASELINE OK; NO INTERFERENCE.
# VERDICT: all of these → vm-095 back as after step 5a · otherwise → STOP, tell the agent
