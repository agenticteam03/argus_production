# EVAL-offers — the unoffered capabilities offered to the classes that fit, measured (2026-10-19 UTC)

Run by conantkd's agent over ssh, unattended overnight; vm-095 lease only, session ddec4bfa4070, and 3d230e47b329 for
the reruns and H1 (each released after its run). The OpenAI spend was approved by conantkd for this run.

**Goal:** several capabilities are offered to no class "until an evaluation batch measures them" (`classes.py`). One
batch per offer, each the base plus ONE tool tag, compared with the base on the same harness:

| tag | capability | offered to |
|---|---|---|
| `cpu_history` | `metrics.cpu_history` | `cpu_saturation` |
| `disk_history` | `metrics.disk_history` | `disk_pressure` |
| `request_path` | `analysis.trace_request_path` | `health_check_failed` |
| `search_logs` | `container.search_logs` | `health_check_failed` (on the new long-log cases) |
| `baseline` | `metrics.compare_baseline` | `cpu_saturation` |

Not tried: `network_history` (no model class fits: dependency and nginx are `baseline` strategies) and
`prior_incidents` (the replay store is empty, so any precedent would be invented).

## How

- Each experiment was a local branch `exp/EVAL-offers-<id>` (never pushed), copied to vm-095 with `git archive` into
  `/tmp/eo-<id>`. An image `argus-v18-agent:eo-<id>` was built from it. The checkout and the services were untouched.
- The run: `ARGUS_EVAL_IMAGE=… ARGUS_EVAL_CASES=/tmp/eo-<id>/tests/eval ARGUS_EVAL_CONFIG=/tmp/eo-<id>/config
  eval-run.sh --trials 5`, replayed from fixtures (only the model's API called). One batch at a time.
- **History fixtures, derived from each case's own numbers** (no new evidence): `container_cpu_cores` = the case's
  `quota_used` × its CPU limit, flat over 30 min (6 cpu cases); `host_disk_used_ratio_mounts` rising at the case's
  `hours_to_full` rate (10 disk cases). Points every 60 s. They are inert unless a class is offered the tool.
- **Long-log cases:** 6 `-longlog` twins of the health cases (`health-api-vm095-01/02`, `health-api-vm166-01/02`,
  `health-db-vm166-01`, `ambiguous-health-no-cause`). Each container log is 251 lines: the case's cause line once, then
  250 lines cycling its other lines, so the cause is outside `container.logs`' tail (50 by default).
- **`compare_baseline` earlier windows are CONSTRUCTED**, not derived: a calm 20 % of the CPU limit 1 h, 1 d and 3 d
  before. They are only in the experiment branch, not in this pull request.

## Found and fixed in the harness (this pull request)

The first pass (E0–E3 below) showed four ways the replay disagreed with the real gateway. Each one is fixed in
`argus/evaluation/replay.py`, with a test that was red first:

1. **An earlier window returned the current one.** `range(end_offset_s=…)` ignored the offset, so `compare_baseline`
   compared a window with itself. Now it reads `range_earlier.<offset>.<signal>`, and with none it has no samples.
2. **Fixed fixture dates.** Fixtures carry `collected_at` 2026-10-12; beside the live snapshot and histories, the
   model read them as a week-old sample and escalated on a "source-time mismatch" (`cpu-api-bound`, E1). A fixture
   answer is now stamped with the time it is read.
3. **No `/connectivity`.** The trace's `network.connectivity` sub-read always failed in the vm-166 health cases, so
   the trace said "not ok: connectivity" for api → cache although both are on `argus-lab-app`. The replay now builds
   it from the two containers' status fixtures, as the gateway builds it from their inspect.
4. **A contradiction in the cases.** `health-api-vm166-01/02` answered every `network_probe` read with the `*` answer,
   so `/http` on the allowlisted `http://argus-lab-api:8080/health` said 200 against the case's own health check (500 /
   timeout), and the model escalated on "contradictory evidence". Those cases and their twins now answer that URL from
   their own health output.

Also: a long log `/containers/<n>/log` answers `logs`, `logs_window` and `search` as the gateway does (the 500-line
window, its `LOG_PATTERNS`; a test keeps the two pattern sets equal).

## Results

All files in `/opt/argus-v18/eval-results/` on vm-095. Hard checks 0 0 0 in every batch.

**First pass** (55 cases, the harness before fixes 1–4; record only):

| batch | file | passed | new tool used | its class |
|---|---|---|---|---|
| E0 base (`main`) | `eval-20261019-042234.jsonl` | 268/275 | — | — |
| E1 + `cpu_history` | `eval-20261019-044749.jsonl` | 271/275 | 10 of 25 cpu runs | cpu 1.00 → 0.96 (fix 2) |
| E2 + `disk_history` | `eval-20261019-051257.jsonl` | 270/275 | 36 of 40 disk runs | disk 0.97 → 1.00 |
| E3 + `request_path` | `eval-20261019-053942.jsonl` | 270/275 | 19 of 25 health runs | health 0.92 = 0.92 (fix 3) |

**Final round** (61 cases, fixes 1–3; F3 also fix 4):

| batch | file | passed | new tool used | its class |
|---|---|---|---|---|
| F0 base | `eval-20261019-061420.jsonl` | 287/305 | — | — |
| F1 + `cpu_history` | `eval-20261019-064618.jsonl` | 287/305 | 15 of 25 cpu runs | cpu 1.00 = 1.00 |
| F2 + `disk_history` | `eval-20261019-071917.jsonl` | 286/305 | 34 of 40 disk runs | disk 0.97 = 0.97 |
| F3 + `request_path` | `eval-20261019-075251.jsonl` | 289/305 | 40 of 50 health runs | health 0.66 → 0.74 |
| G0 base with fix 4 | `eval-20261019-101505.jsonl` | 291/305 | — | — |
| F4 + `search_logs` | `eval-20261019-104707.jsonl` | 300/305 | 4 of 50 health runs | health 0.72 → 0.90 |
| F5 + `baseline` | `eval-20261019-111908.jsonl` | 294/305 | 1 of 25 cpu runs | cpu 1.00 = 1.00 |

F3 and F4 are compared with G0 (both carry fix 4); F1, F2 and F5 with F0.

**The OpenAI account ran out of credits during the first F4** (`eval-20261019-082552.jsonl`, 429
`insufficient_quota` from run 168 of 305) and the first F5 (`eval-20261019-091551.jsonl`, partial). Both are
discarded; G0, F4 and F5 were rerun once credits were added (driver stopping at the first provider error). Every file
in the tables above has no provider error.

**Reading**

- **Health moves a lot by itself.** In batches that do not touch it, `health_check_failed` scored 0.66 (F0), 0.72
  (F1), 0.70 (F2), 0.72 (G0) and 0.82 (F5). With 5 trials, a class-level change in health smaller than that band
  says nothing; the mechanism (did the run read the new evidence, and use it) has to.
- `cpu_history` and `disk_history`: used, the class does not move (F1 1.00 = 1.00, F2 0.97 = 0.97). The first pass's
  disk +1 was noise.
- `request_path`: health 0.72 (G0) → 0.74: no gain.
- `search_logs`: health 0.72 → 0.90, but the model called it in 4 of 50 health runs, 3 of them passed; most of the gain
  is in runs that never called it (`health-api-vm166-02-longlog` 1/5 → 5/5 with the same reads). Inside the band.
- `baseline`: called in 1 of 25 cpu runs: nothing to measure.
- The long-log twins work as designed: on G0, `health-api-vm095-01-longlog` 0/5 and `health-api-vm166-01-longlog`
  1/5 (the cause is outside the tail).

## H1 — the log read brings the pattern matches outside its tail (ACR-0023)

The offers show the model rarely asks for a log search. H1 changes the read it already makes instead:
`container.logs` also calls the gateway's `search` for `error`, `timeout`, `refused`, `oom`, `disk_full` and `auth`
(30 min, at most 500 lines) and adds the matching lines that are not in the tail (counts and the last 6) to the
read's text. Branch `exp/EVAL-offers-h1` `6dbb825`, on this PR's first commit; file `eval-20261019-121648.jsonl`
(288/305, hard 0 0 0).

It changes the evidence of 3 of 61 cases (computed with the replay: the other 58 read exactly the same):

| case | G0 | H1 | in H1 |
|---|---|---|---|
| `health-api-vm166-01-longlog` | 1/5 | **5/5** | all 5 diagnoses cite `KeyError: 'FEATURE_FLAGS'`, the line outside the tail |
| `health-api-vm095-02-longlog` | 5/5 | 3/5 | all 5 name the real cause, `address already in use`, which G0's passes never saw; 2 escalated with it |
| `health-db-vm166-01-longlog` | 5/5 | 5/5 | — |

The changes in the 58 unchanged cases are noise: `restart-exit0-job-01` 5/5 → 2/5 and `container_restart_loop` 1.00
→ 0.87 with identical reads. H1 does not help a cause that matches no pattern (`health-api-vm095-01-longlog`:
"maintenance mode is ON", 0/5 → 0/5).

## Decision

- **No capability is offered to a class.** None showed a gain beyond the noise.
- **Proposed: ACR-0023**, the H1 change, in this pull request (the code, tests, §12.2 and version 1.8.17). It is the
  one change whose mechanism shows in the runs: when the cause matches a pattern outside the tail, the model sees it
  and names it.
- The harness fixes, the 6 long-log cases and the derived history fixtures go in too.

Left on vm-095: the images `argus-v18-agent:eo-*` and `/tmp/eo-*` (sources, driver scripts and logs), used by no
service.
