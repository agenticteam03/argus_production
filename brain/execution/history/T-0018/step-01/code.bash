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
# T-0018 step 01 — probe vm-166 (READ-ONLY): is 172.30.3.0/24 free for a new lab network?           [~2 min]
# Why: SC-07 adds a second lab network `argus-lab-iso`. Two Docker networks (or a host interface/route) on the same
#      VM must never share an address range, so before creating anything we list every range in use on vm-166.
# MUTATES: only /opt/argus-v18/SESSION (S.0, the lease marker). S.1 reads only.   Undo: nothing to undo.
# Lease: conantkd (session 796fd4f3bf61).
# =====================================================================================

# --- S.0 [LAPTOP · PowerShell] Session marker on vm-166 (MUTATES /opt/argus-v18/SESSION) ---------------------------
ssh -o BatchMode=yes argus-vm166 "echo 'holder=conantkd session=796fd4f3bf61' | sudo tee /opt/argus-v18/SESSION"
# Expected: holder=conantkd session=796fd4f3bf61

# --- S.1 [VM vm-166 · bash] (ssh argus-vm166) State probe + address ranges — read-only ------------------------------
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || echo "NOT YOUR SESSION - stop here"
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo docker ps --format '{{.Names}}\t{{.Status}}' | grep -E '^argus-(v18|lab)-' | sort
echo "## docker networks and their ranges"
sudo docker network inspect $(sudo docker network ls -q) --format '{{.Name}} {{range .IPAM.Config}}{{.Subnet}} {{end}}' | sort
echo "## host IPv4 addresses and routes in 172.16.0.0/12"
ip -4 -brief addr | grep -E ' 172\.(1[6-9]|2[0-9]|3[01])\.' || echo "(none)"
ip -4 route | grep -E '^172\.(1[6-9]|2[0-9]|3[01])\.' || echo "(none)"
echo "## verdict"
if sudo docker network inspect $(sudo docker network ls -q) --format '{{range .IPAM.Config}}{{.Subnet}} {{end}}' | tr ' ' '\n' | grep -q '^172\.30\.3\.' \
   || ip -4 route | grep -q '^172\.30\.3\.' || ip -4 addr | grep -q ' 172\.30\.3\.'; then
  echo "SUBNET TAKEN: 172.30.3.0/24 is already used on vm-166"
else
  echo "SUBNET FREE: 172.30.3.0/24 is not used on vm-166"
fi
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: SESSION OK; commit=… ref=main (f126272 or older: vm-166 services unchanged); LAB BASELINE OK;
#           the networks list shows argus-v18-mon 172.30.1.0/24, argus-lab-app 172.30.2.0/24 and the non-Argus ones;
#           "SUBNET FREE: 172.30.3.0/24 …"; NO INTERFERENCE (compared with the last saved "before" snapshot).
