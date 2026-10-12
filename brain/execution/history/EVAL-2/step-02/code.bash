# =====================================================================================
# EVAL-2 step 02 — the same evaluation with the fixes of fc09eb6 (ACR-0008, prompt rule, two fixtures)   [~45 min]
# Why: E.1 showed 5 disk_pressure misses; the fixes are on task/EVAL-2-model-trials. The running agent is NOT
#   rebuilt: the branch is exported (git archive) to /opt/argus-v18/eval-src and built as a separate image tag.
# MUTATES: remote-tracking refs of /opt/argus-v18/app (fetch only, the checkout stays 2a5f06b); creates
#   /opt/argus-v18/eval-src and the image argus-v18-eval:eval2; a new results file.
# ROLLBACK: sudo rm -rf /opt/argus-v18/eval-src; sudo docker image rm argus-v18-eval:eval2
# =====================================================================================

# --- E.3 [VM vm-095 · agent] export the branch, build the eval image, 1 trial per case (~10 min) -------------------
grep -q '^holder=conantkd ' /opt/argus-v18/SESSION || { echo "NOT YOUR SESSION"; exit 1; }
export GIT_SSH_COMMAND="ssh -i /opt/argus-v18/secrets/deploy/id_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile=/opt/argus-v18/secrets/deploy/known_hosts -o StrictHostKeyChecking=yes -o BatchMode=yes"
sudo --preserve-env=GIT_SSH_COMMAND git -C /opt/argus-v18/app -c safe.directory=/opt/argus-v18/app fetch --quiet origin task/EVAL-2-model-trials
SHA=$(sudo git -C /opt/argus-v18/app -c safe.directory=/opt/argus-v18/app rev-parse FETCH_HEAD); echo "eval sha=$SHA"
sudo rm -rf /opt/argus-v18/eval-src && sudo mkdir -p /opt/argus-v18/eval-src
sudo git -C /opt/argus-v18/app -c safe.directory=/opt/argus-v18/app archive "$SHA" | sudo tar -x -C /opt/argus-v18/eval-src
sudo docker build -q -t argus-v18-eval:eval2 /opt/argus-v18/eval-src
sudo git -C /opt/argus-v18/app -c safe.directory=/opt/argus-v18/app rev-parse --short HEAD   # still 2a5f06b
EV="ARGUS_EVAL_IMAGE=argus-v18-eval:eval2 ARGUS_EVAL_CASES=/opt/argus-v18/eval-src/tests/eval ARGUS_EVAL_CONFIG=/opt/argus-v18/eval-src/config"
sudo env $EV bash /opt/argus-v18/eval-src/ops/eval-run.sh --as conantkd --trials 1 2>&1 | tail -14
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expect: eval sha=fc09eb6...; image built; HEAD 2a5f06b; per-class table, hard 0 0 0; NO INTERFERENCE.

# --- E.4 [VM vm-095 · agent] 5 trials per case with the fixes (~35 min) ---------------------------------------------
sudo env $EV bash /opt/argus-v18/eval-src/ops/eval-run.sh --as conantkd --trials 5 2>&1 | grep -E ' FAIL |^cases|runs|^hard|^results'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expect: per class mean / worst trial, hard 0 0 0; NO INTERFERENCE.
