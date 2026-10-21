## 2026-10-21 — T-0047 H1: hypotheses on the decisions, the harness checks log-only, ACR-0024 applied (1.8.27)

Type: implementation
Who: juanbetancurm (+ agent)
Context: ACR-0024 (hypotheses and a transparent cause ranking) was accepted in #215. H1 is its first step: a model
strategy states the candidate causes it considered, and the harness checks them without refusing anything yet, so
the evaluation (H4) can show whether enforcing the checks costs accuracy.
Decision / result:
- `domain/model.py`: `Hypothesis`; optional `hypotheses` on `Conclude`, `Escalate` and `UseReadTools`, `chosen` on
  `Conclude`, and `hypothesis_problems` on the three.
- `tooling/model_harness.py`: the `conclude` and `escalate` tools carry `hypotheses` (at most five, ids `h1`–`h5`,
  the target an enum of the scope plus null) and `conclude` carries `chosen`; the system prompt says how to state
  them. `check_hypotheses` and `check_conclusion` implement the §11.3 rows and return each would-be refusal as a
  sentence; the decision stands. A hypothesis that fails its schema is dropped and reported.
- Both runners audit `hypothesis.invalid` (category `decision`: step, decision, at most 10 problems) after the
  decision's own audit.
- Found while applying: the checks need to know what each cited evidence id is about, and `EvidenceRef` did not
  say. It now carries the stored record's `target` and `kind` (set in `invoke_capability.py` and `runner.py`).
- ARCHITECTURE 1.8.27 describes the whole accepted change; what later steps build is marked with its step (H2–H5).
Consequences: deterministic strategies are untouched. A read step has no tool to carry its list, so
`UseReadTools.hypotheses` stays empty until H2 gives the list a place in the context. A model conclusion without
hypotheses is audited (`a conclusion without hypotheses`) but still concludes. Next: H2, storage and the ranking.
References: [ACR-0024](../../architecture/changes/ACR-0024-hypotheses-and-cause-ranking.md),
[T-0047](../../tasks/current/T-0047-hypotheses-cause-ranking.md), #215.
