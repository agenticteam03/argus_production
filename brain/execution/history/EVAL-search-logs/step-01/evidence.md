# EVAL-search-logs — `search_logs` offered to `health_check_failed`, measured (2026-10-13/14 UTC)

Run by conantkd's agent over ssh; vm-095 lease only, session 565367ce7b4c (released after the run).

**Goal:** T-0037 left `container.search_logs` offered to no class "until an evaluation batch measures it". This batch
offers it to `health_check_failed` and compares with `main`. `health_check_failed` was chosen because it is the class
with the most room, and because a targeted log search is the opposite of the broad snapshot, which lowered this
class in EVAL-snapshot.

## How

The experiment was a local branch `task/EVAL-search-logs-health`, `934716b`, never pushed. Its changes:

1. The tag `search_logs` added to `health_check_failed`'s tool tags.
2. **Search fixtures in the 6 health cases**, derived from each case's own log lines with the read gateway's real
   `LOG_PATTERNS`, so no new evidence was invented.
3. **The replay** answers a key such as `search?pattern=error` whatever `minutes` the model asks for: the most
   specific subset of parameters wins.
4. **The gateway's `error` pattern fixed.** See "Found" below.

Building and running it:

- The branch was copied to vm-095 with `git archive` into `/tmp/evalsl`.
- An image `argus-v18-agent:evalsl` was built from it. The checkout and the services were untouched; the agent stays
  on `argus-v18-agent:1`.
- The run: `ARGUS_EVAL_IMAGE=argus-v18-agent:evalsl … eval-run.sh --trials 5`, the 55 cases replayed from fixtures
  (only the model's API called).
- Results: `eval-20261014-002825.jsonl`.
- The comparison: `main`'s `eval-20261013-042857.jsonl` (EVAL-main), re-graded with today's labels (EVAL-6) by
  `argus.evaluation.regrade`.

## Result

| | `main` (re-graded) | `search_logs` offered to health |
|---|---|---|
| overall | 0.97 (267/275) | 0.98 (270/275) |
| `health_check_failed` | 0.96 | 0.92 (23/25) |
| **health runs that used `search_logs`** | — | **1 of 30** |
| hard | 0 0 0 | 0 0 0 |

**Reading**

- The model almost never asked for the tool. Neither of the two new health misses used it (`health-api-vm095-02`
  t1, `health-api-vm166-02` t2, both `no_action_escalated`), and neither did the case that improved
  (`health-api-vm095-01`, 4 → 5).
- The other changes are run-to-run noise of 5 trials:
  - `dep-backend-wrong-network` 3 → 5 with the same reads in a failed `main` trial and a passed experiment trial;
  - `ambiguous-dep-all-running`, `disk-filler-check`, `restart-exit0-job-01` and `nginx-slow-check` +1 each;
  - `dep-backend-stopped` and `ambiguous-health-no-cause` −1 each.
- **Why the tool is not used:** in these cases a container's log has 2 or 3 lines, and `container.logs` (the tail,
  already offered) returns them all, so a search adds nothing. Its value is in long logs, where the important line is
  not in the tail, and no evaluation case has one. This is a limit of the cases, not proof that the tool is useless.
- **A confound:** change 3 also makes 68 keyed fixtures of other classes answer a request with one more parameter
  (for example `/tcp` with `attempts`).

## Decision

- **`search_logs` is not offered to `health_check_failed`.** There is no evidence it helps.
- The offer, the replay change and the search fixtures are **not merged**. They stay described here.
- To measure log tools, cases with long logs come first: hundreds of lines with the cause outside the tail. That is
  its own task.

## Found: the gateway's `error` pattern missed exception class names

Fixed in this pull request, with tests (red seen on `main`'s pattern: 4 failed).

- `services/target/service.py` `LOG_PATTERNS["error"]` was `\b(error|exception|traceback|fatal|panic)\b`.
- The `\b` before `error` never matches inside `KeyError`, `ValueError` or `RuntimeException`, and `\berror\b` misses
  `errors`.
- So a real `search_logs(pattern=error)` told the model "0 lines matched" for a log with `KeyError: 'FEATURE_FLAGS'`
  (case `health-api-vm166-01`).
- Now `(error|exception)s?\b|\b(traceback|fatal|panic)\b`; ordinary lines still do not match.
- It reaches the VMs when the target services are rebuilt at the next AFTER-MERGE.

Left on vm-095: the image `argus-v18-agent:evalsl` and `/tmp/evalsl`, both used by no service.
