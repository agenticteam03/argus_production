# (archived) E2E-1 step 02, run 2026-10-10 by juanbetancurm on the laptop (vm-166 lease, session cf7b8b638801)
# =====================================================================================
# L.1 claim vm-166 only; L.2 marker + read-only probe on vm-166; E.1 one SC-04 trial; B.1 the 5x batch.
# MUTATES (vm-166 lab only): each run starts its lab container; the runner's reset always removes it.
# =====================================================================================

# --- L.1 [LAPTOP · PowerShell] claim vm-166 -------------------------------------------------------------------------
git pull --ff-only origin main
python brain\tools\brain.py start --vm vm-166 --task E2E-1

# --- L.2 [VM vm-166 · bash] marker and read-only probe ---------------------------------------------------------------
echo 'holder=juanbetancurm session=cf7b8b638801' | sudo tee /opt/argus-v18/SESSION >/dev/null
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^ref=|^commit=|LAB BASELINE'
sudo docker ps -a --format '{{.Names}} {{.Status}}' | grep -E 'argus-lab-(leaker|filler|burner|client|backend|nginx|slow)' || echo "no scenario containers left over"
findmnt /srv/argus-lab-fill >/dev/null && df -h /srv/argus-lab-fill | tail -1 || echo "lab filesystem NOT mounted"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1

# --- E.1 [LAPTOP · PowerShell] one SC-04 trial -----------------------------------------------------------------------
python brain\tools\brain.py renew --vm vm-166 --minutes 120
.venv\Scripts\python.exe ops\e2e\run.py --as juanbetancurm --runs 1 --out ..\e2e-results\sc04-trial.jsonl SC-04

# --- B.1 [LAPTOP · PowerShell, its own window] the batch -------------------------------------------------------------
python brain\tools\brain.py renew --vm vm-166 --minutes 300
.venv\Scripts\python.exe ops\e2e\run.py --as juanbetancurm --runs 5 --out ..\e2e-results\batch-1.jsonl SC-07 SC-04 SC-06 SC-05
