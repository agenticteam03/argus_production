# =====================================================================================
# EVAL-2 — the §21.2 evaluation with the configured model on all 55 cases (T-0025 step 3, again)   [~60 min]
# Why: the model ran x5 on 30 cases (2026-10-09). Since then 25 cases were added (cpu_saturation, nginx, blind spot,
#   dns, disk_pressure with ACR-0007's confirm_then_reason): those classes have never been measured against the
#   baseline (§3 "Enablement").
# Lease: vm-095 only. Nothing of the running agent changes: the evaluation runs in a ONE-OFF container from the
#   current agent image (built on main 2a5f06b in E2E-5 step 2; main 48a895b differs only in Brain files), with only
#   the model key, the cases and the config mounted read-only; no token, no database, not on argus-v18-core.
# MUTATES: only /opt/argus-v18/SESSION (the marker) and a new results file in /opt/argus-v18/eval-results/.
# ROLLBACK: none needed (rm the results file if unwanted).
# Who runs what: all blocks the agent over SSH (no password needed).
# =====================================================================================

# --- E.0 [VM vm-095 · agent] marker and state probe (READ-ONLY apart from the marker) ------------------------------
echo 'holder=conantkd session=2a4990e92fc4' | sudo tee /opt/argus-v18/SESSION >/dev/null
grep -q '^holder=conantkd ' /opt/argus-v18/SESSION && echo "session marker: mine" || echo "NOT YOUR SESSION - stop"
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo git -C /opt/argus-v18/app log --oneline -1
sudo docker ps --format '{{.Names}} {{.Status}}' | grep '^argus-v18-' | sort
sudo docker image inspect -f 'agent image created={{.Created}}' argus-v18-agent:1
ls /opt/argus-v18/app/tests/eval/cases | wc -l
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
# Expect: session mine; ref=main commit=2a5f06b...; LAB BASELINE OK; argus-v18-* Up; 55 cases; NO INTERFERENCE.

# --- E.1 [VM vm-095 · agent] 1 trial per case (55 model runs, ~10 min) ---------------------------------------------
sudo bash /opt/argus-v18/app/ops/eval-run.sh --as conantkd --trials 1 2>&1 | tail -30
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expect: the per-class table, "hard: 0 0 0", a results path; NO INTERFERENCE. Read every FAIL before E.2.

# --- E.2 [VM vm-095 · agent] 5 trials per case (275 model runs, ~45 min) -------------------------------------------
sudo bash /opt/argus-v18/app/ops/eval-run.sh --as conantkd --trials 5 2>&1 | tail -30
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expect: per class mean / worst trial, "hard: 0 0 0"; NO INTERFERENCE.
