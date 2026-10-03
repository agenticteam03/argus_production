# T-0013 — LangGraph skeleton with a Postgres checkpointer (Phase 9, first slice)

| Field | Value |
|---|---|
| Status | `executed` (steps 1-2 of 5; laptop only) |
| Phase | 9 — agent workflow ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md)) |
| Architecture | §10 (orchestration, the safety skeleton), §16 (persistence, checkpoints), §19 (failure behaviour), §21.1 |
| Branch | `task/T-0013-langgraph-skeleton` |
| Owner | `juanbetancurm` (pilot of the shared-Brain protocol) |

## Goal (plain language)

Today the investigation steps run in a plain Python loop (`argus/orchestration/runner.py`, `SkeletonRunner`). If the
agent crashes mid-investigation, the investigation is lost. v1.8 requires the same skeleton as a **LangGraph graph**
whose state is **checkpointed in Postgres**, so an investigation resumes where it stopped. This slice replaces the
runner and nothing else: same nodes, same outputs, same safety rules.

## In scope

- A LangGraph `StateGraph` with the v1.8 nodes: `detect`, `recall`, `investigate`, `act`, `evidence_pack`, `record`
  (the same names the run events and the formatted CLI already use), with the same routing:
  `detect → record` (no incident), `detect → evidence_pack → record` (unsupported / undiagnosable),
  `detect → recall → investigate ⇄ act → record` (a class).
- The Postgres checkpointer (LangGraph's Postgres saver) on the existing `argus-v18-postgres`; its tables through a
  new forward-only migration; the runtime role gets only what the checkpointer needs.
- A switch to roll back: `ARGUS_RUNNER=langgraph|plain` (default `langgraph` once verified).
- The existing guarantees unchanged: every tool call through `InvokeCapability`, budgets, evidence and audit
  insert-only, escalation on provider errors, the `_scrape_up` freshness gate, `UNAVAILABLE` executors.

## Out of scope (later slices)

Splitting api / worker / scheduler (T-0014+), the MCP tools child (Phase 4), HITL nodes beyond the closed write gate.

## Acceptance criteria

1. Tests (red first):
   - the node sequence for diagnosed, healthy and unsupported runs is identical to the plain runner's;
   - **resume after a crash:** a run interrupted after `recall` resumes from its checkpoint and finishes without
     repeating completed tool calls;
   - the full offline suite and the Postgres tests pass; the plain runner still passes behind the switch.
2. Deployment on vm-095 (agent only), with `nonint-check.sh` NO INTERFERENCE.
3. On the VMs: H-1 (healthy, no model call), SC-09 (evidence pack, no model call) and SC-01 (diagnosed, RB-001)
   give the same outcomes as before; formatted and `--raw` views show the same node sequence.
4. Brain updated on the branch: `CURRENT_STATE.md`, `tdd/CURRENT_TEST_STATE.md`, journal entry; SUMMARY.md row
   "Workflow engine" resolved.

## Steps (draft — refine at the start of the task)

1. Add `langgraph` + the Postgres checkpointer to `pyproject.toml`; check ARM64 wheels exist for the agent image.
2. Red: the node-sequence test against a `GraphRunner`; then implement the graph with in-memory checkpoints.
3. Red: the resume-after-crash test; then the Postgres checkpointer + migration (`002_checkpoints.sql`).
4. Switch `ARGUS_RUNNER`; full suite; Postgres tests.
5. VM: state probe → deploy (`ops/deploy.sh`) → migrate → rebuild the agent → H-1, SC-09, SC-01 → NO INTERFERENCE.

## Red seen / evidence

- **Step 1 (2026-10-03):** `langgraph` 1.2.12 + `langgraph-checkpoint-postgres` 3.1.2 added. Every dependency (43
  packages) has a ready-made Linux ARM64 / Python 3.12 build (`pip download --platform manylinux*_aarch64
  --only-binary=:all:`), so the agent image builds on vm-095 without compiling.
- **Step 2 (2026-10-03):** `argus/orchestration/graph_runner.py` (`GraphRunner`, a subclass of the plain runner that
  reuses its audit, evidence, scope, context and record helpers; state = plain JSON) and `ARGUS_RUNNER=plain|langgraph`
  in `wiring.py` (default still `plain` until verified on the VMs).
  - Red seen: `tests/test_graph_runner.py` failed with `'SkeletonRunner' == 'GraphRunner'` (no graph runner yet).
  - Green: parity with the plain runner in 5 scenarios (diagnosed, healthy, unsupported, undiagnosable, refused:
    same nodes, outcome, root cause); resume after a simulated crash continues after the last checkpoint and does
    **not** repeat the completed read (audit `incident.resumed`); the switch refuses unknown values. Suite: 54 passed.
  - Checkpointer: in-memory for now (resume works within one process); step 3 = Postgres.
