# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
#
# Every block says WHERE to run it:
#   [VM vm-095 · bash]      ssh argus-vm095
#   [LAPTOP · PowerShell]   a PowerShell window on your laptop
# Paste what the terminal printed into brain/execution/current/output.bash (gitignored, never committed)
# and tell the agent "output.bash updated".
# =====================================================================================

# =====================================================================================
# T-0021 step 5d — vm-095: the OD-3 benchmark (what the MCP tools process adds to one read)  [~6 min]
# Run ONLY after the agent has pushed the benchmark (the commit after 58720d0).
# Story: deploy + rebuild (the benchmark is in the image; the worker stays mcp, tokens stay argus-tools). Then, as
#   argus-tools (the only user that can read the tokens), the same read 30 times in-process and 30 times through a
#   tools process, alternating: p95 overhead per call must be < 100 ms (ARCHITECTURE §25 OD-3). Two reads: the light
#   container.status and the heavier container.logs, both of vm-095/container:argus-lab-api (healthy lab twin).
# READ-ONLY on the lab (about 120 reads through vm-095's read gateway). MUTATES Argus only: checkout + rebuild.
# =====================================================================================

# --- 5d.0 [LAPTOP · PowerShell] renew the lease (until 17:13 UTC) ---------------------------------------------------
cd C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\argus_production
git stash push brain/execution/current/code.bash
python brain\tools\brain.py renew
git stash pop
# Expected: "Lease renewed until ..."

# --- 5d.1 [VM vm-095 · bash] deploy, rebuild, then the benchmark (asks nothing) -------------------------------------
grep -q "^holder=juanbetancurm " /opt/argus-v18/SESSION && echo "SESSION OK" || echo "NOT YOUR SESSION - stop here"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh task/T-0021-tool-isolation --as juanbetancurm | tail -1
cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler 2>&1 | tail -3; cd ~
sleep 15
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^commit=|LAB BASELINE|^argus:'
sudo docker exec argus-v18-worker sh -c 'echo "catalogue=${ARGUS_TOOL_CATALOGUE}"'
sudo docker exec -u argus-tools argus-v18-worker python -m argus.tooling.mcp.benchmark 30 vm-095/container:argus-lab-api container.status
sudo docker exec -u argus-tools argus-v18-worker python -m argus.tooling.mcp.benchmark 30 vm-095/container:argus-lab-api container.logs
sudo docker exec argus-v18-worker python -m argus.tooling.isolation_check | tail -1
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: SESSION OK; DEPLOY OK: <the new commit>; 3 argus: lines; LAB BASELINE OK; catalogue=mcp;
#   for each read: "direct p50 ... p95 ...", "mcp ...", "overhead ...", "pairs: 30   not ok: 0", last line OD-3 OK;
#   TOOLS ISOLATION OK (unchanged); NO INTERFERENCE.
# VERDICT: both OD-3 OK → step 5 done (the agent closes T-0021) · OD-3 STOP → paste it; the agent decides (rollback = R)

# --- R [VM vm-095 · bash] ROLLBACK only if the agent says so: worker to direct, tokens back to 10010 -----------------
# (2026-10-09: the compose default is now mcp, so the rollback writes direct instead of deleting the line)
# sudo sed -i '/^ARGUS_TOOL_CATALOGUE=/d' /opt/argus-v18/hosts.env; echo 'ARGUS_TOOL_CATALOGUE=direct' | sudo tee -a /opt/argus-v18/hosts.env
# S=/opt/argus-v18/secrets/agent; sudo find $S/vm-095 $S/vm-166 -type f -name '*_token' -exec chown 10010:10010 {} + ; sudo chown 10010:10010 $S/vm-095 $S/vm-166; sudo chmod 0500 $S
# cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --no-deps argus-v18-worker; cd ~
# sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
