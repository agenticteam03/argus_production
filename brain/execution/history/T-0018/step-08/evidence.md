# T-0018 step 08 — evidence (2026-10-07 05:54–06:00 UTC; conantkd, session 796fd4f3bf61)

Goal: SC-07 run 3 with RB-009 1.1.0 (on Docker, compare the networks before blaming DNS) in the agent image.

Deploy, V.1 and V.3 by the agent over SSH at `conantkd`'s request; V.2 by `conantkd` (password), full report kept in
`/tmp/sc07c.txt` on vm-095 and read back. Commands as in steps 04/05. SANITIZED key lines.

| Block | Observed | Result |
|---|---|---|
| deploy vm-095 | `DEPLOY OK: 90df56d55bcd (task/T-0018-sc07-network)`; `health 200`; `version: 1.1.0` (RB-009 in the image); postgres `Up 25 hours (healthy)`; NO INTERFERENCE | OK |
| V.1 vm-166 | `backend health=healthy`; `networks=argus-lab-app` / `networks=argus-lab-iso`; `probe client->backend = 0`; `VERDICT V.1 OK` | OK |
| V.2 | `inc_dbd9ba0253a7`; detect `dependency_unavailable`; recall RB-003 (2), RB-004; step 1 DNS of the client resolved + client logs; step 2 DNS of the backend **FAILED**, TCP 8080 **FAILED**; step 3 conclude. `DIAGNOSED`, root cause `vm-166/host:vm-166`, confidence high: *"a DNS/service-discovery failure for the declared dependency name argus-lab-backend … the client is the victim … inspect the app-network DNS/service registration and backend network attachment/advertisement … Do not restart containers"* | OK, but RB-009 **not read** and the networks **not named** |
| V.3 vm-166 | `SC-07 containers gone`; `argus-lab-iso gone`; `LAB BASELINE OK`; `NO INTERFERENCE` | OK |

nonint-check: NO INTERFERENCE on vm-095 (yes) and vm-166 (yes).

**Three runs compared (same fault):**

| Run | Agent | RB-009 read | Backend status read | Networks named | Root-cause target |
|---|---|---|---|---|---|
| 1 `inc_fb92d115abb2` | no `query_runbook` | no | yes (step 1) | **yes** | backend |
| 2 `inc_21f900ee6139` | `query_runbook`, RB-009 1.0.0 | **yes** (step 2) | yes (step 3) | no | host |
| 3 `inc_dbd9ba0253a7` | `query_runbook`, RB-009 1.1.0 | no | no | no | host |

All three: DIAGNOSED, the network/name layer, the client a victim, no restart. **Reading RB-009 is the model's
choice** (1 of 2 runs since it became possible), so the 1.1.0 change was not exercised in run 3. What the model sees
every time is the parent runbook RB-003's "Diagnostic workflow" (recalled in all three runs), whose step 2 reads
"DNS failure → H1/RB-009" and so stops at the name layer, the same gap RB-009 1.0.0 had.
