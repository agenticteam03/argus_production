# =====================================================================================
# STEP DEPLOY-7f137da — X-2: phase 19 (#324, #347) and the reference corpus (#349, #351, #352) on vm-095   [~45 min]
# Run by conantkd's agent over ssh at conantkd's explicit request (not pasted by the developer), both leases
# (session a0224ada). This file records the commands as run, with D.3's folder creation corrected (evidence note 1).
# MUTATES: vm-095 (backup, checkout 7f137da, migration 017, corpus folders, agent/worker/scheduler rebuilt,
#   argus-v18-weaviate and its volume, the corpus installed and indexed, the UI edge rebuilt). vm-166: checkout only.
# ROLLBACK (vm-095, in this order):
#   sudo bash /opt/argus-v18/app/ops/deploy.sh 798b69a --as conantkd
#   cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml \
#     up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler && cd ~
#   sudo docker rm -f argus-v18-weaviate     (the volume argus-v18-weaviate-data may stay: derived from the bundle)
#   cd /opt/argus-v18/app/deploy/ui && sudo docker compose --env-file vm-095.env -f compose.ui.yml -f compose.public.yml \
#     up -d --build && cd ~
#   Migration 017 is additive (a wider CHECK, one column, one grant): 798b69a's code runs on it. The backup of D.2 is
#   the last resort. vm-166: sudo bash /opt/argus-v18/app/ops/deploy.sh bdcd048 --as conantkd
# =====================================================================================

# --- D.1 [VM vm-166 · bash] (ssh argus-vm166) marker and "before" ----------------------------------------------------
echo 'holder=conantkd session=a0224adadcb2' | sudo tee /opt/argus-v18/SESSION >/dev/null
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
  sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E '^(commit|ref)=|LAB BASELINE'
  echo "VERDICT: D.1 PASS"
else
  echo "VERDICT: D.1 STOP: NOT YOUR SESSION"
fi

# --- D.2 [VM vm-095 · bash] (ssh argus-vm095) marker, "before", backup, checkout 7f137da, migration 017 ---------------
echo 'holder=conantkd session=a0224adadcb2' | sudo tee /opt/argus-v18/SESSION >/dev/null
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
  sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as conantkd </dev/null | tail -1
  sudo bash /opt/argus-v18/app/ops/db-backup.sh verify latest --as conantkd </dev/null | tail -1
  sudo bash /opt/argus-v18/app/ops/deploy.sh 7f137da --as conantkd </dev/null 2>&1 | tail -1
  sudo bash /opt/argus-v18/app/ops/db-migrate.sh </dev/null 2>&1 | tail -3
fi

# --- D.3 [VM vm-095 · bash] corpus folders (owned by the image's argus, 10010), images, Weaviate ---------------------
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  sudo mkdir -p /opt/argus-v18/corpus /opt/argus-v18/corpus-staging
  sudo chown 10010:10010 /opt/argus-v18/corpus /opt/argus-v18/corpus-staging
  sudo chmod 0750 /opt/argus-v18/corpus /opt/argus-v18/corpus-staging
  cd /opt/argus-v18/app/deploy/vm-095
  sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps \
    argus-v18-agent argus-v18-worker argus-v18-scheduler argus-v18-weaviate </dev/null 2>&1 | grep -E "Created|Started|rror"
  cd ~
  sudo docker exec argus-v18-agent argus db check </dev/null 2>&1 | tail -1
fi

# --- D.4 [VM vm-095 · bash] install the bundle (hashes verified) and index it from the worker -------------------------
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  S=/opt/argus-v18/corpus-staging
  sudo test -d $S/base || sudo tar xzf /tmp/argus-corpus-base.tgz -C $S --no-same-owner
  sudo chown -R 10010:10010 $S/base && sudo chmod -R u=rwX,g=rX,o= $S/base
  sudo docker exec argus-v18-agent argus corpus import /corpus-staging/base --dest /corpus </dev/null 2>&1 | tail -1
  sudo docker exec argus-v18-worker argus corpus search "container exited restart" --k 2 </dev/null | head -2
  sudo docker exec argus-v18-worker argus corpus index </dev/null 2>&1 | tail -1
fi

# --- D.5 [VM vm-095 · bash] the UI edge (ACR-0032's X-Argus-Ops in proxy.conf and locations.conf) --------------------
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  cd /opt/argus-v18/app/deploy/ui
  sudo docker compose --env-file vm-095.env -f compose.ui.yml -f compose.public.yml up -d --build </dev/null 2>&1 | tail -2
  cd ~
  sudo docker exec argus-v18-ui nginx -t 2>&1 | tail -1
fi

# --- D.6 [VM vm-166 · bash] checkout only (no target, lab or monitoring change for this host) -------------------------
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  sudo bash /opt/argus-v18/app/ops/deploy.sh 7f137da --as conantkd </dev/null 2>&1 | tail -1
fi

# --- D.7 [both VMs · bash] checks (vm-166: write-gate-check.sh --host-only) -------------------------------------------
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1             # expected: NO INTERFERENCE
