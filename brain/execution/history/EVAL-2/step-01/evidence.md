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
