# (archived) E2E-1 step 03, run 2026-10-10 by juanbetancurm on the laptop (vm-166 lease, session cf7b8b638801)
# =====================================================================================
# A.3 a read-only look at batch 1's misses (the store inside argus-v18-worker on vm-095; writes nothing);
# A.2 batch 2 on vm-166. The read script lived next to the repository (read-misses.py): it printed, per incident,
# the target, class, outcome, root cause, diagnosis, findings, every evidence record's model text and the audit events.
# =====================================================================================

# --- A.3 [LAPTOP · PowerShell] the misses, read-only -------------------------------------------------------------------
Get-Content .\read-misses.py | ssh argus-vm095 'sudo docker exec -i argus-v18-worker python -'

# --- A.2 [LAPTOP · PowerShell, its own window] batch 2 ---------------------------------------------------------------
python brain\tools\brain.py renew --vm vm-166 --minutes 150
.venv\Scripts\python.exe ops\e2e\run.py --as juanbetancurm --runs 5 --out ..\e2e-results\batch-2.jsonl SC-07 SC-05
