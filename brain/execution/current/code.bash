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

# (no block yet: next is T-0020 step 4, Brain + PR; the leaker's tmpfs fix reaches vm-166 with the next checkout)

# =====================================================================================
# AFTER-MERGE T-0020 — vm-166 back on main (checkout only)                                           [~3 min]
# Why: the T-0020 PR is merged; vm-166 still runs task/T-0020-sc04-pg-connections b1e7176. main now has the same
#      target-side code (db-probe metrics, Prometheus job, the sc04 leaker with its tmpfs), so nothing is rebuilt.
# MUTATES: the git checkout under /opt/argus-v18/app and /opt/argus-v18/DEPLOYED only; no container is restarted.
# NOT vm-095: it runs task/T-0021-tool-isolation; main's api and worker would not start there before PR #36 merges.
# Undo: sudo bash /opt/argus-v18/app/ops/deploy.sh task/T-0020-sc04-pg-connections --as <you>
# Lease: whoever runs it (brain.py start); replace <you> with your handle.
# =====================================================================================

# --- M.1 [VM vm-166 · bash] (ssh argus-vm166) -------------------------------------------------------------------------
grep -q "holder=<you> " /opt/argus-v18/SESSION && echo "SESSION OK" || echo "NOT YOUR SESSION"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh main --as <you> | tail -8
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo docker ps --format '{{.Names}}' | grep -c '^argus-lab-leaker$'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: DEPLOY OK: <main head> (main); its rebuild hints can be ignored (the same code already runs); ref=main;
#           LAB BASELINE OK; 0 (no leaker running); NO INTERFERENCE.
# VERDICT: all as expected -> OK · anything else -> STOP and read the full output.


# =====================================================================================
# T-0023 steps 02-03 — vm-166: the lab filesystem, deploy, SC-05 (disk almost full)                 [~25 min]
# Why: SC-05 needs a filesystem that may fill without touching the root disk, node-exporter and the host-probe that
#      see it, and the disk_pressure signals; then the filler fills it to 92 %.
# MUTATES (vm-166 only):
#   - HOST: a 256M ext4 image /opt/argus-v18/lab/fill.img loop-mounted at /srv/argus-lab-fill (nodev,nosuid,noexec;
#     ops/lab-fill-mount.sh; not in fstab). Kept after the run (the lab filesystem, empty) for the diagnosis later;
#   - checkout task/T-0023-sc05-disk; target services rebuilt (rslave, not-mounted check); node-exporter recreated
#     (rslave); Prometheus recreated (HostDiskPressure on every real filesystem);
#   - for the run: argus-lab-filler (sc05) writes /srv/argus-lab-fill/argus-lab-filler.dat, then is removed with it.
# Undo: S.2 (filler and file); sudo sh /opt/argus-v18/app/ops/lab-fill-mount.sh --remove (the mount and the image);
#       deploy.sh task/OP-010-reserved-slot + rebuild the target services + recreate node-exporter and Prometheus.
# Lease: conantkd (session d77b4b79ab5a).
# =====================================================================================

# --- M.1 [VM vm-166 · bash] (ssh argus-vm166) mount, deploy, recreate ------------------------------------------------
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh task/T-0023-sc05-disk --as $ME | tail -1
sudo sh /opt/argus-v18/app/ops/lab-fill-mount.sh
cd /opt/argus-v18/app/deploy/target && sudo docker compose --env-file vm-166.env -f compose.target.yml -f compose.loopback.yml up -d --build 2>&1 | grep -E 'Recreated|Error' | tail -6
cd /opt/argus-v18/app/deploy/monitoring && sudo docker compose --env-file vm-166.env -f compose.monitoring.yml -f compose.loopback.yml up -d 2>&1 | grep -E 'Recreated|Error' | tail -3
sudo docker compose --env-file vm-166.env -f compose.monitoring.yml -f compose.loopback.yml up -d --force-recreate --no-deps argus-v18-prometheus 2>&1 | tail -1; cd ~
# Expected: SESSION OK; baseline saved; DEPLOY OK (task/T-0023-sc05-disk); "lab-fill: mounted /srv/argus-lab-fill
#           size=2xxM used=1%"; host-probe (and the others) recreated; node-exporter recreated; Prometheus started.

# --- M.2 [VM vm-166 · bash] verify: the mount is seen by node-exporter, the signal and the host-probe (wait ~60 s) ----
Q() { curl -s --get http://127.0.0.1:18090/api/v1/query --data-urlencode "query=$1" | python3 -c 'import json,sys
r=json.load(sys.stdin)["data"]["result"]
print(" ".join(x["metric"].get("mountpoint", "") + "=" + x["value"][1][:8] for x in r) or "none")'; }
M='mountpoint=~"/|/srv/argus-lab-fill"'
echo "fs size MiB: $(Q "node_filesystem_size_bytes{argus_host=\"vm-166\",$M} / 2^20")"
echo "fstype of the lab fs: $(curl -s --get http://127.0.0.1:18090/api/v1/query --data-urlencode 'query=node_filesystem_size_bytes{mountpoint="/srv/argus-lab-fill"}' | python3 -c 'import json,sys; r=json.load(sys.stdin)["data"]["result"]; print(r[0]["metric"].get("fstype") if r else "none")')"
echo "host_disk_used_ratio_5m: $(Q "max(min_over_time((1 - node_filesystem_avail_bytes{argus_host=\"vm-166\",$M} / node_filesystem_size_bytes{argus_host=\"vm-166\",$M})[5m:30s]))")"
T=$(sudo cat /opt/argus-v18/secrets/host_probe_token)
echo "host-probe /disk lab: $(curl -s -H "Authorization: Bearer $T" 'http://127.0.0.1:18702/disk?mount=/srv/argus-lab-fill')"; unset T
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^ref=|LAB BASELINE'
# Expected: sizes for "/" (~50000) and "/srv/argus-lab-fill" (~240); fstype ext4; ratio ~0.27 (the root disk is the
#           worst declared mount now); host-probe: mount /srv/argus-lab-fill, total_mib ~240, used_percent ~0-1
#           (NOT the root disk's ~27 %); ref=task/T-0023-sc05-disk; LAB BASELINE OK.
# VERDICT: all as expected -> go on to S.1 · the lab fs missing or reading like the root disk -> STOP.

# --- S.1 [VM vm-166 · bash] SC-05: the filler fills the lab filesystem to 92 % (MUTATES; ~12 min) --------------------
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc05 up -d argus-lab-filler 2>&1 | tail -1; cd ~
sleep 20; sudo docker logs --tail 2 argus-lab-filler 2>&1
L='mountpoint="/srv/argus-lab-fill"'
U="max(min_over_time((1 - node_filesystem_avail_bytes{argus_host=\"vm-166\",$M} / node_filesystem_size_bytes{argus_host=\"vm-166\",$M})[5m:30s]))"
H="min(node_filesystem_avail_bytes{argus_host=\"vm-166\",$M} / (-deriv(node_filesystem_avail_bytes{argus_host=\"vm-166\",$M}[15m]) > 0)) / 3600"
for i in $(seq 1 60); do u=$(Q "$U" | cut -d= -f2); a=$(Q 'count(ALERTS{alertname="HostDiskPressure",alertstate="firing"}) or vector(0)' | cut -d= -f2); echo "$(date -u +%H:%M:%S) lab_used=$(Q "1 - node_filesystem_avail_bytes{$L} / node_filesystem_size_bytes{$L}" | cut -d= -f2) used_5m=$u hours_to_full=$(Q "$H" | cut -d= -f2) alert=$a"; [ "$a" = 1 ] && python3 -c "import sys; sys.exit(0 if float('$u') >= 0.9 else 1)" 2>/dev/null && break; sleep 15; done
sudo docker logs --tail 1 argus-lab-filler 2>&1
echo "in vm-166's Alertmanager: $(curl -s 'http://127.0.0.1:18091/api/v2/alerts?active=true' | python3 -c 'import json,sys; print([a["labels"].get("alertname") for a in json.load(sys.stdin)])')"
# Expected: "filler: /fill is ~240 MiB"; lab_used rises ~17 %/min (2 MiB every 3 s) to 0.92; hours_to_full small while it grows; after
#           5 min at >= 0.9: used_5m >= 0.9 and alert=1; "reached 92.x%"; HostDiskPressure in the Alertmanager.
# VERDICT: used_5m >= 0.9 and alert=1 -> OK · the root disk changes or the filler refuses -> STOP (S.2).

# --- S.2 [VM vm-166 · bash] reset: remove the filler and its file; the lab filesystem stays (MUTATES) ---------------
sudo docker rm -f argus-lab-filler
sudo rm -f /srv/argus-lab-fill/argus-lab-filler.dat
df -h /srv/argus-lab-fill | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^ref=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -3
# Expected: the lab filesystem back to ~1 %; ref=task/T-0023-sc05-disk; LAB BASELINE OK; NO INTERFERENCE.
