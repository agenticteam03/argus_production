# T-0049 R1 step 01 — evidence: `container.detailed_logs` offered to `health_check_failed`, vm-095 (2026-10-22, juanbetancurm)

Goal: the first "evaluate before adding" batch (T-0049 R1): does offering `container.detailed_logs` (T-0037, built,
offered to no class) to the model-driven `health_check_failed` class improve its investigations? Both arms use the
same 12 cases (the five labelled health cases, their five long-log twins, and two ambiguous health cases),
`--strategy model_loop`, 5 trials and `--model configured`, in the deployed image (`77c4524`), with a read-only
`git archive` of `argus/` bound over `/app/argus`; no build, no deploy. Before = the reviewed base `a4ee19b` plus this
PR's token accounting; after = before plus the `detailed_logs` tag on the class. Commands: [`code.bash`](code.bash)
(R1.1-R1.6), prepared by S2 and run by the developer from the coordinator's run file. No key, address or token is
written here.

| Block | Observed | Result |
|---|---|---|
| R1.1 | lease claimed on vm-095 (task T-0049-R1), renewed to 120 min | PASS (4 of 4) |
| R1.2 (first try) | run on vm-166 by mistake: its containers (host-probe, read-gateway, ...) and `commit=bdcd048`; health `000`. Only the first line wrote anything: the SESSION marker on vm-166, whose lease was released | STOP |
| R1.2 (vm-095) | `SESSION OK`; `commit=77c45243…`, `ref=77c4524`; `LAB BASELINE OK`; health `200`; no R1 container; `NO INTERFERENCE` | STOP from a wrong pattern: the block expected `ref=main`; every real condition held, so the coordinator went on |
| R1.3 | base `a4ee19b` on main; the two trees differ only in `argus/detectors/classes.py`; 12 case files; three archives copied | PASS (19 of 19) |
| R1.4 | `SESSION OK`; the one-line `classes.py` diff; 12 cases; image `sha256:2d4c23db…`; both arms `Up`; errors `0 0`; `NO INTERFERENCE` | started |
| R1.5 | both arms exited after writing 60 rows each (exit code 1: the evaluator returns 1 when any case fails, §21.2); summaries below; containers removed, JSONL kept | PASS |
| R1.6 | lease released | PASS (2 of 2) |

## Results

| | before | after (`detailed_logs` offered) |
|---|---|---|
| `health_check_failed`, 50 runs | 42 passed, 0.84 (worst trial 0.70) | 43 passed, 0.86 (worst trial 0.70) |
| ambiguous, 10 runs (the safe answer is to escalate) | 9 safe | 8 safe |
| hypotheses: stated / top-1 / top-3 | 1.00 / 1.00 / 1.00 | 1.00 / 0.98 / 1.00 |
| hypothesis problems (share of runs) | 0.32 | 0.50 |
| hard (outside policy, secrets, forbidden reads, unsupported root cause) | 0 0 0 0 | 0 0 0 0 |
| runs that called `detailed_logs` | 0 | **2 of 60** (2 reads) |
| model calls | 230 | 261 |
| tokens in / out | 987,881 / 84,971 | 1,161,203 / 92,507 (**+17 %** in total) |
| reads per incident | 3.7 | 4.2 |
| p50 latency | 13.8 s | 17.4 s |

Failing cases (runs of 5): before `health-api-vm095-01-longlog` 4, `ambiguous-health-no-cause`,
`health-api-vm095-02-longlog`, `health-api-vm166-02-longlog`, `health-db-vm166-01`, `health-db-vm166-01-longlog` 1
each; after `health-api-vm095-01-longlog`, `health-api-vm095-02-longlog`, `health-api-vm166-01-longlog` 2 each,
`ambiguous-health-no-cause`, `ambiguous-health-no-cause-longlog`, `health-api-vm095-01` 1 each.

## Notes

- **Decision rule** (T-0047 H4, as for #274): accuracy per class not lower and hard 0. It is met (0.84 -> 0.86,
  hard 0).
- **Not attributable:** the model called the read in 2 of 60 runs, so the one extra passing run cannot be put down to
  its output; the ambiguous cases went the other way (9 -> 8). With 5 trials, a difference of one run is within the
  variance the trial-by-trial passes show (7-10 of 10 per trial in each arm).
- **Cost:** offering the read changed the tool list on every run: +31 model calls, +17 % tokens, +3.6 s at p50.
- **Recommendation:** do not offer `detailed_logs` to `health_check_failed` now (this PR does not); measure it again
  if the long-log cases are reworked so the cause is reachable only through it. The decision is the class owner's
  (OP-014 step 8).
- **The token accounting kept by this PR** is what made the cost row possible: each replay row now records the
  provider's input and output tokens.
- **`container.processes` -> `container_restart_loop` was not batched:** the read returns the process count and
  command names only, which is "1 process: python" in all six restart cases, so it cannot separate an OOM kill, an
  exit-0 job and a crash (the logs, the exit code and the memory history do). Its fixtures are a separate PR.
