# =====================================================================================
# Argus — T-0046 session state probe (2026-10-25, conantkd)
# Goal / Why: read the live deployment and lab baseline before any T-0046 VM deployment.
# MUTATES: only the two SESSION lease markers and non-interference snapshots; no service,
#   database, configuration, volume or network changes. Undo: release the leases with
#   `brain.py release`; the SESSION marker is replaced on the next lease claim.
# PR #322 is not merged: these blocks are state probes only and do not deploy its code.
# =====================================================================================

# --- T0046.1 [VM vm-095 · bash] (ssh argus-vm095) initialize lease; read deployed state and compare baseline
echo 'holder=conantkd session=ec6ca2a851a7' | sudo tee /opt/argus-v18/SESSION >/dev/null
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  echo 'SESSION OK'
  before=$(sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null 2>&1)
  printf '%s\n' "$before"
  state=$(sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null 2>&1)
  printf '%s\n' "$state"
  after=$(sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null 2>&1)
  printf '%s\n' "$after"
  ok=0
  printf '%s\n' "$state" | grep -q '^commit=' && ok=$((ok + 1))
  printf '%s\n' "$state" | grep -q 'LAB BASELINE OK' && ok=$((ok + 1))
  printf '%s\n' "$after" | grep -q 'NO INTERFERENCE' && ok=$((ok + 1))
  if [ "$ok" -eq 3 ]; then echo 'VERDICT: T0046.1 PASS (3 of 3)'; else echo "VERDICT: T0046.1 FAIL ($ok of 3)"; fi
else
  echo 'VERDICT: T0046.1 FAIL (SESSION marker mismatch)'
fi
# Expected: current DEPLOYED commit/ref, LAB BASELINE OK, NO INTERFERENCE, VERDICT: T0046.1 PASS (3 of 3).

# --- T0046.2 [VM vm-166 · bash] (ssh argus-vm166) initialize lease; read monitoring/lab state and compare baseline
echo 'holder=conantkd session=ec6ca2a851a7' | sudo tee /opt/argus-v18/SESSION >/dev/null
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  echo 'SESSION OK'
  before=$(sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null 2>&1)
  printf '%s\n' "$before"
  state=$(sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null 2>&1)
  printf '%s\n' "$state"
  after=$(sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null 2>&1)
  printf '%s\n' "$after"
  ok=0
  printf '%s\n' "$state" | grep -q '^commit=' && ok=$((ok + 1))
  printf '%s\n' "$state" | grep -q 'LAB BASELINE OK' && ok=$((ok + 1))
  printf '%s\n' "$after" | grep -q 'NO INTERFERENCE' && ok=$((ok + 1))
  if [ "$ok" -eq 3 ]; then echo 'VERDICT: T0046.2 PASS (3 of 3)'; else echo "VERDICT: T0046.2 FAIL ($ok of 3)"; fi
else
  echo 'VERDICT: T0046.2 FAIL (SESSION marker mismatch)'
fi
# Expected: current DEPLOYED commit/ref, LAB BASELINE OK, NO INTERFERENCE, VERDICT: T0046.2 PASS (3 of 3).
