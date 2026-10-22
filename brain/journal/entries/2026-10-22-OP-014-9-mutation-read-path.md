## 2026-10-22 - OP-014 step 9: the read path's audit trail and evidence pinned (second mutation run)

Type: tests
Who: conantkd (+ agent)
Context: the first run on the policy and `invoke_capability.py` (#260) left 305 mutants timed out on a loaded laptop.
Re-run with 3 workers on `main` `d9edaaa`, the tests of #260 included.
Decision / result:
- 889 mutants: 649 killed, 66 survived, 174 timed out. Of the 66, 8 are #260's equivalents; 58 were new, hidden
  among the first run's timeouts.
- They were in the ordinary read path: which audit event each outcome writes (`tool.requested`, `tool.completed`,
  `tool.failed`, `tool.refused`, `tool.refused_recorded`), with which rule (`validation`, `inventory`, the policy's
  rule) and detail (the error with no URL and at most three entries, the reason, the target); the arguments of
  `tool.requested`; what the evidence record keeps (executor, source time, partial, truncated, units, identities,
  coverage, duration); the redaction count added to the gateway's; the audit id's form; and
  `PolicyEngine.check`'s `max_tool_level` decision.
- `tests/test_op014_mutation_read_path.py` (10 tests, no code changed): each of the 58 re-run with
  `MUTANT_UNDER_TEST`: 56 now fail. The 2 left are equivalent: `getattr(spec, "permission", <default>)` where
  `CapabilitySpec.permission` always exists.
- No defect found: the audit trail and the evidence were right; nothing pinned them.
Consequences: OP-014 step 9 now has 26 equivalent mutants named and no unexplained survivor on the policy, the read
path or the redactor. Left: 174 timeouts (most in `__call__` and `PolicyEngine.__init__`/`check`), and the weekly
CI job (`.github/`, a teammate's review).
References: [OP-014](../../OPEN_PROBLEMS.md), #260, #261.
