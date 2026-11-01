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
# STEP DEPLOY-88fe002.1 — Session marker and state probe on both VMs                      [~1 min]
# Goal / Why: the VM state, not the Brain, decides the deploy (deployed commit, lab, containers, protected objects,
#   write gate). An earlier run of this probe wrote a session id that was never claimed; this one writes the real one.
# MUTATES: /opt/argus-v18/SESSION marker only.   Undo: brain.py release at session end.
# Expected: vm-095 at a60e3f9, vm-166 at bcccb5f; NO INTERFERENCE and WRITE GATE AS RELEASED on both.
# =====================================================================================

# --- 1.1 [VM vm-095 · bash] (ssh argus-vm095) ---
echo 'holder=conantkd session=31b8915f8336' | sudo tee /opt/argus-v18/SESSION >/dev/null
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh | tail -1
echo 'DEPLOY-88fe002 VM095 PROBE DONE'

# --- 1.2 [VM vm-166 · bash] (ssh argus-vm166) ---
echo 'holder=conantkd session=31b8915f8336' | sudo tee /opt/argus-v18/SESSION >/dev/null
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh --host-only | tail -1
echo 'DEPLOY-88fe002 VM166 PROBE DONE'

# =====================================================================================
# STEP DEPLOY-88fe002.2 — Deploy main 88fe002 with the operator console on              [~12 min]
# Goal / Why: put #399-#420 on the VMs (the operator console ACR-0043, its migrations 020-021, the approval that wakes
#   a paused run #419, the console audit fixes #416, UI motion #420). Luis chose to deploy with main-guard red
#   (#390-#398 in redemption PR #400; #419 to be recorded) and to turn the console on.
# MUTATES: vm-166 /opt/argus-v18/app checkout only (no service changed since bcccb5f).
#          vm-095: a verified database backup; the checkout; migrations 020 and 021 (two new tables, additive);
#          ARGUS_OPERATOR_CONSOLE=1 in /opt/argus-v18/hosts.env and deploy/ui/vm-095.env (copies kept as *.pre-88fe002);
#          rebuilds argus-v18-agent, argus-v18-worker, argus-v18-scheduler and argus-v18-ui.
# Undo vm-095: put back the two env copies; deploy.sh a60e3f911a104e2293f1e863b0f60a0af25e3a6c --as conantkd; rebuild the
#          same four services with the same compose commands. Migrations 020-021 stay (a60e3f9 never reads them).
# Undo vm-166: deploy.sh bcccb5f2c4b08be99a837aea5995807a404d2eb7 --as conantkd
# Expected: DEPLOY OK on both; "+ 020_console_command applied", "+ 021_console_analysis applied"; containers recreated;
#           nginx syntax ok; ARGUS_OPERATOR_CONSOLE=1 in the agent; WRITE GATE AS RELEASED; NO INTERFERENCE on both.
# If it fails: stop at the failing line, read that service's recent logs, run the undo while both leases are held.
# =====================================================================================

# --- 2.1 [VM vm-166 · bash] (ssh argus-vm166) checkout only ---
grep -q '^holder=conantkd session=31b8915f8336$' /opt/argus-v18/SESSION || { echo 'NOT YOUR SESSION'; exit 1; }
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh 88fe002230238f1b637d12c87168f9d3f66a2022 --as conantkd </dev/null 2>&1 | tail -1
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh --host-only | tail -1
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
echo 'DEPLOY-88fe002 VM166 DEPLOY DONE'

# --- 2.2 [VM vm-095 · bash] (ssh argus-vm095) backup, checkout, migrations, console flag, rebuilds ---
grep -q '^holder=conantkd session=31b8915f8336$' /opt/argus-v18/SESSION || { echo 'NOT YOUR SESSION'; exit 1; }
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as conantkd </dev/null 2>&1 | tail -1
sudo bash /opt/argus-v18/app/ops/db-backup.sh verify latest --as conantkd </dev/null 2>&1 | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh 88fe002230238f1b637d12c87168f9d3f66a2022 --as conantkd </dev/null 2>&1 | tail -1
sudo bash /opt/argus-v18/app/ops/db-migrate.sh </dev/null | grep -E '\+ |REFUSED|schema:'
for f in /opt/argus-v18/hosts.env /opt/argus-v18/app/deploy/ui/vm-095.env; do
  sudo test -f "$f.pre-88fe002" || sudo cp -p "$f" "$f.pre-88fe002"
  sudo grep -q '^ARGUS_OPERATOR_CONSOLE=' "$f" && sudo sed -i 's/^ARGUS_OPERATOR_CONSOLE=.*/ARGUS_OPERATOR_CONSOLE=1/' "$f" \
    || echo 'ARGUS_OPERATOR_CONSOLE=1' | sudo tee -a "$f" >/dev/null
  echo "$f: $(sudo grep -c '^ARGUS_OPERATOR_CONSOLE=1$' "$f") console line"
done
cd /opt/argus-v18/app/deploy/vm-095
sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps \
  argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E 'Started|Running|Error|error' | tail -4
cd /opt/argus-v18/app/deploy/ui
sudo docker compose --env-file vm-095.env -f compose.ui.yml -f compose.public.yml up -d --build </dev/null 2>&1 \
  | grep -E 'Started|Running|Error|error' | tail -2
cd ~
sudo docker exec argus-v18-ui nginx -t 2>&1 | tail -1
echo "agent console flag: $(sudo docker exec argus-v18-agent printenv ARGUS_OPERATOR_CONSOLE)"
sudo docker ps --filter name=argus-v18- --format '{{.Names}} {{.Status}}' | grep -E 'agent|worker|scheduler|ui'
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh | tail -1
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
echo 'DEPLOY-88fe002 VM095 DEPLOY DONE'

# --- 2.3 [VM vm-095 · bash] (ssh argus-vm095) READ-ONLY checks, re-run after 2.2's ssh capture was lost (the script itself ran to its end) ---
grep -q '^holder=conantkd session=31b8915f8336$' /opt/argus-v18/SESSION || { echo 'NOT YOUR SESSION'; exit 1; }
sudo bash /opt/argus-v18/app/ops/db-backup.sh verify latest --as conantkd </dev/null 2>&1 | tail -1
echo "ui console build flag: $(sudo docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' argus-v18-ui | grep -c '^VITE_ARGUS_CONSOLE=1$' || true) (0 expected: a build arg, baked into the bundle)"
echo "ui bundle mentions the console: $(sudo docker exec argus-v18-ui sh -c 'grep -l "ops/console" /usr/share/nginx/html/assets/*.js 2>/dev/null | wc -l')"
sudo docker exec argus-v18-agent python -c "import urllib.request as u; print('agent health:', u.urlopen('http://127.0.0.1:8000/healthz', timeout=5).status)" 2>&1 | tail -1
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler argus-v18-ui; do
  echo "$c errors since start: $(sudo docker logs --since 10m $c 2>&1 | grep -ciE 'traceback|error|exception')"
done
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh | tail -1
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
echo 'DEPLOY-88fe002 VM095 CHECKS DONE'
