## 2026-10-25 — T-0047 evidence ids per hypothesis and ranking-weight sensitivity report

Type: offline evaluation utility and result-row format
Who: juanbetancurm (+ agent)
Context: T-0047 H4, branch task/T-0047-evidence-ids from origin/main 106190b. Continues the sensitivity report drafted
on 2026-10-22 from 44fe921. This does not change config/ranking.yaml, ranking behavior, or tool offers.

Method and result:
- The evaluation JSONL writer stored each final hypothesis's target, class, status and rank, but not the evidence it
  cited, so a batch's result file could not be re-ranked. Each hypothesis row now also carries `support` and `against`
  (evidence ids only), and each row carries `evidence`: {evidence_id, kind, target} per stored evidence record. No
  evidence text or values are recorded.
- The regrader reads the new fields and still reads old rows that lack them (empty lists).
- Add a read-only analyzer, `argus.evaluation.weights_sensitivity`, that calls application.ranking.rank unchanged for
  the current weights, each of the six score weights halved and doubled one at a time, and untested_penalty set to 0
  and 1. `peer_finding` is inert today (rank() cites no peer finding by id), so its two sets always equal `current`.
  max_target_records is held constant because it is a cap, not a weight. It reads files or stdin.
- For each JSONL result file it reports top-1 and top-3 expected-cause accuracy, ruled-out recall, ranking_disagrees
  counts, and per-class coverage. Stored ranks are ignored. A row without the inputs is counted as not scorable.
- Rows written before this change (the retained H5B and R1 files) are not scorable; no score is inferred from them.
  A new batch is needed for sensitivity numbers, and is a separate decision.
- The token fields (#301) and compare.py (#319) are unchanged.

### Test state

- RED: with replay.py and regrade.py from main, test_a_replay_keeps_the_final_ranked_list and the two regrade tests
  (new fields, old rows) failed on the missing fields.
- GREEN: the focused tests pass. They cover the 15 isolated variants, a rank flip, label-based ruled-out recall,
  per-class metrics, legacy rows, stdin input, the regrader with new and old rows, and a round trip of a row in the
  CLI shape through a JSONL file into the analyzer.
- The one full offline suite is pending the review.

### Next step

Run the next H4 batch with this writer, then run the analyzer on its result file (offline, read-only).
