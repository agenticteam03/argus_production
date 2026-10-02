# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
#
# Every block says WHERE to run it:
#   [LAPTOP · PowerShell]   a PowerShell window on your laptop
#   [VM vm-095 · bash]      ssh argus-vm095
#   [VM vm-166 · bash]      ssh argus-vm166
# Paste what the terminal printed into brain/execution/current/output.bash (gitignored, never committed)
# and tell the agent "output.bash updated". Every block ends with a VERDICT line.
# =====================================================================================

# =====================================================================================
# TASK B6d — Read-only deploy keys on both VMs, then the first `deploy.sh init`   [~20 min + teammate review]
# Why: the VMs must run an exact, known commit of this repository, fetched from GitHub (no laptop copying).
# PART 1 (now): keys on the VMs, registered on GitHub as READ-ONLY deploy keys, access tested. Changes no service.
# PART 2 (after a teammate reviewed and merged the PR that adds ops/deploy.sh): /opt/argus-v18/app becomes a git
#   clone of main. The running containers keep running unchanged; nothing is rebuilt in this task.
# Prerequisite: deploy keys allowed in the organization (Settings -> Member privileges -> Deploy keys).
# =====================================================================================

# --- B6d.1 [LAPTOP · PowerShell] Claim the VM session (MUTATES GitHub: the session branch) --------------------------
cd C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\argus_production
python brain\tools\brain.py start --task B6d
# Expected: "Lease CLAIMED by juanbetancurm until ..." and a "VM marker" line: COPY that echo line, you paste it in
# B6d.2 on BOTH VMs. If it says the VMs are in use by someone else: STOP.

# --- B6d.2 [VM vm-095 · bash] (ssh argus-vm095) Deploy key + pinned GitHub host key (MUTATES /opt/argus-v18 only) --
# Undo: sudo rm -rf /opt/argus-v18/secrets/deploy   (and delete the key on GitHub: see B6d.4)
#   >>> first paste the "VM marker" line printed by B6d.1 <<<
D=/opt/argus-v18/secrets/deploy
sudo install -d -m 700 "$D"
sudo test -f "$D/id_ed25519" || sudo ssh-keygen -q -t ed25519 -N "" -C "argus_production read-only deploy $(hostname)" -f "$D/id_ed25519"
ssh-keyscan -t ed25519 github.com 2>/dev/null | sudo tee "$D/known_hosts" >/dev/null
FP=$(sudo ssh-keygen -lf "$D/known_hosts" | awk '{print $2}'); echo "github.com host key: $FP"
sudo cat "$D/id_ed25519.pub"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after
[ "$FP" = "SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU" ] && sudo test -f "$D/id_ed25519" && grep -q '^holder=juanbetancurm ' /opt/argus-v18/SESSION \
  && echo "VERDICT B6d.2 OK: key ready, GitHub host key verified, session marker yours ($(hostname))" \
  || echo "VERDICT B6d.2 STOP: host key '$FP', or key missing, or SESSION marker not yours"
# Expected: "NO INTERFERENCE" and the VERDICT OK line. The .pub line is public (safe to paste).

# --- B6d.3 [VM vm-166 · bash] (ssh argus-vm166) The same on vm-166 ------------------------------------------------
#   >>> first paste the same "VM marker" line printed by B6d.1 <<<
#   then paste the whole B6d.2 block again (from D=... to the VERDICT line).

# --- B6d.4 [LAPTOP · PowerShell] Register both public keys as READ-ONLY deploy keys (MUTATES GitHub) ---------------
# Undo: gh repo deploy-key list --repo agenticteam03/argus_production  ->  gh repo deploy-key delete <id> --repo ...
foreach ($vm in "argus-vm095", "argus-vm166") {
  $pub = ssh -o BatchMode=yes $vm "sudo cat /opt/argus-v18/secrets/deploy/id_ed25519.pub"
  $f = "$env:TEMP\$vm-deploy.pub"
  Set-Content -Encoding ascii $f $pub
  gh repo deploy-key add $f --repo agenticteam03/argus_production --title "$vm (read-only)"
  Remove-Item $f
}
gh repo deploy-key list --repo agenticteam03/argus_production
$ro = (gh repo deploy-key list --repo agenticteam03/argus_production | Select-String "read-only" | Select-String "argus-vm").Count
if ($ro -eq 2) { "VERDICT B6d.4 OK: 2 read-only deploy keys" } else { "VERDICT B6d.4 STOP: found $ro read-only VM keys (HTTP 422 = deploy keys still disabled in the org)" }

# --- B6d.5 [VM vm-095 · bash] then [VM vm-166 · bash] Test read access with the key (READ-ONLY) -----------------
D=/opt/argus-v18/secrets/deploy
sudo GIT_SSH_COMMAND="ssh -i $D/id_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile=$D/known_hosts -o StrictHostKeyChecking=yes -o BatchMode=yes" \
  git ls-remote git@github.com:agenticteam03/argus_production.git main \
  && echo "VERDICT B6d.5 OK: $(hostname) can read the repository" || echo "VERDICT B6d.5 STOP: $(hostname) cannot read it"
# Expected: one line "<sha>  refs/heads/main" and the VERDICT OK line, on each VM.

# --- B6d.P [LAPTOP · PowerShell] Push this branch, open the PR, ask a teammate to review (MUTATES GitHub) -----------
# You do NOT merge it: conantkd or juanes6554 reviews (brain/agents/REVIEW_PROTOCOL.md), approves and merges.
cd C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\argus_production
git push -u origin task/B6-deploy
$B = "$env:TEMP\argus-pr-deploy.md"
@'
## Why
The VMs must run an exact, known commit of this repository, fetched from GitHub instead of copied from a laptop
(shared-Brain plan, deploy method B). Deploy keys are now allowed in the organization.

## What
- `ops/deploy.sh` (`status`, `init`, `<ref>`): refuses when /opt/argus-v18/SESSION is not yours, when the VM
  checkout has local modifications, or when the ref is unknown; checks out the exact commit (detached), writes
  /opt/argus-v18/DEPLOYED, prints which services to rebuild; never restarts anything. `init` keeps the old folder
  as app.pre-git-<time> for rollback.
- `tests/test_deploy.py`: 6 tests against a throwaway bare repository (red seen first).
- `brain/execution/current/code.bash`: Task B6d (read-only deploy keys on both VMs, pinned GitHub host key, access
  test; after this PR is merged: `deploy.sh init` on both VMs).
- Brain: state, next step, test state, troubleshooting (3 new entries), environment, journal.

## How to review (suggested)
Read `ops/deploy.sh` top to bottom (about 80 lines) and `tests/test_deploy.py`; run `pytest -q tests/test_deploy.py`.
Nothing in this PR changes a running service.

## Tests
53 passed locally, 4 skipped (Postgres needs Docker); CI must be green.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
'@ | Set-Content -Encoding utf8 $B
gh pr create --repo agenticteam03/argus_production --base main --head task/B6-deploy --title "B6d: ops/deploy.sh - the VMs check out an exact commit (deploy keys)" --body-file $B --reviewer conantkd,juanes6554
Remove-Item $B
$N = gh pr view task/B6-deploy --repo agenticteam03/argus_production --json number --jq .number
gh pr checks $N --repo agenticteam03/argus_production --watch --interval 20
if ($LASTEXITCODE -eq 0) { "VERDICT B6d.P OK: PR #$N open, CI green, review requested" } else { "VERDICT B6d.P STOP: CI not green on PR #$N" }
# Then tell your teammates the PR is waiting (they start with: python brain/tools/brain.py start).

# ---------------------------------------------------------------------------------------------------------------------
# PART 2 — only AFTER the PR with ops/deploy.sh is approved by a teammate and merged into main.
# If more than ~60 minutes passed since B6d.1: python brain\tools\brain.py start --task B6d  (and re-paste the marker).
# ---------------------------------------------------------------------------------------------------------------------

# --- B6d.6 [VM vm-095 · bash] then [VM vm-166 · bash] Turn /opt/argus-v18/app into a clone of main (MUTATES files only)
# The old folder is kept as /opt/argus-v18/app.pre-git-<time> (rollback: move it back). Running containers are not
# touched: their mounts keep pointing at the files they started with until they are recreated.
D=/opt/argus-v18/secrets/deploy
sudo rm -rf /tmp/argus-bootstrap
sudo GIT_SSH_COMMAND="ssh -i $D/id_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile=$D/known_hosts -o StrictHostKeyChecking=yes -o BatchMode=yes" \
  git clone -q --depth 1 git@github.com:agenticteam03/argus_production.git /tmp/argus-bootstrap
sudo bash /tmp/argus-bootstrap/ops/deploy.sh init main --as juanbetancurm
sudo rm -rf /tmp/argus-bootstrap
sudo bash /opt/argus-v18/app/ops/deploy.sh status
sudo docker ps --filter name=argus- --format '{{.Names}} {{.Status}}'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after
# Expected: "DEPLOY OK: <commit> (main) on <host>", the status shows commit=... and "local modifications: 0",
# every argus-* container still Up, and "NO INTERFERENCE". (The rebuild hints are for a LATER task: do not run them.)

# --- B6d.7 [LAPTOP · PowerShell] Release the session ---------------------------------------------------------------
python brain\tools\brain.py release
# Expected: "Lease released."
