# OP-012 — `max_per_incident` holds for the whole incident under the LangGraph runner

| Field | Value |
|---|---|
| Status | `done` — step 1 (the fix, offline) 2026-10-12, PR #92 merged; step 2: vm-095's agent, worker and scheduler on `main` `244453b` 2026-10-12 (T-0033 step 2's deploy, `CURRENT_STATE.md`) |
| Phase | 9 (LangGraph skeleton) / 4 (policy) — [`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md) |
| Found by | the SC-05 code review (2026-10-11, `juanbetancurm` + agent): `GraphRunner._ctx` builds a new `InvocationContext` per act node |
| Architecture | no change (no ACR): the code now does what §12.4 step 3 (budget) and `config/policy.yaml` already say |
| Branch | `task/OP-012-incident-read-budget` (from `main`) |
| Owner | `juanbetancurm` (+ agent) |
| Needs the VM lease | step 2 only (both: an agent rebuild on vm-095) |

## Goal (plain language)

`config/policy.yaml` gives every capability a `max_per_incident` (for example `container.status: 8`), and
`InvokeCapability` refuses a read once the incident's counter reaches it. The counters live in the
`InvocationContext`. The plain runner keeps one context for the whole run, so the limit holds. The LangGraph runner
(the one deployed) builds a new context in every `act` and `evidence_pack` step, and since T-0013 it runs ONE read per
graph step for the checkpoint, so every read started from a counter of zero: the limit was never reached. A model that
kept asking for the same read was bounded only by the step budget (`max_steps` × `max_reads_per_step`, 16 by
default), not by the policy.

## Step 1 (done, offline)

- `GraphRunner._ctx(inc, caller, evidence)` rebuilds the counters from the incident's evidence in the run state: one
  per executed read of each capability; a refused read does not count (the plain runner counts only allowed reads).
  The evidence is checkpointed, so a resumed run keeps its counts.
- Tests: `tests/test_op012_incident_budget.py` (3; red seen: `langgraph: 16 container.status reads executed, the
  policy allows 8`). Both runners stop at 8 with a `max_per_incident` refusal; the limit survives a crash and resume.
  `test_graph_runner.py`, `test_core.py` and the evaluation tests pass (143; the Postgres checkpoint-migration test is
  blocked locally by Windows Application Control and runs in CI).

## Step 2 (after the merge, both leases)

vm-095: backup, `deploy.sh main`, rebuild agent, worker and scheduler together; the checks of the AFTER-MERGE block.
No scenario re-run is needed for the fix itself; the next scenario batch runs on it.

## Limits

A refused read is still recorded as evidence (`REFUSED … used 8/8`) and the model sees it, as before; the step budget
still ends the investigation.
