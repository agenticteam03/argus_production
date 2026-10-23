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
# STEP PHASE-16.5c-PREP — the audit digest key and the OCI credential on vm-095   [~10 min]
# Goal / Why: the signed daily digest (steps 5a and 5b) needs two secrets on vm-095 before the scheduler can be given
#   them: the Ed25519 key that signs the digests and the create-only OCI credential that ships them. They go in a NEW
#   folder, /opt/argus-v18/secrets/digest/, and not in secrets/agent/: the worker container mounts all of agent/, and
#   neither secret is the worker's. Nothing mounts the new folder yet (that is the deploy of step 5c), so no container
#   changes and nothing is deployed.
# MUTATES: creates /opt/argus-v18/secrets/digest/ (the key; the OCI credential folder). Undo: sudo rm -r that folder.
# Lease: held by conantkd on vm-095 (session 6bed2b5eda93; the SESSION marker is already written). No secret is printed.
# =====================================================================================

# --- KE.1 [VM vm-095 · bash] (ssh argus-vm095) generate the audit digest key; print only public information -------------
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  D=/opt/argus-v18/secrets/digest; K=$D/audit_digest_ed25519_key
  sudo install -d -m 0700 -o root -g root "$D" </dev/null
  if sudo test -e "$K"; then
    echo "audit digest key already there (kept)"
  else
    sudo sh -c "umask 077; openssl genpkey -algorithm ed25519 -out '$K'" </dev/null
    sudo chown 10010:10010 "$K"
    sudo chmod 0400 "$K"
    echo "audit digest key generated"
  fi
  echo "--- the key file (name, mode, owner, bytes):"
  sudo stat -c '%n %a %U:%G %s' "$K" </dev/null
  echo "--- type:"
  sudo openssl pkey -in "$K" -pubout </dev/null | openssl pkey -pubin -noout -text | head -1
  echo "--- PUBLIC key (safe to record):"
  sudo openssl pkey -in "$K" -pubout </dev/null
  echo "--- key_id (what the shipped digests will carry):"
  sudo openssl pkey -in "$K" -pubout -outform DER </dev/null | tail -c 32 | sha256sum | cut -c1-16
  echo "VERDICT: KE.1 PASS"
else
  echo "VERDICT: KE.1 STOP: NOT YOUR SESSION"
fi
# Expected: "audit digest key generated" (or "kept"); the file 400 10010:10010 119 bytes; "ED25519 Public-Key:"; a public key
#   PEM (-----BEGIN PUBLIC KEY-----); a 16-hex key_id; VERDICT: KE.1 PASS. Copy the PEM and the key_id into output.bash:
#   they are public and the agent records them.

# --- KE.2 [LAPTOP · PowerShell] copy the OCI credential to vm-095 without printing it (MUTATES: the new folder) ------------
# Undo: sudo rm -r /opt/argus-v18/secrets/digest/oci_digest on vm-095. The config is the [ARGUS_DIGEST] profile of
# ~/.oci/config renamed [DEFAULT]; the private key is argus_digest_key.pem. Both pass through a file in the VM's home
# that is shredded at once. The agent never sees either file.
# (The VM's `install -o 10010` refuses a user id with no name, so the owner is set with `chown` afterwards.)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Join-Path $HOME 'OneDrive\Documentos\SoftServe\ArgusAgentV2\wt-ticket')
$top = git rev-parse --show-toplevel
$ok = 0
if (($top -replace '/', '\') -like '*\wt-ticket') { $ok++ }
$cfg = Get-Content (Join-Path $HOME '.oci\config') -Raw
$m = [regex]::Match($cfg, '(?ms)^\[ARGUS_DIGEST\]\s*\r?\n(.*?)(?=^\[|\z)')
if ($m.Success) { $ok++ }
$stage = Join-Path $env:TEMP 'oci_digest_config'
[IO.File]::WriteAllText($stage, ("[DEFAULT]`n" + ($m.Groups[1].Value -replace "`r`n", "`n").TrimEnd() + "`n"), (New-Object Text.UTF8Encoding $false))
scp -q $stage argus-vm095:oci_digest_config
if ($LASTEXITCODE -eq 0) { $ok++ }
scp -q (Join-Path $HOME '.oci\argus_digest_key.pem') argus-vm095:oci_digest_key.pem
if ($LASTEXITCODE -eq 0) { $ok++ }
Remove-Item $stage -Force
ssh argus-vm095 "if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then D=/opt/argus-v18/secrets/digest/oci_digest; sudo install -d -m 0700 `$D && sudo install -m 0400 ~/oci_digest_config `$D/config && sudo install -m 0400 ~/oci_digest_key.pem `$D/key.pem && sudo chown -R 10010:10010 `$D && sudo chmod 0500 `$D; R=`$?; shred -u ~/oci_digest_config ~/oci_digest_key.pem; exit `$R; else shred -u ~/oci_digest_config ~/oci_digest_key.pem; echo NOT-YOUR-SESSION; exit 1; fi"
if ($LASTEXITCODE -eq 0) { $ok++ }
if ($ok -eq 5) { 'VERDICT: KE.2 PASS (5 of 5)' } else { "VERDICT: KE.2 FAIL ($ok of 5)" }
# Expected: no output but the verdict; VERDICT: KE.2 PASS (5 of 5).

# --- KE.3 [VM vm-095 · bash] check the two secrets without printing them, then non-interference --------------------------
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  D=/opt/argus-v18/secrets/digest
  echo "--- files (name, mode, owner:group, bytes):"
  sudo find "$D" -type f -printf '%P %m %u:%g %s\n' </dev/null | sort
  echo "--- the config names these keys (values not shown):"
  sudo sed -n 's/^\([a-z_]*\)=.*/\1/p' "$D/oci_digest/config" </dev/null | sort | tr '\n' ' '; echo
  echo "--- profile header:"
  sudo head -1 "$D/oci_digest/config" </dev/null
  F1=$(sudo sed -n 's/^fingerprint=//p' "$D/oci_digest/config" </dev/null)
  F2=$(sudo openssl rsa -in "$D/oci_digest/key.pem" -pubout -outform DER </dev/null 2>/dev/null | openssl md5 -c | sed 's/.*= //')
  if [ -n "$F1" ] && [ "$F1" = "$F2" ]; then echo "the key matches the fingerprint in the config"; else echo "FINGERPRINT MISMATCH"; fi
  N=$(sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1)
  echo "$N"
  case "$N" in
    *"NO INTERFERENCE"*) [ -n "$F1" ] && [ "$F1" = "$F2" ] && echo "VERDICT: KE.3 PASS" || echo "VERDICT: KE.3 STOP: the key does not match" ;;
    *) echo "VERDICT: KE.3 STOP: $N" ;;
  esac
else
  echo "VERDICT: KE.3 STOP: NOT YOUR SESSION"
fi
# Expected: oci_digest/config 400 10010:10010, oci_digest/key.pem 400 10010:10010, audit_digest_ed25519_key 400 10010:10010;
#   the config names user fingerprint tenancy region key_file; "[DEFAULT]"; "the key matches the fingerprint in the config";
#   NO INTERFERENCE: non-Argus objects unchanged; VERDICT: KE.3 PASS.

# --- KE.4 [LAPTOP · PowerShell] release the lease (MUTATES: the lease) ----------------------------------------------------
# Undo: brain.py start --vm vm-095 again. The secrets stay where they are; the deploy of step 5c claims the lease again.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Join-Path $HOME 'OneDrive\Documentos\SoftServe\ArgusAgentV2\wt-ticket')
$top = git rev-parse --show-toplevel
$ok = 0
if (($top -replace '/', '\') -like '*\wt-ticket') { $ok++ }
..\argus_production\.venv\Scripts\python.exe brain/tools/brain.py --as conantkd release --vm vm-095
if ($LASTEXITCODE -eq 0) { $ok++ }
if ($ok -eq 2) { 'VERDICT: KE.4 PASS (2 of 2)' } else { "VERDICT: KE.4 FAIL ($ok of 2)" }
# Expected: "Lease released on vm-095"; VERDICT: KE.4 PASS (2 of 2).
