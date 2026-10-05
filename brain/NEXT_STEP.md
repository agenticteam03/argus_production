# Next step

**Now (repository setup, owner `juanbetancurm`):** finish shared-Brain step **B6**: Task B6d in `execution/current/code.bash` (read-only deploy keys on
both VMs; the PR with `ops/deploy.sh`, reviewed by `conantkd` or `juanes6554`; then `deploy.sh init` on both VMs).

**Then — the first real task through the protocol (the pilot, B7):**

| | |
|---|---|
| Task | [**T-0013 — LangGraph skeleton with a Postgres checkpointer**](tasks/current/T-0013-langgraph-skeleton.md) |
| Phase | 9 (agent workflow), first slice |
| Who | `juanbetancurm` (pilot), reviewed by the next developer |
| Needs the VM lease | yes, for the deployment steps only |

Before starting T-0013, if the team password is at hand: run the pending login test for each user (legacy step
12b.2 in `execution/history/legacy/code.bash`) and record the result in `CURRENT_STATE.md`.
