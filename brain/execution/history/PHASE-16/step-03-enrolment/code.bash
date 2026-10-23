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
# STEP PHASE-16.D4 — Juan's enrolment ticket (conantkd issues it; Juan issues conantkd's next)   [~10 min]
# Goal / Why: D4 (ARCHITECTURE 1.8.29): a password alone never binds a key. The first WebAuthn credential of each
#   administrator needs a one-time code issued by the other administrator, on vm-095, by the lease holder.
# MUTATES: the SESSION marker on vm-095 and one row in webauthn_enrol_ticket (the code's SHA-256, never the code) plus
#   one audit row. Undo: the ticket expires in 24 h or when used; a reset of Juan's credentials is
#   `argus webauthn reset <name> --as <other admin>` (not needed here). Release the lease with TK.4.
# Lease: you hold vm-095 (brain.py start --vm vm-095). The agent never sees the code: TK.2's output is NOT pasted.
# =====================================================================================

# --- TK.1 [VM vm-095 · bash] (ssh argus-vm095) marker, state probe, "before" snapshot (MUTATES: the marker only) ---------
# The FIRST line carries your lease's session id (from `brain.py start`, or the session branch's session.json). Change
# only that line. The block stops if the id is still a placeholder ("session=REPLACE...").
echo 'holder=conantkd session=a8a664a7e486' | sudo tee /opt/argus-v18/SESSION >/dev/null
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  if grep -q 'session=REPLACE' /opt/argus-v18/SESSION; then
    echo "VERDICT: TK.1 STOP: put the real session id in the first line"
  else
    echo "SESSION OK"
    sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E '^(commit|ref)=|LAB BASELINE'
    echo "health HTTP $(curl -sS -o /dev/null -w '%{http_code}' http://localhost:18000/healthz </dev/null)"
    sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
    echo "VERDICT: TK.1 PASS"
  fi
else
  echo "VERDICT: TK.1 STOP: NOT YOUR SESSION"
fi
# Expected: SESSION OK; commit=77c4524... (or later), LAB BASELINE OK; health HTTP 200; a nonint-check line;
#   VERDICT: TK.1 PASS.

# --- TK.2 [VM vm-095 · bash] Argus principals, then Juan's ticket (MUTATES: one ticket row, one audit row) -------------
# Run it in two steps. First the list (safe to paste); read Juan's Argus username in it (a human) and set OTHER.
# !!! The ticket command prints a one-time code. Copy it to Juan privately (not chat, not output.bash, not the agent).
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  OTHER=juanes6554
  sudo docker exec argus-v18-agent python -c "from argus.infrastructure.wiring import Settings, make_store; [print(r[0], r[1], r[2]) for r in make_store(Settings())._q('SELECT id, kind, role FROM principal ORDER BY id')]" </dev/null
  if [ "${OTHER#REPLACE}" != "$OTHER" ]; then
    echo "set OTHER to Juan's username above, then run this block again"
  else
    sudo docker exec argus-v18-agent argus webauthn allow-enrol "$OTHER" --as conantkd </dev/null
  fi
else
  echo "NOT YOUR SESSION"
fi
# Expected: the principals; the first run stops at "set OTHER..." (nothing is issued); with OTHER set, the second run
#   prints "enrolment code for <Juan> (single use, 24 h): ..." -> give it to Juan; do NOT paste it.

# --- TK.3 [VM vm-095 · bash] Prove the ticket was issued (audit, no code) and non-interference ---------------------------
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  if sudo docker exec argus-v18-agent python -c "import json, sys; from argus.infrastructure.wiring import Settings, make_store; rows = make_store(Settings()).audit_chain(); ev = [(json.loads(b) if isinstance(b, str) else b) for _, b, _, _ in rows[-300:]]; ev = [e for e in ev if e.get('event') == 'security.webauthn_enrol_allowed']; [print(e['actor'], '->', e['detail']['principal'], e['detail']['hours'], 'h', e['at']) for e in ev[-3:]]; print('ENROL TICKETS AUDITED:', len(ev)); sys.exit(0 if ev else 1)" </dev/null; then
    N=$(sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1)
    echo "$N"
    case "$N" in
      *"NO INTERFERENCE"*) echo "VERDICT: TK.3 PASS" ;;
      *) echo "VERDICT: TK.3 STOP: $N" ;;
    esac
  else
    echo "VERDICT: TK.3 STOP: no enrolment ticket in the audit"
  fi
else
  echo "VERDICT: TK.3 STOP: NOT YOUR SESSION"
fi
# Expected: "conantkd -> <Juan> 24 h <time>"; ENROL TICKETS AUDITED: 1 (or more); NO INTERFERENCE; VERDICT: TK.3 PASS.

# --- TK.4 [LAPTOP · PowerShell] Release the lease so Juan can take it and issue yours (MUTATES: the lease) --------------
# Undo: brain.py start --vm vm-095 again. Tell Juan: his code (privately) and that vm-095 is his to claim; he runs the
# same TK.1-TK.3 with `--as <his name>` and OTHER = your Argus username.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Join-Path $HOME 'OneDrive\Documentos\SoftServe\ArgusAgentV2\wt-ticket')
$top = git rev-parse --show-toplevel
$ok = 0
if (($top -replace '/', '\') -like '*\wt-ticket') { $ok++ }
..\argus_production\.venv\Scripts\python.exe brain/tools/brain.py --as conantkd release --vm vm-095
if ($LASTEXITCODE -eq 0) { $ok++ }
if ($ok -eq 2) { 'VERDICT: TK.4 PASS (2 of 2)' } else { "VERDICT: TK.4 FAIL ($ok of 2)" }
# Expected: "Lease released on vm-095"; VERDICT: TK.4 PASS (2 of 2).
# After Juan's code reaches you: on the UI (the DNS name) log in > account menu > Security keys > type the code >
# register this laptop's passkey > "Add another key" (phone or security key; it asks you to confirm with the first).
