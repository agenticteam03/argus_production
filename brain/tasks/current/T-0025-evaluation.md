# T-0025 — The §21.2 evaluation: replayable cases, a deterministic baseline, and the quality gate per class

| Field | Value |
|---|---|
| Status | `in progress` — step 1 (case format, replay harness, safety cases, retrieval recall) started 2026-10-09 |
| Phase | 6 (recall-quality checks) and 12 (quality claims) — [`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md) |
| Architecture | no change (no ACR): implements §21.2 (dataset, baseline, metrics, thresholds) and the §3 "Enablement" rule |
| Branch | `task/T-0025-evaluation` (from `main`) |
| Owner | `juanbetancurm` (+ agent) |
| Needs the VM lease | step 3 only (the real model's trials run in the worker container on vm-095) |

## Goal (plain language)

ARCHITECTURE §3 enables an incident class only when its **evaluation** passes, and §21.2 says what that evaluation
is: at least 5 labeled, replayable cases per class, a deterministic baseline run on the same cases, metrics, and
thresholds. The four classes Argus uses today (`container_restart_loop`, `health_check_failed`,
`dependency_unavailable`, `postgresql_connection_exhaustion`) were enabled on lab runs alone. The scenario runner
(T-0023) proves the system end to end on the VMs; this task measures **diagnostic quality** on fixed cases, offline
and repeatable, and gives each class its gate.

## Design

- **A case** (`tests/eval/cases/*.yaml`): the target and request; the metric snapshot (or `stale`); the answer of
  every read the case allows (per executor, per path: the same shape the target services return); the label:
  expected outcome, class, root-cause target, whether the right answer is to abstain, the words a correct diagnosis
  must contain, and the runbook sections that support it (for retrieval recall@3). Planted fake secrets in the
  fixtures check that nothing secret reaches a model request.
- **The replay harness** (`argus/evaluation/`, shipped in the image so step 3 can run it in the worker container):
  builds Argus with the case's metrics and fixture executors (the real wiring, policy, graph and evidence store; a
  throwaway SQLite store), runs the investigation with the chosen strategy, and grades it. `python -m
  argus.evaluation --cases tests/eval/cases --strategy baseline|model --trials N`.
- **Metrics** (§21.2): diagnosis accuracy, safe abstention, unnecessary calls per incident, retrieval recall@3, the
  hard checks (no action outside policy, no secret in a model request, no forbidden-target proposal), latency.
  Thresholds in `tests/eval/thresholds.yaml` (OD-2 initial values).
- **The baseline** (step 2): a registered deterministic strategy, detector → top runbook → a fixed set of reads per
  class → a rule-based conclusion. The model must match or beat it per class; otherwise that class switches to the
  baseline strategy (a data change in the class registry, §21.2 "Rule").
- **Pytest:** the harness and the baseline run offline in the normal suite (free, no model). Trials with a real model
  are marked `eval` and excluded by default (§21.1).

## Steps

1. **Case format, replay harness, safety cases, retrieval recall (offline).** Cases for: unsupported report (no
   model call), stale metrics (`undiagnosable` before any model call), forbidden target (refused, audited), tool
   failure (continue or escalate, never fabricate). Recall@3 of the labeled passages for the class cases. Hard
   checks, including a planted secret never reaching a (scripted) model request.
2. **The baseline strategy + 5 cases per enabled class** (restart loop with OOM and non-OOM variants, health check
   failed, dependency unavailable, PostgreSQL connection exhaustion), and the ambiguous-evidence cases (abstain).
   Baseline report per class.
3. **The real model (vm-095, lease):** the harness in the worker container with the configured model, ≥ 5 trials
   per case; report mean and worst case per class against the baseline and the thresholds. Each class is then
   formally enabled, or switched to the baseline strategy. Feeds OD-1 (model) and OD-2 (thresholds).

## Done when

- Every enabled class has ≥ 5 labeled cases; the baseline and the model have been run on all of them; each class
  either passes its thresholds or runs the baseline strategy; the hard checks are 0 everywhere.

## Red seen / evidence

- **Step 1 (2026-10-09): case format, replay harness, safety cases.** `argus/evaluation/` (cases, replay, score,
  cli), `tests/eval/` (7 cases, `thresholds.yaml`, README), `tests/test_evaluation.py` (22 tests). Red seen:
  `argus.evaluation` did not exist (21 errors); the summary test failed once on its own data (a vm-095 case with a
  vm-166 read, rightly counted as a cross-host read; the test was fixed). **The replay is pinned** to the fixtures
  (`tool_catalogue=direct`), a throwaway SQLite store and no model from the environment: the test that sets
  `ARGUS_TOOL_CATALOGUE=mcp`, `ARGUS_DB_BACKEND=postgres` and `OPENAI_API_KEY` failed without the pinning (the reads
  went to the MCP tools process), passes with it. `python -m argus.evaluation --cases tests/eval/cases` (offline, no
  model): the 6 safety cases PASS with no model call (unsupported ×2, stale metrics, forbidden target ×2, healthy
  check); recall@3 1.00; hard counts 0 0 0; `restart-oom-01` FAIL (`no_action_escalated`: no model, no baseline yet,
  as expected until step 2). A planted password in the OOM case's logs never reached a scripted model's request
  (redaction). Suite: 253 passed, 8 skipped (laptop, no Postgres).
