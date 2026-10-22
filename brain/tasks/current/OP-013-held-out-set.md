# OP-013 — A held-out evaluation set for the two classes under the baseline

| Field | Value |
|---|---|
| Status | `in progress` — 12 held-out cases written, offline baseline measured; the model's runs need the vm-095 lease |
| Problem | [OP-013](../../OPEN_PROBLEMS.md) (from D-003) |
| Architecture | none (§21.2 as written; an ACR only if the rule itself should change) |
| Owner | `juanbetancurm` (+ agent) |
| Needs the VM lease | vm-095, for the model runs only (§21.2's one-off evaluation container, `ops/eval-run.sh`) |

## Goal (plain language)

D-003 moved `dependency_unavailable` and `nginx_upstream_failure` to the deterministic `baseline` because it scored
1.00 on their evaluation cases against the model's 0.90 and 0.92. The baseline's rules were written while looking at
those same cases, so 1.00 is an upper bound, not its accuracy on incidents nobody had seen. This task measures both
strategies on cases written **after** the rules and **without reading them**, then re-decides each class by §21.2.

## The held-out set (`tests/eval/heldout/cases/`)

Twelve cases, six per class, each a failure mechanism or dependency pair the 55 main cases do not have. Labels come
from RB-003 and RB-015 and from what the fixtures show, written before any strategy was run on them.

| Case | Class | Mechanism | Right answer |
|---|---|---|---|
| `heldout-dep-cache-oom-killed` | dependency | the cache was OOM-killed (exit 137) and stays down | `argus-lab-cache` |
| `heldout-dep-backend-wrong-port` | dependency | the backend runs on the shared network but listens on 9090, not 8080 | `argus-lab-backend` |
| `heldout-dep-db-shutdown` | dependency | the lab PostgreSQL was shut down; its client (the leaker) gets refused | `argus-lab-db` |
| `heldout-dep-backend-overloaded` | dependency | the backend is at its CPU limit and drops connections (RB-003 H5) | `argus-lab-backend` |
| `heldout-dep-cache-maxclients` | dependency | the cache accepts TCP but refuses new clients (its client limit) | `argus-lab-cache` |
| `heldout-dep-backend-flap` | dependency (ambiguous) | one timeout and a network reconnect; everything answers now | escalate |
| `heldout-nginx-upstream-closes` | nginx | the upstream's handler crashes and closes the connection: 502 | `argus-lab-slow` |
| `heldout-nginx-upstream-cpu-starved` | nginx | the upstream at its CPU limit answers after the 2 s timeout: 504 | `argus-lab-slow` |
| `heldout-nginx-upstream-restarting` | nginx | the upstream keeps restarting (bad `DELAY_S`); found by a scheduled check | `argus-lab-slow` |
| `heldout-nginx-wrong-upstream-port` | nginx | `proxy_pass` points at 8081; the upstream is healthy on 8080 | `argus-lab-nginx` |
| `heldout-nginx-header-too-big` | nginx | the upstream answers fast; its header exceeds `proxy_buffer_size` | `argus-lab-nginx` |
| `heldout-nginx-errors-no-trace` | nginx (ambiguous) | gateway errors, but no upstream error in the log and a fast upstream | escalate |

Two nginx cases put the cause in the proxy itself (RB-015 H5 and its decision tree: "equivalent backend succeeds →
proxy config investigation"); the main set has none. **Labels to review first:** these two and the two ambiguous
cases, since they decide most of the difference.

**Why a separate folder:** `load_cases` reads every `*.yaml` of a folder, and `tests/eval/cases` is loaded by CI's
offline evaluation and by `test_d003_class_registry.py`, which requires every case of these classes to pass under the
baseline. A held-out case there would turn CI red as soon as the baseline missed it, and the next rule fix would be
tuned against it. `tests/test_op013_heldout_cases.py` checks the set's structure only (ids, at least 5 per class with
one to escalate, targets in the inventory, the default network answer) and that no `heldout-*` file enters the main
folder. **Rule for later work:** do not change the baseline's rules from a held-out miss in the same pull request as the
re-decision; a rule fix earns a new held-out set.

## Results so far

| Run | `dependency_unavailable` | `nginx_upstream_failure` | Hard |
|---|---|---|---|
| baseline, offline, main `76bb1f0` and again on `9d65e1e`, 1 trial (deterministic) | 3/6 = 0.50 | 3/6 = 0.50 | 0 0 0 0 |

Counted as D-003 did: all of the class's cases, the ambiguous one included (the summary's per-class line leaves the
ambiguous case out: 2/5 and 3/5). The baseline escalates the wrong-port, overloaded and max-clients dependency cases,
names the upstream for both proxy-cause nginx cases, and diagnoses the ambiguous nginx case. Labels were not changed
after this run.

## Plan for the model runs (S1 schedules them; vm-095 lease)

`--strategy` applies one strategy to every class and `--category` filters `class`/`ambiguous`, not the incident
class, so each model strategy runs over all 12 cases and only its class's rows count (from the results file):

1. **baseline**: done offline above (it uses no model; re-run on the laptop if the code changes):
   `python -m argus.evaluation --cases tests/eval/heldout/cases --strategy baseline`.
2. **`model_loop`** (the pre-D-003 strategy of `dependency_unavailable`), 5 trials, on vm-095:
   `ops/eval-run.sh --as <holder> --trials 5 --strategy model_loop`, with `ARGUS_EVAL_CASES` pointing at a folder
   that holds this branch's `tests/eval/heldout` (fetched and `git archive`d as in EVAL-2 step 02; the deployed image
   and config, no build: this branch changes no runtime code). Count the 6 dependency rows per trial.
3. **`plan_then_reason`** (the pre-D-003 strategy of `nginx_upstream_failure`), the same way. Count the 6 nginx rows.

60 model runs per strategy (about 10 min each, scaled from PARALLEL_LANES: 150 evaluation runs ~25 min). Report per class: mean and worst trial,
the hard counts (must be 0), and each case's verdict.

## Decision rule (§21.2, as D-003 applied it)

A class keeps or returns to a model strategy only if, on the held-out set, the model matches or beats the baseline
(all 6 cases, 5 trials, mean) with every hard count 0. Otherwise it stays on `baseline`. If the result is "the model is
within a few points and safer" (escalates where the baseline is wrong), propose an ACR for the rule (OP-013's example:
"within 0.10 of the baseline and hard 0") instead of bending it. Each class's re-decision goes in its own pull request
(the registry line in `argus/detectors/classes.py`, `tests/test_d003_class_registry.py`, D-003 and OP-013 by the
roll-up).

## Steps

| Step | What | State |
|---|---|---|
| 1 | 12 held-out cases, the structure test, this file, the journal entry | done (this branch) |
| 2 | Labels reviewed by a teammate before the model runs count | open |
| 3 | The two model runs on vm-095 (S1 holds the lease) | open |
| 4 | Results recorded here; each class re-decided in its own PR | open |
