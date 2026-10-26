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
# STEP DEPLOY-16028c7 — main 16028c7 on vm-095: migrations 014 and 015, agent, worker, scheduler   [~25 min]
# Goal / Why: since 01db0d7, main brings T-0046 L6 (#322: probe history replayed from a per-link cursor, migration
#   014; `network.link_states` offered to three classes) and phase 18 (#323: the offline supervised action path,
#   migration 015: proposals, judge verdicts, approvals, outbox, actions, holds, outcomes). Phase 18 adds no route, no
#   gateway and no wiring: `write_gate.open` stays empty, nothing can act. No UI, contract or compose change; vm-166
#   does not change. Both leases (a migration and an agent rebuild need both).
# Order: backup, checkout, migrations 014 and 015, then the images (the new scheduler reads link_probe_cursor).
# MUTATES: vm-095 (a backup, the checkout to 16028c7, migrations 014 and 015, the agent/worker/scheduler images and
#   containers, a deploy event).
# ROLLBACK: sudo bash /opt/argus-v18/app/ops/deploy.sh 01db0d7 --as conantkd, then the compose command of D.3; the
#   migrations stay (the old image does not read their tables).
# =====================================================================================

# --- D.1 [VM vm-166 · bash] (ssh argus-vm166) marker and "before" (MUTATES: the marker and a snapshot) -------------------
echo 'holder=conantkd session=13d7ed009aaa' | sudo tee /opt/argus-v18/SESSION >/dev/null
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
  echo "VERDICT: D.1 PASS"
else
  echo "VERDICT: D.1 STOP: NOT YOUR SESSION"
fi
# Expected: a "before" snapshot line; VERDICT: D.1 PASS.

# --- D.2 [VM vm-095 · bash] (ssh argus-vm095) marker, no running evaluation, backup, checkout, migrations (MUTATES) ---
echo 'holder=conantkd session=13d7ed009aaa' | sudo tee /opt/argus-v18/SESSION >/dev/null
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E '^(commit|ref)=|LAB BASELINE'
  sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
  RUNNING=$(pgrep -af 'argus.evaluation|argus evaluate' | grep -v pgrep | wc -l)
  echo "evaluations running: $RUNNING"
  if [ "$RUNNING" -ne 0 ]; then
    echo "VERDICT: D.2 STOP: an evaluation is still running (nothing changed)"
  else
    sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as conantkd </dev/null | tail -1
    sudo bash /opt/argus-v18/app/ops/db-backup.sh verify latest --as conantkd </dev/null | tail -1
    OUT=$(sudo bash /opt/argus-v18/app/ops/deploy.sh 16028c7 --as conantkd </dev/null 2>&1)
    echo "$OUT" | tail -4
    case "$OUT" in
      *"DEPLOY OK"*)
        MIG=$(sudo bash /opt/argus-v18/app/ops/db-migrate.sh </dev/null 2>&1)
        echo "$MIG" | grep -E "\+ |REFUSED|schema:"
        case "$MIG" in
          *REFUSED*) echo "VERDICT: D.2 STOP: a migration was refused (the image is not rebuilt)" ;;
          *"015_remediation"*) echo "VERDICT: D.2 PASS" ;;
          *) echo "VERDICT: D.2 STOP: migration 015 not reported (the image is not rebuilt)" ;;
        esac ;;
      *) echo "VERDICT: D.2 STOP: deploy.sh did not say DEPLOY OK" ;;
    esac
  fi
else
  echo "VERDICT: D.2 STOP: NOT YOUR SESSION"
fi
# Expected: ref=01db0d7, LAB BASELINE OK; a "before" line; evaluations running: 0; BACKUP OK; VERIFY OK; DEPLOY OK:
#   16028c7...; "+ 014_link_probe_cursor applied", "+ 015_remediation applied" (schema 001-015); VERDICT: D.2 PASS.
#   A REFUSED line: STOP (rollback above).

# --- D.3 [VM vm-095 · bash] rebuild agent, worker, scheduler; record the deploy (MUTATES) --------------------------------
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  cd /opt/argus-v18/app/deploy/vm-095
  sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps \
    argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E "Recreated|Started|rror"
  cd ~
  for i in $(seq 1 30); do c=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done
  echo "health $c"
  sudo docker exec argus-v18-agent argus deploy record --commit 16028c7 --ref main --as conantkd </dev/null | tail -1
  [ "$c" = 200 ] && echo "VERDICT: D.3 PASS" || echo "VERDICT: D.3 STOP: health $c"
else
  echo "VERDICT: D.3 STOP: NOT YOUR SESSION"
fi
# Expected: agent, worker, scheduler Recreated/Started, no "rror"; health 200; deploy recorded; VERDICT: D.3 PASS.

# --- D.4 [VM vm-095 · bash] verification (READ-ONLY, except the "after" snapshot) ---------------------------------------------
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  for c in argus-v18-agent argus-v18-worker argus-v18-scheduler argus-v18-ui; do echo "$c $(sudo docker inspect -f '{{.State.Status}} restarts={{.RestartCount}}' $c </dev/null)"; done
  for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do n=$(sudo docker logs --since 10m $c 2>&1 </dev/null | grep -v argus_probe_error | grep -ciE "traceback|error"); echo "$c error lines: $n"; done
  echo "new tables: $(sudo docker exec argus-v18-agent python -c "from argus.infrastructure.wiring import Settings, make_store; q=make_store(Settings())._q; print(q(\"SELECT count(*) FROM information_schema.tables WHERE table_name IN ('link_probe_cursor','action_proposal','judge_verdict','approval','notification_outbox','resume_intent','action','target_hold','action_outcome')\")[0][0])" </dev/null)"
  sleep 75
  echo "link cursors after a tick: $(sudo docker exec argus-v18-agent python -c "from argus.infrastructure.wiring import Settings, make_store; print(make_store(Settings())._q('SELECT count(*) FROM link_probe_cursor')[0][0])" </dev/null)"
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
# Expected: four running restarts=0 (the UI untouched); error lines 0; new tables: 9; link cursors after a tick > 0; "89/89 database checks passed"; the audit chain
#   verified; "phase 17 live; denied hosts: ['vm-095']"; "audit_digest: enabled: false"; /me 401; ref=16028c7,
#   LAB BASELINE OK; NO INTERFERENCE.

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
# MUTATES: the lease file on GitHub. Undo: python brain/tools/brain.py start --task DEPLOY-16028c7 --vm both
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
