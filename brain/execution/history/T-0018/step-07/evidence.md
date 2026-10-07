# T-0018 step 07 — evidence (2026-10-07 05:36–05:45 UTC; conantkd, session 796fd4f3bf61)

Goal: deploy `knowledge.runbook` (`query_runbook`) on vm-095 and run SC-07 again: does the model reach the
branch runbook RB-009 during the investigation?

The deploy, V.1 and V.3 were run by the agent over SSH at `conantkd`'s request; V.2 (needs the user's password)
by `conantkd`, with the full report kept in `/tmp/sc07b.txt` on vm-095 and read back by the agent. Key output
lines, SANITIZED (no VM addresses, no secrets, no personal names). The commands are those of step 04 (rebuild)
and step 05 (V.1–V.3); see those folders.

| Block | Expected | Observed | Result |
|---|---|---|---|
| deploy vm-095 | `DEPLOY OK`, agent rebuilt, postgres untouched | `DEPLOY OK: 68d4963045fb (task/T-0018-sc07-network) on argus-vm095`; `health 200`; agent `Up 5 seconds`, postgres `Up 25 hours (healthy)`; `agent has query_runbook argus_internal worker`; `LAB BASELINE OK`; NO INTERFERENCE | OK |
| V.1 vm-166 | backend healthy on `argus-lab-iso`, client on `argus-lab-app`, probe 0 | containers started; `backend health=healthy`; `networks=argus-lab-app` / `networks=argus-lab-iso`; `[Errno -3] Try again`; `probe client->backend = 0`; `VERDICT V.1 OK` | OK |
| V.2 detect / recall | `dependency_unavailable`; RB-003 | `incident inc_21f900ee6139`; `dependency_probe_min=0.0`; RB-003 (2 sections), RB-004 | OK |
| V.2 investigate | the model reads RB-009 when the evidence points to the network | step 1 DNS of the client resolved, TCP `argus-lab-backend:8080` **FAILED**; **step 2 `knowledge.runbook` → `[argus@vm-166] query_runbook ✓ RB-009: 3 section(s) for 'diagnostic workflow for back…'`**; step 3 DNS of the backend **FAILED**, `container.status` of the backend running; step 4 conclude | OK |
| V.2 record | `DIAGNOSED`, a network problem, no restart | `outcome: DIAGNOSED · class dependency_unavailable`; `root cause: vm-166/host:vm-166 · confidence high`; *"unavailable at the name-resolution layer … the backend container itself is running and healthy … not supported as the root cause; the client is the victim … inspect the app-network service-discovery record, resolver reachability, and network attachment/route … Do not restart the backend"*; 5 cited evidence records | OK |
| V.3 reset | containers and network gone; baseline | `SC-07 containers gone`; `argus-lab-iso gone`; `LAB BASELINE OK`; `NO INTERFERENCE: non-Argus objects unchanged` | OK |

nonint-check: NO INTERFERENCE on vm-095 (yes) and vm-166 (yes).

**Result:** the branch runbook RB-009 is reached through `query_runbook`, chosen by the model after the TCP probe
failed, and its layered workflow (name resolution before transport) shows in the next step and in the diagnosis.

**Compared with run 1** (`inc_fb92d115abb2`, before `knowledge.runbook`): run 1 named both networks and blamed the
backend's attachment; run 2 stays at the name-resolution layer and names the host as root-cause target (Docker
networks are host objects) without naming `argus-lab-iso`. Both are correct and advise no restart; one run each
supports no quality claim (≥ 5 runs per scenario, Phase 12).
