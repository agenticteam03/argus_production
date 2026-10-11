# (archived) E2E-3 step 02, run 2026-10-11 by the agent over SSH (A, D.1, D.2) and conantkd on the laptop (B.1); both leases, session 0e96417eb3e8
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
# E2E-3 step 02 — both VMs to main (#75-#77); rebuild vm-166's target services and vm-095's agent; SC-05 + SC-08 x5
#   [~105 min: deploy ~10, batch ~95]
# Why: #75 adds host_mounts to the read-gateway's container inspect (vm-166's target image) and to container.status's
#   text and description (vm-095's agent image). #77 adds SC-08 to the runner catalogue (laptop only). #76 is brain.py
#   only. No migration, no inventory change; vm-095's own target services are not rebuilt (its only declared mount is
#   /, which names nothing, and an older gateway gives today's text).
# Lease: BOTH (an agent rebuild on vm-095), conantkd, session 0e96417eb3e8.
# Who runs what: A, D.1, D.2 the agent over SSH; B.1 conantkd (the shared password), in its own PowerShell window.
# =====================================================================================

# --- A [VM vm-095 and vm-166 · bash] state probe (READ-ONLY, the session's first block on each VM) -----------------
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo docker ps --format '{{.Names}} {{.Status}}' | grep -E '^argus-v18-' | sort
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expect on both: commit=0f076f2... ref=main (E2E-2 step 2); LAB BASELINE OK; argus-v18-* Up; NO INTERFERENCE.

# --- D.1 [VM vm-166 · bash] (ssh argus-vm166) checkout main, rebuild the 4 target services (MUTATES) ---------------
# MUTATES: SESSION; the checkout + DEPLOYED marker; recreates argus-v18-read-gateway, -host-probe, -network-probe,
#   -exporter (one image, a few seconds each). db-probe, Prometheus, Alertmanager and the lab are not touched.
# ROLLBACK: sudo bash /opt/argus-v18/app/ops/deploy.sh 0f076f2 --as conantkd, then the same compose command.
echo 'holder=conantkd session=0e96417eb3e8' | sudo tee /opt/argus-v18/SESSION >/dev/null
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh main --as conantkd | tail -4
cd /opt/argus-v18/app/deploy/target && sudo docker compose --env-file vm-166.env -f compose.target.yml -f compose.loopback.yml \
  up -d --build --no-deps argus-v18-read-gateway argus-v18-host-probe argus-v18-network-probe argus-v18-exporter </dev/null 2>&1 \
  | grep -E 'Started|Recreated|Error' | tail -6; cd ~
sleep 15
sudo docker ps --format '{{.Names}} {{.Status}}' | grep -E '^argus-v18-(read-gateway|host-probe|network-probe|exporter)' | sort
echo "host_mounts in the gateway image: $(sudo docker exec argus-v18-read-gateway grep -c 'def host_mounts' /app/service.py)"
findmnt /srv/argus-lab-fill >/dev/null && echo "lab filesystem mounted" || echo "lab filesystem NOT mounted"
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expect: NO INTERFERENCE (before); DEPLOY OK e3286df (main); 4 services Up; host_mounts in the gateway image: 1;
#   lab filesystem mounted; ref=main, LAB BASELINE OK; NO INTERFERENCE.

# --- D.2 [VM vm-095 · bash] (ssh argus-vm095) backup, checkout main, rebuild agent/worker/scheduler (MUTATES) -------
# MUTATES: SESSION; one backup file; the checkout; recreates argus-v18-agent/worker/scheduler (an interrupted run
#   resumes from its checkpoint, T-0014). ROLLBACK: deploy.sh 0f076f2 --as conantkd, then the same compose command.
echo 'holder=conantkd session=0e96417eb3e8' | sudo tee /opt/argus-v18/SESSION >/dev/null
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as conantkd | tail -2
sudo bash /opt/argus-v18/app/ops/deploy.sh main --as conantkd | tail -4
cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml \
  up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E 'Started|Recreated|Error' | tail -4; cd ~
sleep 20
sudo docker exec argus-v18-agent argus db check </dev/null | tail -1
curl -s http://127.0.0.1:18000/healthz; echo
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c $(sudo docker inspect -f '{{.State.Status}} restarts={{.RestartCount}}' $c)"; done
sudo docker exec argus-v18-worker python -c "from argus.capabilities.catalog import build_catalog; s = next(x for x in build_catalog() if x.name == 'container.status'); print('host mounts in description:', 'filesystems' in s.description, 'disk' in s.use_when)"
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expect: BACKUP OK; DEPLOY OK e3286df (main); 3 containers running, restarts 0; db check all passed; healthz ok;
#   host mounts in description: True True; WRITE GATE CLOSED; LAB BASELINE OK; NO INTERFERENCE.

# --- B.1 [LAPTOP · PowerShell, its own window · conantkd] the batch (~95 min: SC-05 ~11 min/run, SC-08 ~8 min/run) --
python brain\tools\brain.py renew --vm both --minutes 150
.venv\Scripts\python.exe ops\e2e\run.py --as conantkd --runs 5 --out ..\e2e-results\e2e3-batch.jsonl SC-05 SC-08
# Expect: SC-05 5/5 (before E2E-3: 4/5, the miss named the host); SC-08 5/5 (first repeated runs; T-0029 1/1);
#   0 errors; NO INTERFERENCE after every run.
