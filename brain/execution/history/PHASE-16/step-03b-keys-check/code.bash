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
# STEP PHASE-16.KEYS — check that every enabled operator has two security keys   [~5 min]
# Goal / Why: ACR-0018 D3 asks for two credentials per privileged person. The team reports they are registered; this
#   reads the database to turn the report into evidence, so CURRENT_STATE.md can say it.
# MUTATES: only the SESSION marker on vm-095 (the block reads the credential counts, nothing else; no key or id is
#   printed). Undo: release the lease with KY.2.
# Lease: claim vm-095 first: `brain.py --as conantkd start --vm vm-095` from a clean checkout (wt-ticket).
# =====================================================================================

# --- KY.1 [VM vm-095 · bash] (ssh argus-vm095) marker, then the number of credentials per operator -----------------------
# Replace REPLACE_WITH_SESSION_ID in the FIRST line by the SESSION id of the new lease. Change only that line.
echo 'holder=conantkd session=1c60b890bf65' | sudo tee /opt/argus-v18/SESSION >/dev/null
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  if grep -q 'session=REPLACE' /opt/argus-v18/SESSION; then
    echo "VERDICT: KY.1 STOP: put the real session id in the first line"
  else
    sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
    if sudo docker exec argus-v18-agent python -c "import sys; from argus.infrastructure.wiring import Settings, make_store; s = make_store(Settings()); r = {n: len(s.webauthn_credentials(n)) for n in ('conantkd', 'juanbetancurm', 'juanes6554')}; print(r); sys.exit(0 if all(v >= 2 for v in r.values()) else 1)" </dev/null; then
      N=$(sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1)
      echo "$N"
      case "$N" in
        *"NO INTERFERENCE"*) echo "VERDICT: KY.1 PASS" ;;
        *) echo "VERDICT: KY.1 STOP: $N" ;;
      esac
    else
      echo "VERDICT: KY.1 STOP: someone has fewer than two keys (the counts are above)"
    fi
  fi
else
  echo "VERDICT: KY.1 STOP: NOT YOUR SESSION"
fi
# Expected: a dict like {'conantkd': 2, 'juanbetancurm': 2, 'juanes6554': 2} (2 or more each); NO INTERFERENCE;
#   VERDICT: KY.1 PASS. It prints counts only: no credential id, key or name of a key.

# --- KY.3 [VM vm-095 · bash] Non-interference after the check (READ-ONLY; KY.1 stopped before it could run it) -----------
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  N=$(sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1)
  echo "$N"
  case "$N" in
    *"NO INTERFERENCE"*) echo "VERDICT: KY.3 PASS" ;;
    *) echo "VERDICT: KY.3 STOP: $N" ;;
  esac
else
  echo "VERDICT: KY.3 STOP: NOT YOUR SESSION"
fi
# Expected: NO INTERFERENCE: non-Argus objects unchanged; VERDICT: KY.3 PASS. Run KY.3, then KY.2.

# --- KY.2 [LAPTOP · PowerShell] Release the lease (MUTATES: the lease) ------------------------------------------------
# Undo: brain.py start --vm vm-095 again.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Join-Path $HOME 'OneDrive\Documentos\SoftServe\ArgusAgentV2\wt-ticket')
$top = git rev-parse --show-toplevel
$ok = 0
if (($top -replace '/', '\') -like '*\wt-ticket') { $ok++ }
..\argus_production\.venv\Scripts\python.exe brain/tools/brain.py --as conantkd release --vm vm-095
if ($LASTEXITCODE -eq 0) { $ok++ }
if ($ok -eq 2) { 'VERDICT: KY.2 PASS (2 of 2)' } else { "VERDICT: KY.2 FAIL ($ok of 2)" }
# Expected: "Lease released on vm-095"; VERDICT: KY.2 PASS (2 of 2).
