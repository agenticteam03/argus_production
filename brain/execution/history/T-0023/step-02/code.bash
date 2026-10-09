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
# (record) S.1-S.4 ran first with d00e867 (see evidence.md); this is the last block that ran.
# T-0023 step 2, second part — SC-01 runs 3 to 5 with the hardened runner  [~45 min, mostly waiting]
# V.1 showed both VMs clean. The runner in the agent's worktree now opens ITS OWN tunnel (local port 18001) and
#   reopens it if it drops; ssh retries a dropped connection. You may close the old S.2 tunnel window (port 18000).
# MUTATES: the lab only (SC-01 starts and removes argus-lab-worker on vm-166). Calls the model 3 times.
# If something you type at the password prompt is echoed, delete it from output.bash before pasting.
# =====================================================================================

# --- S.5 [LAPTOP · PowerShell] renew the lease, then SC-01 × 3 ---------------------------------------------------------
cd C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\argus_production
git stash push brain/execution/current/code.bash
python brain\tools\brain.py renew
git stash pop
$W = '<a checkout of task/T-0023-e2e-runner>'
python $W\ops\e2e\run.py SC-01 --runs 3 --as juanbetancurm --out $HOME\argus-e2e\t0023-step2.jsonl
# Expected: "Lease renewed until ..."; the password prompt; SC-01 run 1/3, 2/3, 3/3 PASS (each up to ~15 min: the
#   pre-gate waits until the last run's restarts leave the 10-minute window); summary SC-01 3 3 0 0; "results: ...".
#   (The run numbers restart at 1: these are the 3rd to 5th SC-01 runs of step 2.)
# If it is still running after ~45 min, renew from another window (cd, stash, renew, stash pop); the runner goes on.
# VERDICT: 3 PASS → step 2 done (the agent records it) · FAIL/ERROR → paste everything · BATCH STOPPED → paste, stop.
