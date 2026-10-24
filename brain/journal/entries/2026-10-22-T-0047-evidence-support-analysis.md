## 2026-10-22 — T-0047: what `problems 0.45` is made of, and the own-target support check (analysis, no code)

Type: analysis
Who: juanbetancurm (+ agent)
Context: #274's one hard (`dep-backend-stopped` trial 1, `unsupported_root_cause`) came with the problem "supported
without an observation or metric snapshot of its own target", and both arms showed `problems 0.45`. The §3.2 checks
are log-only (ACR-0024, T-0047 H1) until an evaluation shows enforcing them does not lower accuracy. Before any code:
how often each problem occurs, whether the checker is right, and what enforcing would change. Two read-only blocks on
vm-095 read the #274 result files (run stamp `20261022T174900`, 60 runs per arm, `model_loop`); no key, address or
token is written here.
Decision / result:
- **The problem kinds** (runs with the kind, of 60; PASS/FAIL among them):

  | Kind | Before | After | Groups | Verdict |
  |---|---|---|---|---|
  | a hypothesis with no target whose relation is not `external` | 24 (23/1) | 19 (19/0) | restart only | harmless |
  | cites an evidence id not stored for the incident | 5 (5/0) | 6 (5/1) | all | mostly harmless |
  | `supported` without an observation of its own target | 1 (0/1) | 5 (3/1, one hard) | dep 4, restart 1 | see below |
  | the same evidence for and against | 1 (1/0) | 1 (1/0) | restart | harmless |

  - `problems 0.45` is mostly the first kind: restart runs whose hypotheses leave `target` empty.
  - The problems do not explain the failures. FAILs with no problem: 11 of 13 before, 3 of 5 after.
  - The OP-013 files log no hypotheses, so they say nothing here.
- **The own-target flags, run by run (6 runs):**
  - **Real, 2 runs.** The model decided on a `supported` hypothesis without ever reading its target:
    - before, `dep-backend-wrong-network` trial 4: an `escalate` at step 1 with no reads (FAIL: it should have
      diagnosed);
    - after, `dep-backend-stopped` trial 1: a `conclude` after reading only the client, with DNS and connectivity
      from the client. That connectivity read names the backend but does not observe it (the hard).
  - **The checker's timing, 2 runs** (`dep-cache-paused` trial 3, `dep-cache-restarting` trial 2, both PASS):
    - the flag comes on a read step: `hypothesis.invalid` is audited right after `decision.use_read_tools`;
    - the conclusion after it carries no problem, and the cache is in `observed`.
    - A `state_hypotheses` list is checked against the evidence *before* that step's reads run (`runner.py`
      audits the decision, then executes the reads). The model marks `supported` the cause whose reads it is
      requesting in the same step.
    - This is a false positive of the check, not a model fault: the prompt asks for "the list as it stands".
  - **Caused by a mis-copied id, 1 run** (`restart-oom-01` trial 2, PASS):
    - `h3` cites `obs_6217e42a3a2f450`, which has 15 hex digits where ids have 16, so it is "not stored";
    - with its only support dropped, `h3` has no observation of its target, so the own-target flag follows from
      the unknown-id problem.
  - EVS.1 counted "chosen flagged" from all steps' problems. A row flattens every step's problems (the step is
    dropped), so 2 of its 3 come from the timing case above.
- **What enforcement (an `InvalidDecision(malformed)` with "Correct it") would do:**
  - On `conclude` only: it would refuse 1 of 60 after-runs, the hard, which had 6 steps left. It is likely to fix
    it, because the backend's status, logs and events can be read.
  - On every step: it would also refuse the 2 timing runs, costing steps for nothing.
  - Refusing an `escalate` would block the safe path. The before-run escalation is better addressed by the prompt.

Recommendation, in order:
1. **Fix the checker's timing** (code, offline tests):
   - Check the evidence-dependent rows of §3.2 only on the deciding step (`conclude` / `escalate`): `supported`
     without an observation of its own target, `ruled_out` without `against`, and an `external` hypothesis
     supported without an in-scope observation.
   - A `state_hypotheses` list keeps the structural rows: unknown ids, the same id twice, scope, a missing
     target, and more than five.
   - The row keeps the step and decision kind of each problem (the audit already has them), so
     `hypothesis_problem_rate` can be read per decision.
   - ACR-0024 §3.2 does not say which step the rows apply to. This is a refinement, recorded in its "as built"
     notes, and `conantkd` reviews it.
2. **Make the prompt exact** (prompt, model batch):
   - every hypothesis except an `external` one names a target (the incident's own target for `self`);
   - `supported` needs a read of that target itself, and a read of another container that names it does not
     count;
   - copy evidence ids exactly.
   This targets the largest kind and both real own-target runs. It changes what the model sees, so it gets the
   #274 batch shape: the 12 cases, 5 trials, before and after. The rule is accuracy per class not lower and hard 0.
3. **Enforce later, and only on `conclude`:** only if a model batch after 1 and 2 still shows the real
   own-target case. It is 1 run in 60 today.

Consequences: the decision is 1 first, as its own change
([the fix](2026-10-22-T-0047-hypothesis-check-steps.md)); 2 follows after 1 is reviewed, as a separate change.
`dependency_unavailable`'s `anomaly` tag (removed in #274 for the hard) can be measured again after 2.
References: [T-0047](../../tasks/current/T-0047-hypotheses-cause-ranking.md), ACR-0024 §3.2,
`argus/tooling/model_harness.py` (`check_hypotheses`), `argus/orchestration/runner.py` (the audit before the reads).

### Test state

No code changed; analysis of the #274 result files only.

### Next step

T-0047 evidence support: the checker fix ([its entry](2026-10-22-T-0047-hypothesis-check-steps.md)), then the
prompt with a model batch.
