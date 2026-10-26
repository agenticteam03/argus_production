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
# STEP DEPLOY-01db0d7 — main 01db0d7 on vm-095 (agent, worker, scheduler; the UI stays)   [~25 min]
# Goal / Why: since c8d8594, main brings phase 17's action cards and read-only next-action suggestions (#316) with
#   the vm-095 denial (#318); phase 16 step 5's audit digest (5a/5b code, #303/#311) and step 5c's wiring (#314: the
#   scheduler mounts the digest key and the OCI credential from secrets/digest/, its memory 160m -> 256m,
#   ARGUS_AUDIT_DIGEST_SINK from hosts.env); RB-003's wording and evaluation-only code (#300, #319, #329-#333).
#   `audit_digest` stays off (enabled: false). No migration (#322's 014 is not merged), no UI or contract change;
#   vm-166 does not change. Both leases (an agent rebuild needs both).
# Order matters: a bind mount of a missing path makes Docker create a directory there. D.2 checks the key file and the
#   credential folder's config and key.pem before anything changes, and stops otherwise.
# MUTATES: vm-095 (a backup, the checkout to 01db0d7, the agent/worker/scheduler images and containers, a deploy event).
# ROLLBACK: sudo bash /opt/argus-v18/app/ops/deploy.sh c8d8594 --as conantkd, then the compose command of D.3.
# =====================================================================================

# --- D.1 [VM vm-166 · bash] (ssh argus-vm166) marker and "before" (MUTATES: the marker and a snapshot) -------------------
echo 'holder=conantkd session=15ed09dde784' | sudo tee /opt/argus-v18/SESSION >/dev/null
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
  echo "VERDICT: D.1 PASS"
else
  echo "VERDICT: D.1 STOP: NOT YOUR SESSION"
fi
# Expected: a "before" snapshot line; VERDICT: D.1 PASS.

# --- D.2 [VM vm-095 · bash] (ssh argus-vm095) marker, digest files, no running evaluation, backup, checkout (MUTATES) ---
echo 'holder=conantkd session=15ed09dde784' | sudo tee /opt/argus-v18/SESSION >/dev/null
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E '^(commit|ref)=|LAB BASELINE'
  sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
  FILES=0
  for f in audit_digest_ed25519_key oci_digest/config oci_digest/key.pem; do
    if sudo test -f "/opt/argus-v18/secrets/digest/$f"; then echo "digest $f: file"; FILES=$((FILES+1)); else echo "digest $f: MISSING or not a file"; fi
  done
  echo "digest sink in hosts.env: $(sudo grep -c '^ARGUS_AUDIT_DIGEST_SINK=' /opt/argus-v18/hosts.env)"
  RUNNING=$(pgrep -af 'argus.evaluation|argus evaluate' | grep -v pgrep | wc -l)
  echo "evaluations running: $RUNNING"
  if [ "$FILES" -ne 3 ]; then
    echo "VERDICT: D.2 STOP: a digest file is missing (nothing changed)"
  elif [ "$RUNNING" -ne 0 ]; then
    echo "VERDICT: D.2 STOP: an evaluation is still running (nothing changed)"
  else
    sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as conantkd </dev/null | tail -1
    sudo bash /opt/argus-v18/app/ops/db-backup.sh verify latest --as conantkd </dev/null | tail -1
    OUT=$(sudo bash /opt/argus-v18/app/ops/deploy.sh 01db0d7 --as conantkd </dev/null 2>&1)
    echo "$OUT" | tail -4
    case "$OUT" in *"DEPLOY OK"*) echo "VERDICT: D.2 PASS" ;; *) echo "VERDICT: D.2 STOP: deploy.sh did not say DEPLOY OK" ;; esac
  fi
else
  echo "VERDICT: D.2 STOP: NOT YOUR SESSION"
fi
# Expected: ref=c8d8594, LAB BASELINE OK; a "before" line; the three digest files "file" (the key; oci_digest/ is a folder: config, key.pem); the sink line count (0 or 1:
#   either is fine, the job is off); evaluations running: 0; BACKUP OK; VERIFY OK; DEPLOY OK: 01db0d7...; VERDICT: D.2 PASS.

# --- D.3 [VM vm-095 · bash] rebuild agent, worker, scheduler; record the deploy (MUTATES) --------------------------------
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  cd /opt/argus-v18/app/deploy/vm-095
  sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps \
    argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E "Recreated|Started|rror"
  cd ~
  for i in $(seq 1 30); do c=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done
  echo "health $c"
  sudo docker exec argus-v18-agent argus deploy record --commit 01db0d7 --ref main --as conantkd </dev/null | tail -1
  [ "$c" = 200 ] && echo "VERDICT: D.3 PASS" || echo "VERDICT: D.3 STOP: health $c"
else
  echo "VERDICT: D.3 STOP: NOT YOUR SESSION"
fi
# Expected: agent, worker, scheduler Recreated/Started, no "rror"; health 200; deploy recorded; VERDICT: D.3 PASS.

# --- D.4 [VM vm-095 · bash] verification (READ-ONLY, except the "after" snapshot) ---------------------------------------------
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  for c in argus-v18-agent argus-v18-worker argus-v18-scheduler argus-v18-ui; do echo "$c $(sudo docker inspect -f '{{.State.Status}} restarts={{.RestartCount}}' $c </dev/null)"; done
  for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do n=$(sudo docker logs --since 10m $c 2>&1 </dev/null | grep -v argus_probe_error | grep -ciE "traceback|error"); echo "$c error lines: $n"; done
  echo "scheduler memory limit MB: $(( $(sudo docker inspect -f '{{.HostConfig.Memory}}' argus-v18-scheduler </dev/null) / 1048576 ))"
  echo "scheduler digest mounts as files: $(sudo docker exec argus-v18-scheduler sh -c 'n=0; for f in audit_digest_ed25519_key oci_digest/config oci_digest/key.pem; do [ -f /run/argus-secrets/$f ] && n=$((n+1)); done; echo $n' </dev/null)"
  echo "worker sees no digest file: $(sudo docker exec argus-v18-worker sh -c 'ls /run/argus-secrets/ 2>/dev/null | grep -c digest' </dev/null)"
  sudo docker exec argus-v18-agent argus db check </dev/null | grep -E "FAIL|checks passed"
  sudo docker exec argus-v18-agent argus audit verify </dev/null | tail -1
  sudo docker exec argus-v18-agent python -c "from argus.actions.incident import _ACTION_DENIED_HOSTS as d; print('phase 17 live; denied hosts:', sorted(d))" </dev/null
  echo "audit_digest: $(grep -A1 '^audit_digest:' /opt/argus-v18/app/deploy/scheduler/schedules.yaml | grep -o 'enabled: [a-z]*')"
  echo "/me unauthenticated: $(curl -s -o /dev/null -w '%{http_code}' http://localhost:18000/api/v1/me </dev/null) (401)"
  sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E '^(commit|ref)=|LAB BASELINE'
  sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
  echo "VERDICT: D.4 DONE (compare with Expected)"
else
  echo "VERDICT: D.4 STOP: NOT YOUR SESSION"
fi
# Expected: four running restarts=0 (the UI untouched); error lines 0; scheduler memory limit MB: 256; digest mounts
#   as files: 3; worker sees no digest file: 0; "56/56 database checks passed"; the audit chain verified; "phase 17
#   live; denied hosts: ['vm-095']"; "audit_digest: enabled: false"; /me 401; ref=01db0d7, LAB BASELINE OK;
#   NO INTERFERENCE.

# --- D.5 [VM vm-166 · bash] (ssh argus-vm166) "after" snapshot -------------------------------------------------------------
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
  echo "VERDICT: D.5 DONE"
else
  echo "VERDICT: D.5 STOP: NOT YOUR SESSION"
fi
# Expected: NO INTERFERENCE.

# ---------------------------------------------------------------------------------------------------------
# D.6 [LAPTOP · PowerShell] Release both leases (only after D.4 and D.5; tell the agent first if anything stopped)
# MUTATES: the lease file on GitHub. Undo: python brain/tools/brain.py start --task DEPLOY-01db0d7 --vm both
# Expected: "Lease released on vm-095 and vm-166"; VERDICT: D.6 PASS (1 of 1).
# ---------------------------------------------------------------------------------------------------------
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (git rev-parse --show-toplevel)
git rev-parse --show-toplevel
$ok = 0
python brain/tools/brain.py --as conantkd release
if ($LASTEXITCODE -eq 0) { $ok++ }
if ($ok -eq 1) { 'VERDICT: D.6 PASS (1 of 1)' } else { "VERDICT: D.6 FAIL ($ok of 1)" }
# >>> Paste everything into output.bash and tell the agent "output.bash updated". <<<
