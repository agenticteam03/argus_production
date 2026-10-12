# (archived) T-0033 step 02, run 2026-10-12 by juanbetancurm; both leases, session 351b0fdf7301
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
# 2026-10-12, juanbetancurm. Both leases, session 351b0fdf7301 (until 19:17 UTC). main 244453b, CI all green.
# Part 1, deploy: 45dda69 → 244453b. Changed: OP-012 (graph_runner), T-0033 (dispatch, wiring), EVAL-3 (baseline) =
#   the agent image on vm-095; ops/rotate-token.sh = the checkout on vm-166. No target service code changed.
# Part 2, T-0033 step 2: rotate vm-166's host_probe token; the same report before / after the rotation / after the
#   agent's copy is replaced, with the worker NOT restarted. The report reads host.memory/host.cpu through vm-166's
#   probe (evidence pack, no model call).
# Order: M.1 → D.1 (vm-166) → D.2 (vm-095) → T.1 (vm-095) → T.2 (vm-166) → T.3 (vm-095) → T.4 (laptop) → T.5 (vm-095)
#   → R.1. Two ssh windows help: one on vm-095 (D.2, T.1, T.3, T.5), one on vm-166 (D.1, T.2).
# =====================================================================================

# --- M.1 [LAPTOP · PowerShell] the session marker on both VMs ---------------------------------------------------------
ssh argus-vm166 'echo holder=juanbetancurm session=351b0fdf7301 | sudo tee /opt/argus-v18/SESSION >/dev/null; cat /opt/argus-v18/SESSION'
ssh argus-vm095 'echo holder=juanbetancurm session=351b0fdf7301 | sudo tee /opt/argus-v18/SESSION >/dev/null; cat /opt/argus-v18/SESSION'
# Expected: twice  holder=juanbetancurm session=351b0fdf7301

# --- D.1 [VM vm-166 · bash] (ssh argus-vm166) checkout main only (MUTATES the checkout; no service rebuilt) -----------
grep -q "^holder=juanbetancurm " /opt/argus-v18/SESSION && echo "SESSION OK" || echo "NOT YOUR SESSION - STOP"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh main --as juanbetancurm | tail -1
ls -l /opt/argus-v18/app/ops/rotate-token.sh
sudo stat -c '%a %U:%G %n' /opt/argus-v18/secrets/host_probe_token
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: SESSION OK; NO INTERFERENCE; DEPLOY OK 244453b (main); the script exists; the token's mode and owner
#   (note them); commit=244453b... ref=main; LAB BASELINE OK; NO INTERFERENCE. Keep this window open.

# --- D.2 [VM vm-095 · bash] (ssh argus-vm095) backup, checkout main, agent/worker/scheduler together (MUTATES) --------
# ROLLBACK: deploy.sh 45dda69 --as juanbetancurm, then the same compose command.
grep -q "^holder=juanbetancurm " /opt/argus-v18/SESSION && echo "SESSION OK" || echo "NOT YOUR SESSION - STOP"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as juanbetancurm | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh main --as juanbetancurm | tail -1
cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler 2>&1 | grep -E "Recreated|Started" | tr '\n' ' '; echo; cd ~
for i in $(seq 1 24); do c=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18000/healthz); [ "$c" = 200 ] && break; sleep 5; done; echo "health $c"
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c image=$(sudo docker inspect -f '{{.Image}}' $c | cut -c8-19) $(sudo docker inspect -f '{{.State.Status}} restarts={{.RestartCount}} started={{.State.StartedAt}}' $c)"; done
sudo docker exec argus-v18-agent argus db check </dev/null | tail -1
sudo docker run --rm --network argus-v18-core -v /opt/argus-v18/secrets/agent:/s:ro -v /opt/argus-v18/app/ops/phase3_check.py:/c.py:ro python:3.12-alpine python /c.py | grep -E "checks passed|FAIL"
sudo docker exec argus-v18-worker python -c "import inspect; from argus.tooling.dispatch import Dispatcher; from argus.orchestration.graph_runner import GraphRunner; print('token reload:', 'reload' in inspect.signature(Dispatcher).parameters, '| incident counters:', 'evidence' in inspect.signature(GraphRunner._ctx).parameters)"
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: SESSION OK; NO INTERFERENCE; BACKUP OK; DEPLOY OK 244453b; 3 recreated; health 200; ONE image, running,
#   restarts=0 (note the worker's started= time); 20/20; 55/55 checks passed; "token reload: True | incident counters:
#   True"; WRITE GATE CLOSED; commit=244453b... ref=main; LAB BASELINE OK; NO INTERFERENCE. Keep this window open.

# --- T.1 [VM vm-095 · bash, same window] report #1: before the rotation (READ-ONLY; no model call) ---------------------
read -rsp "Shared Argus password: " ARGUS_PASSWORD; echo; export ARGUS_PASSWORD
ARGUS="sudo --preserve-env=ARGUS_PASSWORD docker exec -i -e ARGUS_USER=juanbetancurm -e ARGUS_PASSWORD argus-v18-agent argus"
$ARGUS diagnose vm-166/host:vm-166 --reason "T-0033 before the rotation" --no-color < /dev/null | grep -E '^incident|get_host|outcome'
# Expected: incident inc_...; get_host_memory and get_host_cpu ✓ (through vm-166's probe); outcome escalated
#   (unsupported: the evidence pack, no diagnosis). If a class matched instead (a full disk), paste it and STOP.

# --- T.2 [VM vm-166 · bash, the other window] rotate the host_probe token (MUTATES; the token is never printed) ------
sudo sh /opt/argus-v18/app/ops/rotate-token.sh host_probe --as juanbetancurm
sudo stat -c '%a %U:%G %n' /opt/argus-v18/secrets/host_probe_token /opt/argus-v18/secrets/host_probe_token.prev
sudo docker ps --format '{{.Names}} {{.Status}}' | grep argus-v18-host-probe
# Expected: "TOKEN ROTATE host_probe on vm-166 by juanbetancurm: argus-v18-host-probe recreated; sha256 ..."; the token
#   with the SAME mode/owner as in D.1, .prev mode 400; the probe Up a few seconds.
# ROLLBACK (only if needed): sudo sh /opt/argus-v18/app/ops/rotate-token.sh host_probe --rollback --as juanbetancurm

# --- T.3 [VM vm-095 · bash] report #2: the agent still holds the OLD token (READ-ONLY) -------------------------------
$ARGUS diagnose vm-166/host:vm-166 --reason "T-0033 after the rotation, old copy" --no-color < /dev/null | grep -E '^incident|get_host|forbidden|outcome'
sudo docker inspect -f 'worker restarts={{.RestartCount}} started={{.State.StartedAt}}' argus-v18-worker
# Expected: get_host_memory / get_host_cpu ✗ error with "forbidden" (HTTP 401); outcome escalated (no crash);
#   the worker's restarts and started= UNCHANGED since D.2.

# --- T.4 [LAPTOP · PowerShell] the agent's copy of the new token (never displayed) -----------------------------------
ssh argus-vm166 'sudo cat /opt/argus-v18/secrets/host_probe_token' | ssh argus-vm095 'sudo tee /opt/argus-v18/secrets/agent/vm-166/host_probe_token.new >/dev/null'
ssh argus-vm166 'sudo cat /opt/argus-v18/secrets/host_probe_token | tr -d [:space:] | sha256sum | cut -c1-12'
ssh argus-vm095 'sudo cat /opt/argus-v18/secrets/agent/vm-166/host_probe_token.new | tr -d [:space:] | sha256sum | cut -c1-12'
# Expected: no output from the first line; the two 12-character hashes EQUAL and not e3b0c44298fc (empty).
#   (First version: `sudo tr ... < file` opened the file without sudo: Permission denied; fixed while running.)

# --- T.5 [VM vm-095 · bash] put the copy in place (same owner and mode), then report #3 (no worker restart) ---------
f=/opt/argus-v18/secrets/agent/vm-166/host_probe_token
sudo cp -p $f $f.prev && sudo chown --reference=$f $f.new && sudo chmod --reference=$f $f.new && sudo mv $f.new $f
sudo stat -c '%a %u:%g %n' $f $f.prev
$ARGUS diagnose vm-166/host:vm-166 --reason "T-0033 after the new copy" --no-color < /dev/null | grep -E '^incident|get_host|forbidden|outcome'
sudo docker inspect -f 'worker restarts={{.RestartCount}} started={{.State.StartedAt}}' argus-v18-worker
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
unset ARGUS_PASSWORD
# Expected: both files with the same mode and owner as before; get_host_memory and get_host_cpu ✓ AGAIN; outcome
#   escalated (as report #1); worker restarts and started= STILL UNCHANGED (picked up without a restart); NO INTERFERENCE.
# Then in the vm-166 window: sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1   (NO INTERFERENCE)

# --- R.1 [LAPTOP · PowerShell] release both leases ----------------------------------------------------------------------
git stash push brain/execution/current/code.bash
python brain\tools\brain.py release --vm both
git stash pop
# VERDICT: paste M.1 to R.1, say "output updated". Never paste the password.
