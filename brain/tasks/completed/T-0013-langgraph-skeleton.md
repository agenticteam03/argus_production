# T-0013 — LangGraph skeleton with a Postgres checkpointer (Phase 9, first slice)

| Field | Value |
|---|---|
| Status | `verified` on vm-095 (2026-10-04); PR open — merged = done |
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
- **Steps 3-4 (2026-10-04):** the Postgres checkpointer.
  - `deploy/migrations/002_checkpoints.sql` = LangGraph's checkpoint schema (library migrations 0-9, recorded in
    `checkpoint_migrations`), created by the owner; indexes non-concurrent (one transaction per migration); the runtime
    role gets SELECT/INSERT/UPDATE only (no DELETE, no DDL).
  - `PostgresStore.checkpointer()` (own small pool: autocommit, dict rows, no prepared statements); `wiring.py` uses it
    when `ARGUS_RUNNER=langgraph` on Postgres; `argus db check` proves 15 guarantees (+ checkpoint insert allowed,
    checkpoint DELETE refused); `compose.core.yml` passes `ARGUS_RUNNER` (default `plain`).
  - Red seen: `test_checkpoint_migration_covers_every_library_migration` (no 002 file) and
    `test_graph_runner_resumes_from_postgres_after_a_restart` (`'InMemorySaver' == 'PostgresSaver'`).
  - Green: a NEW app (new pool, nothing in memory) resumes the crashed run from Postgres without repeating the read.
    Full suite against a throwaway Postgres: **60 passed**.
- **Step 5 (VMs) needs PR #2 (`ops/deploy.sh`) merged first:** deploy this branch on vm-095, run `ops/db-migrate.sh`
  (applies 002), `argus db check` (15/15), rebuild the agent with `ARGUS_RUNNER=langgraph`, then H-1, SC-09, SC-01 and
  NO INTERFERENCE. Rollback: `ARGUS_RUNNER=plain` (the 002 tables stay, unused).
- **Step 5 (2026-10-04, VMs) — verified.** `deploy.sh init` on both VMs (vm-166: `main`, vm-095: this branch);
  migration 002 applied; agent rebuilt with `ARGUS_RUNNER=langgraph`; `argus db check` 15/15; H-1 HEALTHY, SC-09
  UNSUPPORTED, SC-01 DIAGNOSED (RB-001), each run checkpointed in Postgres; NO INTERFERENCE on both VMs. First SC-01
  attempt escalated (UNSUPPORTED) because the wait checked Docker's restart counter while Prometheus still had 1 —
  fixed with a Prometheus readiness gate. Evidence: `execution/history/T-0013/step-05/evidence.md`.
- **Closing:** compose now defaults to `ARGUS_RUNNER=langgraph`; `wiring.py` keeps `plain` as the library default
  (tests choose explicitly). Not in this slice: automatic resume of interrupted runs (needs the worker, T-0014).
- **Review (conantkd, 2026-10-05):** re-ran step 5 on the VMs (same results; evidence in
  `execution/history/T-0013-review/step-01/`) and did the per-user login test (all three HEALTHY). Findings:
  1. `ARGUS_RUNNER` default: already `langgraph` in `compose.core.yml` (closing commit, not yet pushed when he
     reviewed); `wiring.py` keeps `plain` as the library default because the tests choose explicitly.
  2. Brain items (journal, SUMMARY row, CURRENT_STATE): already in the closing commit, likewise.
  3. **A crash in the middle of `act` repeated the reads already completed in that step** (criterion 1). Fixed:
     `act` and `evidence_pack` make one read per graph step, so each completed read is checkpointed. Red seen:
     `test_resume_inside_act_does_not_repeat_completed_reads` (status read twice) and
     `test_resume_inside_evidence_pack_does_not_repeat_completed_reads` (8 reads for 6 distinct). Suite: 63 passed.
  4. Checkpoint growth (no retention, orphaned checkpoints of failed runs) -> proposal OP-004, separate PR.
  5. `restarts_10m` undercounts when the first sample is already above 0 -> proposal OP-005, separate PR.
- **Final review (conantkd, 2026-10-05, on `5a1b765`):** suite 63 passed / 5 skipped locally (Postgres tests green in
  CI); red seen reproduced for both new tests on the previous `graph_runner.py`. Approved and merged as is, with one
  follow-up:
  6. The fixed `recursion_limit` of 100 can be too small now that each read is its own graph step (worst case
     `max_steps × (1 + max(reads_per_step, 6)) + 4`; 60 with the defaults, 144 with `ARGUS_MAX_STEPS=20`). Not a
     problem with today's configuration -> OP-006.
  - Not yet run on the VMs: vm-095 still runs `c87d76c`. Repeat H-1 / SC-09 / SC-01 after `deploy.sh main`.
