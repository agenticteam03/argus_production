## 2026-10-23 — T-0049 R1: `detailed_logs` measured for `health_check_failed`, not offered; token usage in each replay row

Type: evaluation
Who: juanbetancurm (+ agents: S2 prepared the ranking, the code and the batch; S1 ran and recorded it)
Context: T-0049 R1 ("evaluate before adding"): the reads built in T-0036 to T-0040 are offered to no class. S2 ranked
the five tasks offline and proposed `container.detailed_logs` -> `health_check_failed` first (twelve labelled cases,
long-log twins whose cause is outside the default 50-line tail, a model-driven class). The batch ran on vm-095 on
2026-10-22, before = the reviewed base `a4ee19b` with token accounting, after = the same plus the class's
`detailed_logs` tag.
Decision / result:
- Health class 0.84 -> 0.86 (42 -> 43 of 50), ambiguous safe 9 -> 8 of 10, hard 0 in both arms. The model called the
  read in 2 of 60 runs, so the gain is not attributable; offering it cost +31 model calls, +17 % tokens and +3.6 s at
  p50. The class is left unchanged: `detailed_logs` stays offered to no class
  ([evidence](../../execution/history/T-0049-R1/step-01/evidence.md)).
- Kept: `RecordingLLM` sums the provider's input and output tokens per run; `CaseRun`, the JSONL row and the regrader
  carry `input_tokens` / `output_tokens`. This is what measured the cost.
- `container.processes` -> `container_restart_loop` (S2's second candidate) is not worth a batch: the read returns
  the process count and names, the same "1 process: python" in all six restart cases. Its replay fixtures are a
  separate PR.
- R1.2's deploy check expected `ref=main`; `deploy.sh status` prints the full commit and `ref=<sha>`. Later batch
  blocks check the commit prefix.
Consequences: an offer is judged on usage and cost as well as the rule (accuracy not lower, hard 0); a read the
model rarely calls only adds cost. The other candidates of S2's ranking stay proposals.
References: T-0049 R1; T-0037; #274 (the same batch method); the evidence above.

### Test state

- RED then GREEN (S2): `test_a_model_run_records_provider_token_usage` failed until `RecordingLLM` recorded usage;
  `test_the_command_line_runs_the_model_and_writes_one_json_line_per_run` asserts the two new row fields.
- The offer's tests (`test_t0049_r1_offers.py`, the `test_t0037` offer assertion) were removed with the offer.
- Full offline suite on `8b40610` plus this change, Git Bash first on `PATH`: 1858 passed, 34 skipped, 1
  deselected. Ruff, Brain lint and audit, `git diff --check`: clean.

### Next step

conantkd reviews. Then the hypothesis-instruction batch (T-0047 H4) reuses these blocks with the corrected deploy check.
