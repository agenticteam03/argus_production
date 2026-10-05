# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
#
#   [LAPTOP · PowerShell]   a PowerShell window on your laptop
#   [VM vm-095 · bash]      ssh argus-vm095
#   [VM vm-166 · bash]      ssh argus-vm166
# Paste what the terminal printed into brain/execution/current/output.bash (gitignored, never committed)
# and tell the agent "output.bash updated". Every block ends with a VERDICT line.
# =====================================================================================

# =====================================================================================
# TASK SP-1 — State probe + login test per user                                   [~10 min]
# Why: (1) learn what is REALLY deployed on the VMs (the VM wins over CURRENT_STATE.md);
#      (2) close the pending legacy step 12b.2: each of the 3 users can log in.
# Both blocks are READ-ONLY for services (the login test creates 3 small "healthy check" incidents, no AI call).
# =====================================================================================

# --- SP-1.1 [VM vm-095 · bash] (ssh argus-vm095) State probe — READ-ONLY -------------------------------------------
echo "--- DEPLOYED marker"; cat /opt/argus-v18/DEPLOYED 2>/dev/null || echo "(no DEPLOYED marker)"
echo "--- SESSION marker"; cat /opt/argus-v18/SESSION 2>/dev/null || echo "(no SESSION marker)"
echo "--- containers"; sudo docker ps --format '{{.Names}}\t{{.Status}}' | grep -E 'argus-v18-|argus-lab-' | sort
echo "--- health"; curl -s -o /dev/null -w "agent API /health -> HTTP %{http_code}\n" http://127.0.0.1:18000/health
echo "--- app dir is a git clone?"; git -C /opt/argus-v18/app rev-parse --short HEAD 2>&1 | head -1
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after
# Expected: DEPLOYED lines (or "no marker" = deploy.sh init not run yet), the argus containers Up, NO INTERFERENCE.

# --- SP-1.2 [VM vm-166 · bash] (ssh argus-vm166) State probe — READ-ONLY -------------------------------------------
echo "--- DEPLOYED marker"; cat /opt/argus-v18/DEPLOYED 2>/dev/null || echo "(no DEPLOYED marker)"
echo "--- containers"; sudo docker ps --format '{{.Names}}\t{{.Status}}' | grep -E 'argus-v18-|argus-lab-' | sort
echo "--- app dir is a git clone?"; git -C /opt/argus-v18/app rev-parse --short HEAD 2>&1 | head -1
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after
# Expected: Argus containers Up, NO INTERFERENCE.

# --- SP-1.3 [VM vm-095 · bash] Login test per user (legacy 12b.2) — hidden password prompt --------------------------
# Creates 3 cheap incidents (no model call). Undo: nothing to undo (incidents are audit records).
read -rsp "Shared Argus password: " ARGUS_PASSWORD; echo; export ARGUS_PASSWORD
for U in juanbetancurm conantkd juanes6554; do
  echo "== $U"
  sudo --preserve-env=ARGUS_PASSWORD docker exec -i -e ARGUS_USER="$U" -e ARGUS_PASSWORD argus-v18-agent \
    argus diagnose vm-095/container:argus-lab-api --check --reason "login test $U" | grep -E "^incident|outcome"
done
unset ARGUS_PASSWORD
# Expected, 3 times: "incident inc_..." and "outcome: HEALTHY". Do NOT paste the password anywhere.
# >>> Paste everything into output.bash and tell the agent "output.bash updated". <<<
