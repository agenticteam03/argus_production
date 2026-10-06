# AFTER-MERGE step 01 — evidence (2026-10-06, run by juanbetancurm, session accd19622024)

Goal: both VMs from the `task/lab-baseline-check` checkout (`58a51c3`) back to `main` after PRs #15–#18.

| Block | Expected | Observed | Result |
|---|---|---|---|
| A.0 lease + markers | lease claimed, same marker on both VMs | `Lease CLAIMED by juanbetancurm`; both VMs `holder=juanbetancurm session=accd19622024` | OK |
| A.1 vm-166 → main | `DEPLOY OK (main)`, LAB BASELINE OK, NO INTERFERENCE | **not run**: the A.2 block was pasted twice instead | **PENDING** |
| A.2 vm-095 → main + agent | `DEPLOY OK (main)`, agent hint only, `langgraph`, db 15/15 | `DEPLOY OK: 2097eb155cc8 (main)`, hint: agent only (no migration); image built 25.1 s; `agent runner: langgraph`; healthz `"ok":true`, `llm_configured:true`; `VERDICT A.2 OK` (db check 15/15); `commit=2097eb1…`, `ref=main`; `LAB BASELINE OK`; `NO INTERFERENCE` | OK |
| A.3 release | lease released | `Lease released.` | OK |

State after this step: **vm-095 = `main` `2097eb1`** (agent image matches); **vm-166 = `58a51c3`** (checkout of
`task/lab-baseline-check`; its running services are identical to `main`, only the DEPLOYED marker is behind).
Remaining: A.1 on vm-166 (`execution/current/code.bash`).
