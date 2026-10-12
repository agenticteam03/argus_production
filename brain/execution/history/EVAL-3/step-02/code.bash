# (archived) EVAL-3 step 2, run 2026-10-12 by conantkd; both leases, session 66378486227b
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
# 2026-10-12, conantkd. EVAL-3 step 2 — the configured model on the 55 evaluation cases, 5 trials      [~45 min]
# Why: EVAL-3 (#93) relabelled restart-sigkill-01 `no_action_escalated` (RB-008: an exit 137 without an OOM kill is
#      unexplained); EVAL-2's model escalated it 5/5, so it should now pass. Also the first model run on main after
#      OP-012 (#92: max_per_incident under LangGraph; the evaluation replays with the plain runner) and T-0033 (#94).
# What: vm-095 runs main 244453b (deploy.sh status), whose evaluation code, cases and config equal main 817d88f (only
#      Brain files changed after it). So eval-run.sh runs with its defaults: the deployed agent image
#      argus-v18-agent:1 (the worker's image) and the checkout's tests/eval and config. No export, no build.
#      One-off containers: read-only, the model key only, no token, no database, not on argus-v18-core; the running
#      agent is not touched. Compare with EVAL-2 E.4 (5 trials: 0.93, core 0.95, abstention 0.96) and T-0019 batch 2
#      E.8+E.9 (5 trials: 0.92, core 0.95, abstention 1.00).
# MUTATES: one results file in /opt/argus-v18/eval-results/ and its log (kept, as earlier runs).
# Lease: vm-095 (both held, session 66378486227b).
# =====================================================================================

# --- V.1 [VM vm-095 · bash] (ssh argus-vm095) prerequisites (read-only) ----------------------------------------------
grep -q '^holder=conantkd ' /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)='
sudo docker inspect -f '{{.Config.Image}} {{.Image}}' argus-v18-worker | cut -c1-50
grep -A3 '^label:' /opt/argus-v18/app/tests/eval/cases/restart-sigkill-01.yaml
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
# Expected: SESSION OK; commit=244453b... ref=main; argus-v18-agent:1 sha256:8d5bb11aa480...;
#   outcome: no_action_escalated / abstain: true; NO INTERFERENCE.

# --- V.2 [VM vm-095 · bash] the model, 5 trials per case (detached: survives an ssh drop) -----------------------------
L=/opt/argus-v18/eval-results/EVAL-3-step2.log
sudo sh -c "nohup bash /opt/argus-v18/app/ops/eval-run.sh --as conantkd --trials 5 > $L 2>&1 &"
# Then, until the summary appears (about 40 minutes):
sudo tail -18 /opt/argus-v18/eval-results/EVAL-3-step2.log
# Expected: the summary, the per-class table, "hard: 0 0 0"; restart-sigkill-01 passes in every trial.

# --- V.3 [VM vm-095 · bash] after it ------------------------------------------------------------------------------------
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: NO INTERFERENCE. Nothing to clean up (no export, no image).
