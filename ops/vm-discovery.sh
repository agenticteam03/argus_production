#!/usr/bin/env bash
# Argus v1.8 — READ-ONLY discovery for VM 0.95 and VM 0.166 (same script on both).
#
# It changes nothing: no file is created or modified, no service/container/network is touched,
# no package is installed, no firewall rule changes. Output goes to stdout only.
# It never prints environment variables, .env contents, secrets or `docker inspect` Env sections.
#
# Run on each VM:   sudo bash vm-discovery.sh > discovery-$(hostname)-$(date +%Y%m%d-%H%M).txt 2>&1

set -u
export LC_ALL=C
T=15
HOSTS_ENV=${ARGUS_HOSTS_ENV:-/opt/argus-v18/hosts.env}   # VM-local, never committed (template: deploy/hosts.env.example)
# shellcheck source=/dev/null   # hosts.env exists only on the VMs
[ -r "$HOSTS_ENV" ] && . "$HOSTS_ENV"
V95="${ARGUS_VM095_PRIVATE_IP:-unset}"; V166="${ARGUS_VM166_PRIVATE_IP:-unset}"
PEERS="$V95 $V166"                                # private IPs of VM 0.95 and VM 0.166
# Candidate ports for Argus v1.8 (plan §3). The script only reports whether they are free.
CANDIDATE_PORTS="18000 18001 18090 18093 18100 18180 18701 18702 18703 18704 18705"
# Ports of existing / earlier services worth testing across the private network.
KNOWN_PORTS="22 8080 9090 9091 9100 9101"

section() { printf '\n\n===== %s =====\n' "$1"; }
run() { local d="$1"; shift; printf '\n--- %s\n$ %s\n' "$d" "$*"; timeout "$T" "$@" 2>&1 || printf '(exit %s)\n' "$?"; }
have() { command -v "$1" >/dev/null 2>&1; }

section "0. WHICH MACHINE IS THIS"
MYIPS=$(hostname -I 2>/dev/null)
ROLE="UNKNOWN"
case " $MYIPS " in
  *" $V95 "*) ROLE="VM 0.95  (vm-095, private $V95)";;
  *" $V166 "*) ROLE="VM 0.166 (vm-166, private $V166)";;
esac
echo "MACHINE: $ROLE"
echo "hostname: $(hostname)   ips: $MYIPS"
run "date (UTC)" date -u
run "running as (SUDO_USER shows who ran sudo)" sh -c 'id; echo "SUDO_USER=${SUDO_USER:-none}"'

section "1. OS, kernel, CPU, memory, disk"
run "os-release" sh -c '. /etc/os-release; echo "$PRETTY_NAME"'
run "kernel / arch" uname -srm
run "virtualisation" systemd-detect-virt
run "uptime/load" uptime
run "cpu" sh -c 'nproc; lscpu | grep -E "Model name|Architecture|^CPU\(s\)"'
run "memory" free -m
run "swap" swapon --show
run "pressure (PSI)" sh -c 'for f in cpu memory io; do echo "$f: $(head -1 /proc/pressure/$f 2>/dev/null)"; done'
run "top memory processes" sh -c 'ps -eo pid,user,rss,comm --sort=-rss | head -20'
run "filesystems" df -hT -x tmpfs -x devtmpfs -x squashfs -x overlay
run "inodes" df -i -x tmpfs -x devtmpfs -x squashfs -x overlay
run "cgroup version" stat -fc %T /sys/fs/cgroup
run "dmesg restricted / ip_forward" sh -c 'echo "dmesg_restrict=$(sysctl -n kernel.dmesg_restrict) ip_forward=$(sysctl -n net.ipv4.ip_forward)"'
run "journald on disk" journalctl --disk-usage

section "2. Docker"
if have docker; then
  run "versions" sh -c 'docker version --format "client={{.Client.Version}} server={{.Server.Version}}"; docker compose version'
  run "engine (selected)" docker info --format 'driver={{.Driver}} cgroup={{.CgroupDriver}}/v{{.CgroupVersion}} root={{.DockerRootDir}} containers={{.Containers}} running={{.ContainersRunning}} images={{.Images}} logdriver={{.LoggingDriver}}'
  run "daemon.json" sh -c 'cat /etc/docker/daemon.json 2>/dev/null || echo "none"'
  run "compose projects" docker compose ls --all
  run "containers (all)" docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}\t{{.Networks}}'
  run "limits / restart / socket mount / project (no Env)" sh -c \
    'docker ps -aq | xargs -r docker inspect --format "{{.Name}} mem={{.HostConfig.Memory}} memswap={{.HostConfig.MemorySwap}} cpus={{.HostConfig.NanoCpus}} restart={{.HostConfig.RestartPolicy.Name}} privileged={{.HostConfig.Privileged}} netmode={{.HostConfig.NetworkMode}} socket={{range .Mounts}}{{if eq .Source \"/var/run/docker.sock\"}}YES{{end}}{{end}} project={{index .Config.Labels \"com.docker.compose.project\"}} dir={{index .Config.Labels \"com.docker.compose.project.working_dir\"}}"'
  run "mount sources of monitoring containers (paths only)" sh -c \
    'for c in $(docker ps -a --format "{{.Names}}" | grep -iE "prom|alert|export|cadvisor|grafana"); do docker inspect "$c" --format "{{.Name}}: {{range .Mounts}}{{.Source}}->{{.Destination}} {{end}}"; done'
  run "live usage" docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}'
  run "networks + subnets" sh -c 'docker network ls -q | xargs -r docker network inspect --format "{{.Name}} driver={{.Driver}} subnet={{range .IPAM.Config}}{{.Subnet}} {{end}}internal={{.Internal}}"'
  run "volumes" docker volume ls
  run "disk usage" docker system df
else
  echo "docker not installed"
fi

section "3. Network, ports, firewall"
run "addresses" ip -brief address
run "routes" ip route
run "listening sockets" ss -tulpn
run "candidate Argus ports (FREE = nothing listening)" sh -c \
  "for p in $CANDIDATE_PORTS; do if ss -ltn \"( sport = :\$p )\" | grep -q LISTEN; then echo \"\$p IN-USE\"; else echo \"\$p FREE\"; fi; done"
run "ufw" sh -c 'ufw status verbose 2>/dev/null || echo "ufw not available"'
run "iptables filter (incl. INPUT, FORWARD, DOCKER-USER)" iptables -S
run "iptables nat" iptables -t nat -S
run "netfilter-persistent saved rules present" sh -c 'ls -l /etc/iptables/rules.v4 2>/dev/null || echo "no /etc/iptables/rules.v4"'
run "reachability to the peer VM (open / refused / timeout=filtered)" sh -c "
for ip in $PEERS; do
  case \" $MYIPS \" in *\" \$ip \"*) continue;; esac
  for p in $KNOWN_PORTS $CANDIDATE_PORTS; do
    if timeout 3 bash -c \"</dev/tcp/\$ip/\$p\" 2>/dev/null; then r=open; else rc=\$?; [ \$rc -eq 124 ] && r=timeout || r=refused; fi
    echo \"\$ip:\$p \$r\"
  done
done"
run "outbound: model provider (401 expected) / GitHub / Docker Hub" sh -c \
  'for u in https://api.openai.com/v1/models https://github.com https://registry-1.docker.io/v2/; do printf "%s %s\n" "$(curl -s -o /dev/null -m 10 -w "%{http_code}" "$u")" "$u"; done'

section "4. Services"
run "running services" systemctl list-units --type=service --state=running --no-pager --no-legend
run "failed units" systemctl --failed --no-pager --no-legend
run "monitoring-related units" sh -c 'systemctl list-unit-files --no-pager | grep -iE "prometheus|node.?exporter|alertmanager|grafana|cadvisor|telegraf" || echo "none"'
run "time sync" timedatectl
run "systemd journal readable for kernel OOM records" sh -c 'journalctl -k --since "-1h" --no-pager -q 2>/dev/null | tail -1 >/dev/null && echo "kernel journal readable" || echo "kernel journal NOT readable"'

section "5. Earlier deployments and leftovers (names/presence only, never contents)"
run "Argus/lab directories" sh -c 'find /home /opt /srv /root -maxdepth 3 -type d \( -iname "*argus*" -o -iname "*lab-agent*" -o -iname "*lab*mvp*" -o -iname "*server_agent*" \) 2>/dev/null'
run "credential files left by the earlier demo (present/absent only)" sh -c \
  'for f in /home/ubuntu/lab-agent/.env /home/ubuntu/env-gateway.bak; do [ -e "$f" ] && echo "PRESENT $f" || echo "absent  $f"; done'
run "compose files (paths only)" sh -c 'find /home /opt /srv /root -maxdepth 4 -type f \( -name "docker-compose*.y*ml" -o -name "compose*.y*ml" \) 2>/dev/null'
run "git remotes (credentials masked)" sh -c 'for d in $(find /home /opt /srv /root -maxdepth 3 -type d -name .git 2>/dev/null); do printf "%s -> " "$(dirname "$d")"; (git -C "$(dirname "$d")" remote get-url origin 2>/dev/null || echo "(no origin)") | sed -E "s#//[^/@]+@#//***@#"; done'
run "candidate Argus directories (expected: absent)" sh -c 'for d in /opt/argus /opt/argus-v18 /opt/argus-runbooks /srv/argus-lab-fill; do [ -e "$d" ] && echo "EXISTS $d" || echo "absent $d"; done'

section "6. Access"
run "docker / sudo group members" sh -c 'getent group docker; getent group sudo'
run "authorized_keys entries (count and key types only)" sh -c \
  'for f in /home/*/.ssh/authorized_keys /root/.ssh/authorized_keys; do [ -f "$f" ] && echo "$f: $(wc -l < "$f") keys; types: $(awk "{print \$1}" "$f" | sort | uniq -c | tr "\n" " ")"; done'
run "sudo mode for the invoking user" sh -c 'u=${SUDO_USER:-$(id -un)}; sudo -l -U "$u" 2>/dev/null | grep -E "NOPASSWD|ALL" | head -3'

printf '\n\n===== END (%s) =====\n' "$ROLE"
