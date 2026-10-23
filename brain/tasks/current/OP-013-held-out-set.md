# OP-013 — A held-out evaluation set for the two classes under the baseline

| Field | Value |
|---|---|
| Status | `in progress` — set, baseline and model runs measured; each class's re-decision is its own PR |
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

Twelve cases, six per class, each a failure mechanism or dependency pair the 61 main cases do not have. Labels come
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

**The model runs (vm-095, 2026-10-22, 5 trials each, hard `0 0 0` in both):** counted the same way, the 6 cases of the
class in each trial. Evidence: [step 02](../../execution/history/OP-013/step-02/evidence.md).

| Strategy | `dependency_unavailable` (trials of 6) | `nginx_upstream_failure` (trials of 6) |
|---|---|---|
| `baseline` (offline, deterministic) | 3 → **0.50** | 3 → **0.50** |
| `model_loop` | 5, 4, 4, 5, 5 → **0.77** (worst 0.67) | 5, 6, 4, 5, 4 → 0.80 (worst 0.67) |
| `plan_then_reason` | 6, 4, 3, 3, 4 → 0.67 (worst 0.50) | 4, 6, 6, 5, 5 → **0.87** (worst 0.67) |

- Both ambiguous cases escalated in every trial of both strategies (the baseline diagnosed the nginx one).
- The model's misses: `model_loop` dep backend-wrong-port 4/5, cache-maxclients 3/5; `plan_then_reason` nginx
  upstream-closes 2/5, header-too-big 1/5, upstream-cpu-starved 1/5. The proxy-cause nginx cases, which the baseline
  always misses, passed in 9 of 10 `plan_then_reason` runs.
- **Measured on the deployed `6c83da3`**, not main: the image predates T-0047 H4, so the VM copy of the cases lost
  `label.expected_hypotheses` (the repo's cases are unchanged). Nothing on the model's path differs from main (agent
  loop, strategies, prompts, tool tags; the H5 read is offered to no class) and PASS/FAIL is graded the same; the run
  has no hypothesis metrics and no `unsupported_root_cause` count.
- Small set: 6 cases per class. The gap to the baseline (+0.27 and +0.37) is larger than the spread between trials,
  but a single case is worth 0.17.

## Decision proposal (§21.2 as D-003 applied it)

Both classes meet the rule on the held-out set: the model's mean beats the baseline with every hard count 0.

**Provisional until step 2:** the runs came before the label review (`conantkd`, #270), so these numbers count only
once the labels are confirmed, first the four flagged above. A changed label is regraded from the results files on
vm-095 (`eval-results/eval-20261022-113954.jsonl`, `eval-20261022-120509.jsonl`) before any class changes; the class
PRs wait for the review.

| Class | Today | Proposal | Held-out | Main set (D-003) |
|---|---|---|---|---|
| `dependency_unavailable` | `baseline` | back to `model_loop` | 0.77 vs 0.50 | 0.90 vs 1.00 |
| `nginx_upstream_failure` | `baseline` | back to `plan_then_reason` | 0.87 vs 0.50 | 0.92 vs 1.00 |

The two sets disagree because the baseline's rules were written from the main set: on cases nobody tuned it on, it
gets half right. The held-out result is the one §21.2 asks for (an unseen mechanism is the normal incident). The
baseline stays the fallback when no model is configured. Each class changes in its own PR (`argus/detectors/classes.py`,
`tests/test_d003_class_registry.py`, which today requires the baseline for these classes; `conantkd` reviews); D-003
and OP-013 are updated by the roll-up. Not part of the proposal: changing the baseline's rules from these misses
(a rule fix needs a new held-out set, as above).

## Plan for the model runs (done; kept for a re-run) (S1 schedules them; vm-095 lease)

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
| 2 | Labels reviewed by a teammate before the model runs count | open (the four named above first) |
| 3 | The two model runs on vm-095 | done 2026-10-22 ([evidence](../../execution/history/OP-013/step-02/evidence.md)) |
| 4 | Results recorded here; each class re-decided in its own PR | results recorded (provisional); the two PRs follow step 2 |
