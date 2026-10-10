# T-0030 step 02 — a Postgres restart and a 30 s outage on vm-095 (2026-10-10, conantkd, session d550d6afba41).
# Run by the agent over SSH (the blocks below, summarized). Proof branch task/T-0030-vm-proof (task/T-0029-vm-proof,
# which the VMs ran, + task/T-0030-pg-restart). MUTATES: vm-095: a backup, the agent processes recreated, Postgres
# restarted then stopped 30 s; vm-166: argus-lab-cache stopped then started (SC-03, to have a run and alerts).
# ROLLBACK: deploy.sh task/T-0029-vm-proof on vm-095 + recreate agent/worker/scheduler; `docker start` anything stopped.

# S.1 [vm-095] nonint-check before; db-backup.sh backup --as conantkd; deploy.sh task/T-0030-vm-proof;
#     compose up -d --build --force-recreate --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler;
#     docker inspect RestartCount/StartedAt of the four containers.
# S.2 [vm-166] docker stop argus-lab-cache.  [vm-095] poll (2 s) until the SC-03 incident is `running`, then
#     docker restart argus-v18-postgres; poll (5 s) until it concludes; RestartCount again; worker/scheduler logs.
# S.3 [vm-095] docker stop argus-v18-postgres; 12 s: api /healthz; 18 s: docker start argus-v18-postgres; 75 s:
#     RestartCount, worker log "database call failed", scheduler passes, api /healthz and a read.
# S.4 [vm-166] docker start argus-lab-cache; poll until no alert; [vm-095] the occurrences resolved;
#     deploy.sh status and nonint-check after on both VMs.
