# =====================================================================================
# T-0022 step 02 — discovery for phase 7 (both VMs)                                           [~2 min, READ-ONLY]
# Why: before adding argus-v18-alertmanager, -node-exporter and -cadvisor, know the room on each VM: RAM and
#      disk, CPU architecture, cgroup version, our ports in 18000-18799, subnets, what our containers use now,
#      whether the images are already present, whether the registry is reachable, and (vm-166) the tunnel
#      account's current permitopen destinations.
# MUTATES: nothing. Undo: nothing to undo.

# --- D.1 [VM vm-095 · bash] then [VM vm-166 · bash] (the same lines on each) -----------------------------------------
echo "== host"; uname -m; nproc; free -m | sed -n 1,2p; df -h / | tail -1; stat -fc 'cgroup fs: %T' /sys/fs/cgroup
echo "== argus ports in use (18000-18799)"; sudo ss -ltnH | awk '{print $4}' | grep -oE ':(18[0-7][0-9]{2})$' | sort -u | tr '\n' ' '; echo
echo "== docker networks (subnets)"; for n in $(sudo docker network ls -q); do sudo docker network inspect -f '{{.Name}} {{range .IPAM.Config}}{{.Subnet}}{{end}}' $n; done | sort
echo "== argus memory now"; sudo docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' | grep -E '^argus-(v18|lab)-' | sort
echo "== images present"; sudo docker image ls --format '{{.Repository}}:{{.Tag}}' | grep -E 'alertmanager|node-exporter|cadvisor|prometheus' | sort -u
echo "== registry reachable"; curl -s -o /dev/null -w 'docker hub %{http_code}\n' https://registry-1.docker.io/v2/; curl -s -o /dev/null -w 'gcr %{http_code}\n' https://gcr.io/v2/
echo "== tunnel permitopen (vm-166 only)"; sudo test -f /var/lib/argus-v18-tunnel/.ssh/authorized_keys && sudo grep -oE 'permitopen="[^"]+"' /var/lib/argus-v18-tunnel/.ssh/authorized_keys | sort || echo "no tunnel account here"
# Expected: aarch64; free RAM and disk; cgroup2fs; our ports; subnets 172.30.x ours; memory per argus container;
#           registry 401 (reachable); on vm-166 the 5 permitopen destinations (18701-18704, 18090).
