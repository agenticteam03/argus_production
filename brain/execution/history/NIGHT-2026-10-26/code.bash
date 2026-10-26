# NIGHT-2026-10-26 — the one mutating block of this record (A.1); the others below were read-only queries.
# MUTATES: vm-095's checkout (b6e64eb, #338) and a scheduler restart. ROLLBACK: deploy.sh 16028c7, restart the scheduler.

# --- A.1 [VM vm-095 · bash] apply #338: checkout and scheduler restart (schedules are read at start) ---
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  OUT=$(sudo bash /opt/argus-v18/app/ops/deploy.sh b6e64eb --as conantkd </dev/null 2>&1); echo "$OUT" | tail -3
  case "$OUT" in *"DEPLOY OK"*)
    sudo docker restart argus-v18-scheduler </dev/null >/dev/null
    sleep 12
    echo "scheduler: $(sudo docker inspect -f '{{.State.Status}} restarts={{.RestartCount}}' argus-v18-scheduler </dev/null)"
    sudo docker logs --since 1m argus-v18-scheduler 2>&1 </dev/null | grep -E "audit digest|audit chain check|rror" | tail -4
    echo "audit_digest in the checkout: $(grep -A1 '^audit_digest:' /opt/argus-v18/app/deploy/scheduler/schedules.yaml | grep -o 'enabled: [a-z]*')"
    sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E '^ref=|LAB BASELINE'
    echo "VERDICT: A.1 DONE" ;;
  *) echo "VERDICT: A.1 STOP: deploy.sh did not say DEPLOY OK" ;; esac
fi
