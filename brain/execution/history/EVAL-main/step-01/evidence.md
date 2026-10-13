# EVAL on main d34f0cb — the model on the 55 cases, 5 trials (2026-10-13 UTC, conantkd's agent; session 4f8a9d4f8dc1)

Goal: measure the configured model on `main` after the AFTER-MERGE of #97–#111 (T-0019 3a/3b/3c with the `/tcp`
budget, the snapshot offered to no class, EVAL-4's labels, EVAL-5's allowed values, the #110 redactor), and compare
with the last batch (T-0019 3c step 07).

Run on vm-095: `sudo nohup bash /opt/argus-v18/app/ops/eval-run.sh --as conantkd --trials 5`, log
`/opt/argus-v18/eval-results/AFTER-MERGE-main.log`, results `eval-20261013-042857.jsonl` (both kept on vm-095). The
replay answers every read from the case fixtures: no target was read, only the model's API was called.

| Run | Accuracy (core) | Abstention | dependency | health | nginx | restart loop | disk | reads/incident | hard |
|---|---|---|---|---|---|---|---|---|---|
| T-0019 3c step 07 (`030690a`) | 0.96 (0.99) | 0.98 | 0.96 | 0.76 | 0.96 | | | | 0 0 0 |
| 3c, re-graded with EVAL-4's labels | 0.98 (0.99) | 0.98 | 0.96 | 0.92 | 0.96 | | | | |
| **`main` `d34f0cb`** | **0.96 (0.97)** | **0.98** | **0.92** | **0.88** | **0.92** | 0.97 | 0.97 | 3.8 | **0 0 0** |

Per class (`main`): container_restart_loop 0.97 (30 runs), cpu_saturation 1.00, dependency_unavailable 0.92,
disk_pressure 0.97 (40), health_check_failed 0.88, monitoring_blind_spot 1.00, nginx_upstream_failure 0.92,
postgresql_connection_exhaustion 1.00; recall@3 1.00; p50 7956 ms. 265 of 275 passed.

The 10 misses (one trial each unless noted):
- `ambiguous-dep-all-running` trial 2: `diagnosed` where abstention was expected;
- `dep-backend-wrong-network` trials 1 and 4: `diagnosed`, graded a miss (step 07 had one, an empty
  `root_cause_target`);
- `disk-filler-check` trial 4, `health-api-vm095-01` trial 5, `restart-exit0-job-01` trial 2: `no_action_escalated`;
- `health-api-vm166-01` trials 2 and 3, `nginx-slow-check` trials 3 and 4: `diagnosed`, graded a miss.

**Reading:** within the noise of 5 trials (one miss moves a class by 0.04): the same overall accuracy as step 07
(0.96), abstention unchanged, hard metrics still 0 0 0. dependency and nginx lost one run each, health is 0.88 (0.92
with the same labels at step 07). No class regressed by more than one run. Not yet looked at: why
`dep-backend-wrong-network` trials 1 and 4 failed this time (a follow-up for the next evaluation task, with the
results file).
