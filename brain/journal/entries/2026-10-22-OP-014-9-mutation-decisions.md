## 2026-10-22 - OP-014 step 9: the policy's decisions and the refusals' targets pinned (third mutation run)

Type: tests
Who: conantkd (+ agent)
Context: the second run (#262) left 174 mutants timed out. Re-run alone with 2 workers on `main` `3db567a`.
Decision / result:
- Of the 174: 93 killed, 45 survived, 36 still timed out (most in `InvokeCapability.__call__` and `_finish`).
- The 45 were the rule and reason of each `PolicyEngine.check` decision (`safety_class` naming the profile,
  `max_per_incident` with its default of 10 and the count, `inspection` with the inspection policy's reason,
  `allow:<capability>`), the security audit of an unknown capability (its name and arguments), the event and detail of
  a recorded refusal, a refused read keeping its own target (inventory, arguments, a lost audit record) and its reason
  (the parse error, the inventory kind), the capability in a validation refusal's audit, and the arguments the policy
  sees (the inspection policy cannot allow a file read without its path).
- `tests/test_op014_mutation_policy_decisions.py` (11 tests, no code changed): each of the 45 re-run with
  `MUTANT_UNDER_TEST`: 37 now fail. The 8 left are equivalent: `getattr` of `permission` or `max_subcalls` with
  another name or default, both always present on `CapabilitySpec` (5), and `_refused(None, ...)` where a target is
  given, so the context is not read (3).
- No defect found.
Consequences: across the four runs, 186 survivors killed, 34 equivalents named, 36 timeouts left; the weekly CI job
is the next step (`.github/`, a teammate's review).
References: [OP-014](../../OPEN_PROBLEMS.md), #260, #261, #262.
