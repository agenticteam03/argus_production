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
# OP-005 step 02 — VM proof: young container restarts (PR #41)                                     [~5 min left]
# Why: restarts_10m must count a young container's early restarts (Docker count = signal), and an exporter restart
#      must not invent restarts on an old healthy container.
# Lease: conantkd (session 21a9ce710773).
#
# ALREADY DONE by the agent over SSH (2026-10-09, record only, do not re-run):
#   vm-095: nonint before; deploy task/OP-005-young-restarts b26effa; agent/worker/scheduler, target services and
#           Prometheus rebuilt; /opt/argus-v18/secrets/prometheus created on purpose (empty, root, 0755);
#           catalogue=mcp, TOOLS ISOLATION OK; LAB BASELINE OK; NO INTERFERENCE.
#   vm-166: nonint before; deploy task/OP-005-vm166-proof 4247dc8 (OP-010 stack + main + OP-005); target services and
#           Prometheus rebuilt; argus_container_created_seconds published; LAB BASELINE OK; NO INTERFERENCE.
#   vm-166: SC-01 started 09:52; at Prometheus counter 3 (age 41 s): new restarts_10m = 3, old max-min = 1;
#           ContainerRestartLoop firing 09:53:09 and present in vm-166's Alertmanager. SC-01 is STILL RUNNING.
#
# MUTATES: one incident row (the diagnosis). Nothing on the hosts.
# =====================================================================================

# --- D.1 [VM vm-095 · bash] (ssh argus-vm095) — conantkd: asks for YOUR Argus password -------------------------------
grep -q "holder=conantkd " /opt/argus-v18/SESSION && echo "SESSION OK" || echo "NOT YOUR SESSION"
sudo docker exec -it -e ARGUS_USER=conantkd argus-v18-agent argus diagnose vm-166/container:argus-lab-worker --reason "keeps restarting"
# (no "| tail": with -t the password prompt goes through the pipe, and tail hides it until the end)
# Expected: SESSION OK; a live run ending with outcome DIAGNOSED, class container_restart_loop, RB-001 recalled first,
#           every read on vm-166 (no model call is needed for the OOM case: killed by its own 64 MiB limit).
# VERDICT: as expected -> OK · UNSUPPORTED / UNDIAGNOSABLE / a read on vm-095 -> STOP and paste the full output.
# Then tell the agent "output.bash updated": it resets SC-01, runs the old-container exporter check and the
# non-interference checks on both hosts.
