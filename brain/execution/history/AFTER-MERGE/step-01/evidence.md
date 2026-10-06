# AFTER-MERGE step 01 — evidence (2026-10-06, run by juanbetancurm, session accd19622024)

Goal: both VMs from the `task/lab-baseline-check` checkout (`58a51c3`) back to `main` after PRs #15–#18.

| Block | Expected | Observed | Result |
|---|---|---|---|
| A.0 lease + markers | lease claimed, same marker on both VMs | `Lease CLAIMED by juanbetancurm`; both VMs `holder=juanbetancurm session=accd19622024` | OK |
| A.1 vm-166 → main | `DEPLOY OK (main)`, LAB BASELINE OK, NO INTERFERENCE | first skipped (the A.2 block was pasted twice), then run: `DEPLOY OK: 2097eb155cc8 (main)`, hint: agent of vm-095 only; `ref=main`; `LAB BASELINE OK`; `NO INTERFERENCE` | OK (after A.3, see below) |
| A.2 vm-095 → main + agent | `DEPLOY OK (main)`, agent hint only, `langgraph`, db 15/15 | `DEPLOY OK: 2097eb155cc8 (main)`, hint: agent only (no migration); image built 25.1 s; `agent runner: langgraph`; healthz `"ok":true`, `llm_configured:true`; `VERDICT A.2 OK` (db check 15/15); `commit=2097eb1…`, `ref=main`; `LAB BASELINE OK`; `NO INTERFERENCE` | OK |
| A.3 release | lease released | `Lease released.` | OK |

State after this step: **both VMs on `main` `2097eb1`** (vm-095's agent image matches the deployed commit).

Protocol slip: A.1 ran **after** A.3 had released the lease. Harmless (nobody claimed the VMs in between and the
vm-166 marker still named this session), but a VM block must run inside the lease: run the blocks in their order.
