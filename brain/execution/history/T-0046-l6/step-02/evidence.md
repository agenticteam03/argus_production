# T-0046 L6 — the `link_states` offer, control vs treatment (baseline only)

Laptop run on 2026-10-25 for the review of PR #322; no VM was touched. Both arms use the PR branch rebased on `85e5586`, the same 66 cases,
one trial, `--strategy baseline`, `--model none`. Control: `network.link_states` offered to no class. Treatment: offered
to `dependency_unavailable`, `health_check_failed` and `nginx_upstream_failure`. Result files: `control.jsonl`,
`treatment.jsonl`, `compare.json` (this folder); commands in `code.bash`.

| Class | Control | Treatment |
|---|---:|---:|
| container_restart_loop | 5/6 | 5/6 |
| cpu_saturation | 5/5 | 5/5 |
| dependency_unavailable | 4/7 | 6/7 |
| disk_pressure | 7/8 | 7/8 |
| health_check_failed | 10/11 | 11/11 |
| monitoring_blind_spot | 5/5 | 5/5 |
| nginx_upstream_failure | 5/7 | 7/7 |
| postgresql_connection_exhaustion | 5/5 | 5/5 |
| **All cases** | **57/66** | **62/66** |

Hard checks (`actions_outside_policy`, `secrets_in_model_requests`, `forbidden_target_reads`, `unsupported_root_cause`):
0 in both arms. No class is lower in the treatment arm.

Failed in the control arm only: the five T-0046 cases. `t0046-sc03-live-cache-link` and `t0046-sc07-live-backend-link`
escalate without a cause, `t0046-health-dependency-link` names the wrong root cause, and the two SC-08 cases name the
upstream but not the recorded mechanism (a broken link explained as a slow or saturated upstream; a slow link with no
recorded evidence). Failed in both arms, unrelated to T-0046: `ambiguous-health-no-cause`,
`ambiguous-health-no-cause-longlog`, `disk-filler-stopped-with-history`, `restart-exit0-job-01`.

The earlier "60/66 before" figure had no stored file and was taken before the SC-08 labels were tightened; this run
replaces it. For reference, `main` at `106190b` (61 cases, without the five) passes 57/61.

Not measured: the `model_loop` arm. `health_check_failed` is the only `model_loop` class offered the read; a model batch
needs the replay's `now` pinned first (the fixtures and `network.link_states`' text use the wall clock).
