# T-0031 step 03 — the write-gate check on vm-166 (host-only) and again on vm-095 (2026-10-10, conantkd,
# session 9c71a9bf260a, both leases). Run by the agent over SSH. READ-ONLY: docker ps / inspect / exec (a python
# reading files); ls of the deploy home's secrets/ (names only).
# The branch sources were copied to /tmp/argus-t0031 on each VM with git archive from the laptop (the deployed main
#   ebbe9c9 is not changed):  git archive HEAD ops argus | ssh <vm> 'mkdir -p /tmp/argus-t0031 && tar -x -C /tmp/argus-t0031'
# ROLLBACK: sudo rm -rf /tmp/argus-t0031 (done at the end of each block).

# --- W.1 [vm-166 · agent] host-only check -------------------------------------------------------------------------
echo 'holder=conantkd session=9c71a9bf260a' | sudo tee /opt/argus-v18/SESSION >/dev/null
grep -q '^holder=conantkd ' /opt/argus-v18/SESSION && echo "session marker: mine" || { echo "NOT YOUR SESSION - stop"; exit 1; }
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo docker ps -a --format '{{.Names}}' | grep '^argus-v18-' | tr '\n' ' '; echo
sudo ls /opt/argus-v18/secrets 2>/dev/null | tr '\n' ' '; echo "(secrets/ entries, names only)"
sudo bash /tmp/argus-t0031/ops/write-gate-check.sh --host-only; echo "exit=$?"
sudo rm -rf /tmp/argus-t0031
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1

# --- W.2 [vm-095 · agent] the full check again (the script changed) -----------------------------------------------
echo 'holder=conantkd session=9c71a9bf260a' | sudo tee /opt/argus-v18/SESSION >/dev/null
grep -q '^holder=conantkd ' /opt/argus-v18/SESSION && echo "session marker: mine" || { echo "NOT YOUR SESSION - stop"; exit 1; }
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo docker ps -a --format '{{.Names}}' | grep '^argus-v18-' | wc -l | sed 's/^/argus-v18 containers: /'
sudo bash /tmp/argus-t0031/ops/write-gate-check.sh; echo "exit=$?"
curl -s http://127.0.0.1:18000/healthz; echo
sudo rm -rf /tmp/argus-t0031
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
