# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
#
# Every block says WHERE to run it:
#   [LAPTOP · PowerShell]   a PowerShell window on your laptop
#   [VM vm-095 · bash]      ssh argus-vm095
#   [VM vm-166 · bash]      ssh argus-vm166
# Paste what the terminal printed into brain/execution/current/output.bash (gitignored, never committed)
# and tell the agent "output.bash updated".
# =====================================================================================

# =====================================================================================
# 2026-10-13, conantkd. T-0035 step 3 — verify the monitoring heartbeat as T-0032 did (juanbetancurm's note 3 of
#   #108): a queued application incident of vm-166 stays open while vm-166's monitoring is lost.   [~40 min]
# State before: both VMs on task/T-0035-monitoring-heartbeat 239e1d6, the check on, both hosts `alive` (step 2).
# Lease: both (renew first: python brain\tools\brain.py renew --vm both --minutes 90).
# MUTATES (on purpose, all restored at the end): vm-095's worker stopped (so the incident stays queued); vm-166's
#   argus-lab-cache stopped (the application alert), its Prometheus stopped ~6 min, then its Alertmanager ~6 min.
# ROLLBACK at any point: on vm-166  sudo docker start argus-v18-prometheus argus-v18-alertmanager argus-lab-cache ;
#   on vm-095  sudo docker start argus-v18-worker .
# Order: P (probe, reused) → C.1 → C.2 → C.3 → C.4 → C.5 → C.6 → C.7.
# =====================================================================================

# --- P [VM vm-095 · bash] the probe (read-only; run it whenever a block says "P") ------------------------------------
sudo docker exec argus-v18-worker python -c "
from argus.infrastructure.wiring import Settings, make_store
s = make_store(Settings())
for h in ('vm-095', 'vm-166'):
    st = s.monitoring_state(h) or {}
    print(h, 'state=%s fresh_ticks=%s last_beat=%s episode=%s incident=%s' % (st.get('state'), st.get('fresh_ticks'),
          (st.get('last_beat_at') or '')[11:19], (st.get('episode_start') or '')[11:19], st.get('incident_id')))
incs = s.list_incidents(40)
for i in [i for i in incs if i.trigger_id.startswith('monitoring:')][:4]:
    print('monitoring', i.id, i.target, i.status, i.outcome, i.incident_class, '|', (i.diagnosis or '')[:170])
    n = [x for x in s.notifications(200) if x['key'] == i.id + ':escalation'] if hasattr(s, 'notifications') else []
    print('   notified:', bool(n), (n[0]['payload'].get('route') if n else None))
app = [i for i in incs if i.trigger_id.startswith('alert:') and i.target.host == 'vm-166' and 'Heartbeat' not in i.reason]
if app:
    a = app[0]
    print('app', a.id, a.target, a.status, a.outcome, a.opened_at.strftime('%H:%M:%S'),
          [(o['alertname'], o['status']) for o in s.alert_occurrences(a.id)])
" 2>&1 || echo "(worker stopped: run P with  argus-v18-scheduler  instead of  argus-v18-worker)"
sudo docker logs --since 3m argus-v18-scheduler 2>&1 | grep -E "reconcile firing alerts:|monitoring of" | tail -3 | cut -c12-220

# --- C.1 [VM vm-095 · bash] stop the worker (incidents stay queued) ----------------------------------------------------
grep -q "^holder=conantkd " /opt/argus-v18/SESSION && echo "SESSION OK" || exit 1
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo docker stop argus-v18-worker </dev/null; date -u +%T
# Expected: SESSION OK; baseline saved; argus-v18-worker; the time.

# --- C.2 [VM vm-166 · bash] the application alert: stop the lab cache ---------------------------------------------------
grep -q "^holder=conantkd " /opt/argus-v18/SESSION && echo "SESSION OK" || exit 1
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo docker stop argus-lab-cache </dev/null; date -u +%T
# Then wait ~3 min (alert `for: 1m` + one reconcile tick) and run P on vm-095 (with argus-v18-scheduler).
# Expected P: both `alive`; `app inc_… vm-166/container:argus-lab-api queued None … [('DependencyProbeFailed', 'firing'), …]`.

# --- C.3 [VM vm-166 · bash] stop vm-166's Prometheus (T-0032) ------------------------------------------------------------
sudo docker stop argus-v18-prometheus </dev/null; date -u +%T
# Run P every minute for 6 minutes. Expected:
#   - first: scheduler log `'resolve': 'heartbeat not fresh'` for vm-166 once its renewal is older than 180 s;
#   - within ~4 min of the stop: `vm-166 state=lost … incident=inc_…` and ONE line
#     `monitoring inc_… vm-166/host:vm-166 escalated undiagnosable monitoring_blind_spot | Host monitoring unavailable on
#     vm-166 …: heartbeat lost …; Prometheus not reachable from Argus …` and `notified: True channel:operators`;
#   - the app incident still `queued` with its occurrences `firing` (the alerts expired at their endsAt: not resolved);
#   - vm-095 `alive` throughout.

# --- C.4 [VM vm-166 · bash] Prometheus back ------------------------------------------------------------------------------
sudo docker start argus-v18-prometheus </dev/null; date -u +%T
# Run P every minute for 4 minutes. Expected: vm-166 back to `alive` after two fresh ticks (audit monitoring.recovered);
#   still ONE monitoring incident; the app incident still queued (the cache is still stopped).

# --- C.5 [VM vm-166 · bash] the lab cache back --------------------------------------------------------------------------
sudo docker start argus-lab-cache </dev/null; date -u +%T
# Wait ~3 min, run P. Expected: the app incident's occurrences `resolved` and the incident `closed resolved_externally`
#   (every alert resolved while queued: T-0026), now that the monitoring is alive.

# --- C.6 [VM vm-166 · bash] the second episode: stop vm-166's Alertmanager -------------------------------------------------
sudo docker stop argus-v18-alertmanager </dev/null; date -u +%T
# Run P every minute for 6 minutes. Expected: a SECOND monitoring incident for vm-166 (a new episode), cause
#   `monitoring cannot be read: check the host's Alertmanager and the transport`; vm-095 `alive`. Note how long the
#   scheduler's read of vm-166 takes to fail through the tunnel (its 8 s timeout, the reconcile log time stamps).
sudo docker start argus-v18-alertmanager </dev/null; date -u +%T
# Run P after 3 minutes. Expected: vm-166 `alive` again.

# --- C.7 [VM vm-095 · bash] the worker back, then the baselines on both VMs ----------------------------------------------
sudo docker start argus-v18-worker </dev/null
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# and on vm-166:
#   sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
#   sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: worker running; LAB BASELINE OK and NO INTERFERENCE on both.
# VERDICT: paste P after C.2, C.3 (the last), C.4, C.5, C.6 and C.7 into output.bash, say "output.bash updated".
