## 2026-10-22 — T-0047 H4: the hypothesis rules the model is told, made explicit

Type: implementation
Who: juanbetancurm (+ agent)
Context: step 2 of the analysis of #274's batch (`2026-10-22-T-0047-evidence-support-analysis.md`, in the
checker fix's PR). Three rules that the §3.2 checks already apply were vague or missing in what the model is told:
- 19-24 restart runs per arm stated a hypothesis with no target;
- both real own-target cases decided on a `supported` cause they never read;
- one run cited a mis-copied evidence id (15 hex digits where ids have 16).
The checker fix (a read step gets the structural checks only, branch `task/T-0047-hypothesis-check-steps`) is a
separate change; this one changes only text.
Decision / result:
- `argus/tooling/model_harness.py`, the system prompt's "Hypotheses" section:
  - every hypothesis that is not `external` names its target (for `self`, the incident's target);
  - copy evidence IDs exactly as shown, every character;
  - mark one `supported` only once an observation or metric snapshot of its own target is in the evidence; a read
    requested in the same step is not one yet, so keep it `untested`. This replaces "a supported hypothesis needs
    evidence about its own target".
- The `state_hypotheses` tool description adds the read-step form of the second rule: "`supported` only once a read
  of its target is in the evidence".
- Nothing else changes: the checks, the schema, the context slot (`SLOT_CHARS` 1200), the ranking and the classes.
- `tests/test_t0047_hypothesis_instructions.py` (red first: 5 failed, one per rule plus the removed vague sentence):
  - each rule is in the prompt or the tool description;
  - the slot's text, its bound and the hypothesis schema are unchanged;
  - all 15 labelled cases replay with a scripted model that reads the cause and concludes on it: diagnosed, the
    labelled root cause, no hypothesis problem, `unsupported_root_cause` 0.
Consequences: the prompt changes what the model sees, so a model batch decides whether it stays, after the checker fix
merges:
- the 12 cases of #274 (`dep-*`, `ambiguous-dep-all-running`, `restart-*`), `--strategy model_loop`, 5 trials;
- before (main with the checker fix) and after (this branch), on vm-095 with the archive bind;
- rule: accuracy per class not lower and hard 0, otherwise the text is reverted.
Also read: the problem kinds by step (the checker fix's row format), especially "no target" and the own-target
problem on `conclude`.
References: [T-0047](../../tasks/current/T-0047-hypotheses-cause-ranking.md), ACR-0024 §3.2.

### Test state

T-0047 H4 hypothesis instructions: `tests/test_t0047_hypothesis_instructions.py` 7 passed (red seen: 5 failed); the
T-0047 H1, H2 and H4 test files and the two earlier prompt-rule test files pass with it. Full offline suite, with
Git Bash first on PATH, on `b22c669` plus this change: **1843 passed, 1 failed, 34 skipped, 1 deselected**. The
failure is `test_acr0011_ui_edge.py::test_what_passes_and_what_is_refused[GET-/api/v1/me-200]` (502 on the fake
API's first request); it fails the same way on `main` `8b40610` without this change, and this change touches neither
the edge nor the API.

### Next step

T-0047 H4: review of the hypothesis instructions; after the checker fix merges, the model batch above decides whether
they stay.
