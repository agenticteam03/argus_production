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
# STEP T-0017.1 — State probe before the Postgres backup/restore drill           [~2 min]
# Goal / Why: confirm vm-095 matches the Brain and measure what the drill needs: database size, free disk under
#             /opt/argus-v18, free memory, and whether the postgres:16-alpine image is already present.
# READ-ONLY (except the session marker, which records that conantkd holds the VMs now).
# =====================================================================================

# --- 1.1 [VM vm-095 · bash] (ssh argus-vm095) Session marker -----------------------------------------------
echo 'holder=conantkd session=06cb9843af9b' | sudo tee /opt/argus-v18/SESSION >/dev/null && cat /opt/argus-v18/SESSION
# Expected: holder=conantkd session=06cb9843af9b

# --- 1.2 [VM vm-095 · bash] Deployed code and Argus containers ---------------------------------------------
cat /opt/argus-v18/DEPLOYED
# Expected: commit=2097eb1... ref=main
sudo docker ps --format '{{.Names}} {{.Status}}' | grep -E '^argus-(v18|lab)-' | sort
# Expected: argus-v18-postgres Up ... (healthy), argus-v18-agent Up ..., no argus-lab-pgrestore

# --- 1.3 [VM vm-095 · bash] What the drill needs -----------------------------------------------------------
sudo docker exec argus-v18-postgres psql -X -At -U argus_owner -d argus -c \
  "SELECT 'pg: ' || current_setting('server_version') || ' size: ' || pg_size_pretty(pg_database_size('argus'))"
# Expected: pg: 16.x size: <a few MB>
sudo docker exec argus-v18-postgres psql -X -At -U argus_owner -d argus -c \
  "SELECT relname || ' ' || n_live_tup FROM pg_stat_user_tables ORDER BY relname"
# Expected: one line per table (incident, evidence, audit, principal, run_event, notification, checkpoints ...)
df -h /opt/argus-v18 | tail -1; free -m | sed -n 2p
# Expected: free disk well above the database size; some hundred MB of available memory
sudo docker image ls postgres:16-alpine --format 'image: {{.Repository}}:{{.Tag}} {{.ID}}'
# Expected: image: postgres:16-alpine <id>
sudo ls -ld /opt/argus-v18/backups 2>/dev/null || echo "backups: none yet"
# Expected: backups: none yet

# --- 1.4 [VM vm-095 · bash] Non-interference ---------------------------------------------------------------
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after
# Expected: NO INTERFERENCE
echo "T-0017.1 PROBE DONE"
# >>> Paste everything into output.bash and tell the agent "output.bash updated". <<<
