# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
# DEMO — run `argus demo` on vm-095 (offline, stdlib only, nothing deployed)
#
#   [LAPTOP · PowerShell]   a PowerShell window on your laptop
#   [VM vm-095 · bash]      ssh argus-vm095
# Paste what the terminal printed into brain/execution/current/output.bash (gitignored, never committed)
# and tell the agent "output.bash updated".
# =====================================================================================

# =====================================================================================
# STEP DEMO.1 — Put the demo files on vm-095, apart from the deployed app            [~1 min]
# Goal / Why: the demo needs 7 small files of branch task/demo-cli-replay. It does NOT go through deploy.sh, so the
#   running agent (/opt/argus-v18/app) keeps its commit and nothing restarts.
# MUTATES: creates /opt/argus-v18/demo (files only) and fetches one branch into the app's Git object store
#   (the working tree is not touched).   Undo: sudo rm -rf /opt/argus-v18/demo
# =====================================================================================

# --- 1.0 [LAPTOP · PowerShell] claim vm-095 (the session lease) ------------------------------------------------
#   python brain/tools/brain.py start --vm vm-095
# Expected: "Lease CLAIMED by conantkd on vm-095 ...". It ends by printing the VM marker command (next block).

# --- 1.0b [VM vm-095 · bash] (ssh argus-vm095) Write the session marker: COPY THE EXACT LINE brain.py printed -----
#   echo 'holder=conantkd session=<id printed by brain.py start>' | sudo tee /opt/argus-v18/SESSION >/dev/null
# MUTATES: the marker file only.   Undo: brain.py release (the marker is overwritten by the next claim)

# --- 1.1 [VM vm-095 · bash] Session marker, Python version, "before" snapshot ----------------------------------
# (no `exit`: in an interactive SSH shell it would close your session)
grep -q "holder=conantkd" /opt/argus-v18/SESSION && echo "SESSION OK" || echo "NOT YOUR SESSION - STOP, do not run the rest"
python3 -c 'import sys; assert sys.version_info >= (3, 12), sys.version' && python3 --version   # expected: Python 3.12+
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before

# --- 1.2 [VM vm-095 · bash] Fetch the branch and extract only the demo files ------------------------------------
APP=/opt/argus-v18/app
sudo git -C "$APP" -c safe.directory="$APP" fetch --quiet origin task/demo-cli-replay
sudo mkdir -p /opt/argus-v18/demo
sudo git -C "$APP" -c safe.directory="$APP" archive FETCH_HEAD \
  argus/__init__.py argus/adapters/__init__.py argus/adapters/inbound/__init__.py \
  argus/adapters/inbound/cli/__init__.py argus/adapters/inbound/cli/render.py argus/adapters/inbound/cli/demo.py \
  contracts/samples/events.json | sudo tar -x -C /opt/argus-v18/demo
ls /opt/argus-v18/demo/argus/adapters/inbound/cli/ /opt/argus-v18/demo/contracts/samples/
# Expected: demo.py render.py __init__.py   and   events.json

# --- 1.3 [VM vm-095 · bash] Prove non-interference and the app is untouched --------------------------------------
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after          # expected: NO INTERFERENCE
sudo git -C "$APP" -c safe.directory="$APP" status --porcelain | wc -l      # expected: 0
echo "DEMO.1 OK"
# >>> Paste everything into output.bash and tell the agent "output.bash updated". <<<

# =====================================================================================
# STEP DEMO.2 — Run the demo in the VM terminal (what the audience sees)             [3 min]
# READ-ONLY: prints to your terminal; no API, no model, no host read, no file written.
# Use a real terminal over SSH (a tty) so the colors and the spinner show; maximize the window, ~110 columns,
# and a dark theme. Rehearse once with --duration 30 before presenting.
# =====================================================================================

# --- 2.1 [VM vm-095 · bash] (ssh -t argus-vm095) Rehearsal, 30 seconds ----------------------------------------------
cd /opt/argus-v18/demo && PYTHONDONTWRITEBYTECODE=1 python3 -m argus.adapters.inbound.cli.demo --duration 30
# Expected: FAILURE DETECTED (red) … AWAITING HUMAN APPROVAL (magenta), pending nodes listed

# --- 2.2 [VM vm-095 · bash] The real demo, 3 minutes ----------------------------------------------------------------
clear; cd /opt/argus-v18/demo && PYTHONDONTWRITEBYTECODE=1 python3 -m argus.adapters.inbound.cli.demo --duration 180
# Expected: the same story over 180 s; Ctrl+C stops it at any time.

# --- 2.3 [LAPTOP · PowerShell] release the VM when you are done -----------------------------------------------------
#   python brain/tools/brain.py release
