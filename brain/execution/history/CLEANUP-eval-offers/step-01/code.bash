# (archived) CLEANUP-eval-offers step 01, run 2026-10-20 by conantkd's agent over ssh; lease vm-095, session f14c4089c29d.
# Removes what EVAL-offers left on vm-095 (its evidence: execution/history/EVAL-offers/step-01/evidence.md, last note).
# MUTATES vm-095: Argus objects only (argus-v18-agent:eo-* images, /tmp/eo-*), used by no service. No rollback needed:
#   the results are archived and the images can be rebuilt from the EVAL-offers commits.

# --- C.1 [VM vm-095 · bash] list first (READ-ONLY) ---
sudo ls -lad /tmp/eo-*; sudo docker images --format '{{.Repository}}:{{.Tag}} {{.ID}} {{.Size}}' | grep -E ':eo-'
sudo docker ps -a --format '{{.Names}} {{.Image}}' | grep -E 'eo-' || echo none

# --- C.2 [VM vm-095 · bash] remove (MUTATES) ---
grep -q '^holder=conantkd ' /opt/argus-v18/SESSION || { echo 'NOT YOUR SESSION'; exit 1; }; echo SESSION OK
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
for i in $(sudo docker images --format '{{.Repository}}:{{.Tag}}' | grep -E '^argus-v18-agent:eo-'); do sudo docker rmi "$i" </dev/null >/dev/null && echo "removed $i"; done | wc -l
sudo rm -rf /tmp/eo-*
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
# Expected: none in use; 13 images removed; no /tmp/eo-* left; services unchanged; LAB BASELINE OK; NO INTERFERENCE.
