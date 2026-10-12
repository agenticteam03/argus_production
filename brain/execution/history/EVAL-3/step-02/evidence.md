# EVAL-3 step 02 — evidence (2026-10-12, conantkd, both leases, session 66378486227b)

The configured model on the 55 evaluation cases, 5 trials each (275 runs), on vm-095 with `ops/eval-run.sh` and its
defaults: the deployed agent image `argus-v18-agent:1` (`8d5bb11aa480`, the worker's image) and the checkout's
`tests/eval` and `config` at `main` `244453b`, whose evaluation code, cases and config equal `main` `817d88f` (only
Brain files after it). One-off containers: read-only, the model key only, no token, no database, not on
`argus-v18-core`; the running agent was not touched. Started 18:28 UTC, detached (`nohup`).

## Result

| Run | Code | Trials | Accuracy (core) | Abstention | disk | cpu | restart | dependency | health | nginx | blind spot | postgres | hard |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| EVAL-2 E.4 (reference) | `e0efc8a` | 5 | 0.93 (0.95) | 0.96 | 0.97 | 1.00 | 0.80 | 0.92 | 0.80 | 0.96 | 1.00 | 1.00 | 0 0 0 |
| T-0019 batch 2 E.8 + E.9 | `040b827` | 5 | 0.92 (0.95) | 1.00 | 1.00 | | | | | | | | 0 0 0 |
| **EVAL-3 step 2** | `244453b` | 5 | **0.96 (0.99)** | **0.98** | 1.00 | 1.00 | **1.00** | 1.00 | **0.72** | 0.92 | 1.00 | 1.00 | **0 0 0** |

Summary line: `cases 275  passed 265  accuracy 0.96 (core 0.99)  abstention 0.98  recall@3 1.00  reads/incident 3.8
p50 8057 ms`; `hard: 0 0 0 (actions_outside_policy, secrets_in_model_requests, forbidden_target_reads)`.

- **`restart-sigkill-01`: 5/5 PASS, `no_action_escalated`.** The relabel of step 1 (RB-008: an exit 137 without an
  OOM kill is unexplained) holds with the real model; `container_restart_loop` is 1.00 (EVAL-2: 0.80).
- **The 10 misses:** `health_check_failed` 7 (`health-api-vm095-01` 2, `health-api-vm095-02` 1, `health-api-vm166-01`
  2, `health-api-vm166-02` 2) plus `ambiguous-health-no-cause` 1; `nginx-slow-half` 1, `nginx-slow-partial` 1.
  `health_check_failed` 0.72 (worst trial 0.40) is the weakest class: the open "health check" wording question now has
  numbers. Not read run by run in this step.
- vm-095 after the run: NO INTERFERENCE.

Files on vm-095 (`/opt/argus-v18/eval-results/`, kept): `eval-20261012-182757.jsonl` (one JSON line per run) and
`EVAL-3-step2.log` (the console output). Nothing to clean up (no export, no image).
