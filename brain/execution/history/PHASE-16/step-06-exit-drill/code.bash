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
# STEP DEPLOY-6e87828 + PHASE-16 step 6 — migration 016 on vm-095, then the tamper drill   [~40 min]
# Goal / Why: main 6e87828 brings #342 (migration 016: an approval row, or a move to `approved`, needs the judge's
#   stored `agree` on the proposal's digest; a review that cannot start stores a `doubt`; the judge model id is the
#   called model). Phase 18 stays offline: no route, no gateway, `write_gate.open` empty. Then phase 16's exit drill
#   (ACR-0018 step 6): the owner edits one chained audit row; `argus audit verify` and the scheduler's chain check
#   must name it; the edit is undone and the chain verifies again. Both leases (a migration and an agent rebuild).
# MUTATES: vm-095 (a backup, the checkout to 6e87828, migration 016, the agent/worker/scheduler images and containers,
#   a deploy event; in the drill one audit row edited and restored, two scheduler restarts, their security events).
# ROLLBACK: deploy: sudo bash /opt/argus-v18/app/ops/deploy.sh b6e64eb --as conantkd, then the compose command of
#   D.3 (016 stays: the old image never writes an approval). Drill: T.2 removes the one key T.1 added (jsonb keeps no
#   key order, so the body is byte-identical again); the backup of D.2 is the last resort.
# =====================================================================================

# --- D.1 [VM vm-166 · bash] (ssh argus-vm166) marker and "before" (MUTATES: the marker and a snapshot) -------------------
echo 'holder=conantkd session=903b77486495' | sudo tee /opt/argus-v18/SESSION >/dev/null
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
  echo "VERDICT: D.1 PASS"
else
  echo "VERDICT: D.1 STOP: NOT YOUR SESSION"
fi
# Expected: a "before" snapshot line; VERDICT: D.1 PASS.

# --- D.2 [VM vm-095 · bash] (ssh argus-vm095) marker, no running evaluation, backup, checkout, migration 016 (MUTATES) ---
echo 'holder=conantkd session=903b77486495' | sudo tee /opt/argus-v18/SESSION >/dev/null
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
    OUT=$(sudo bash /opt/argus-v18/app/ops/deploy.sh 6e87828 --as conantkd </dev/null 2>&1)
    echo "$OUT" | tail -4
    case "$OUT" in
      *"DEPLOY OK"*)
        MIG=$(sudo bash /opt/argus-v18/app/ops/db-migrate.sh </dev/null 2>&1)
        echo "$MIG" | grep -E "\+ |REFUSED|schema:"
        case "$MIG" in
          *REFUSED*) echo "VERDICT: D.2 STOP: a migration was refused (the image is not rebuilt)" ;;
          *"016_approval_needs_agree"*) echo "VERDICT: D.2 PASS" ;;
          *) echo "VERDICT: D.2 STOP: migration 016 not reported (the image is not rebuilt)" ;;
        esac ;;
      *) echo "VERDICT: D.2 STOP: deploy.sh did not say DEPLOY OK" ;;
    esac
  fi
else
  echo "VERDICT: D.2 STOP: NOT YOUR SESSION"
fi
# Expected: ref=b6e64eb, LAB BASELINE OK; a "before" line; evaluations running: 0; BACKUP OK; VERIFY OK; DEPLOY OK:
#   6e87828...; "+ 016_approval_needs_agree applied" (schema 001-016); VERDICT: D.2 PASS. REFUSED: STOP (rollback above).

# --- D.3 [VM vm-095 · bash] rebuild agent, worker, scheduler; record the deploy (MUTATES) --------------------------------
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  cd /opt/argus-v18/app/deploy/vm-095
  sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps \
    argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E "Recreated|Started|rror"
  cd ~
  for i in $(seq 1 30); do c=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done
  echo "health $c"
  sudo docker exec argus-v18-agent argus deploy record --commit 6e87828 --ref main --as conantkd </dev/null | tail -1
  [ "$c" = 200 ] && echo "VERDICT: D.3 PASS" || echo "VERDICT: D.3 STOP: health $c"
else
  echo "VERDICT: D.3 STOP: NOT YOUR SESSION"
fi
# Expected: agent, worker, scheduler Recreated/Started, no "rror"; health 200; deploy recorded; VERDICT: D.3 PASS.

# --- D.4 [VM vm-095 · bash] verification (READ-ONLY) -----------------------------------------------------------------------
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  for c in argus-v18-agent argus-v18-worker argus-v18-scheduler argus-v18-ui; do echo "$c $(sudo docker inspect -f '{{.State.Status}} restarts={{.RestartCount}}' $c </dev/null)"; done
  sleep 30
  for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do n=$(sudo docker logs --since 10m $c 2>&1 </dev/null | grep -v argus_probe_error | grep -ciE "traceback|error"); echo "$c error lines: $n"; done
  echo "016 trigger: $(sudo docker exec argus-v18-postgres psql -X -q -At -U argus_owner -d argus -c "SELECT count(*) FROM pg_trigger WHERE tgname = 'approval_needs_agree' AND NOT tgisinternal" </dev/null)"
  sudo docker exec argus-v18-agent argus db check </dev/null | grep -E "FAIL|checks passed"
  sudo docker exec argus-v18-agent argus audit verify </dev/null | tail -1
  sudo docker exec argus-v18-agent python -c "from argus.actions.incident import _ACTION_DENIED_HOSTS as d; print('phase 17 live; denied hosts:', sorted(d))" </dev/null
  echo "/me unauthenticated: $(curl -s -o /dev/null -w '%{http_code}' http://localhost:18000/api/v1/me </dev/null) (401)"
  sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E '^(commit|ref)=|LAB BASELINE'
  echo "VERDICT: D.4 DONE (compare with Expected)"
else
  echo "VERDICT: D.4 STOP: NOT YOUR SESSION"
fi
# Expected: four running restarts=0 (the UI untouched); error lines 0; 016 trigger: 1; "91/91 database checks passed";
#   AUDIT CHAIN OK; "phase 17 live; denied hosts: ['vm-095']"; /me 401; ref=6e87828, LAB BASELINE OK.

# --- T.1 [VM vm-095 · bash] tamper drill: the owner edits one chained audit row; verify and the scheduled check name it (MUTATES) ---
# The row: the newest chained `security.audit_chain_verified` event. The edit adds one key, detail.drill = true, with the
# insert-only trigger off for that one statement (an owner can do this; the runtime role cannot). Nothing else changes.
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  PSQL="sudo docker exec -i argus-v18-postgres psql -X -q -At -v ON_ERROR_STOP=1 -U argus_owner -d argus"
  ROW=$($PSQL -c "SELECT audit_id FROM audit WHERE hash IS NOT NULL AND body->>'event' = 'security.audit_chain_verified' ORDER BY seq DESC LIMIT 1" </dev/null)
  echo "drill row: $ROW"
  printf '%s\n' "BEGIN;" "ALTER TABLE audit DISABLE TRIGGER audit_insert_only;" \
    "UPDATE audit SET body = jsonb_set(body, '{detail,drill}', 'true'::jsonb) WHERE audit_id = '$ROW';" \
    "ALTER TABLE audit ENABLE TRIGGER audit_insert_only;" "COMMIT;" | $PSQL
  echo "edited rows: $($PSQL -c "SELECT count(*) FROM audit WHERE body->'detail' ? 'drill'" </dev/null)"
  echo "trigger enabled again: $($PSQL -c "SELECT tgenabled FROM pg_trigger WHERE tgname = 'audit_insert_only'" </dev/null)"
  sudo docker exec argus-v18-agent argus audit verify </dev/null 2>&1 | tail -3
  sudo docker restart argus-v18-scheduler </dev/null >/dev/null
  sleep 45
  sudo docker logs --since 2m argus-v18-scheduler 2>&1 </dev/null | grep -E "AUDIT CHAIN BROKEN|audit chain" | tail -2
  echo "scheduled check: $($PSQL -c "SELECT body->>'event' || ' ' || (body->'detail'->>'problems') || ' ' || (body->'detail'->'first'->>0) FROM audit WHERE body->>'category' = 'security' AND body->>'event' LIKE 'security.audit_chain_%' ORDER BY seq DESC LIMIT 1" </dev/null)"
  echo "VERDICT: T.1 DONE (compare with Expected)"
else
  echo "VERDICT: T.1 STOP: NOT YOUR SESSION"
fi
# Expected: drill row: aud_...; edited rows: 1; trigger enabled again: O; verify: "BROKEN  <that row>: hash does not
#   match its body (the row was edited)" and "AUDIT CHAIN BROKEN: 1 problem(s)"; the scheduler log "AUDIT CHAIN BROKEN";
#   scheduled check: "security.audit_chain_broken 1 <that row>: hash does not match its body ...". Whatever T.1 prints,
#   run T.2 next: it undoes the edit.

# --- T.2 [VM vm-095 · bash] undo the edit; verify and the scheduled check pass again (MUTATES) -----------------------------
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  PSQL="sudo docker exec -i argus-v18-postgres psql -X -q -At -v ON_ERROR_STOP=1 -U argus_owner -d argus"
  printf '%s\n' "BEGIN;" "ALTER TABLE audit DISABLE TRIGGER audit_insert_only;" \
    "UPDATE audit SET body = body #- '{detail,drill}' WHERE body->'detail' ? 'drill';" \
    "ALTER TABLE audit ENABLE TRIGGER audit_insert_only;" "COMMIT;" | $PSQL
  echo "edited rows: $($PSQL -c "SELECT count(*) FROM audit WHERE body->'detail' ? 'drill'" </dev/null)"
  echo "trigger enabled again: $($PSQL -c "SELECT tgenabled FROM pg_trigger WHERE tgname = 'audit_insert_only'" </dev/null)"
  sudo docker exec argus-v18-agent argus audit verify </dev/null 2>&1 | tail -1
  sudo docker restart argus-v18-scheduler </dev/null >/dev/null
  sleep 45
  echo "scheduled check: $($PSQL -c "SELECT body->>'event' || ' ' || (body->'detail'->>'problems') FROM audit WHERE body->>'category' = 'security' AND body->>'event' LIKE 'security.audit_chain_%' ORDER BY seq DESC LIMIT 1" </dev/null)"
  echo "scheduler $(sudo docker inspect -f '{{.State.Status}}' argus-v18-scheduler </dev/null)"
  sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
  echo "VERDICT: T.2 DONE (compare with Expected)"
else
  echo "VERDICT: T.2 STOP: NOT YOUR SESSION"
fi
# Expected: edited rows: 0; trigger enabled again: O; AUDIT CHAIN OK; scheduled check: "security.audit_chain_verified 0";
#   scheduler running; NO INTERFERENCE.

# --- D.5 [VM vm-166 · bash] (ssh argus-vm166) "after" snapshot -------------------------------------------------------------
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
  echo "VERDICT: D.5 DONE"
else
  echo "VERDICT: D.5 STOP: NOT YOUR SESSION"
fi
# Expected: NO INTERFERENCE.
