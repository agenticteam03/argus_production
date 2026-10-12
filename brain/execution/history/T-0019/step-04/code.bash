# (archived) T-0019 batch 2 step 01 (history step-04), run 2026-10-12 by the agent over SSH (session cd4367edd721)
# T-0019 batch 2, step 01 — read-only checks on vm-166 before the new host-probe verbs              [~3 min]
# Why: the verbs load, io, top_processes, socket_summary, directory_sizes and kernel_oom_records read the host's
#      /proc, /sys and logs from inside argus-v18-host-probe (root in the container, no extra capability, /proc and /
#      mounted read-only). Before writing them: what the kernel offers (PSI, cgroup v2, block devices), what the
#      container can read (other processes, pid 1's network namespace, kernel log), and how big the walk of a
#      declared mount is. Nothing is changed (the SESSION marker is the session's own file).
# MUTATES: /opt/argus-v18/SESSION only (the session marker).
# =====================================================================================

# --- S1.1 [VM vm-166 · bash] (ssh argus-vm166) --------------------------------------------------------------------
echo 'holder=conantkd session=cd4367edd721' | sudo tee /opt/argus-v18/SESSION >/dev/null
grep -q "^holder=conantkd " /opt/argus-v18/SESSION && echo "SESSION OK" || echo "NOT YOUR SESSION - stop here"
sudo bash /opt/argus-v18/app/ops/deploy.sh status 2>&1 | tail -3
. /etc/os-release; echo "os=$PRETTY_NAME kernel=$(uname -r) arch=$(uname -m)"
echo "cgroup fs=$(stat -fc %T /sys/fs/cgroup)  psi=$(ls /proc/pressure 2>/dev/null | tr '\n' ' ')"
echo "proc mount options: $(awk '$2=="/proc" {print $4}' /proc/mounts)"
echo "kernel.dmesg_restrict=$(sysctl -n kernel.dmesg_restrict)  oom_kill since boot=$(awk '/^oom_kill /{print $2}' /proc/vmstat)"
echo "block devices: $(awk '$3 !~ /^(loop|ram|zram)/ && $3 !~ /[0-9]p?[0-9]+$/ {print $3}' /proc/diskstats | tr '\n' ' ')"
for f in /var/log/kern.log /var/log/syslog /var/log/messages; do [ -e "$f" ] && echo "$f present, oom lines=$(sudo grep -c -E 'Out of memory|oom-kill:|Killed process' "$f")"; done
echo "journal persistent: $([ -d /var/log/journal ] && echo yes || echo no)"
P=argus-v18-host-probe
sudo docker exec $P sh -c 'echo "in probe: pids visible=$(ls /host/proc | grep -c "^[0-9]") uid=$(id -u)"'
sudo docker exec $P sh -c 'head -3 /host/proc/1/net/sockstat 2>&1 | sed "s/^/  pid1 sockstat: /"'
sudo docker exec $P sh -c 'echo "  pid1 tcp lines=$(wc -l < /host/proc/1/net/tcp 2>&1) tcp6 lines=$(wc -l < /host/proc/1/net/tcp6 2>&1)"'
sudo docker exec $P sh -c 'pid=$(pgrep -o dockerd 2>/dev/null || ls /host/proc | grep "^[0-9]" | tail -1); echo "  other-process stat readable: $(cut -d" " -f2 /host/proc/$pid/stat 2>&1 | head -1) cgroup line: $(head -c 60 /host/proc/$pid/cgroup 2>&1)"'
sudo docker exec $P sh -c 'n=$(ls -d /rootfs/sys/fs/cgroup/system.slice/docker-*.scope 2>/dev/null | wc -l); echo "  container cgroups seen: $n"; f=$(ls -d /rootfs/sys/fs/cgroup/system.slice/docker-*.scope 2>/dev/null | head -1); [ -n "$f" ] && echo "  memory.events: $(tr "\n" " " < $f/memory.events)"'
sudo docker exec $P sh -c 'for f in /rootfs/var/log/kern.log /rootfs/var/log/syslog /rootfs/var/log/messages; do [ -e $f ] && echo "  $f readable in probe: $(head -c 1 $f >/dev/null 2>&1 && echo yes || echo no)"; done; true'
sudo docker exec $P sh -c 'ls /host/proc/pressure 2>&1 | tr "\n" " " | sed "s/^/  psi in probe: /"; echo'
cfg=$(ls /opt/argus-v18/app/deploy/target/config/*.json | grep -v vm-095 | head -1)
sudo python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print('declared mounts:', d.get('mounts'))" "$cfg"
for m in $(sudo python3 -c "import json,sys; print(' '.join(json.load(open(sys.argv[1])).get('mounts',[])))" "$cfg"); do
  s=$(date +%s%N); n=$(sudo find "$m" -xdev 2>/dev/null | head -200000 | wc -l); e=$(( ($(date +%s%N)-s)/1000000 ))
  echo "walk $m: entries=$n (capped 200000) in ${e} ms; top-level dirs=$(sudo find "$m" -xdev -mindepth 1 -maxdepth 1 2>/dev/null | wc -l)"
done
sudo docker stats --no-stream --format '{{.Name}} mem={{.MemUsage}} cpu={{.CPUPerc}}' $P
free -m | awk '/^Mem:/ {print "mem total="$2"MB available="$7"MB"}'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: SESSION OK; LAB BASELINE OK; cgroup2fs; psi cpu io memory; the probe sees every pid (no hidepid) and
#           pid 1's sockstat; a kernel log file readable in the probe (or none: then OOM records come from cgroup
#           memory.events and /proc/vmstat only); the walk of the lab fill mount is small; NO INTERFERENCE.

# --- S1.2 [VM vm-166 · bash] (ssh argus-vm166) — follow-up: where the kernel's OOM records are ---------------------
# Why: S1.1 showed oom_kill=18567 since boot but 0 OOM lines in today's kern.log. Counts and formats only; process
#      and cgroup names are masked before printing.
grep -q "^holder=conantkd " /opt/argus-v18/SESSION || exit 1
ls /var/log/kern.log* | tr '\n' ' '; echo
for f in /var/log/kern.log.1 /var/log/kern.log.2.gz; do [ -e $f ] && echo "$f oom lines=$(sudo zgrep -c -E 'oom-kill:|Killed process' $f)"; done
echo "journal kernel oom (last 7 days): $(sudo journalctl -k --since '-7d' --no-pager -o cat 2>/dev/null | grep -c -E 'oom-kill:|Killed process')"
sudo grep -m1 -E 'oom-kill:' /var/log/kern.log.1 | sed -E 's/(task=)[^,]*/\1<name>/; s/(oom_memcg=|task_memcg=)[^,]*/\1<cg>/g' | cut -c1-120
sudo grep -m1 -E 'Killed process' /var/log/kern.log.1 | sed -E 's/\(([^)]*)\)/(<name>)/' | cut -c1-230
ls -la /var/log/kern.log /var/log/kern.log.1 | awk '{print $5, $6, $7, $8, $9}'
grep -E 'rotate|weekly' /etc/logrotate.d/rsyslog | head -2; grep -rh "FileFormat" /etc/rsyslog.conf /etc/rsyslog.d/ | head -1
