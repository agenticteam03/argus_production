# T-0019 batch 2 step 03 (history step-06) — evidence (2026-10-12, conantkd, sessions cd4367edd721 / 7a5515db6285)

Goal: deploy the six host-probe routes on both VMs and the seven capabilities in the agent, verify every route on
the host and through the agent's own code path, and show the model did not get worse on the 55 evaluation cases.
Run by the agent over SSH; IP addresses masked; process names never printed (counts, keys and ids only).

## What happened, in order

| # | Block | Observed | Consequence |
|---|---|---|---|
| 1 | S3.1, first version (vm-166, `785ee43`): deploy, then every route from **inside** the probe (`docker exec … python`) | `DEPLOY OK`, the five target services Up; the route checks printed nothing; Docker events: `exec_start` → `oom` → `die 137` → `start` (the probe restarted once) | the 64 MiB probe was OOM-killed while answering |
| 2 | read-only measure, each route alone from the host (loopback port), the probe's cgroup `memory.peak` after each | 15 MiB at rest; every route +0 except `/oom?minutes=1440` (peak 31 MiB: 4 MiB of log held as text) and `/directory_sizes?path=/` (46 MiB: 18 MiB file cache + 12 MiB slab charged to the cgroup, 50 000 entries); with the exec'd checker (~10 MiB) in the same cgroup it crossed 64 MiB | fix in code, not a bigger limit: the log tail is read line by line keeping only OOM lines, the walk stops at 20 000 entries (tests: 11 MiB traced peak → < 1 MiB; red seen) — `1e8e977` |
| 3 | S3.1, as archived (vm-166, `1e8e977`): every route with `curl` from the host + cgroup memory; then 2 walks of `/` + 2 OOM reads of 24 h **at once**, twice | all 200; `by=disk` 400; `/etc` 400; no `cmdline`/`environ` key; `/sockets` host (pid 1) by state, 9 listening ports; `/oom` 1 record in 60 min (the probe's own kill of row 1: `since_boot` 18 567 → 18 568); **peak 22 MiB** in the parallel rounds, `oom_kill=0`, restarts 0; `LAB BASELINE OK`; `NO INTERFERENCE` | the new verb found a real incident: the OOM kill of row 1, by container id, `python`, anon RSS 15.2 MiB |
| 4 | S3.2 (vm-095): deploy, target services, agent rebuilt; `phase3_check` with the agent's tokens; the capabilities from `argus-v18-agent` | health 200, no startup errors; **`phase3_check` 55/55** on both hosts (14 new host-probe checks per host); the capability snippet: every read **401** | since T-0021 `argus-v18-agent` holds no executor token: the snippet ran in the wrong container |
| 5 | S3.3 (vm-095): the same capabilities through `wiring.tools_dispatcher` as `argus-tools` (uid 10011) in `argus-v18-worker` | first run `KeyError: 'host.load'`: S3.2 rebuilt the image but recreated **only** `argus-v18-agent`; worker and scheduler still ran the old code. Recreated both (same image id as the agent, no startup errors); then **14 of 14 `level 2 ok`** | the block now recreates agent, worker and scheduler; an incident's reads go through the worker |
| 6 | S3.3 output, `get_directory_sizes` on `vm-095:/` | in name order: `usr/` used the whole budget (partial), `var/` never read | each child now gets a share of what is left (test: the last child was missing; red seen) — `b4623dc` |
| 7 | S3.4 (both VMs, `b4623dc`): target services rebuilt (agent unchanged) | `phase3_check` 55/55; `vm-095:/` → `var/ ≥ 3987 MiB (partial)`, `usr/ ≥ 84.9`, `opt/ ≥ 20.9`, `home/ 6.5` …; `vm-166:/srv/argus-lab-fill` complete; every target service restarts 0; `LAB BASELINE OK`; `NO INTERFERENCE` on both | — |

S3.4's `docker exec -i … python -c` read the rest of the piped script as its stdin, so the block's last lines did not
run; they were run separately (restarts 0, `LAB BASELINE OK`, `NO INTERFERENCE`, both VMs) and the `-i` removed.

## The capabilities through the agent's code path (row 5, as the tools process sees them)

| Capability | vm-166 | vm-095 |
|---|---|---|
| `get_host_load` | load 0.10/0.26/0.15, 489 threads, cpus 1; PSI cpu some 4.3 % | load 0.53/0.43/0.25; PSI cpu some 46.1 %, io some 13.1 % |
| `get_io_metrics` | sda idle | sda write 2 872 KiB/s, 54/s, busy 1.9 % |
| `get_top_cpu_processes` / `get_top_memory_processes` | 3 processes each | 3 each; 2 of the memory top in containers |
| `get_socket_summary` | listen 11, established 16, time_wait 6; 9 listening ports | listen 7, established 10; 4 listening ports |
| `get_directory_sizes` | `/srv/argus-lab-fill`: complete | `/`: partial, as row 7 after the fix |
| `get_kernel_oom_records` | 1 in 60 min: container `0bacba035e11` (the probe of row 1), `python`, 15.2 MiB; since boot 18 568 | none in 60 min; since boot 0 |

## Redeploy on the branch head (S3.5, after the rebase)

Both VMs on `040b827` (the branch rebased on `task/EVAL-2-model-trials`, so it carries EVAL-2 and the new prompt rule):
vm-166 target services up; vm-095 target services, agent, worker and scheduler on one image, health 200, no startup
errors, `phase3_check` 55/55, the prompt rule present in the worker, `get_host_load`, `get_kernel_oom_records`,
`get_directory_sizes` ok through `tools_dispatcher`; `LAB BASELINE OK`, `NO INTERFERENCE` on both. The commits after
`040b827` change only the evaluation tool (`invalid_decisions`), tests and the Brain.

## Evaluation (the configured model, the 55 cases, one-off containers on vm-095)

Measured on what `main` will be after #89 and this PR: EVAL-2 + batch 2. The running agent was never used (eval-run.sh:
read-only, no token, no database, not on `argus-v18-core`). Reference: EVAL-2's E.4 (5 trials, after its fixes).

| Run | Code | Trials | Accuracy (core) | Abstention | disk | cpu | restart | dependency | health | nginx | blind spot | postgres | hard |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| EVAL-2 E.4 (reference) | `e0efc8a` = `8d42c19` | 5 | 0.93 (0.95) | 0.96 | 0.97 | 1.00 | 0.80 | 0.92 | 0.80 | 0.96 | 1.00 | 1.00 | 0 0 0 |
| E.6: new tools, the cases cannot answer them | local merge `59defdf` | 3 | 0.92 (0.93) | **0.89** | 0.92 | 1.00 | 0.83 | 0.87 | 0.87 | 0.93 | 1.00 | 1.00 | 0 0 0 |
| E.7: the cases answer them (`61e11f1`) | local merge `e9f048c` | 3 | 0.91 (0.92) | 0.96 | **0.79** | 1.00 | 0.83 | 1.00 | 0.80 | 0.93 | 1.00 | 1.00 | 0 0 0 |
| **E.8 + E.9: + the prompt rule** | **`040b827`** (pushed) | **5** | **0.92 (0.95)** | **1.00** | **1.00** | 0.96 | 0.80 | 0.92 | 0.76 | 0.92 | 1.00 | 1.00 | **0 0 0** |

- **E.6.** The model asked the new tools at once: `get_directory_sizes` 41 times in 24 disk runs, `get_io_metrics` 3,
  `get_host_load` 6 (cpu), `get_kernel_oom_records` 3 (restart loop). The cases had no answer for them (their
  `host_probe` `"*"` row: every new capability said `unknown`), and `disk-filler-no-logs` concluded 2 of 3 times
  (E.4: 1 of 5). → the 21 cases of the three offered classes answer the new routes from their own story, labels
  unchanged (`61e11f1`, rule in its commit and in `test_every_case_of_an_offered_class_answers_its_new_tools`; the
  filler's file name only where the case's logs say it wrote the data, kernel OOM kills only where the case's metrics
  say `oom_killed`).
- **E.7.** With "data-0007.bin 202 MiB" in front of it the model concluded in the abstain disk cases:
  `disk-filler-no-logs` 2/3 (named the filler because it could write there), `disk-filler-stopped` 2/3 and
  `disk-filler-read-only` 1/3 (named the host: "the file is the root cause"). A real risk of the new tool, not of the
  fixtures. → system prompt: a large file shows where the space went, not who wrote it; a writer is named only when the
  evidence ties it to the data (`040b827`, test first).
- **E.8 + E.9.** disk 1.00 and abstention 1.00 (5 trials), core 0.95 as E.4. Below E.4 by one run each (25 runs per
  class): cpu (`cpu-burner-05` trial 5: 7 invalid decisions in a row, step budget exhausted; 6 replays of the case on
  the same image all diagnosed, no invalid decision), health (wording and `health-api-vm095-02` escalated 2/5) and
  nginx (two escalations). Those two classes are offered no new tool. The invalid loop's reasons were not in the
  results row (`decision.invalid` only) → each run now keeps them (`invalid_decisions`, `66900ff`).
- FAILs by case (of 5) in E.8 + E.9: `restart-sigkill-01` 5 (as E.4, RB-008 question), `health-api-vm095-02` 2,
  `health-db-vm166-01` 2 (wording), and 1 each: `cpu-burner-05`, `dep-backend-wrong-network` (wording),
  `dep-cache-stopped`, `health-api-vm095-01` (wording), `health-api-vm166-02` (wording), `nginx-slow-check`,
  `nginx-slow-half`, `restart-exit0-job-01`.

Files on vm-095 (`eval-results/`, kept): `eval-20261012-113332.jsonl` (E.6), `eval-20261012-120416.jsonl` (E.7),
`eval-20261012-123101.jsonl` (E.8), the E.9 file after it. Clean-up: `/opt/argus-v18/eval-src` removed, the image
`argus-v18-eval:t0019b2` removed by name (each rebuild removed the previous one by name first; no prune); no dangling
image left; `LAB BASELINE OK`, `NO INTERFERENCE`.
