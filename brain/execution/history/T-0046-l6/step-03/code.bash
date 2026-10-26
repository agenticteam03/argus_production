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
# STEP T-0046-L6-live — SC-03 and SC-07 on vm-095's main 16028c7 (link history replay live)   [~5 min]
# Goal / Why: T-0046's next step after #322's deploy: run SC-03 (the cache stopped) and SC-07 (the backend
#   unreachable) once each and see that the incident reads the link history (`network.link_states`, now offered to
#   dependency_unavailable) and names the right root cause. Both classes run the deterministic baseline: no model call.
# Lease: both VMs held by conantkd (session 13d7ed009aaa, renewed by the agent); this block runs under it.
# MUTATES: vm-166 lab containers only, through the reviewed catalogue (ops/e2e/scenarios.yaml); each run resets.
# Run it in the worktree on current main (.work-deploy3), not the main checkout (an old branch there).
# Your Argus password is asked hidden; never paste it into output.bash.
# Expected: "SC-03 ... PASS" (root cause argus-lab-cache) and "SC-07 ... PASS" (root cause argus-lab-backend), each
#   with its incident id; VERDICT: S.1 PASS (2 of 2). The agent then reads the link rows and the incidents (read-only).
# Undo: the runner resets each scenario itself; if a run is interrupted, tell the agent (it checks the lab baseline).
# =====================================================================================

# ---------------------------------------------------------------------------------------------------------
# S.1 [LAPTOP · PowerShell] SC-03 and SC-07, one run each
# MUTATES: vm-166 lab containers through the catalogue; each run resets. Undo: none needed (the runner resets).
# Expected: "main 16028c7 is in this worktree"; SC-03 PASS and SC-07 PASS; VERDICT: S.1 PASS (2 of 2).
# ---------------------------------------------------------------------------------------------------------
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath '.work-deploy3'   # from the main checkout's root
Set-Location -LiteralPath (git rev-parse --show-toplevel)
git rev-parse --show-toplevel
$ok = 0
git merge-base --is-ancestor 16028c7 HEAD
if ($LASTEXITCODE -eq 0) { 'main 16028c7 is in this worktree' } else { throw 'this worktree does not contain 16028c7' }
..\.venv\Scripts\python.exe ops\e2e\run.py SC-03 --runs 1 --as conantkd
if ($LASTEXITCODE -eq 0) { $ok++ }
..\.venv\Scripts\python.exe ops\e2e\run.py SC-07 --runs 1 --as conantkd
if ($LASTEXITCODE -eq 0) { $ok++ }
if ($ok -eq 2) { 'VERDICT: S.1 PASS (2 of 2)' } else { "VERDICT: S.1 FAIL ($ok of 2)" }
# >>> Paste everything (never the password) into output.bash and tell the agent "output.bash updated". <<<
