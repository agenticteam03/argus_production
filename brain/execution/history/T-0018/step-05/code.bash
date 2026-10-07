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
# T-0018 step 05 — run SC-07 on vm-166: induce → signal → diagnose → reset                           [~10 min]
# Why: prove Argus diagnoses "healthy backend on the wrong network" (RB-009), not "backend down".
# MUTATES (vm-166 only): starts argus-lab-backend (on the new network argus-lab-iso, 172.30.3.0/24, free per step 01)
#          and argus-lab-client (on argus-lab-app); V.3 removes both and the network. vm-095: reads only (+ audit rows).
# Undo: V.3 (also safe to run alone: it only removes the two SC-07 containers and argus-lab-iso).
# Lease: conantkd (session 796fd4f3bf61).
# =====================================================================================

# --- V.1 [VM vm-166 · bash] (ssh argus-vm166) induce + wait for the signal (MUTATES: the two SC-07 containers) -------
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || echo "NOT YOUR SESSION - stop here"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc07 up -d 2>&1 | tail -4; cd ~
for i in $(seq 1 12); do s=$(sudo docker inspect -f '{{.State.Health.Status}}' argus-lab-backend); echo "backend health=$s"; [ "$s" = healthy ] && break; sleep 10; done
sudo docker inspect -f '{{.Name}} networks={{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' argus-lab-client argus-lab-backend
sudo docker logs --tail 3 argus-lab-client 2>&1
Q='argus_probe_success{owner="argus-lab-client"}'
for i in $(seq 1 12); do v=$(curl -s --data-urlencode "query=$Q" http://127.0.0.1:18090/api/v1/query | python3 -c 'import json,sys; r=json.load(sys.stdin)["data"]["result"]; print(r[0]["value"][1] if r else "none")'); echo "probe client->backend = $v"; [ "$v" = 0 ] && break; sleep 10; done
[ "$s" = healthy ] && [ "$v" = 0 ] && echo "VERDICT V.1 OK: backend healthy, client's probe = 0" || echo "VERDICT V.1 STOP"
# Expected: backend health=healthy; client networks=argus-lab-app, backend networks=argus-lab-iso; client log
#           "ERROR cannot reach http://argus-lab-backend:8080/health: [Errno -2] Name does not resolve" (or similar);
#           probe client->backend = 0; VERDICT V.1 OK.

# --- V.2 [VM vm-095 · bash] (ssh argus-vm095) diagnose the client (READ-ONLY; calls the model; asks your password) --
ME=conantkd
read -rsp "Argus password for $ME: " ARGUS_PASSWORD; echo; export ARGUS_PASSWORD
ARGUS="sudo --preserve-env=ARGUS_PASSWORD docker exec -i -e ARGUS_USER=$ME -e ARGUS_PASSWORD argus-v18-agent argus"
$ARGUS diagnose vm-166/container:argus-lab-client --reason "the client cannot reach its backend" --no-color < /dev/null | tee /tmp/sc07.txt | tail -40
grep -qi 'diagnosed' /tmp/sc07.txt && grep -qiE 'argus-lab-iso|network' /tmp/sc07.txt && echo "VERDICT V.2 OK: diagnosed as a network problem" || echo "VERDICT V.2 CHECK: read the diagnosis"
# Expected: DETECT dependency_unavailable → RECALL RB-003 (+ RB-009 branch) → reads on vm-166 only (status of the client
#           and the backend shows their networks; DNS/TCP from argus-lab-app fail; the backend is healthy) → RECORD
#           DIAGNOSED: root cause a network misattachment (backend only on argus-lab-iso), not a failed backend.

# --- V.3 [VM vm-166 · bash] reset: remove the SC-07 containers and the network (MUTATES) -----------------------------
sudo docker rm -f argus-lab-client argus-lab-backend
sudo docker network rm argus-lab-iso
sudo docker ps -a --format '{{.Names}}' | grep -E '^argus-lab-(client|backend)$' || echo "SC-07 containers gone"
sudo docker network ls --format '{{.Name}}' | grep -x argus-lab-iso || echo "argus-lab-iso gone"
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E 'LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
echo "T-0018.5 SC-07 DONE"
# Expected: both containers and the network gone; LAB BASELINE OK; NO INTERFERENCE; T-0018.5 SC-07 DONE.
