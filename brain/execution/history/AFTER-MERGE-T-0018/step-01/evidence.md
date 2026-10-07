# AFTER-MERGE (T-0018) step 01 — evidence (2026-10-07, conantkd, session 3307114120d3)

Goal: put both VMs' checkout back on `main` (`974d1d7`, after PRs #27 and #28) without restarting or rebuilding
anything. All blocks were run by the agent over SSH (`ssh argus-vm166|argus-vm095 'bash -s'`); nothing needed a
password.

Key output lines from output.bash, SANITIZED (no addresses, no secrets, no personal names).

| Block | Expected | Observed | Result |
|---|---|---|---|
| State probe (read-only) + session marker, both VMs | marker = this session; T-0018 checkout; `LAB BASELINE OK`; NO INTERFERENCE | `holder=conantkd session=3307114120d3` on both; vm-166 `e9b4fa3…`, vm-095 `65eb9f1…`, both `ref=task/T-0018-sc07-network`, 0 local modifications; `LAB BASELINE OK` on both; all `argus-v18-*` Up (postgres healthy); `NO INTERFERENCE` on both | OK |
| M.1 vm-166 | `SESSION OK`; `DEPLOY OK` on `main`; `ref=main`; `LAB BASELINE OK`; same uptime; NO INTERFERENCE | `SESSION OK`; `saved … before.txt (87 lines)`; rebuild hints name only the agent and its config (vm-095, not run); `DEPLOY OK: 974d1d779ff0 (main) on argus-vm166`; `ref=main`; `LAB BASELINE OK`; `argus-v18-exporter Up 10 hours` (not restarted); `NO INTERFERENCE: non-Argus objects unchanged` | OK |
| M.1 vm-095 | the same | `SESSION OK`; `saved … before.txt (69 lines)`; the same rebuild hints (not run); `DEPLOY OK: 974d1d779ff0 (main) on argus-vm095`; `ref=main`; `LAB BASELINE OK`; `argus-v18-agent Up 9 hours` (not restarted); `NO INTERFERENCE: non-Argus objects unchanged` | OK |

nonint-check: NO INTERFERENCE on vm-166 (yes) and vm-095 (yes).

**Result:** both VMs are on `main` `974d1d7`. Nothing was restarted. vm-166's target services run the same code as
`main`. The vm-095 agent image is from `65eb9f1`: `main` also holds `a90400e` (`knowledge.runbook` at Level 3,
class tag `knowledge`), which reaches the agent with T-0019's agent rebuild. The mounted `config/policy.yaml` now says
`max_tool_level: 3`; it is read at the next agent start, and the running code has no Level 3 capability, so nothing
changes until then.
