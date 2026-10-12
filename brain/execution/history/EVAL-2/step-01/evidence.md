# EVAL-2 step 01 — state probe and 1 trial per case (vm-095, 2026-10-12)

Run by the agent over SSH for `conantkd` (lease vm-095, session `af6224b988ab`).

## E.0 state probe (05:3x UTC)

```
session marker: mine
commit=2a5f06b7168af7520f035fda23704549888553d4
ref=main
LAB BASELINE OK
argus-v18-* : 13 containers Up (agent, worker, scheduler Up 6 hours; postgres, cadvisor healthy)
agent image created=2026-10-11T23:23:55Z   (rebuilt in E2E-5 step 2 on 2a5f06b)
55                                          (cases in /opt/argus-v18/app/tests/eval/cases)
saved /opt/argus-v18/baseline/before.txt (54 lines)
```

`uname -n` on the VMs now answers `argus-vm095` / `argus-vm166` (START_HERE updated).

## E.1 `ops/eval-run.sh --as conantkd --trials 1` (05:32:13Z → 05:39:24Z, 7 min)

Results file: `/opt/argus-v18/eval-results/eval-20261012-053213.jsonl`.

```
cases 55  passed 48  accuracy 0.84 (core 0.89)  abstention 1.00  recall@3 1.00  reads/incident 3.6  p50 8005 ms
  container_restart_loop             runs   6  accuracy 0.83  worst trial 0.83
  cpu_saturation                     runs   5  accuracy 1.00  worst trial 1.00
  dependency_unavailable             runs   5  accuracy 1.00  worst trial 1.00
  disk_pressure                      runs   8  accuracy 0.38  worst trial 0.38
  health_check_failed                runs   5  accuracy 0.80  worst trial 0.80
  monitoring_blind_spot              runs   5  accuracy 1.00  worst trial 1.00
  nginx_upstream_failure             runs   5  accuracy 1.00  worst trial 1.00
  postgresql_connection_exhaustion   runs   5  accuracy 1.00  worst trial 1.00
hard: 0 0 0  (actions_outside_policy, secrets_in_model_requests, forbidden_target_reads)
NO INTERFERENCE: non-Argus objects unchanged
```

The 7 FAILs (read from the results file):

| Case | Outcome / root cause | Reads | Reading |
|---|---|---|---|
| `disk-filler-stopped-with-history` | diagnosed, host (expected the filler) | disk_usage, filler status | real miss: the writer is stopped, so `confirm_then_reason` plans no log read and the model did not ask for it |
| `disk-filler-no-logs` | diagnosed, host (expected escalate) | + filler logs (empty), resources | real miss: "does not prove it is the writer", yet concluded |
| `disk-root-full-writer-elsewhere` | diagnosed, host (expected escalate) | disk_usage ×2, filler status, logs | real miss: "the producer is not established", yet concluded |
| `disk-filler-read-only` | diagnosed, filler (expected escalate) | + filler logs | **fixture contradiction**: the ro-mount case's log says `filler: wrote 202 MiB to /fill, 92.6% used` |
| `disk-filler-stopped` | diagnosed, filler (expected escalate) | + filler logs (`filler: done`) | debatable label: an exited filler of the full mount |
| `health-db-vm166-01` | diagnosed, correct root cause | 4 reads | wording only ("health probe") |
| `restart-sigkill-01` | diagnosed, correct target | status, events | wording only (says OOMKilled=false, not "not OOM"/"SIGKILL") |

The cases were **not changed** before step 02 (T-0025: no label tuning after seeing answers).

## E.2 `ops/eval-run.sh --as conantkd --trials 5` on the same image (05:40:12Z → 06:14:21Z, 34 min) — "before"

Results file: `/opt/argus-v18/eval-results/eval-20261012-054012.jsonl` (275 rows). The SSH session dropped at
05:57 (`Connection reset by peer`); the one-off container kept running and wrote every row, so the summary was
recomputed from the file with `argus.evaluation.score.summarize` (the same function the CLI prints; checked against
E.1's printed summary: identical). `nonint-check.sh after`: `NO INTERFERENCE`.

```
runs 275 (cases 55, trials 5)
cases 275  passed 234  accuracy 0.83 (core 0.87)  abstention 0.93  recall@3 1.00  reads/incident 3.5  p50 7713 ms
  container_restart_loop             runs  30  accuracy 0.80  worst trial 0.67
  cpu_saturation                     runs  25  accuracy 1.00  worst trial 1.00
  dependency_unavailable             runs  25  accuracy 0.96  worst trial 0.80
  disk_pressure                      runs  40  accuracy 0.45  worst trial 0.38
  health_check_failed                runs  25  accuracy 0.68  worst trial 0.60
  monitoring_blind_spot              runs  25  accuracy 1.00  worst trial 1.00
  nginx_upstream_failure             runs  25  accuracy 0.96  worst trial 0.80
  postgresql_connection_exhaustion   runs  25  accuracy 1.00  worst trial 1.00
hard: 0 0 0
```

FAILs by case (of 5): `disk-filler-no-logs` 5, `disk-filler-stopped` 5, `restart-sigkill-01` 5 (wording ×4, escalated ×3),
`disk-filler-read-only` 4, `disk-root-full-writer-elsewhere` 4, `health-db-vm166-01` 4 (wording), `ambiguous-health-no-cause` 3,
`disk-filler-stopped-with-history` 3, `health-api-vm095-01` 2 (wording), and 1 each: `dep-cache-paused`, `disk-filler-check`,
`health-api-vm166-01`, `health-api-vm166-02`, `nginx-slow-partial`, `restart-exit0-job-01`.
