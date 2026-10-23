# OP-013 step 02 — evidence: the model runs on the held-out set, vm-095 (2026-10-22, juanbetancurm, session a1229b5c5cdb)

Goal: run `model_loop` and `plan_then_reason`, 5 trials each, over the 12 held-out cases of commit `45869b8` in §21.2's
one-off evaluation container, with the deployed image and config (no build, no deploy). Blocks run by the developer
from the coordinator's run file. Commands: [`code.bash`](code.bash) (OP13.3b and OP13.4b were written by the
coordinator). No key, address or token is written here.

| Block | Observed | Result |
|---|---|---|
| OP13.2 | lease claimed on vm-095 (task OP-013), renewed to 120 min | PASS (2 of 2) |
| OP13.3 | `SESSION OK`; deployed `ref=6c83da3`; `LAB BASELINE OK`; `before` saved (54 lines); cases sha `45869b8`; 12 cases; runs started; 0 result lines after 60 s | started |
| OP13.3b | both runs had ended: the deployed `6c83da3` (before T-0047 H4) refuses `label.expected_hypotheses` (`extra_forbidden`); 0 runs | failed at load |
| OP13.3c | that key removed from the VM copy only (labels 10 → 0, 12 cases); both runs started again; after 90 s `argus-v18-eval Up`, 0 errors | OK |
| RN.1 | lease renewed until 14:10 UTC | PASS (1 of 1) |
| OP13.4 | `model_loop` 60 runs, 47 passed; `plan_then_reason` 60 runs, 46 passed; hard `0 0 0` in both; no `results:` line (the 6c83da3 `eval-run.sh` stops before it when a case fails), so the per-class lines were empty; `NO INTERFERENCE: non-Argus objects unchanged` (relayed by the coordinator's summary) | summaries |
| OP13.4b | per class over its 6 cases (the ambiguous one included), from `eval-20261022-113954.jsonl` (model_loop) and `eval-20261022-120509.jsonl` (plan_then_reason): see the table below | OK |
| OP13.5 | lease released | PASS (1 of 1) |

| Strategy | `dependency_unavailable` trials of 6 | mean | `nginx_upstream_failure` trials of 6 | mean |
|---|---|---|---|---|
| `model_loop` | 5, 4, 4, 5, 5 | 0.77 | 5, 6, 4, 5, 4 | 0.80 |
| `plan_then_reason` | 6, 4, 3, 3, 4 | 0.67 | 4, 6, 6, 5, 5 | 0.87 |

Failing runs (of 5): `model_loop` dep backend-wrong-port 4, cache-maxclients 3; nginx header-too-big 1, upstream-closes
1, upstream-cpu-starved 2, wrong-upstream-port 2. `plan_then_reason` dep backend-overloaded 3, backend-wrong-port 3,
cache-maxclients 2, db-shutdown 2; nginx header-too-big 1, upstream-closes 2, upstream-cpu-starved 1. Both ambiguous
cases escalated in every trial of both strategies.

## Notes

- **Measured on `6c83da3`, not main.** Between them nothing changed in the agent loop, the strategies, the prompts or
  the class registry's tool tags (`git diff 6c83da3 9d65e1e -- argus/`); PASS/FAIL is graded the same. The run has no
  hypothesis metrics and no `unsupported_root_cause` count (both after 6c83da3). Checked offline before OP13.3c:
  the stripped copies load with 6c83da3's code, and its baseline gives 6/12 with the same failing cases as main.
- The failing runs' outcomes (wrong diagnosis or escalation) were not printed; the results files stay on vm-095 in
  `eval-results/`.
- OP13.4's raw output was replaced before it was copied; its lines are recorded from the coordinator's summary.
