# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
#   [LAPTOP · PowerShell]   [VM vm-095 · bash] = ssh argus-vm095   [VM vm-166 · bash] = ssh argus-vm166
# Paste what the terminal printed into brain/execution/current/output.bash (gitignored, never committed)
# and tell the agent "output.bash updated". Every block ends with a VERDICT line.
# =====================================================================================

# =====================================================================================
# LGS — re-run on the LangGraph runner (final main code) the scenarios verified only on the plain runner:
#   H-2, SC-02, the identity proof (SC-01 + SC-02 at once), SC-11, SC-10, SC-12.                       [~30 min]
# Why: CURRENT_STATE §4 — on LangGraph only H-1, SC-09, SC-01, SC-03 are verified; the rest are "expected to behave
#   the same" (parity tests). Phase 12 asks for real runs with archived output.
# MUTATES: lab containers only (argus-lab-worker on both VMs), vm-095's argus-v18-exporter (SC-10, stopped and
#   started inside block A) and vm-166's argus-v18-read-gateway (SC-12, between A and B). All restored at the end.
# Undo (everything): vm-095: cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc02
#   rm -sf argus-lab-worker-crash; sudo docker start argus-v18-exporter.  vm-166: sudo docker start
#   argus-v18-read-gateway; cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc01
#   rm -sf argus-lab-worker-oom.
#
# PROGRESS
#   R1 DONE: SC-02 running on vm-095 (Prometheus restarts_10m=5, oom=false); SC-01 running on vm-166
#     (restarts_10m=3, oom=true). Both gates on Prometheus, not on Docker's counter (TROUBLESHOOTING #17).
#   A DONE (all as expected): SC-02 inc_36771c1cc56a DIAGNOSED non-OOM exit 1, missing /etc/worker/config.yml, RB-008,
#     reads on vm-095 only · identity inc_9a4913fd71b6 DIAGNOSED OOM 137 at the 64 MiB limit, reads on vm-166 only ·
#     H-2 inc_c6cf74c0c7a7 HEALTHY · SC-11 inc_03310115718d REFUSED "not in the inventory; nothing was read" ·
#     SC-10 inc_3f5a3143ad03 UNDIAGNOSABLE (exporter scrape down on vm-095, RB-014) + inc_c6bf99ad8fd0 vm-166 HEALTHY.
#   R2 DONE: SC-02 removed on vm-095 (exporter Up); SC-01 still looping on vm-166 (12 restarts); vm-166 read gateway
#     stopped (Exited 137).
#   B DONE: SC-12 inc_29434f3bdef9 ESCALATED at step 2 (docker@vm-166 read failed; no made-up diagnosis).
#   R3 DONE: gateway Up, SC-01 removed; both VMs LAB BASELINE OK and NO INTERFERENCE. LGS COMPLETE.
# =====================================================================================

# --- R1 [VM vm-095 · bash] + [VM vm-166 · bash] Start SC-02 (vm-095) and SC-01 (vm-166); gate on Prometheus ---------
# vm-095: P=sc02 S=argus-lab-worker-crash H=vm-095      vm-166: P=sc01 S=argus-lab-worker-oom H=vm-166
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile "$P" up -d "$S"; cd ~
Q="max_over_time(argus_container_restart_count{argus_host=\"$H\",container=\"argus-lab-worker\"}[10m]) - min_over_time(argus_container_restart_count{argus_host=\"$H\",container=\"argus-lab-worker\"}[10m])"
URL="http://127.0.0.1:9090/api/v1/query?query=$(python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$Q")"
for i in $(seq 1 36); do v=$(sudo docker exec argus-v18-prometheus wget -qO- "$URL" | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; print(int(float(r[0]["value"][1])) if r else 0)'); echo "prometheus restarts_10m=$v"; [ "$v" -ge 3 ] && break; sleep 10; done
[ "$v" -ge 3 ] && echo "VERDICT R1 OK ($H)" || echo "VERDICT R1 STOP ($H)"

# --- A [VM vm-095 · bash] (prompt ubuntu@argus-vm095) H-2, SC-02, identity proof, SC-11, SC-10 ---------------------
ME=conantkd
read -rsp "Shared Argus password: " ARGUS_PASSWORD; echo; export ARGUS_PASSWORD
ARGUS="sudo --preserve-env=ARGUS_PASSWORD docker exec -i -e ARGUS_USER=$ME -e ARGUS_PASSWORD argus-v18-agent argus"
d() { echo; echo "##### $*"; $ARGUS diagnose "$@" --no-color < /dev/null 2>&1 | grep -vE '^\s*$|^\s*[│┌└]' | tail -22; }
d vm-095/container:argus-lab-worker --reason "keeps restarting"                 # SC-02: DIAGNOSED, non-OOM, missing config, RB-008, reads on vm-095 only
d vm-166/container:argus-lab-worker --reason "keeps restarting"                 # identity proof: DIAGNOSED, OOM, RB-001, reads on vm-166 only
d vm-095/container:argus-lab-api --check --reason "LGS H-2"                     # H-2: HEALTHY
d vm-166/container:argus-api-1 --reason "check"                                 # SC-11: refused, not in the inventory, nothing read
sudo docker stop argus-v18-exporter >/dev/null && echo "SC-10: vm-095 exporter stopped"; sleep 45
d vm-095/container:argus-lab-api --check --reason "LGS SC-10 blind"             # SC-10: UNDIAGNOSABLE (monitoring blind spot, RB-014)
d vm-166/container:argus-lab-api --check --reason "LGS SC-10 other host"        # SC-10: vm-166 unaffected -> HEALTHY
sudo docker start argus-v18-exporter >/dev/null && echo "SC-10: vm-095 exporter started again"
echo "VERDICT A DONE: paste everything below the password prompt"
# Keep this shell open (ARGUS_PASSWORD and d() stay set) for block B.

# --- R2 [VM vm-095 · bash] then [VM vm-166 · bash] Reset SC-02; stop vm-166's read gateway with SC-01 still running ----
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc02 rm -sf argus-lab-worker-crash; cd ~   # vm-095
sudo docker stop argus-v18-read-gateway; sleep 20                                                                    # vm-166

# --- B [VM vm-095 · bash] (same shell as A) SC-12: a real incident on vm-166 while Argus cannot read Docker there ----
d vm-166/container:argus-lab-worker --reason "keeps restarting"                 # SC-12: docker@vm-166 reads fail -> ESCALATED early (never a made-up diagnosis)
unset ARGUS_PASSWORD
echo "VERDICT B DONE"

# --- R3 [VM vm-166 · bash] then [VM vm-095 · bash] Restore the gateway, reset SC-01, prove non-interference ---------
sudo docker start argus-v18-read-gateway                                                                            # vm-166
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc01 rm -sf argus-lab-worker-oom; cd ~   # vm-166
sudo bash /opt/argus-v18/app/ops/deploy.sh status | tail -3; sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1   # both VMs
# Expected: LAB BASELINE OK and NO INTERFERENCE on both VMs.
