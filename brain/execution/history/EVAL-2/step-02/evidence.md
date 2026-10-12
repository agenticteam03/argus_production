# EVAL-2 step 02 — the evaluation with the fixes (vm-095, 2026-10-12)

Run by the agent over SSH for `conantkd` (lease vm-095). The commands actually run are
[`eval-run-branch.sh`](eval-run-branch.sh) (the E.3 block of `code.bash` as one script, started with `nohup` after the
SSH drop of step 01; `TRIALS=5` for E.4). Each run: fetch `task/EVAL-2-model-trials` into `/opt/argus-v18/app`
(remote refs only), `git archive` it to `/opt/argus-v18/eval-src`, build `argus-v18-eval:eval2`, run
`eval-src/ops/eval-run.sh` with that image, cases and config. The checkout stayed `2a5f06b` every time
(`app HEAD 2a5f06b`); the running agent was not rebuilt.

## One trial per case, three prompt versions

| Run | Commit | Result | What it showed |
|---|---|---|---|
| E.3 06:14-06:24 | `fc09eb6` | 44/55, 0.75 (core 0.80); disk 1.00, dependency 0.40, health 0.20, nginx 0.60 | "escalate when the cause is only plausible" made the model escalate correct diagnoses |
| E.3b 06:33-06:40 | `7065d42` | 50/55, 0.89; disk, dependency, nginx 1.00; restart loop 0.50, health 0.60 | "the service that reported the symptom" made it escalate restart loops and failing checks, whose container is its own cause |
| E.3c 06:49-06:57 | `e0efc8a` | 53/55, 0.95 (core 0.98); all classes ≥ 0.80 | the rule names the host only; kept |

All three: `hard: 0 0 0`, `NO INTERFERENCE`. Results files `eval-20261012-061505.jsonl`, `-063337`, `-064952`.

## E.4 — five trials per case on `e0efc8a` (06:57:48Z → 07:33:21Z) — "after"

`eval-20261012-065751.jsonl`: 273 rows. The CLI died at run 274 (`unsupported-stale-data`, trial 4) without printing
its summary: one throwaway SQLite store per run in the container's 64 MiB `/tmp` (tmpfs), 273 of them with the model's
evidence filled it (the traceback was dropped by the block's `grep`; fixed in this branch: each run removes its store,
`test_a_replay_leaves_no_store_behind`, red seen). The two missing runs of that deterministic, no-model case were run
on the same image (`--category unsupported --trials 2`, `eval-20261012-073544.jsonl`: PASS, PASS) and merged as
trials 4 and 5. Summary recomputed with `argus.evaluation.score.summarize` (as in step 01):

```
runs 275 (cases 55, trials 5)
cases 275  passed 257  accuracy 0.93 (core 0.95)  abstention 0.96  recall@3 1.00  reads/incident 3.7  p50 7682 ms
  container_restart_loop             runs  30  accuracy 0.80  worst trial 0.67
  cpu_saturation                     runs  25  accuracy 1.00  worst trial 1.00
  dependency_unavailable             runs  25  accuracy 0.92  worst trial 0.80
  disk_pressure                      runs  40  accuracy 0.97  worst trial 0.88
  health_check_failed                runs  25  accuracy 0.80  worst trial 0.40
  monitoring_blind_spot              runs  25  accuracy 1.00  worst trial 1.00
  nginx_upstream_failure             runs  25  accuracy 0.96  worst trial 0.80
  postgresql_connection_exhaustion   runs  25  accuracy 1.00  worst trial 1.00
hard: 0 0 0
```

FAILs by case (of 5): `restart-sigkill-01` 5 (escalated: exit 137 with OOMKilled=false, no external kill named),
`ambiguous-health-no-cause` 2, `health-db-vm166-01` 2 (wording), and 1 each: `dep-cache-paused`, `dep-cache-stopped`,
`disk-filler-no-logs`, `health-api-vm095-01` (wording), `health-api-vm166-01` (wording), `health-api-vm166-02`,
`nginx-slow-check`, `restart-exit0-job-01`, `tool-failure-status`.

## Clean-up

`rm -rf /opt/argus-v18/eval-src`, `docker image rm argus-v18-eval:eval2`, and `docker image prune -f --filter
dangling=true` for the intermediate layers of the three builds. **Note:** that prune is host-wide (it removes any
dangling image, not only Argus's); `nonint-check.sh after` reported `NO INTERFERENCE: non-Argus objects unchanged`.
Next time remove only the Argus image by name. After: checkout `2a5f06b`, `LAB BASELINE OK`, `NO INTERFERENCE`. Lease
released.

**Commit ids.** On 2026-10-12, after the runs, this branch's commit messages were rewritten to drop attribution
trailers (the trees are unchanged, so the code that ran is the same). The ids recorded above map to the branch's
current commits: `01c2c7d` = `07cc3b2`, `fc09eb6` = `a01b22a`, `7065d42` = `372ac95`, `e0efc8a` = `8d42c19`,
`5ad9d8c` = `b6b8a0c`.
