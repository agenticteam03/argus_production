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
# STEP PHASE-16-enrol-ticket — conantkd's enrolment ticket, issued by juanes6554          [~5 min]
# Goal / Why: NEXT_STEP item 1 (reciprocal tickets, ACR-0018 D4: nobody issues their own). juanes6554 issues the
#   one-time code that lets conantkd register his first security key at /account/security; conantkd issues
#   juanes6554's the same way. The code is single-use and valid 24 h (ARGUS_WEBAUTHN_ENROL_TICKET_HOURS).
# Lease: vm-095 only, juanes6554, session 7175903bfff6 (brain.py start, 2026-10-23). No container, image, migration
#   or hosts.env change, so one lease is enough (PARALLEL_LANES.md).
# MUTATES: vm-095: the SESSION marker; one row in the enrolment-ticket table and one audit record
#   (security.webauthn_enrol_allowed). Nothing else.
# Undo: none needed: the code expires unused after 24 h and works once. If it leaked before conantkd used it:
#   sudo docker exec argus-v18-agent argus webauthn reset conantkd --as juanes6554 </dev/null
#   (revokes any key registered with it and ends his sessions), then issue a new ticket with E.2.
# >>> NEVER paste the enrolment code into output.bash, a chat, a commit or a PR. Give it to conantkd privately. <<<
# =====================================================================================

# --- E.1 [VM vm-095 · bash] (ssh argus-vm095) marker, "before" snapshot, the principals (READ-ONLY after the marker) ---
echo 'holder=juanes6554 session=7175903bfff6' | sudo tee /opt/argus-v18/SESSION >/dev/null
if grep -Eq '^holder=juanes6554 session=' /opt/argus-v18/SESSION; then
  sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
  sudo docker exec argus-v18-agent python -c "from argus.infrastructure.wiring import Settings, make_store; [print(r[0], r[1], r[2]) for r in make_store(Settings())._q('SELECT id, kind, role FROM principal ORDER BY id')]" </dev/null
  printf '%s\n' 'VERDICT: E.1 PASS'
else
  printf '%s\n' 'VERDICT: E.1 STOP: NOT YOUR SESSION'
fi
# Expected: a "before" snapshot line; the principals, among them "conantkd human ..." and "juanes6554 human ...";
#   VERDICT: E.1 PASS. If conantkd is not in the list, STOP and ask him for his Argus username.

# --- E.2 [VM vm-095 · bash] conantkd's ticket (MUTATES: one ticket row + one audit record) ------------------------------
# The line "enrolment code for conantkd (single use, 24 h) ..." must stay private: copy the code to conantkd privately
# (a direct message only he can read), then clear the screen (clear). Do NOT paste this block's output.
if grep -Eq '^holder=juanes6554 session=' /opt/argus-v18/SESSION; then
  if sudo docker exec argus-v18-agent argus webauthn allow-enrol conantkd --as juanes6554 </dev/null; then
    printf '%s\n' 'VERDICT: E.2 TICKET ISSUED'
  else
    printf '%s\n' 'VERDICT: E.2 STOP: allow-enrol refused'
  fi
else
  printf '%s\n' 'VERDICT: E.2 STOP: NOT YOUR SESSION'
fi
# Expected: "enrolment code for conantkd (single use, 24 h): <code>" (keep it out of every record), then
#   VERDICT: E.2 TICKET ISSUED. Into output.bash goes ONLY the VERDICT line.

# --- E.3 [VM vm-095 · bash] the audit record (without the code) and "after" (READ-ONLY) --------------------------------
if grep -Eq '^holder=juanes6554 session=' /opt/argus-v18/SESSION; then
  sudo docker exec argus-v18-agent argus audit verify </dev/null | tail -1
  sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
  printf '%s\n' 'VERDICT: E.3 PASS'
else
  printf '%s\n' 'VERDICT: E.3 STOP: NOT YOUR SESSION'
fi
# Expected: the audit chain verified; NO INTERFERENCE; VERDICT: E.3 PASS.

# --- E.4 [LAPTOP · PowerShell] release the lease (MUTATES: the lease on the session branch. Undo: brain.py start) ------
# Expected: the repository path; "Lease released"; VERDICT: E.4 PASS (1 of 1).
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Juan Díaz\Cursos\Agentic Frameworks Project Lab - SoftServe\argus_production')
git rev-parse --show-toplevel
$ok = 0
python brain/tools/brain.py release
if ($LASTEXITCODE -eq 0) { $ok++ }
if ($ok -eq 1) { 'VERDICT: E.4 PASS (1 of 1)' } else { "VERDICT: E.4 FAIL ($ok of 1)" }
# >>> Paste E.1, the VERDICT line of E.2, E.3 and E.4 into output.bash and tell the agent "output.bash updated". <<<
