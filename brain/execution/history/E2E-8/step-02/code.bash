# (archived) E2E-8 step 2, run 2026-10-13 by conantkd; both leases, session 38abbb604d92
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
#
# Every block says WHERE to run it:
#   [LAPTOP · PowerShell]   a PowerShell window on your laptop
# =====================================================================================

# =====================================================================================
# 2026-10-13, conantkd. E2E-8 step 2: the remaining scenarios ×5 through the runner.   [~1.5-2 h]
# Why: Phase 12 needs five runs of every scenario; SC-01 … SC-08 have them, H-1/H-2, SC-09 … SC-12 and the identity
#      proof had one run each (LangGraph, LGS). Both VMs on main ad72617 (AFTER-MERGE 2026-10-13).
# Lease: both (session 38abbb604d92). The runner checks the session marker and NO INTERFERENCE on every touched host.
# MUTATES: only the catalogue's commands (ops/e2e/scenarios.yaml, reviewed in #131): lab containers started and
#          removed; SC-10 stops and starts vm-095's argus-v18-node-exporter, SC-12 vm-166's argus-v18-read-gateway.
# ROLLBACK: the reset of each scenario (run after every attempted start, also after an error).
# Model calls: none in batch 1 or SC-10 (no class, or monitoring_blind_spot); the identity proof's two diagnoses do.
# =====================================================================================

# --- B.1 [LAPTOP · PowerShell] batch 1: no failure induced (minutes) -------------------------------------------------
.venv\Scripts\python.exe ops\e2e\run.py --as conantkd --runs 5 --out ..\e2e-results\e2e8-batch-1.jsonl H-1 H-2 SC-09 SC-11
# Expected: 5/5 each; 0 errors.

# --- B.2 [LAPTOP · PowerShell] batch 2: Argus's own services stopped; two hosts at once (~1-1.5 h) ------------------
.venv\Scripts\python.exe ops\e2e\run.py --as conantkd --runs 5 --out ..\e2e-results\e2e8-batch-2.jsonl SC-10 SC-12 ID-1
# Expected: SC-10 monitoring_blind_spot no_action_escalated RB-014, no model call, vm-166 no_incident; SC-12 the
#   vm-166 report escalated (never diagnosed), vm-095 answers; ID-1 two incidents, each its own host's root cause.
