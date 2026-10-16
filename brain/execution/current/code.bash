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
APP=/opt/argus-v18/app; KEYDIR=/opt/argus-v18/secrets/deploy
# same deploy key and pinned known_hosts that ops/deploy.sh uses (root's default SSH has no access to the repo)
GSSH="ssh -i $KEYDIR/id_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile=$KEYDIR/known_hosts -o StrictHostKeyChecking=yes -o BatchMode=yes"
sudo env GIT_SSH_COMMAND="$GSSH" git -C "$APP" -c safe.directory="$APP" fetch --quiet origin task/demo-cli-replay
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

# =====================================================================================
# STEP DEMO.3 — Run SC-01 (OOM restart loop) for real, so the incident is recorded and visible in the UI   [~10 min]
# Goal / Why: a real investigation through the API (evidence + audit), the same failure the demo replays.
# MUTATES (vm-166): starts the lab container argus-lab-worker-oom (profile sc01), then the runner removes it.
#   Creates one incident in the database of vm-095 (kept; that is the point).
#   Undo if the runner dies halfway: [VM vm-166 · bash]
#     cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc01 rm -sf argus-lab-worker-oom
# Needs BOTH leases (the runner touches vm-166 and reads through vm-095).
# =====================================================================================

# --- 3.0 [LAPTOP · PowerShell] claim vm-166 too and write its marker ---------------------------------------------
#   python brain/tools/brain.py start --vm vm-166
#   then on [VM vm-166 · bash] (ssh argus-vm166) paste the exact `echo 'holder=conantkd session=<id>' | sudo tee ...` line it prints
#   (if you only see "ACTIVE" without the line, read the id with:  git show origin/session:session.json )

# --- 3.1 [LAPTOP · PowerShell] Dry run: prints what would be done, touches nothing (READ-ONLY) ------------------
python ops/e2e/run.py SC-01 --runs 1 --as conantkd --dry-run
# Expected: the catalogue commands for SC-01 listed, no ssh executed.

# --- 3.2 [LAPTOP · PowerShell] The real run (asks the Argus password with a hidden prompt; never paste it) -------
python ops/e2e/run.py SC-01 --runs 1 --as conantkd
# Expected: pre-gate clean -> start -> gate (>=3 restarts, up to 5 min) -> investigate -> PASS (diagnosed, container_restart_loop,
#   RB-001) -> reset -> nonint-check "NO INTERFERENCE" on both hosts. One JSON line is written under ~/argus-e2e/.
# Then open the UI (Incidents) and look for the newest incident on vm-166/container:argus-lab-worker.
# >>> Paste the runner's final lines into output.bash and tell the agent "output.bash updated". <<<

# =====================================================================================
# STEP DEMO.4 — The same real run, typed inside the VMs (no laptop runner)          [~10 min]
# Same commands as ops/e2e/scenarios.yaml SC-01 (reviewed catalogue), run by hand. Leases: vm-166 AND vm-095 (3.0).
# MUTATES (vm-166): starts argus-lab-worker-oom; 4.3 removes it.  Creates one incident (kept).
# Undo at any point: block 4.3.
# =====================================================================================

# --- 4.1 [VM vm-166 · bash] (ssh argus-vm166) Marker, "before" snapshot, clean pre-state, start the failure --------
grep -q "holder=conantkd" /opt/argus-v18/SESSION && echo "SESSION OK" || echo "NOT YOUR SESSION - STOP, do not run the rest"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before
sudo docker ps -a --filter name=argus-lab-worker --format '{{.Names}} {{.Status}}'      # expected: nothing listed
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc01 up -d argus-lab-worker-oom
# Expected: "Container argus-lab-worker Started" (name may differ slightly)

# --- 4.2 [VM vm-166 · bash] Wait until the detector can see it: >= 3 restarts in 10 min (max ~5 min) -----------------
for i in $(seq 1 20); do
  v=$(curl -s --data-urlencode 'query=max_over_time(argus_container_restart_count{argus_host="vm-166",container="argus-lab-worker"}[10m]) - min_over_time(argus_container_restart_count{argus_host="vm-166",container="argus-lab-worker"}[10m])' http://127.0.0.1:18090/api/v1/query | python3 -c 'import json,sys; r=json.load(sys.stdin)["data"]["result"]; print(r[0]["value"][1] if r else "none")')
  echo "restarts in 10 min: $v"; case "$v" in none|0|1|2|0.*|1.*|2.*) sleep 15;; *) echo "GATE OK"; break;; esac
done
# Expected: "GATE OK". If it never appears, go to 4.3 and tell the agent.

# --- 4.3 (RUN LAST) [VM vm-166 · bash] Reset and prove non-interference ----------------------------------------------
#   cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc01 rm -sf argus-lab-worker-oom
#   sudo bash /opt/argus-v18/app/ops/nonint-check.sh after          # expected: NO INTERFERENCE

# --- 4.4 [VM vm-095 · bash] (ssh -t argus-vm095) The investigation. Run it ALONE (not pasted with other lines: TROUBLESHOOTING #18).
#   sudo docker exec -it -e ARGUS_USER=conantkd argus-v18-agent argus diagnose vm-166/container:argus-lab-worker --reason "keeps restarting"
# It asks the Argus password with a hidden prompt (never paste it anywhere). Expected: the colored live view ends in
#   "outcome: DIAGNOSED · class container_restart_loop"; the incident id is printed on the first line and the incident
#   appears in the UI. Run 4.3 right after, then paste the output into output.bash.
