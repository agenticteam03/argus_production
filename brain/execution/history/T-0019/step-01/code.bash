# (archived) T-0019 batch 1 step 01, run 2026-10-07 by the agent over SSH (session 3307114120d3)
# =====================================================================================
# T-0019 batch 1, step 01 — read-only checks on vm-166 before the db-probe                          [~2 min]
# Why: the db-probe image installs pg8000 from PyPI; argus-lab-db pulls postgres:16-alpine; the probe binds
#      127.0.0.1:18704; the lab DB needs memory headroom. Nothing is changed.
# MUTATES: nothing (read-only).
# =====================================================================================

# --- S1.1 [VM vm-166 · bash] (ssh argus-vm166) --------------------------------------------------------------------
grep -q "^holder=conantkd " /opt/argus-v18/SESSION && echo "SESSION OK" || echo "NOT YOUR SESSION - stop here"
c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 https://pypi.org/simple/pg8000/); echo "pypi pg8000 http=$c"
sudo docker image inspect postgres:16-alpine >/dev/null 2>&1 && echo "image postgres:16-alpine present" || echo "image postgres:16-alpine absent (pull needed)"
c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 https://registry-1.docker.io/v2/); echo "docker hub http=$c"
sudo ss -ltnH '( sport = :18704 )' | grep -q . && echo "PORT 18704 BUSY" || echo "port 18704 free"
sudo docker network inspect argus-lab-app -f 'network {{.Name}} {{range .IPAM.Config}}{{.Subnet}}{{end}}' 2>&1 | sed -E 's/[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/<addr>/'
free -m | awk '/^Mem:/ {print "mem total="$2"MB available="$7"MB"}'
df -h /var/lib/docker | awk 'NR==2 {print "docker disk used="$5" avail="$4}'
sudo docker ps --format '{{.Names}}' | grep -c -E '^argus-(v18|lab)-' | sed 's/^/argus containers running: /'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: SESSION OK; pypi http=200; postgres image present or docker hub http=401 (reachable); port 18704 free;
#           network argus-lab-app exists; mem available >= 1024MB; docker disk below 80%; NO INTERFERENCE.
