# LEGACY — the command history of Tasks 0-12c (2026-09-30 .. 2026-10-02), from before the shared repository.
# Sanitized: addresses, local paths and personal names replaced by placeholders. Kept for reference only:
# paths, deployment method (laptop tarball) and helper names are OUTDATED. New commands go to
# brain/execution/current/code.bash following brain/policies/CODE_BASH.md.


# =====================================================================================
# Argus v1.8 on the two Oracle VMs — commands to copy and paste
#
# Every block says WHERE to run it:
#   [LAPTOP · PowerShell]  → a PowerShell window on your Windows laptop
#   [VM 0.95 · bash]       → SSH session on <vm-095 public address>  (prompt: ubuntu@vm-appsvnic)
#   [VM 0.166 · bash]      → SSH session on <vm-166 public address> (prompt: ubuntu@agent-test-vnic)
#
# Plan: AAbrainProject/plans/argus-v1.8-two-vm-plan.md
# =====================================================================================


# -------------------------------------------------------------------------------------
# TASK 0 — Commit the two untracked runbook files so the library can be pinned   [~1 min]
# -------------------------------------------------------------------------------------

# --- 0.1 [LAPTOP · PowerShell] ---------------------------------------------------------
cd <workspace>\RunbooksLab
git add RUNBOOK-CONVENTIONS.md RUNBOOK-INDEX.md
git commit -m "Add runbook conventions and index (pinned by Argus v1.8)"
git push
git log --oneline -1          # tell Claude this commit id: it becomes the pinned library version


# -------------------------------------------------------------------------------------
# TASK 1 — Read-only discovery of both VMs (Phase 0)                       [~5 min]
# -------------------------------------------------------------------------------------

# --- 1.1 [LAPTOP · PowerShell] Variables for this window ------------------------------
$KEY  = "$HOME\.ssh\team_vm_ed25519"
$V95  = "argus-vm095"
$V166 = "argus-vm166"
$OPS  = "<workspace>\<08 folder>\ops"

# --- 1.2 [LAPTOP · PowerShell] Upload the script to both VMs ---------------------------
scp -i $KEY "$OPS\vm-discovery.sh" "${V95}:~/vm-discovery.sh"
scp -i $KEY "$OPS\vm-discovery.sh" "${V166}:~/vm-discovery.sh"

# --- 1.3 [LAPTOP · PowerShell] Run it on both VMs and bring the reports back -----------
# (sudo on VM 0.95 may ask for a password: that itself tells us its sudo is not NOPASSWD.)
ssh -t -i $KEY $V95  "sudo bash ~/vm-discovery.sh > ~/discovery.txt 2>&1; wc -l ~/discovery.txt"
ssh -t -i $KEY $V166 "sudo bash ~/vm-discovery.sh > ~/discovery.txt 2>&1; wc -l ~/discovery.txt"
scp -i $KEY "${V95}:~/discovery.txt"  "$OPS\discovery-vm095.txt"
scp -i $KEY "${V166}:~/discovery.txt" "$OPS\discovery-vm166.txt"
# Expected: several hundred lines each. Then tell Claude: "discovery done".

ssh -i $KEY $V166 "cat ~/discovery.txt" | Out-File

# -------------------------------------------------------------------------------------
# TASK 2 — Cross-VM reachability of the Argus ports (read-only)            [~2 min]
# The discovery's reachability loop stopped early (script time limit). This finishes it.
# -------------------------------------------------------------------------------------

# --- 2.1 [LAPTOP · PowerShell] Upload and run on both VMs ------------------------------
scp -i $KEY "$OPS\reachability.sh" "${V95}:~/reachability.sh"
scp -i $KEY "$OPS\reachability.sh" "${V166}:~/reachability.sh"
ssh -i $KEY $V95  "bash ~/reachability.sh"
ssh -i $KEY $V166 "bash ~/reachability.sh"
# >>> Send Claude both outputs. "timeout (filtered)" on 187xx/18090/18001 means the Oracle VCN
#     security list blocks them; "refused (path open)" means the path is open. <<<


# -------------------------------------------------------------------------------------
# TASK 3 — Clean-up of OUR leftovers on VM 0.166 (strictly limited)        [~1 min]
# Discovery result: only ONE leftover is both ours and unused by anything else:
#   /home/ubuntu/env-gateway.bak  (course-gateway credentials backup from the September demo)
# NOT removed (ours, but now used by the other Argus deployment in /opt/argus-lab):
#   compose project labmvp (lab-victim, mvp-exporter), network labmvp_default, volume
#   labmvp_agent-data, /home/ubuntu/lab-agent and its .env. Nothing is removed on VM 0.95.
# -------------------------------------------------------------------------------------

# --- 3.1 [VM 0.166 · bash] Guarded removal: stops if anything references the file -------
f=/home/ubuntu/env-gateway.bak
if docker ps -q | xargs -r docker inspect --format '{{range .Mounts}}{{.Source}} {{end}}' | grep -q "env-gateway"; then echo "STOP: a container mounts it"
elif grep -rlsI "env-gateway" /home/ubuntu/lab-agent /opt/argus-lab 2>/dev/null | grep -q .; then echo "STOP: a project file references it"
elif [ -f "$f" ]; then shred -u "$f" && echo "removed $f"
else echo "already absent"; fi
ls -l /home/ubuntu/env-gateway.bak 2>&1 | head -1          # expected: No such file or directory
# DONE 2026-10-01: removed.


# -------------------------------------------------------------------------------------
# TASK 4 (old) — Oracle console rules: NOT POSSIBLE (no console access). Superseded by TASK 4 below.
# -------------------------------------------------------------------------------------


# -------------------------------------------------------------------------------------
# TASK 4 — Encrypted cross-host path: restricted SSH tunnel vm-095 -> vm-166  [~10 min]
# Port 22 is the only open path between the VMs. A dedicated, shell-less user on VM 0.166 whose key
# may ONLY forward to 5 loopback ports (127.0.0.1:18701-18704, 18090). Argus still talks HTTP to the
# v1.8 gateways/probes with their own tokens; SSH only carries the traffic (v1.8 §3.2: encrypted tunnel).
# Nothing of conantkd's deployment, his WireGuard, sshd_config or any firewall is touched.
# If 4.1 says forwarding is not allowed for this user, STOP: fallback = use the VPS as vm-166.
# -------------------------------------------------------------------------------------

# --- 4.1 [VM 0.166 · bash] READ-ONLY: does sshd allow restricted forwarding for this user? ---
sudo sshd -T -C user=argus-v18-tunnel,host=vm-appsvnic,addr=<vm-095 private IP> | grep -iE '^(allowtcpforwarding|disableforwarding|allowusers|allowgroups|denyusers|denygroups|pubkeyauthentication|authorizedkeysfile|permitopen|usepam) '
ls /etc/ssh/sshd_config.d/
# GO only if: allowtcpforwarding yes|local · disableforwarding no · pubkeyauthentication yes ·
#             no allowusers/allowgroups line (or it would include argus-v18-tunnel).
# >>> If unsure, send Claude this output before continuing. <<<

# --- 4.2 [VM 0.95 · bash] Tunnel key + pinned host key of VM 0.166 ----------------------------
sudo install -d -m 700 /opt/argus-v18 /opt/argus-v18/secrets /opt/argus-v18/secrets/tunnel
sudo test -f /opt/argus-v18/secrets/tunnel/id_ed25519 || sudo ssh-keygen -q -t ed25519 -N "" -C "argus-v18-tunnel@vm-095" -f /opt/argus-v18/secrets/tunnel/id_ed25519
ssh-keyscan -t ed25519 <vm-166 private IP> 2>/dev/null | sudo tee /opt/argus-v18/secrets/tunnel/known_hosts >/dev/null
sudo ssh-keygen -lf /opt/argus-v18/secrets/tunnel/known_hosts        # fingerprint as seen from VM 0.95

# --- 4.3 [VM 0.166 · bash] READ-ONLY: its own host key fingerprint (must equal 4.2) -----------
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
# If the two fingerprints differ: STOP and tell Claude.

# --- 4.4 [LAPTOP · PowerShell] Carry the PUBLIC key from VM 0.95 to VM 0.166 -------------------
# (Variables again, in case this is a new PowerShell window: $KEY etc. only live in the window that set them.)
$KEY = "$HOME\.ssh\team_vm_ed25519"; $V95 = "argus-vm095"; $V166 = "argus-vm166"
$OPS = "<workspace>\<08 folder>\ops"
ssh -i $KEY $V95 "sudo cat /opt/argus-v18/secrets/tunnel/id_ed25519.pub" | Out-File -Encoding ascii "$env:TEMP\argus-v18-tunnel.pub"
scp -i $KEY "$env:TEMP\argus-v18-tunnel.pub" "${V166}:~/argus-v18-tunnel.pub"
Remove-Item "$env:TEMP\argus-v18-tunnel.pub"

# --- 4.5 [VM 0.166 · bash] Shell-less user whose key can only forward to 5 loopback ports ------
id argus-v18-tunnel 2>/dev/null || sudo useradd --system --create-home --home-dir /var/lib/argus-v18-tunnel --shell /usr/sbin/nologin argus-v18-tunnel
sudo usermod -p '*' argus-v18-tunnel          # no password; key login only
sudo install -d -m 700 -o argus-v18-tunnel -g argus-v18-tunnel /var/lib/argus-v18-tunnel/.ssh
OPTS='restrict,port-forwarding,permitopen="127.0.0.1:18701",permitopen="127.0.0.1:18702",permitopen="127.0.0.1:18703",permitopen="127.0.0.1:18704",permitopen="127.0.0.1:18090"'
if grep -q '^ssh-ed25519 ' ~/argus-v18-tunnel.pub 2>/dev/null; then
  echo "$OPTS $(tr -d '\r' < ~/argus-v18-tunnel.pub)" | sudo tee /var/lib/argus-v18-tunnel/.ssh/authorized_keys >/dev/null
  sudo chown argus-v18-tunnel:argus-v18-tunnel /var/lib/argus-v18-tunnel/.ssh/authorized_keys
  sudo chmod 600 /var/lib/argus-v18-tunnel/.ssh/authorized_keys
  rm -f ~/argus-v18-tunnel.pub && echo "KEY INSTALLED"
else echo "STOP: ~/argus-v18-tunnel.pub missing or not a key - run 4.4 on the laptop first"; fi
sudo cut -c1-120 /var/lib/argus-v18-tunnel/.ssh/authorized_keys     # expected: restrict,port-forwarding,permitopen=...

# --- 4.6 [LAPTOP · PowerShell] End-to-end test (temporary listener on VM 0.166 for 2 minutes) ---
# Same PowerShell window as 4.4 (the variables must exist).
scp -i $KEY "$OPS\tunnel-test.sh" "${V95}:~/tunnel-test.sh"
ssh -i $KEY $V166 "setsid nohup timeout 120 python3 -m http.server 18701 --bind 127.0.0.1 >/dev/null 2>&1 < /dev/null &"
ssh -i $KEY $V95 "sudo bash ~/tunnel-test.sh"
# Expected:
#   1. allowed forward  (expect 200): 200
#   2. forbidden forward (expect 000): 000
#   3. shell attempt (expect refusal): This account is currently not available.
#   ssh client messages: ... administratively prohibited ...   (the forbidden forward)
# >>> Send Claude the output. <<<

# --- 4.7 [LAPTOP · PowerShell] Undo (only if we abandon the tunnel; then the fallback is the VPS) ---
# ssh -i $KEY $V166 "sudo userdel -r argus-v18-tunnel"
# ssh -i $KEY $V95  "sudo rm -rf /opt/argus-v18/secrets/tunnel"


# -------------------------------------------------------------------------------------
# TASK 5 — Phase 3: tunnel sidecar + v1.8 target services + Prometheus on BOTH VMs  [~15 min]
# Names argus-v18-* / argus-lab-*; networks 172.30.0-2.0/24; vm-166 publishes ONLY on 127.0.0.1;
# vm-095 publishes nothing. conantkd's deployment and every other object are not touched (checked in 5.2/5.7).
# -------------------------------------------------------------------------------------

# --- 5.1 [LAPTOP · PowerShell] Package and upload (one window for the whole task) -------------
$KEY = "$HOME\.ssh\team_vm_ed25519"; $V95 = "argus-vm095"; $V166 = "argus-vm166"
$APP = "<workspace>\<08 folder>"
cd $APP
.\.venv\Scripts\python ops\render_target_config.py
.\.venv\Scripts\python ops\make_secrets.py
tar -czf "$env:TEMP\argus-v18-app.tgz" --exclude=.venv --exclude=__pycache__ --exclude=.pytest_cache --exclude=argus.egg-info --exclude=deploy/secrets --exclude=ops/discovery-vm095.txt --exclude=ops/discovery-vm166.txt --exclude=output.bash .
scp -i $KEY "$env:TEMP\argus-v18-app.tgz" "${V95}:~/argus-v18-app.tgz"
scp -i $KEY "$env:TEMP\argus-v18-app.tgz" "${V166}:~/argus-v18-app.tgz"
ssh -i $KEY $V95  "rm -rf ~/argus-v18-secrets"
ssh -i $KEY $V166 "rm -rf ~/argus-v18-secrets"
scp -r -i $KEY "$APP\deploy\secrets\vm-095" "${V95}:~/argus-v18-secrets"
scp -r -i $KEY "$APP\deploy\secrets\vm-166" "${V166}:~/argus-v18-secrets"

# --- 5.2 [VM 0.166 · bash] Install, BEFORE-snapshot, start (loopback only) — safe to re-run -------
# /opt/argus-v18 = 0755 (code, not secret); /opt/argus-v18/secrets = 0700 root (tokens).
sudo install -d -m 755 /opt/argus-v18 && sudo install -d -m 700 /opt/argus-v18/secrets
if [ -f ~/argus-v18-app.tgz ]; then sudo rm -rf /opt/argus-v18/app && sudo mkdir -p /opt/argus-v18/app && sudo tar -xzf ~/argus-v18-app.tgz -C /opt/argus-v18/app && rm ~/argus-v18-app.tgz; fi
sudo chmod -R a+rX /opt/argus-v18/app
if [ -d ~/argus-v18-secrets ]; then sudo sh -c 'cp /home/ubuntu/argus-v18-secrets/*_token /opt/argus-v18/secrets/ && chmod 600 /opt/argus-v18/secrets/*_token' && rm -rf ~/argus-v18-secrets; fi
sudo sh -c 'ls -l /opt/argus-v18/secrets/'                       # expected: 3 *_token files, -rw-------
sudo test -f /opt/argus-v18/baseline/before.txt || sudo bash /opt/argus-v18/app/ops/nonint-check.sh before
cd /opt/argus-v18/app/deploy/target && sudo docker compose --env-file vm-166.env -f compose.target.yml -f compose.loopback.yml up -d --build
cd /opt/argus-v18/app/deploy/monitoring && sudo docker compose --env-file vm-166.env -f compose.monitoring.yml -f compose.loopback.yml up -d
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile base-166 up -d
cd ~ && sudo docker ps --filter name=argus- --format '{{.Names}}  {{.Status}}  {{.Ports}}'
# Expected: 7 argus-* containers Up; ports only 127.0.0.1:18701-18703 and 127.0.0.1:18090.

# --- 5.3 [VM 0.95 · bash] Install, BEFORE-snapshot, start (nothing published) — safe to re-run -----
sudo install -d -m 755 /opt/argus-v18 && sudo chmod 755 /opt/argus-v18 && sudo install -d -m 700 /opt/argus-v18/secrets
if [ -f ~/argus-v18-app.tgz ]; then sudo rm -rf /opt/argus-v18/app && sudo mkdir -p /opt/argus-v18/app && sudo tar -xzf ~/argus-v18-app.tgz -C /opt/argus-v18/app && rm ~/argus-v18-app.tgz; fi
sudo chmod -R a+rX /opt/argus-v18/app
if [ -d ~/argus-v18-secrets ]; then sudo sh -c 'cp /home/ubuntu/argus-v18-secrets/*_token /opt/argus-v18/secrets/ && rm -rf /opt/argus-v18/secrets/agent && cp -r /home/ubuntu/argus-v18-secrets/agent /opt/argus-v18/secrets/agent && chmod -R go-rwx /opt/argus-v18/secrets' && rm -rf ~/argus-v18-secrets; fi
sudo sh -c 'ls -l /opt/argus-v18/secrets/ /opt/argus-v18/secrets/agent/'   # expected: tokens, agent/, tunnel/
sudo test -f /opt/argus-v18/baseline/before.txt || sudo bash /opt/argus-v18/app/ops/nonint-check.sh before
cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose -f compose.core.yml up -d --build
cd /opt/argus-v18/app/deploy/target && sudo docker compose --env-file vm-095.env -f compose.target.yml -f compose.core-join.yml up -d --build
cd /opt/argus-v18/app/deploy/monitoring && sudo docker compose --env-file vm-095.env -f compose.monitoring.yml -f compose.core-join.yml up -d
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile base-095 up -d
cd ~ && sudo docker ps --filter name=argus- --format '{{.Names}}  {{.Status}}  {{.Ports}}'
sudo docker logs --tail 5 argus-v18-tunnel
# Expected: argus-v18-tunnel + 4 target services + prometheus + argus-lab-api Up, NO ports; tunnel log without errors.

# --- 5.4 [VM 0.95 · bash] Phase 3 check: both hosts through the inventory endpoints --------------
sleep 40     # Prometheus needs a couple of scrapes
sudo docker run --rm --network argus-v18-core -v /opt/argus-v18/secrets/agent:/s:ro -v /opt/argus-v18/app/ops/phase3_check.py:/c.py:ro python:3.12-alpine python /c.py
# Expected: "28/28 checks passed" (14 per host).

# --- 5.5 [VM 0.166 · bash] AFTER-snapshot: nothing outside Argus changed ------------------------
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after
# Expected last line: NO INTERFERENCE: non-Argus objects unchanged

# --- 5.6 [VM 0.95 · bash] AFTER-snapshot -------------------------------------------------------
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after
# >>> Send Claude: the docker ps lines of 5.2/5.3, the whole 5.4 output, and the last lines of 5.5/5.6. <<<

# --- 5.7 [both VMs · bash] Undo Phase 3 (only if needed; touches ONLY argus-v18/argus-lab projects) ---
# cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile base-166 --profile base-095 down
# cd /opt/argus-v18/app/deploy/monitoring && sudo docker compose --env-file <vm>.env -f compose.monitoring.yml down -v
# cd /opt/argus-v18/app/deploy/target && sudo docker compose --env-file <vm>.env -f compose.target.yml down
# (vm-095 only) cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose -f compose.core.yml down

# RESULT 2026-10-01: 5.2/5.3 deployed; 5.4 = 28/28 PASSED; 5.6 vm-095 = NO INTERFERENCE;
# 5.5 vm-166 showed ONE new anonymous volume = created by our argus-lab-cache (redis declares VOLUME /data).
# Also: vm-095's argus-lab-api twin was unhealthy by design (it pinged a cache that only exists on vm-166).

# -------------------------------------------------------------------------------------
# TASK 5.8 — Fix the two lab-baseline issues and re-check non-interference      [~5 min]
# cache -> tmpfs (no Docker volume); vm-095 twin -> no dependency (healthy);
# nonint-check.sh -> volumes from OUR compose projects count as Argus objects.
# Every removal below first checks the object carries OUR compose project label.
# -------------------------------------------------------------------------------------

# --- 5.8.1 [LAPTOP · PowerShell] Upload the 3 corrected files to both VMs ----------------------
$KEY = "$HOME\.ssh\team_vm_ed25519"; $V95 = "argus-vm095"; $V166 = "argus-vm166"
$APP = "<workspace>\<08 folder>"
foreach ($vm in $V95, $V166) {
  scp -i $KEY "$APP\deploy\lab\compose.lab.yml" "$APP\deploy\lab\workloads\api.py" "$APP\ops\nonint-check.sh" "${vm}:~/"
}

# --- 5.8.2 [VM 0.166 · bash] Install files, recreate the cache without volume, remove OUR old volume ---
sudo cp ~/compose.lab.yml /opt/argus-v18/app/deploy/lab/compose.lab.yml && sudo cp ~/api.py /opt/argus-v18/app/deploy/lab/workloads/api.py && sudo cp ~/nonint-check.sh /opt/argus-v18/app/ops/nonint-check.sh && rm ~/compose.lab.yml ~/api.py ~/nonint-check.sh
V=$(sudo docker inspect -f '{{range .Mounts}}{{if eq .Type "volume"}}{{.Name}}{{end}}{{end}}' argus-lab-cache); echo "cache volume: $V"
P=$(sudo docker volume inspect -f '{{index .Labels "com.docker.compose.project"}}' "$V"); echo "its project: $P"   # expected: argus-lab-workloads
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile base-166 up -d && cd ~
if [ "$P" = "argus-lab-workloads" ] && [ -n "$V" ]; then sudo docker volume rm "$V" && echo "removed OUR volume $V"; else echo "STOP: volume not proven ours - not removed"; fi
sleep 30; sudo docker ps --filter name=argus-lab --format '{{.Names}}  {{.Status}}'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after
# Expected: argus-lab-cache/api Up (api healthy); last line: NO INTERFERENCE

# --- 5.8.3 [VM 0.95 · bash] Install files, replace OUR api twin with the standalone (healthy) one ---
sudo cp ~/compose.lab.yml /opt/argus-v18/app/deploy/lab/compose.lab.yml && sudo cp ~/api.py /opt/argus-v18/app/deploy/lab/workloads/api.py && sudo cp ~/nonint-check.sh /opt/argus-v18/app/ops/nonint-check.sh && rm ~/compose.lab.yml ~/api.py ~/nonint-check.sh
if [ "$(sudo docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' argus-lab-api)" = "argus-lab-workloads" ]; then sudo docker rm -f argus-lab-api; else echo "STOP: argus-lab-api not proven ours"; fi
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile base-095 up -d && cd ~
sleep 35; sudo docker ps --filter name=argus-lab --format '{{.Names}}  {{.Status}}'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after
# Expected: argus-lab-api Up (healthy); last line: NO INTERFERENCE
# >>> Send Claude the output of 5.8.2 and 5.8.3. <<<

# RESULT 5.8 (2026-10-01): vm-095 api twin replaced -> healthy. vm-166 cache recreated, BUT compose kept the
# old anonymous volume attached, and the guard refused to remove it (anonymous volumes carry no compose label).
# nonint-check.sh failed on both VMs: it had Windows CRLF line endings (Python write_text on Windows).
# Fixed: all files converted to LF + a test that blocks CRLF in anything deployed.

# -------------------------------------------------------------------------------------
# TASK 5.9 — LF nonint-check, detach + remove OUR anonymous cache volume, final check   [~3 min]
# Ownership proof for the volume: its ONLY user is our argus-lab-cache container.
# -------------------------------------------------------------------------------------

# --- 5.9.1 [LAPTOP · PowerShell] Upload the LF versions ---------------------------------------
$KEY = "$HOME\.ssh\team_vm_ed25519"; $V95 = "argus-vm095"; $V166 = "argus-vm166"
$APP = "<workspace>\<08 folder>"
foreach ($vm in $V95, $V166) { scp -i $KEY "$APP\ops\nonint-check.sh" "$APP\deploy\lab\compose.lab.yml" "${vm}:~/" }

# --- 5.9.2 [VM 0.166 · bash] -------------------------------------------------------------------
sudo cp ~/nonint-check.sh /opt/argus-v18/app/ops/nonint-check.sh && sudo cp ~/compose.lab.yml /opt/argus-v18/app/deploy/lab/compose.lab.yml && rm ~/nonint-check.sh ~/compose.lab.yml
V=381fd4ad6a921cbe8d95cae921fd6d56be297324286949be3b542b38d518cbac
U=$(sudo docker ps -a --filter volume=$V --format '{{.Names}}' | tr '\n' ' '); echo "users of the volume: [$U]"   # expected: [argus-lab-cache ]
if [ "$U" = "argus-lab-cache " ] && [ "$(sudo docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' argus-lab-cache)" = "argus-lab-workloads" ]; then
  cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile base-166 up -d --force-recreate --renew-anon-volumes argus-lab-cache && cd ~
  sudo docker inspect -f '{{range .Mounts}}{{.Type}}:{{.Destination}} {{end}}' argus-lab-cache          # expected: no "volume:" entry
  [ -z "$(sudo docker ps -a --filter volume=$V -q)" ] && sudo docker volume rm $V && echo "removed OUR volume $V"
else echo "STOP: volume users are not exactly our argus-lab-cache - nothing removed"; fi
sleep 20; sudo docker ps --filter name=argus- --format '{{.Names}}  {{.Status}}'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after
# Expected last line: NO INTERFERENCE: non-Argus objects unchanged

# --- 5.9.3 [VM 0.95 · bash] --------------------------------------------------------------------
sudo cp ~/nonint-check.sh /opt/argus-v18/app/ops/nonint-check.sh && sudo cp ~/compose.lab.yml /opt/argus-v18/app/deploy/lab/compose.lab.yml && rm ~/nonint-check.sh ~/compose.lab.yml
sudo docker ps --filter name=argus- --format '{{.Names}}  {{.Status}}'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after
# Expected last line: NO INTERFERENCE: non-Argus objects unchanged
# >>> Send Claude the output of 5.9.2 and 5.9.3. <<<

# RESULT 5.9 (2026-10-01): vm-166 - our anonymous cache volume removed (sole user argus-lab-cache), NO INTERFERENCE.
# vm-095 - twin healthy, NO INTERFERENCE. Phase 3 COMPLETE. Encrypted migration export done (secrets 1043).

# =====================================================================================
# TASK 6 — Phase 4: the Argus agent on VM 0.95 + first real diagnoses on BOTH hosts   [~15 min]
# argus-v18-agent = API (127.0.0.1:18000 only) + worker, on network argus-v18-core. It reaches vm-095's
# executors directly and vm-166's through argus-v18-tunnel. Runbooks: pinned library commit 056b36e,
# mounted read-only from /opt/argus-runbooks/056b36e (never copied into the code). Write gate CLOSED.
# =====================================================================================

# --- 6.1 [LAPTOP · PowerShell] Package app + pinned runbooks, upload to VM 0.95 ----------------------
$KEY = "$HOME\.ssh\team_vm_ed25519"; $V95 = "argus-vm095"; $V166 = "argus-vm166"
$APP = "<workspace>\<08 folder>"
$RB  = "<workspace>\RunbooksLab"
cd $APP
tar -czf "$env:TEMP\argus-v18-app.tgz" --exclude=.venv --exclude=__pycache__ --exclude=.pytest_cache --exclude=argus.egg-info --exclude=deploy/secrets --exclude=ops/discovery-vm095.txt --exclude=ops/discovery-vm166.txt --exclude=output.bash .
git -C $RB archive --format=tar.gz -o "$env:TEMP\runbooks-056b36e.tgz" 056b36e RUNBOOK-INDEX.md RUNBOOK-CONVENTIONS.md runbooks
scp -i $KEY "$env:TEMP\argus-v18-app.tgz" "$env:TEMP\runbooks-056b36e.tgz" "${V95}:~/"

# --- 6.2 [VM 0.95 · bash] Install app + runbooks, OpenAI key, start the agent — safe to re-run -----
if [ -f ~/argus-v18-app.tgz ]; then sudo rm -rf /opt/argus-v18/app && sudo mkdir -p /opt/argus-v18/app && sudo tar -xzf ~/argus-v18-app.tgz -C /opt/argus-v18/app && rm ~/argus-v18-app.tgz; fi
if [ -f ~/runbooks-056b36e.tgz ]; then sudo install -d -m 755 /opt/argus-runbooks/056b36e && sudo tar -xzf ~/runbooks-056b36e.tgz -C /opt/argus-runbooks/056b36e && rm ~/runbooks-056b36e.tgz; fi
ls /opt/argus-runbooks/056b36e /opt/argus-runbooks/056b36e/runbooks | head -5          # expected: RUNBOOK-*.md, runbooks/, RB-001...
# OpenAI key (the same one the VPS lab uses). Input is HIDDEN: paste, press Enter. Skipped if already present.
sudo test -s /opt/argus-v18/secrets/agent/openai_api_key || { read -rsp "Paste the OpenAI API key, then Enter: " K; echo; printf '%s' "$K" | sudo tee /opt/argus-v18/secrets/agent/openai_api_key >/dev/null; unset K; }
# the agent runs as UID 10010 inside its container: it must be able to read ITS secrets (and nobody else)
sudo chown -R 10010:10010 /opt/argus-v18/secrets/agent && sudo chmod -R u=rX,go= /opt/argus-v18/secrets/agent
sudo find /opt/argus-v18/secrets/agent -type f | sed 's|.*/agent/||' | sort     # expected 8: jwt_signing_key, openai_api_key, vm-095/3 tokens, vm-166/3 tokens
cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose -f compose.core.yml up -d --build --no-deps argus-v18-agent && cd ~
sleep 15; sudo docker logs --tail 15 argus-v18-agent                            # expected: Uvicorn running on :8000 and :8001, no "startup validation failed"
curl -s -o /dev/null -w "swagger %{http_code}\n" http://127.0.0.1:18000/docs   # expected: swagger 200
sudo docker ps --filter name=argus-v18-agent --format '{{.Names}}  {{.Status}}  {{.Ports}}'   # expected port: 127.0.0.1:18000->8000/tcp ONLY

# --- 6.3 [VM 0.95 · bash] Create your operator user (asks a password, >= 10 chars, twice) ------------
sudo docker exec -it argus-v18-agent python -m argus user add <old-operator> --role operator

# --- 6.4 [VM 0.95 · bash] First real diagnoses: healthy checks on BOTH hosts (same container name!) --
sudo docker exec -it -e ARGUS_USER=<old-operator> argus-v18-agent argus diagnose vm-166/container:argus-lab-api --check --reason "is it healthy?"
sudo docker exec -it -e ARGUS_USER=<old-operator> argus-v18-agent argus diagnose vm-095/container:argus-lab-api --check --reason "is it healthy?"
# Expected: both end in RECORD with outcome no_incident, each attributed to ITS host (vm-166 / vm-095).

# --- 6.5 [VM 0.166 · bash] SC-01: start the OOM restart loop and wait for the signal -----------------
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc01 up -d --build argus-lab-worker-oom && cd ~
for i in $(seq 1 24); do R=$(sudo docker inspect -f '{{.RestartCount}}' argus-lab-worker); echo "restarts=$R oom=$(sudo docker inspect -f '{{.State.OOMKilled}}' argus-lab-worker)"; [ "$R" -ge 3 ] && break; sleep 10; done
# Expected: restarts reach 3 (OOMKilled true) within ~2-4 min.

# --- 6.6 [VM 0.95 · bash] Diagnose SC-01 — formatted, then the same incident raw ---------------------
sudo docker exec -it -e ARGUS_USER=<old-operator> argus-v18-agent argus diagnose vm-166/container:argus-lab-worker --reason "keeps restarting"
# Expected: DETECT container_restart_loop -> RECALL RB-001 -> INVESTIGATE/ACT on vm-166 -> RECORD diagnosed: OOM by its own limit.
# Raw view of the same run (replace INC with the incident id printed on the first line):
# sudo docker exec -it -e ARGUS_USER=<old-operator> argus-v18-agent argus incident INC --raw | tail -n 5

# --- 6.7 [VM 0.166 · bash] Reset SC-01 + non-interference -------------------------------------------
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc01 rm -sf argus-lab-worker-oom && cd ~
sudo docker ps --filter name=argus- --format '{{.Names}}  {{.Status}}'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after          # expected: NO INTERFERENCE

# --- 6.8 [VM 0.95 · bash] Non-interference ---------------------------------------------------------
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after          # expected: NO INTERFERENCE (conantkd's argus-* untouched)

# --- 6.9 [LAPTOP · PowerShell] OPTIONAL: Swagger in your browser -> http://127.0.0.1:18000/docs ------
# ssh -i $KEY -N -L 18000:127.0.0.1:18000 $V95          (leave it open; Ctrl+C to close)
# >>> Send Claude the output of 6.2, 6.4, 6.5, 6.6, 6.7 and 6.8. <<<

# RESULT 6 (2026-10-01): agent up (127.0.0.1:18000 only), swagger 200, user <old-operator>. Healthy checks on BOTH hosts =
# no_incident, correct host attribution. SC-01 detected (container_restart_loop, 14 restarts, OOM, exit 137),
# runbooks recalled from commit 056b36e. FAILED at the model: gpt-5.6-luna refuses function tools with reasoning
# on /v1/chat/completions (400). Fixed: adapter now uses the Responses API (/v1/responses); 400 errors are not
# retried; recall now ranks RB-001 first for OOM. NO INTERFERENCE on both VMs.

# =====================================================================================
# TASK 7 — Redeploy the agent (Responses API) and re-run SC-01 end to end   [~6 min]
# Runs from the NEW laptop (verified 2026-10-01: key present, SSH to vm-095 OK, 23 tests pass).
# Also included: a model-provider error now escalates at once (no longer burns the 8-step budget).
# =====================================================================================

# --- 7.1 [LAPTOP · PowerShell] -----------------------------------------------------------------------
$KEY = "$HOME\.ssh\team_vm_ed25519"; $V95 = "argus-vm095"; $V166 = "argus-vm166"
$APP = "<workspace>\<08 folder>"
cd $APP
tar -czf "$env:TEMP\argus-v18-app.tgz" --exclude=.venv --exclude=__pycache__ --exclude=.pytest_cache --exclude=argus.egg-info --exclude=deploy/secrets --exclude=ops/discovery-vm095.txt --exclude=ops/discovery-vm166.txt --exclude=output.bash .
scp -i $KEY "$env:TEMP\argus-v18-app.tgz" "${V95}:~/"

# --- 7.2 [VM 0.95 · bash] Rebuild + restart ONLY the agent (data volume and user <old-operator> are kept) ------
if [ -f ~/argus-v18-app.tgz ]; then sudo rm -rf /opt/argus-v18/app && sudo mkdir -p /opt/argus-v18/app && sudo tar -xzf ~/argus-v18-app.tgz -C /opt/argus-v18/app && rm ~/argus-v18-app.tgz; fi
cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose -f compose.core.yml up -d --build --no-deps argus-v18-agent && cd ~
sleep 12; curl -s http://127.0.0.1:18000/healthz; echo                  # expected: "llm_configured":true

# --- 7.3 [VM 0.166 · bash] Start SC-01 and wait for >= 3 restarts -----------------------------------
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc01 up -d argus-lab-worker-oom && cd ~
for i in $(seq 1 24); do R=$(sudo docker inspect -f '{{.RestartCount}}' argus-lab-worker); echo "restarts=$R"; [ "$R" -ge 3 ] && break; sleep 10; done

# --- 7.4 [VM 0.95 · bash] Diagnose (formatted), then the raw tail of the same incident ---------------
sudo docker exec -it -e ARGUS_USER=<old-operator> argus-v18-agent argus diagnose vm-166/container:argus-lab-worker --reason "keeps restarting"
# Expected: RECALL RB-001 first -> INVESTIGATE/ACT tool calls on vm-166 -> RECORD diagnosed (OOM by its own 64 MiB limit).
# Raw (replace INC with the id printed on the first line):
# sudo docker exec -it -e ARGUS_USER=<old-operator> argus-v18-agent argus incident INC --raw | tail -n 3

# --- 7.5 [VM 0.166 · bash] Reset SC-01 + non-interference -------------------------------------------
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc01 rm -sf argus-lab-worker-oom && cd ~
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after          # expected: NO INTERFERENCE

# --- 7.6 [VM 0.95 · bash] Non-interference ---------------------------------------------------------
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after          # expected: NO INTERFERENCE
# More incidents to try (Swagger bodies + CLI): <08 folder>\docs\INCIDENTS.md
# >>> Send Claude the output of 7.2, 7.4, 7.5 and 7.6. <<<

# RESULT 7 (2026-10-01): agent rebuilt (llm_configured true, Responses API). SC-01 END TO END: detect
# container_restart_loop (6 restarts, OOMKilled, exit 137) -> RECALL RB-001 first -> 3 model steps, 6 reads ALL on
# vm-166 -> RECORD DIAGNOSED, confidence high, root cause vm-166/container:argus-lab-worker ("exceeds its 64 MiB
# limit"; host not under memory pressure; human actions recommended). NO INTERFERENCE on both VMs.

# =====================================================================================
# TASK 8 — More incidents: SC-02, identity proof (SC-01 + SC-02 together), SC-03, SC-09, SC-11   [~15 min]
# Same pattern each time: start the failure -> diagnose from VM 0.95 -> reset. Details: docs\INCIDENTS.md
# The diagnose helper asks <old-operator>'s password ONCE per VM 0.95 shell (kept in a shell variable, never on screen).
# =====================================================================================

# --- 8.0 [VM 0.95 · bash] Helper for this shell (paste once; re-paste if you open a new shell) -------
read -rsp "Argus password for <old-operator>: " ARGUS_PASSWORD; echo; export ARGUS_PASSWORD
argus() { sudo docker exec -it -e ARGUS_USER=<old-operator> -e ARGUS_PASSWORD argus-v18-agent argus "$@"; }

# --- 8.1 [VM 0.95 · bash] SC-02: non-OOM crash loop on vm-095 (same name as SC-01's worker) ----------
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc02 up -d argus-lab-worker-crash && cd ~
for i in $(seq 1 24); do R=$(sudo docker inspect -f '{{.RestartCount}}' argus-lab-worker); echo "restarts=$R oom=$(sudo docker inspect -f '{{.State.OOMKilled}}' argus-lab-worker) exit=$(sudo docker inspect -f '{{.State.ExitCode}}' argus-lab-worker)"; [ "$R" -ge 3 ] && break; sleep 10; done
sleep 30                                                    # let Prometheus scrape the restarts
argus diagnose vm-095/container:argus-lab-worker --reason "keeps restarting"
# Expected: DETECT container_restart_loop (OOMKilled=False, exit 1) -> RECALL RB-008 first -> reads on vm-095 ONLY
# (logs: "FATAL: config file not found") -> RECORD diagnosed: non-OOM crash, missing config. Leave it RUNNING for 8.2.

# --- 8.2 [VM 0.166 · bash] Identity proof, part 1: start SC-01 again on vm-166 -----------------------
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc01 up -d argus-lab-worker-oom && cd ~
for i in $(seq 1 24); do R=$(sudo docker inspect -f '{{.RestartCount}}' argus-lab-worker); echo "restarts=$R"; [ "$R" -ge 3 ] && break; sleep 10; done
sleep 30

# --- 8.3 [VM 0.95 · bash] Identity proof, part 2: the SAME name on both hosts, two diagnoses ---------
argus diagnose vm-166/container:argus-lab-worker --reason "keeps restarting"
argus diagnose vm-095/container:argus-lab-worker --reason "keeps restarting"
# Expected: two incidents; vm-166 = OOM (RB-001), vm-095 = missing config (RB-008); every ACT line shows its OWN host.

# --- 8.4 [VM 0.166 · bash] Reset SC-01 ---------------------------------------------------------------
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc01 rm -sf argus-lab-worker-oom && cd ~

# --- 8.5 [VM 0.95 · bash] Reset SC-02 ----------------------------------------------------------------
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc02 rm -sf argus-lab-worker-crash && cd ~

# --- 8.6 [VM 0.166 · bash] SC-03: stop the cache; the api becomes its victim -------------------------
sudo docker stop argus-lab-cache
sleep 75; sudo docker inspect -f 'api health={{.State.Health.Status}}' argus-lab-api     # expected: unhealthy (or still starting to fail)

# --- 8.7 [VM 0.95 · bash] Diagnose SC-03 -------------------------------------------------------------
argus diagnose vm-166/container:argus-lab-api --reason "api returns errors"
# Expected: DETECT dependency_unavailable (health_check_failed maybe as a finding) -> RECALL RB-003 ->
# RECORD diagnosed, root cause = vm-166/container:argus-lab-cache (the api is the VICTIM; no "restart the api").

# --- 8.8 [VM 0.166 · bash] Reset SC-03 + non-interference -------------------------------------------
sudo docker start argus-lab-cache
sleep 40; sudo docker inspect -f 'api health={{.State.Health.Status}}' argus-lab-api     # expected: healthy
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after          # expected: NO INTERFERENCE

# --- 8.9 [VM 0.95 · bash] SC-09 (no matching class) + SC-11 (not in inventory) + non-interference ---
argus diagnose vm-095/container:argus-lab-api --reason "users see stale data"
# Expected: unsupported_escalated — evidence pack, NO model step, no diagnosis.
argus diagnose vm-166/container:argus-api-1 --reason "check"
# Expected: refused — not in the inventory, nothing read (conantkd's container is never touched).
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after          # expected: NO INTERFERENCE
unset ARGUS_PASSWORD
# >>> Paste everything into output.bash and tell Claude "output.bash updated". <<<

# RESULT 8 (2026-10-01): SC-02 vm-095 DIAGNOSED (non-OOM, missing /etc/worker/config.yml, reads on vm-095 only).
# Identity proof: two incidents, each read ONLY its own host; both diagnoses correct. SC-03 root cause = argus-lab-cache
# (api = victim) BUT the diagnosis text was EMPTY (model sent ""). SC-09 unsupported_escalated (evidence pack, no
# model). SC-11 refused, nothing read. NO INTERFERENCE on both VMs. Bugs found:
#  (1) SC-01's 2nd run was detected as NON-OOM (exit 0): the exporter published Docker's CURRENT State.ExitCode /
#      OOMKilled, which reset when the container runs again -> RB-008 recalled first. Fixed: last exit from die/oom events.
#  (2) empty diagnosis accepted -> now rejected and the model is asked to correct it.
#  (3) the helper still asked the password: sudo drops env vars -> now sudo --preserve-env=ARGUS_PASSWORD.

# =====================================================================================
# TASK 9 — Deploy the fixes (exporter on BOTH VMs + agent) and re-verify SC-01 and SC-03   [~12 min]
# Only argus-v18-* containers are recreated (read-gateway/host-probe/network-probe/exporter share one image).
# =====================================================================================

# --- 9.1 [LAPTOP · PowerShell] Package and upload to BOTH VMs ----------------------------------------
$KEY = "$HOME\.ssh\team_vm_ed25519"; $V95 = "argus-vm095"; $V166 = "argus-vm166"
cd "<workspace>\<08 folder>"
tar -czf "$env:TEMP\argus-v18-app.tgz" --exclude=.venv --exclude=__pycache__ --exclude=.pytest_cache --exclude=argus.egg-info --exclude=deploy/secrets --exclude=ops/discovery-vm095.txt --exclude=ops/discovery-vm166.txt --exclude=output.bash .
scp -i $KEY "$env:TEMP\argus-v18-app.tgz" "${V95}:~/"
scp -i $KEY "$env:TEMP\argus-v18-app.tgz" "${V166}:~/"

# --- 9.2 [VM 0.166 · bash] Install + recreate the 4 target services ---------------------------------
if [ -f ~/argus-v18-app.tgz ]; then sudo rm -rf /opt/argus-v18/app && sudo mkdir -p /opt/argus-v18/app && sudo tar -xzf ~/argus-v18-app.tgz -C /opt/argus-v18/app && rm ~/argus-v18-app.tgz; fi
sudo chmod -R a+rX /opt/argus-v18/app
cd /opt/argus-v18/app/deploy/target && sudo docker compose --env-file vm-166.env -f compose.target.yml -f compose.loopback.yml up -d --build && cd ~
sudo docker ps --filter name=argus-v18 --format '{{.Names}}  {{.Status}}  {{.Ports}}'
# Expected: read-gateway/host-probe/network-probe/exporter "Up a few seconds"; ports still only 127.0.0.1:18701-18703 (+18090 prometheus).

# --- 9.3 [VM 0.95 · bash] Install + recreate the 4 target services + the agent ----------------------
if [ -f ~/argus-v18-app.tgz ]; then sudo rm -rf /opt/argus-v18/app && sudo mkdir -p /opt/argus-v18/app && sudo tar -xzf ~/argus-v18-app.tgz -C /opt/argus-v18/app && rm ~/argus-v18-app.tgz; fi
sudo chmod -R a+rX /opt/argus-v18/app
cd /opt/argus-v18/app/deploy/target && sudo docker compose --env-file vm-095.env -f compose.target.yml -f compose.core-join.yml up -d --build && cd ~
cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose -f compose.core.yml up -d --build --no-deps argus-v18-agent && cd ~
sleep 12; curl -s http://127.0.0.1:18000/healthz; echo                  # expected: "ok":true ... "llm_configured":true
sudo docker ps --filter name=argus-v18 --format '{{.Names}}  {{.Status}}  {{.Ports}}'   # agent "Up ~15 seconds"; only 127.0.0.1:18000

# --- 9.4 [VM 0.166 · bash] SC-01 again: the metric must say 137 / OOM even while the worker RUNS ------
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc01 up -d argus-lab-worker-oom && cd ~
for i in $(seq 1 24); do R=$(sudo docker inspect -f '{{.RestartCount}}' argus-lab-worker); echo "restarts=$R running=$(sudo docker inspect -f '{{.State.Running}}' argus-lab-worker)"; [ "$R" -ge 3 ] && break; sleep 10; done
sleep 25
for m in argus_container_last_exit_code argus_container_oom_killed; do curl -s "http://127.0.0.1:18090/api/v1/query?query=$m%7Bcontainer%3D%22argus-lab-worker%22%7D" | grep -o '"value":\[[^]]*\]' | sed "s/^/$m /"; done
# Expected: last_exit_code ... "137" and oom_killed ... "1" (no longer 0 while the container is running).

# --- 9.5 [VM 0.95 · bash] Diagnose SC-01 (password asked ONCE) -------------------------------------
read -rsp "Argus password for <old-operator>: " ARGUS_PASSWORD; echo; export ARGUS_PASSWORD
argus() { sudo --preserve-env=ARGUS_PASSWORD docker exec -it -e ARGUS_USER=<old-operator> -e ARGUS_PASSWORD argus-v18-agent argus "$@"; }
argus diagnose vm-166/container:argus-lab-worker --reason "keeps restarting"
# Expected: NO second password prompt; DETECT OOMKilled=True, exit 137 -> RECALL RB-001 first -> RECORD diagnosed (OOM, 64 MiB).

# --- 9.6 [VM 0.166 · bash] Reset SC-01, start SC-03 -------------------------------------------------
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc01 rm -sf argus-lab-worker-oom && cd ~
sudo docker stop argus-lab-cache
sleep 75; sudo docker inspect -f 'api health={{.State.Health.Status}}' argus-lab-api     # expected: unhealthy

# --- 9.7 [VM 0.95 · bash] Diagnose SC-03 (same shell as 9.5) ----------------------------------------
argus diagnose vm-166/container:argus-lab-api --reason "api returns errors"
# Expected: root cause vm-166/container:argus-lab-cache AND a non-empty diagnosis box (api = victim).

# --- 9.8 [VM 0.166 · bash] Reset SC-03 + non-interference -------------------------------------------
sudo docker start argus-lab-cache
sleep 40; sudo docker inspect -f 'api health={{.State.Health.Status}}' argus-lab-api     # expected: healthy
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after          # expected: NO INTERFERENCE

# --- 9.9 [VM 0.95 · bash] Non-interference ---------------------------------------------------------
unset ARGUS_PASSWORD
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after          # expected: NO INTERFERENCE
# >>> Paste everything into output.bash and tell Claude "output.bash updated". <<<

# RESULT 9 (2026-10-01): exporter fix live on both VMs: while the SC-01 worker RUNS, Prometheus shows
# last_exit_code=137 and oom_killed=1. SC-01 -> RB-001 first -> DIAGNOSED (OOM at its 64 MiB limit, host not under
# pressure). SC-03 -> root cause argus-lab-cache with a FULL diagnosis text (api = victim). Password asked once.
# NO INTERFERENCE on both VMs. All runnable scenarios now pass: H-1/H-2, SC-01, SC-02, identity proof, SC-03, SC-09, SC-11.

# =====================================================================================
# TASK 10 — Failure isolation: SC-10 (monitoring blind spot on vm-095) + SC-12 (executor partition on vm-166)  [~10 min]
# v1.8: a failure on ONE host must give "undiagnosable"/"escalated" for THAT host only; the other host keeps working.
# Only OUR containers are stopped (argus-v18-exporter on vm-095, argus-v18-read-gateway on vm-166) and restarted.
# =====================================================================================

# --- 10.1 [VM 0.95 · bash] SC-10: stop vm-095's exporter -> vm-095 is blind, vm-166 is not ------------
read -rsp "Argus password for <old-operator>: " ARGUS_PASSWORD; echo; export ARGUS_PASSWORD
argus() { sudo --preserve-env=ARGUS_PASSWORD docker exec -it -e ARGUS_USER=<old-operator> -e ARGUS_PASSWORD argus-v18-agent argus "$@"; }
sudo docker stop argus-v18-exporter
sleep 40                                                    # Prometheus marks the series stale after a failed scrape
argus diagnose vm-095/container:argus-lab-api --check --reason "is it healthy?"
# Expected: DETECT "metrics stale or unavailable", RB-014 -> EVIDENCE_PACK (reads still work) -> UNDIAGNOSABLE, no model.
argus diagnose vm-166/container:argus-lab-api --check --reason "is it healthy?"
# Expected: vm-166 unaffected -> NO_INCIDENT.

# --- 10.2 [VM 0.95 · bash] Reset SC-10 --------------------------------------------------------------
sudo docker start argus-v18-exporter
sleep 40; argus diagnose vm-095/container:argus-lab-api --check --reason "is it healthy?"     # expected: NO_INCIDENT again

# --- 10.3 [VM 0.166 · bash] SC-12: a real incident on vm-166, then cut Argus's Docker reads there ----
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc01 up -d argus-lab-worker-oom && cd ~
for i in $(seq 1 24); do R=$(sudo docker inspect -f '{{.RestartCount}}' argus-lab-worker); echo "restarts=$R"; [ "$R" -ge 3 ] && break; sleep 10; done
sudo docker stop argus-v18-read-gateway
sleep 20

# --- 10.4 [VM 0.95 · bash] Diagnose during the partition ---------------------------------------------
argus diagnose vm-166/container:argus-lab-worker --reason "keeps restarting"
# Expected: DETECT still works (Prometheus is a separate executor) -> every docker@vm-166 read FAILS (unreachable),
# NEVER answered by vm-095 -> ESCALATED, or a diagnosis that cites only the metric evidence and says the docker reads failed.
argus diagnose vm-095/container:argus-lab-api --check --reason "is it healthy?"
# Expected: vm-095 keeps working -> NO_INCIDENT.

# --- 10.5 [VM 0.166 · bash] Reset SC-12 + SC-01 + non-interference -----------------------------------
sudo docker start argus-v18-read-gateway
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc01 rm -sf argus-lab-worker-oom && cd ~
sudo docker ps --filter name=argus-v18 --format '{{.Names}}  {{.Status}}'      # expected: all Up again
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after          # expected: NO INTERFERENCE

# --- 10.6 [VM 0.95 · bash] Non-interference ---------------------------------------------------------
unset ARGUS_PASSWORD
sudo docker ps --filter name=argus-v18 --format '{{.Names}}  {{.Status}}'      # expected: all Up (exporter too)
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after          # expected: NO INTERFERENCE
# >>> Paste everything into output.bash and tell Claude "output.bash updated". <<<

# RESULT 10 (2026-10-01): SC-12 PASSED - with vm-166's read gateway stopped, every docker@vm-166 read failed (never
# answered by vm-095), the model ESCALATED with the evidence it had, and vm-095 stayed healthy. But the model retried the
# dead gateway for 7 steps. SC-10 FAILED (safety bug): with vm-095's exporter stopped, a check said HEALTHY because
# restarts_10m (a range function) still answered 0 from older samples while every other signal was unknown.
# Fixed: (1) a freshness gate - detection first checks up{job="argus-v18-exporter"} for the host; down => undiagnosable;
# (2) an unreachable/timed-out executor is shown to the model as UNAVAILABLE for the rest of the incident.
# NO INTERFERENCE on both VMs.

# =====================================================================================
# TASK 11 — Deploy the two fixes (agent + config on vm-095 only) and re-run SC-10 and SC-12   [~10 min]
# =====================================================================================

# --- 11.1 [LAPTOP · PowerShell] Package and upload to VM 0.95 ---------------------------------------
$KEY = "$HOME\.ssh\team_vm_ed25519"; $V95 = "argus-vm095"
cd "<workspace>\<08 folder>"
tar -czf "$env:TEMP\argus-v18-app.tgz" --exclude=.venv --exclude=__pycache__ --exclude=.pytest_cache --exclude=argus.egg-info --exclude=deploy/secrets --exclude=ops/discovery-vm095.txt --exclude=ops/discovery-vm166.txt --exclude=output.bash .
scp -i $KEY "$env:TEMP\argus-v18-app.tgz" "${V95}:~/"

# --- 11.2 [VM 0.95 · bash] Install + rebuild the agent ---------------------------------------------
if [ -f ~/argus-v18-app.tgz ]; then sudo rm -rf /opt/argus-v18/app && sudo mkdir -p /opt/argus-v18/app && sudo tar -xzf ~/argus-v18-app.tgz -C /opt/argus-v18/app && rm ~/argus-v18-app.tgz; fi
sudo chmod -R a+rX /opt/argus-v18/app
cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose -f compose.core.yml up -d --build --no-deps --force-recreate argus-v18-agent && cd ~
sleep 12; curl -s http://127.0.0.1:18000/healthz; echo                  # expected: "ok":true ... "llm_configured":true

# --- 11.3 [VM 0.95 · bash] SC-10 again: healthy first, then blind --------------------------------------
read -rsp "Argus password for <old-operator>: " ARGUS_PASSWORD; echo; export ARGUS_PASSWORD
argus() { sudo --preserve-env=ARGUS_PASSWORD docker exec -it -e ARGUS_USER=<old-operator> -e ARGUS_PASSWORD argus-v18-agent argus "$@"; }
argus diagnose vm-095/container:argus-lab-api --check --reason "is it healthy?"     # expected: NO_INCIDENT (gate passes)
sudo docker stop argus-v18-exporter
sleep 40
argus diagnose vm-095/container:argus-lab-api --check --reason "is it healthy?"
# Expected: DETECT "exporter scrape is down on vm-095 (monitoring blind spot)", RB-014 -> EVIDENCE_PACK -> UNDIAGNOSABLE.
argus diagnose vm-166/container:argus-lab-api --check --reason "is it healthy?"     # expected: NO_INCIDENT (vm-166 unaffected)
sudo docker start argus-v18-exporter

# --- 11.4 [VM 0.166 · bash] SC-12 again: SC-01 running, then stop OUR read gateway ------------------
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc01 up -d argus-lab-worker-oom && cd ~
for i in $(seq 1 24); do R=$(sudo docker inspect -f '{{.RestartCount}}' argus-lab-worker); echo "restarts=$R"; [ "$R" -ge 3 ] && break; sleep 10; done
sudo docker stop argus-v18-read-gateway
sleep 20

# --- 11.5 [VM 0.95 · bash] Diagnose during the partition (same shell as 11.3) -----------------------
argus diagnose vm-166/container:argus-lab-worker --reason "keeps restarting"
# Expected: the first docker@vm-166 read fails -> the model stops calling docker tools (metrics/host tools only)
# -> ESCALATED in far fewer than 7 steps (or a diagnosis that cites only metric evidence and names the failed reads).

# --- 11.6 [VM 0.166 · bash] Reset + non-interference ------------------------------------------------
sudo docker start argus-v18-read-gateway
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc01 rm -sf argus-lab-worker-oom && cd ~
sudo docker ps --filter name=argus-v18 --format '{{.Names}}  {{.Status}}'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after          # expected: NO INTERFERENCE

# --- 11.7 [VM 0.95 · bash] Non-interference ---------------------------------------------------------
unset ARGUS_PASSWORD
sudo docker ps --filter name=argus-v18 --format '{{.Names}}  {{.Status}}'      # expected: all Up (exporter too)
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after          # expected: NO INTERFERENCE
# >>> Paste everything into output.bash and tell Claude "output.bash updated". <<<

# RESULT 11 (2026-10-01): SC-10 PASSED - exporter stopped => "exporter scrape is down on vm-095 (monitoring blind spot)"
# -> evidence pack -> UNDIAGNOSABLE; vm-166 stayed healthy; healthy again after restart. SC-12 PASSED - after the first
# failed docker@vm-166 read the model used only metrics/host tools and ESCALATED at step 3 (was 7). NO INTERFERENCE on both.
# All runnable scenarios pass. Next: Phase 5 (Postgres) - see AAbrainProject/plans/argus-v1.8-phases-brief.md

# =====================================================================================
# TASK 12 — Phase 5: Postgres becomes the system of record (vm-095 only)   [~15 min]
# argus-v18-postgres (postgres:16-alpine, network argus-v18-core, NO host port, volume argus-v18-pgdata, 256 MiB).
# Schema = deploy/migrations/*.sql applied by ops/db-migrate.sh as the OWNER. The agent connects as argus_runtime:
# no DELETE anywhere, no UPDATE on evidence/audit/run events, no DDL; closed incidents cannot reopen; evidence needs a
# SHA-256. The SQLite history (incidents, evidence, audit, user <old-operator>) is copied in; the SQLite file is KEPT (rollback).
# Passwords are generated ON the VM (never leave it, never printed).
# =====================================================================================

# --- 12.1 [LAPTOP · PowerShell] Package and upload to VM 0.95 ---------------------------------------
$KEY = "$HOME\.ssh\team_vm_ed25519"; $V95 = "argus-vm095"
cd "<workspace>\<08 folder>"
tar -czf "$env:TEMP\argus-v18-app.tgz" --exclude=.venv --exclude=__pycache__ --exclude=.pytest_cache --exclude=argus.egg-info --exclude=deploy/secrets --exclude=ops/discovery-vm095.txt --exclude=ops/discovery-vm166.txt --exclude=output.bash .
scp -i $KEY "$env:TEMP\argus-v18-app.tgz" "${V95}:~/"

# --- 12.2 [VM 0.95 · bash] Install + generate the two database passwords (re-runnable; existing ones are kept) ---
if [ -f ~/argus-v18-app.tgz ]; then sudo rm -rf /opt/argus-v18/app && sudo mkdir -p /opt/argus-v18/app && sudo tar -xzf ~/argus-v18-app.tgz -C /opt/argus-v18/app && rm ~/argus-v18-app.tgz; fi
sudo chmod -R a+rX /opt/argus-v18/app
sudo install -d -m 700 /opt/argus-v18/secrets/postgres
sudo test -s /opt/argus-v18/secrets/postgres/owner_password || sudo sh -c 'openssl rand -hex 24 > /opt/argus-v18/secrets/postgres/owner_password'
sudo chown 70:70 /opt/argus-v18/secrets/postgres/owner_password && sudo chmod 400 /opt/argus-v18/secrets/postgres/owner_password   # uid 70 = postgres (alpine)
sudo test -s /opt/argus-v18/secrets/agent/db_password || sudo sh -c 'openssl rand -hex 24 > /opt/argus-v18/secrets/agent/db_password'
sudo chown 10010:10010 /opt/argus-v18/secrets/agent/db_password && sudo chmod 400 /opt/argus-v18/secrets/agent/db_password
sudo sh -c 'ls -l /opt/argus-v18/secrets/postgres/ /opt/argus-v18/secrets/agent/db_password'   # expected: two files, -r-------- (no content shown)

# --- 12.3 [VM 0.95 · bash] Start Postgres, apply the schema ------------------------------------------
cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose -f compose.core.yml up -d argus-v18-postgres && cd ~
for i in $(seq 1 30); do S=$(sudo docker inspect -f '{{.State.Health.Status}}' argus-v18-postgres); echo "postgres $S"; [ "$S" = healthy ] && break; sleep 3; done
sudo bash /opt/argus-v18/app/ops/db-migrate.sh
# Expected: "+ 001_init applied", "argus_runtime password set", "schema: 001_init". Re-running prints "= 001_init (already applied)".

# --- 12.4 [VM 0.95 · bash] New agent image; copy the SQLite history; start the agent on Postgres -----
cd /opt/argus-v18/app/deploy/vm-095
sudo docker compose -f compose.core.yml build argus-v18-agent
sudo docker compose -f compose.core.yml stop argus-v18-agent
sudo docker compose -f compose.core.yml run --rm --no-deps argus-v18-agent python -m argus db import-sqlite /data/argus.db
# Expected: "imported (new rows): incident=N, evidence=N, audit=N, principal=1, run_event=N, notification=N"
sudo docker compose -f compose.core.yml up -d --no-deps --force-recreate argus-v18-agent && cd ~
sleep 15; curl -s http://127.0.0.1:18000/healthz; echo                  # expected: "ok":true ... "llm_configured":true
sudo docker logs --tail 5 argus-v18-agent                               # expected: Uvicorn running, no Traceback
sudo docker exec argus-v18-agent python -m argus db check
# Expected: 13/13 database checks passed (UPDATE/DELETE/TRUNCATE evidence+audit refused, closed incident cannot reopen, ...)
sudo docker ps --filter name=argus-v18 --format '{{.Names}}  {{.Status}}  {{.Ports}}'   # postgres: NO ports; agent: only 127.0.0.1:18000

# --- 12.5 [VM 0.95 · bash] Prove it: login (<old-operator> migrated), old history, new runs, Postgres restart -----
read -rsp "Argus password for <old-operator>: " ARGUS_PASSWORD; echo; export ARGUS_PASSWORD
argus() { sudo --preserve-env=ARGUS_PASSWORD docker exec -it -e ARGUS_USER=<old-operator> -e ARGUS_PASSWORD argus-v18-agent argus "$@"; }
argus incident inc_575f7ddf94bd | tail -n 8          # Task 9's SC-01, now read from Postgres: DIAGNOSED, cited evidence
argus diagnose vm-166/container:argus-lab-api --check --reason "is it healthy?"            # expected: NO_INCIDENT
argus diagnose vm-095/container:argus-lab-api --reason "users see stale data"               # expected: UNSUPPORTED, evidence pack stored
sudo docker restart argus-v18-postgres; sleep 20
argus diagnose vm-095/container:argus-lab-api --check --reason "after a postgres restart"   # expected: NO_INCIDENT (pool reconnected)
sudo docker exec argus-v18-postgres psql -U argus_owner -d argus -c "SELECT (SELECT count(*) FROM incident) AS incidents, (SELECT count(*) FROM evidence) AS evidence, (SELECT count(*) FROM audit) AS audit, (SELECT count(*) FROM principal) AS users"
unset ARGUS_PASSWORD

# --- 12.6 [VM 0.95 · bash] Non-interference ---------------------------------------------------------
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after          # expected: NO INTERFERENCE (argus-v18-pgdata is ours)

# --- 12.7 [VM 0.95 · bash] ROLLBACK (only if needed): back to SQLite; Postgres keeps its data ----------
# cd /opt/argus-v18/app/deploy/vm-095 && sudo ARGUS_DB_BACKEND=sqlite docker compose -f compose.core.yml up -d --no-deps --force-recreate argus-v18-agent && cd ~
# >>> Paste everything into output.bash and tell Claude "output.bash updated". <<<

# RESULT 12 (2026-10-02): PHASE 5 LIVE. argus-v18-postgres healthy (no host port, volume argus-v18-pgdata); 001_init
# applied; SQLite history imported (incident=24, evidence=104, audit=237, principal=1, run_event=274, notification=7);
# agent on Postgres; db check 13/13 as argus_runtime. <old-operator> logged in (migrated); Task 9's SC-01 read back from Postgres;
# H-1 no_incident, SC-09 unsupported (evidence pack stored); after `docker restart argus-v18-postgres` the next run
# worked (pool reconnected). Totals: 27 incidents, 116 evidence, 258 audit, 1 user. NO INTERFERENCE on vm-095.
# Note: the SSH session dropped once (client_loop reset) - network only; vm-095 says "System restart required"
# (conantkd's VM: do NOT reboot without him).

# =====================================================================================
# TASK 12b — Team logins: 3 Argus users with ONE shared password; disable "<old-operator>"   [~5 min]
# (T-0013 stays reserved for the Phase 9 pilot.) Users = GitHub handles: juanbetancurm, conantkd, juanes6554, role
# operator. Same password for the three (agreed 2026-10-02) - the audit trail still records WHO ran each investigation.
# The password: >= 10 characters, typed ONLY at the hidden prompts; share it privately (password manager / direct
# message) - NEVER in code.bash, output.bash, the Brain, a commit or a chat with the AI.
# Stored only as an argon2 hash in Postgres (table principal). Nothing else changes; no restart needed.
# =====================================================================================

# --- 12b.1 [VM 0.95 · bash] Create the three users (each asks the password twice: type the SAME shared password) ---
for U in juanbetancurm conantkd juanes6554; do sudo docker exec -it argus-v18-agent python -m argus user add "$U" --role operator; done
# Expected, 3 times: "user <name> saved with role operator"

# --- 12b.2 [VM 0.95 · bash] Each user can log in and run a (cheap, no-AI) healthy check ---------------------
read -rsp "Shared Argus password: " ARGUS_PASSWORD; echo; export ARGUS_PASSWORD
for U in juanbetancurm conantkd juanes6554; do sudo --preserve-env=ARGUS_PASSWORD docker exec -i -e ARGUS_USER="$U" -e ARGUS_PASSWORD argus-v18-agent argus diagnose vm-095/container:argus-lab-api --check --reason "login test $U" | grep -E "^incident|outcome"; done
# Expected, 3 times: "incident inc_..." and "outcome: HEALTHY"

# --- 12b.3 [VM 0.95 · bash] Disable the old personal user "<old-operator>" and prove it can no longer log in -----------
sudo docker exec -it argus-v18-agent python -m argus user disable <old-operator>            # expected: disabled <old-operator>
curl -s -o /dev/null -w "<old-operator> login -> HTTP %{http_code}\n" -X POST http://127.0.0.1:18000/api/v1/auth/token -d "username=<old-operator>&password=wrong-on-purpose"
# Expected: <old-operator> login -> HTTP 401 (nothing secret is sent: the password above is deliberately wrong)
sudo docker exec argus-v18-postgres psql -U argus_owner -d argus -c "SELECT id, role, disabled FROM principal ORDER BY id"
# Expected: conantkd/juanbetancurm/juanes6554 operator false; <old-operator> operator true (no password hashes shown)
unset ARGUS_PASSWORD

# --- From now on, the helper for ANY developer (replace <you> with your GitHub handle) -----------------------
# read -rsp "Shared Argus password: " ARGUS_PASSWORD; echo; export ARGUS_PASSWORD
# argus() { sudo --preserve-env=ARGUS_PASSWORD docker exec -it -e ARGUS_USER=<you> -e ARGUS_PASSWORD argus-v18-agent argus "$@"; }
# Swagger (Authorize): username = your GitHub handle, password = the shared password.
# To change the shared password later: re-run 12b.1 with the new password (it updates the three users).
# >>> Paste the output into output.bash (it contains no secret) and tell Claude "output.bash updated". <<<

# RESULT 12b (2026-10-02): users juanbetancurm, conantkd, juanes6554 saved (operator, one shared password); <old-operator> disabled
# (principal table: <old-operator> disabled=t). 12b.2 (login test per user) NOT run yet - run it once from any laptop.


# =====================================================================================
# TASK 12c — Shared Brain step B2: VM-local hosts.env + read-only checks   [~5 min]
# The new repo (wwfinal_project\argus_production, NOT pushed yet) no longer contains private IPs: the tunnel and
# ops/*.sh read them from /opt/argus-v18/hosts.env on each VM (never committed). This task only CREATES that small
# file and CHECKS that it matches what the running tunnel already uses. No container is restarted or rebuilt.
# Also: 12b.2 (login test per user) is still pending - run it at the end of this task if you have the password at hand.
# =====================================================================================

# --- 12c.1 [VM 0.95 · bash] Create hosts.env (only if missing) and compare it with the LIVE tunnel ----------
sudo test -f /opt/argus-v18/hosts.env || printf 'ARGUS_VM095_PRIVATE_IP=<vm-095 private IP>\nARGUS_VM166_PRIVATE_IP=<vm-166 private IP>\n' | sudo tee /opt/argus-v18/hosts.env >/dev/null
sudo chmod 644 /opt/argus-v18/hosts.env; cat /opt/argus-v18/hosts.env
. /opt/argus-v18/hosts.env
hostname -I | grep -qw "$ARGUS_VM095_PRIVATE_IP" && echo "THIS HOST IS vm-095: OK" || echo "STOP: this is not vm-095"
LIVE=$(sudo docker inspect argus-v18-tunnel --format '{{json .Config.Entrypoint}} {{json .Config.Cmd}}' | grep -o 'argus-v18-tunnel@[0-9.]*')
[ "$LIVE" = "argus-v18-tunnel@$ARGUS_VM166_PRIVATE_IP" ] && echo "TUNNEL TARGET MATCHES hosts.env" || echo "MISMATCH: live=$LIVE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after          # expected: NO INTERFERENCE
# Expected: the two lines of hosts.env, "THIS HOST IS vm-095: OK", "TUNNEL TARGET MATCHES hosts.env", NO INTERFERENCE

# --- 12c.2 [VM 0.166 · bash] Same file on vm-166 (used by ops/reachability.sh and ops/vm-discovery.sh) -------
sudo test -f /opt/argus-v18/hosts.env || printf 'ARGUS_VM095_PRIVATE_IP=<vm-095 private IP>\nARGUS_VM166_PRIVATE_IP=<vm-166 private IP>\n' | sudo tee /opt/argus-v18/hosts.env >/dev/null
sudo chmod 644 /opt/argus-v18/hosts.env; cat /opt/argus-v18/hosts.env
. /opt/argus-v18/hosts.env
hostname -I | grep -qw "$ARGUS_VM166_PRIVATE_IP" && echo "THIS HOST IS vm-166: OK" || echo "STOP: this is not vm-166"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after          # expected: NO INTERFERENCE

# --- 12c.3 [LAPTOP · PowerShell] SSH aliases used by the new repo's docs (adds them only if missing) ---------
# The repo's docs say `ssh argus-vm095` / `ssh argus-vm166` instead of public IPs.
$CFG = "$HOME\.ssh\config"
if (-not (Select-String -Path $CFG -Pattern '^Host argus-vm095' -Quiet)) {
  Add-Content -Encoding ascii $CFG "`nHost argus-vm095`n    HostName <vm-095 public address>`n    User ubuntu`n    IdentityFile ~/.ssh/team_vm_ed25519`n`nHost argus-vm166`n    HostName <vm-166 public address>`n    User ubuntu`n    IdentityFile ~/.ssh/team_vm_ed25519`n"
}
ssh -o BatchMode=yes argus-vm095 hostname       # expected: vm-appsvnic
ssh -o BatchMode=yes argus-vm166 hostname       # expected: agent-test-vnic

# --- 12c.4 [VM 0.95 · bash] (optional, pending from 12b) the login test per user: run 12b.2 as written -------
# >>> Paste everything into output.bash (no secrets in it) and tell Claude "output.bash updated". <<<

# RESULT 12c (2026-10-02): hosts.env created on both VMs (0644); vm-095 live tunnel target MATCHES hosts.env;
# NO INTERFERENCE on both VMs; laptop aliases argus-vm095 / argus-vm166 work. 12b.2 (login test) still NOT run.
