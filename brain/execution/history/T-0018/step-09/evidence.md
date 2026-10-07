# T-0018 step 09 — evidence (2026-10-07 06:09–06:18 UTC; conantkd, session 796fd4f3bf61)

Goal: SC-07 run 4 after the `get_container_status` description names the attached networks (`65eb9f1`).

Deploy, V.1 and V.3 by the agent over SSH at `conantkd`'s request; V.2 by `conantkd` (password), report kept in
`/tmp/sc07d.txt` on vm-095; the evidence texts read back from Postgres (read-only). Commands as in steps 04/05.
SANITIZED key lines.

| Block | Observed | Result |
|---|---|---|
| deploy vm-095 | `DEPLOY OK: 65eb9f1b1365`; `health 200`; the image's description ends "…and the names of the Docker networks it is attached to."; postgres `Up 25 hours (healthy)`; NO INTERFERENCE | OK |
| V.1 vm-166 | `backend health=healthy`; `networks=argus-lab-app` / `networks=argus-lab-iso`; `probe client->backend = 0`; `VERDICT V.1 OK` | OK |
| V.2 | `inc_6a1511e19269`; step 1 **`container.status` of the client (`networks=argus-lab-app`) and of the backend (`networks=argus-lab-iso`, healthy)**; step 2 **`query_runbook` → RB-009 `version="1.1.0"`**; step 3 conclude. `DIAGNOSED`, confidence high, root-cause target none: *"The client cannot reach the running backend because they are attached to different Docker networks: the client is on argus-lab-app while the backend is on argus-lab-iso. This supports a wrong network attachment/topology failure, not a backend crash … The client is the victim … correct the attachment/alias so both services share the intended application network, then verify DNS, TCP, and application protocol connectivity. Do not restart either container as a first response."* | OK |
| V.3 vm-166 | `SC-07 containers gone`; `argus-lab-iso gone`; `LAB BASELINE OK`; NO INTERFERENCE | OK |

nonint-check: NO INTERFERENCE on vm-095 (yes) and vm-166 (yes).

**Four runs compared:**

| Run | Change in place | Status of both sides | RB-009 read | Networks named |
|---|---|---|---|---|
| 1 `inc_fb92d115abb2` | `networks` field | yes | no | yes |
| 2 `inc_21f900ee6139` | + `query_runbook` | backend only | 1.0.0 | no |
| 3 `inc_dbd9ba0253a7` | + RB-009 1.1.0 | none | no | no |
| 4 `inc_6a1511e19269` | + tool description | **yes, step 1** | **1.1.0** | **yes** |

Run 4 is the first with all three: both sides' networks, RB-009 1.1.0, and the misattachment named. One run is not
a quality claim (≥ 5 runs per scenario, Phase 12). The root-cause target is empty: the fault is the attachment, not
one container.
