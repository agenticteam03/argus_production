# (archived) AFTER-MERGE T-0018 block, run 2026-10-07 by the agent over SSH (session 3307114120d3)
# =====================================================================================
# AFTER-MERGE (T-0018) — put both VMs back on `main` once the T-0018 pull request is merged          [~3 min]
# Why: both VMs run the checkout of task/T-0018-sc07-network; after the merge `main` holds the same code, so the
#      running images (vm-166 target services, vm-095 agent) already match it: checkout only, NO rebuild.
# MUTATES: the checkout in /opt/argus-v18/app on both VMs + DEPLOYED marker.
# Undo: deploy.sh task/T-0018-sc07-network --as <you>
# Run it only AFTER the merge, inside your own VM lease (brain.py start; session marker = you).
# =====================================================================================

# --- M.1 [VM vm-166 · bash] then [VM vm-095 · bash] (the same lines on each) ----------------------------------------
grep -q "holder=<you> " /opt/argus-v18/SESSION && echo "SESSION OK" || echo "NOT YOUR SESSION"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh main --as <you> | tail -8
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: DEPLOY OK: <main head> (main); its rebuild hints can be ignored (the same code already runs); ref=main;
#           LAB BASELINE OK; NO INTERFERENCE.
