set -u
grep -q '^holder=conantkd ' /opt/argus-v18/SESSION || { echo "NOT YOUR SESSION"; exit 1; }
echo "=== E.3 $(date -u +%H:%M:%SZ)"
export GIT_SSH_COMMAND="ssh -i /opt/argus-v18/secrets/deploy/id_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile=/opt/argus-v18/secrets/deploy/known_hosts -o StrictHostKeyChecking=yes -o BatchMode=yes"
G="git -C /opt/argus-v18/app -c safe.directory=/opt/argus-v18/app"
sudo --preserve-env=GIT_SSH_COMMAND $G fetch --quiet origin task/EVAL-2-model-trials || { echo "E.3 STOP: fetch"; exit 1; }
SHA=$(sudo $G rev-parse FETCH_HEAD); echo "eval sha=$SHA"
sudo rm -rf /opt/argus-v18/eval-src && sudo mkdir -p /opt/argus-v18/eval-src
sudo $G archive "$SHA" | sudo tar -x -C /opt/argus-v18/eval-src
sudo docker build -q -t argus-v18-eval:eval2 /opt/argus-v18/eval-src || { echo "E.3 STOP: build"; exit 1; }
echo "app HEAD $(sudo $G rev-parse --short HEAD)"
EV="ARGUS_EVAL_IMAGE=argus-v18-eval:eval2 ARGUS_EVAL_CASES=/opt/argus-v18/eval-src/tests/eval ARGUS_EVAL_CONFIG=/opt/argus-v18/eval-src/config"
sudo env $EV bash /opt/argus-v18/eval-src/ops/eval-run.sh --as conantkd --trials "${TRIALS:-1}" 2>&1 | grep -E ' FAIL |^    - |^cases|runs|^hard|^results'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
echo "=== E.3 end $(date -u +%H:%M:%SZ)"
