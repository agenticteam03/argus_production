# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
# T-0046 L5 step 02 (2026-10-21) — SC-03 and SC-07 once each with link recording on; SC-01 once to see a model
#   strategy's hypotheses (T-0047 H1, log-only). vm-095 at 2324186, vm-166 at bdcd048.                [~30 min]
# MUTATES: vm-166 lab containers only, through the reviewed catalogue (ops/e2e/scenarios.yaml); each run resets.
# =====================================================================================

# --- S.0 [LAPTOP · PowerShell] both leases; markers on both VMs (holder=conantkd) ------------------------------------
python brain/tools/brain.py --as conantkd start --task T-0046-L5-scenarios --vm both

# --- S.1 [VM vm-166 · bash, by the agent] SC-03's catalogue commands by hand, no investigation (no password) --------
#   nonint-check before on both VMs; pre-gate min(argus_probe_success{owner="argus-lab-api"}) == 1
sudo docker stop argus-lab-cache          # start
#   gate: the same probe == 0 (reached 18:35:27), then the reset at once
sudo docker start argus-lab-cache         # reset
#   nonint-check after on both VMs

# --- S.2 [LAPTOP · PowerShell, conantkd's terminal: asks the Argus password, hidden] ---------------------------------
.venv\Scripts\python.exe ops\e2e\run.py SC-03 SC-07 --runs 1 --as conantkd
.venv\Scripts\python.exe ops\e2e\run.py SC-01 --runs 1 --as conantkd

# --- S.3 [VM vm-095 · bash, read-only] the link rows, each incident's chart link events and its decisions ----------
#   a python script in argus-v18-worker (build(); store._q on link_event and audit; incident_metrics.window), copied
#   to /tmp, run, removed; prints states, times, labels and hypothesis ids / statuses / statement heads, no values

# --- S.4 [LAPTOP · PowerShell] release -------------------------------------------------------------------------------
python brain/tools/brain.py --as conantkd release
