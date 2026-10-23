# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
# DEPLOY-77c4524 (prepared 2026-10-22 by the agent; to be run by conantkd) — main 77c4524 on vm-095. Since afb72e8:
#   PHASE-16 step 3 (#280: migration 013, the WebAuthn second factor and the step-up token; #284: the UI's security
#   keys page), the Bearer redaction fix (#278), the replay's per-target series (#267, evaluation only).
#   Migration 013 before the image. vm-166: no change.  [~35 min]
# MUTATES: vm-095 (backup, checkout, migration 013, hosts.env (two lines), agent/worker/scheduler, the UI); one
#   enrolment ticket. Both leases.
# EFFECT: nobody's access changes (no privileged permission exists yet); /me lists manage_second_factor and the
#   account menu shows "Security keys".
# ROLLBACK: sudo bash /opt/argus-v18/app/ops/deploy.sh afb72e8 --as conantkd, then the compose commands of D.3 and
#   D.4; migration 013 stays (the old image does not read its tables); hosts.env from its .bak copy.
# Never paste the enrolment code (D.6) into output.bash: give it to Juan privately; it is single-use, 24 h.
# =====================================================================================

# --- D.0 [LAPTOP · PowerShell] both leases (wait for "Lease CLAIMED": verify-main takes 3-4 min; do not interrupt) ---
python brain/tools/brain.py --as conantkd start --task DEPLOY-77c4524 --vm both
# Expected: "Lease CLAIMED by conantkd on vm-095 and vm-166"; copy the SESSION id into D.1 and D.2.

# --- D.1 [VM vm-166 · bash] (ssh argus-vm166) marker, before -------------------------------------------------------------
echo 'holder=conantkd session=<from D.0>' | sudo tee /opt/argus-v18/SESSION >/dev/null
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
# Expected: a "before" snapshot line.

# --- D.2 [VM vm-095 · bash] (ssh argus-vm095) marker, backup and verify, checkout, migration 013 (MUTATES) ------------
ME=conantkd; BR=77c4524
echo 'holder=conantkd session=<from D.0>' | sudo tee /opt/argus-v18/SESSION >/dev/null
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || echo "NOT YOUR SESSION - stop here"
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as $ME </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/db-backup.sh verify latest --as $ME </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh $BR --as $ME </dev/null | tail -3
sudo bash /opt/argus-v18/app/ops/db-migrate.sh </dev/null | grep -E "\+ |REFUSED|schema:"
# Expected: SESSION OK; ref=afb72e8, LAB BASELINE OK; BACKUP OK; VERIFY OK (tables and rows match); DEPLOY OK: 77c4524;
#   "+ 013_webauthn applied", schema 001 to 013. A REFUSED line: STOP (rollback above).

# --- D.3 [VM vm-095 · bash] the relying party in hosts.env (the UI's name, read from its env file), the agent (MUTATES) --
H=/opt/argus-v18/hosts.env; D=$(sudo sed -n 's/^ARGUS_UI_DOMAIN=//p' /opt/argus-v18/app/deploy/ui/vm-095.env | tr -d '[:space:]')
case "$D" in ""|*[!a-z0-9.-]*) echo "ARGUS_UI_DOMAIN is not a DNS name - stop here";; *) echo "UI name read (not printed here)";; esac
sudo cp -p $H $H.bak-before-webauthn
for kv in "ARGUS_WEBAUTHN_RP_ID=$D" "ARGUS_WEBAUTHN_ORIGIN=https://$D"; do k=${kv%%=*}; if sudo grep -q "^$k=" $H; then sudo sed -i "s|^$k=.*|$kv|" $H; else echo "$kv" | sudo tee -a $H >/dev/null; fi; done
echo "hosts.env WebAuthn lines: $(sudo grep -c '^ARGUS_WEBAUTHN_' $H)"
cd /opt/argus-v18/app/deploy/vm-095
sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E "Recreated|Started|rror"
cd ~
for i in $(seq 1 30); do c=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done; echo "health $c"
sudo docker exec argus-v18-agent argus deploy record --commit 77c4524 --ref main --as $ME </dev/null | tail -1
# Expected: "UI name read"; "hosts.env WebAuthn lines: 2"; three Recreated/Started, no "rror"; health 200; deploy recorded.

# --- D.4 [VM vm-095 · bash] the UI: the security keys page and the edge's seven new routes (MUTATES) ---------------------
cd /opt/argus-v18/app/deploy/ui
sudo docker compose --env-file vm-095.env -f compose.ui.yml -f compose.public.yml up -d --build </dev/null 2>&1 | grep -E "Recreated|Started" | tr '\n' ' '; echo
cd ~
for i in $(seq 1 30); do s=$(sudo docker inspect -f '{{.State.Health.Status}}' argus-v18-ui </dev/null 2>/dev/null); [ "$s" = healthy ] && break; sleep 3; done
echo "ui: $(sudo docker inspect -f '{{.State.Status}} health={{.State.Health.Status}} restarts={{.RestartCount}}' argus-v18-ui </dev/null)"
echo "security page in bundle: $(sudo docker exec argus-v18-ui sh -c 'grep -l "auth/webauthn/register/options" /usr/share/nginx/html/assets/*.js | wc -l' </dev/null)"
# Expected: ui Recreated/Started; healthy restarts=0; security page in bundle >= 1.

# --- D.5 [VM vm-095 · bash] verification (read-only) ---------------------------------------------------------------------
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c $(sudo docker inspect -f "{{.State.Status}} restarts={{.RestartCount}}" $c </dev/null)"; done
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do n=$(sudo docker logs --since 10m $c 2>&1 </dev/null | grep -v argus_probe_error | grep -ciE "traceback|error"); echo "$c error lines: $n"; done
sudo docker exec argus-v18-agent python -c "from argus.infrastructure.wiring import Settings as S; s=S(); print('WebAuthn relying party set' if s.webauthn_rp_id and s.webauthn_origin == 'https://' + s.webauthn_rp_id else 'WEBAUTHN NOT SET')" </dev/null
echo "edge, ceremony without a token: $(curl -sk -o /dev/null -w '%{http_code}' -X POST -H "Host: $D" https://127.0.0.1/api/v1/auth/webauthn/login/options </dev/null) (401: proxied; 404: the edge lacks the route)"
echo "/me without a token: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18000/api/v1/me </dev/null) (401)"
sudo docker exec argus-v18-agent argus db check </dev/null | grep -E "FAIL|checks passed"
sudo docker exec argus-v18-agent argus audit verify </dev/null | tail -1
sudo docker exec argus-v18-agent python -c "from argus.capabilities.redaction import Redactor; print('Bearer fix live' if 'hunter2' not in Redactor().text('Bearer\npassword=hunter2xyz')[0] else 'BEARER FIX MISSING')" </dev/null
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
# Expected: three running restarts=0; error lines 0; "WebAuthn relying party set"; edge 401; /me 401;
#   "49/49 database checks passed"; the audit chain verified; "Bearer fix live"; ref=77c4524, LAB BASELINE OK.

# --- D.6 [VM vm-095 · bash] Juan's enrolment ticket, issued by you (D4: nobody issues their own) (MUTATES) ---------------
sudo docker exec argus-v18-agent python -c "from argus.infrastructure.wiring import Settings, make_store; [print(r[0], r[1], r[2]) for r in make_store(Settings())._q('SELECT id, kind, role FROM principal ORDER BY id')]" </dev/null
# Read Juan's Argus username in that list (a human), set it below, then run the next line. Its output is a one-time
# code: copy it to Juan privately and do NOT paste it into output.bash. Juan issues yours the same way, with --as his.
OTHER=REPLACE_WITH_JUANS_USERNAME
if [ "$OTHER" = REPLACE_WITH_JUANS_USERNAME ]; then echo "set OTHER to Juan's username first"; else sudo docker exec argus-v18-agent argus webauthn allow-enrol "$OTHER" --as $ME </dev/null; fi
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
# Expected: the principals; "enrolment code for <Juan> (single use, 24 h): ..." (keep it out of the output);
#   NO INTERFERENCE.

# --- D.7 [VM vm-166 · bash] after, then [LAPTOP · PowerShell] release -----------------------------------------------------
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
python brain/tools/brain.py --as conantkd release
# Expected: NO INTERFERENCE; "Lease released on vm-095 and vm-166."

# --- D.8 [LAPTOP · browser] once Juan has issued your ticket ---------------------------------------------------------------
# Log in again on the UI, open the account menu > Security keys, type the code and register this laptop's passkey;
# then "Add another key" (your phone or a security key: it asks you to confirm with the first). "Confirm with my key".
# >>> Paste everything (except the enrolment code) into output.bash and tell the agent "output.bash updated". <<<
