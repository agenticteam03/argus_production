# (archived) E2E-2 step 02, run 2026-10-10 by the agent over SSH (D.1, D.2) and conantkd on the laptop (B.1); both leases, session 2a68b62c2aee
# =====================================================================================
# E2E-2 step 02 — both VMs to main (#65-#71); rebuild vm-095's agent; re-run SC-05 and SC-07 ×5   [~75 min]
# Why: main changed host.disk_usage (every declared mount, an unreadable one reported) and container.status
#   (declared networks), and declares SC-07's networks in config/inventory.yaml. Those live in the agent image on
#   vm-095. Nothing changed in vm-166's services or the monitoring; no migration (ebbe9c9..main: argus/, config/,
#   ops/write-gate-check.sh only).
# Lease: BOTH (an agent rebuild on vm-095), session 2a68b62c2aee.
# Who runs what: D.1 and D.2 the agent over SSH; B.1 conantkd (the shared password), in its own PowerShell window.
# =====================================================================================

# --- D.1 [vm-166 · agent] checkout main (no rebuild: nothing there changed) ----------------------------------------
# MUTATES: SESSION; the git checkout + DEPLOYED marker. ROLLBACK: sudo bash /opt/argus-v18/app/ops/deploy.sh ebbe9c9 --as conantkd
echo 'holder=conantkd session=2a68b62c2aee' | sudo tee /opt/argus-v18/SESSION >/dev/null
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh main --as conantkd | tail -4
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
findmnt /srv/argus-lab-fill >/dev/null && echo "lab filesystem mounted" || echo "lab filesystem NOT mounted"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expect: ref=main, LAB BASELINE OK, lab filesystem mounted, NO INTERFERENCE.

# --- D.2 [vm-095 · agent] backup, checkout main, rebuild agent/worker/scheduler -------------------------------------
# MUTATES: SESSION; one backup file; the checkout; recreates argus-v18-agent/worker/scheduler (an interrupted run
#   resumes from its checkpoint, T-0014). ROLLBACK: deploy.sh ebbe9c9 --as conantkd, then the same compose command.
echo 'holder=conantkd session=2a68b62c2aee' | sudo tee /opt/argus-v18/SESSION >/dev/null
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as conantkd | tail -2
sudo bash /opt/argus-v18/app/ops/deploy.sh main --as conantkd | tail -4
cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml \
  up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E 'Started|Recreated|Error' | tail -4; cd ~
sleep 20
sudo docker exec argus-v18-agent argus db check </dev/null | tail -1
curl -s http://127.0.0.1:18000/healthz; echo
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c $(sudo docker inspect -f '{{.State.Status}} restarts={{.RestartCount}}' $c)"; done
sudo docker exec argus-v18-agent python -c "from argus.capabilities.catalog import DiskArgs; print('disk default mount:', DiskArgs().mount)"
sudo docker exec argus-v18-agent python -c "from argus.adapters.outbound.config_adapters import YamlInventory; from argus.domain.model import TargetRef; import os; inv = YamlInventory(open(os.path.join(os.getenv('ARGUS_CONFIG_DIR', 'config'), 'inventory.yaml')).read()); print('declared networks:', [inv.target(TargetRef.parse('vm-166/container:argus-lab-' + n)).networks for n in ('client', 'backend')])"
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expect: BACKUP OK; ref=main; 3 containers running, restarts 0; db check all passed; healthz ok (new policy/
#   inventory versions); disk default mount: None; 2 declared networks; WRITE GATE CLOSED; LAB BASELINE OK; NO INTERFERENCE.

# --- B.1 [LAPTOP · PowerShell, its own window · conantkd] the batch (~65 min: SC-05 ~11 min/run, SC-07 ~2 min/run) --
python brain\tools\brain.py renew --vm both --minutes 150
.venv\Scripts\python.exe ops\e2e\run.py --as conantkd --runs 5 --out ..\e2e-results\e2e2-batch.jsonl SC-05 SC-07
# Expect: SC-05 5/5 and SC-07 5/5 (before E2E-2: 6/10 each); 0 errors; NO INTERFERENCE after every run.
