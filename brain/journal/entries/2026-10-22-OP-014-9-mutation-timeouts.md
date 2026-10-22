## 2026-10-22 - OP-014 step 9: the last 36 timeouts judged (13 survivors killed, 8 equivalent)

Type: tests
Who: conantkd (+ agent)
Context: the fourth mutation run left 36 mutants timed out in `PolicyEngine` (`__init__`, `check`,
`capability_known`), `InvokeCapability` (`__call__`, `_finish`) and `inspection._normal`. A timeout says nothing
until the mutant is run without the time limit.
Decision / result:
- mutmut 3.3.1 with one worker on main `3cfc7d6`: 12 killed, 11 survived, 13 timed out again. Each of those 13 under
  `MUTANT_UNDER_TEST` with a 600 s limit: 3 fail (detected), 10 pass in 30-60 s (survivors that had only been slow).
- `tests/test_op014_mutation_timeouts.py` (6 tests; no code changed) kills 13 of the 21, each checked one by one
  under `MUTANT_UNDER_TEST`: a policy without `max_tool_level` allows level 1 only (3 mutants of the default);
  the two startup refusals say exactly why (2: a regex `match` let `XX...XX` through); a refusal is `False`, not
  merely falsy, with its reason (3); a capability whose spec is not a read is refused before anything runs (1: the
  check had no test, as every catalogue spec is a read); a bad target is audited with its capability (2); a policy
  refusal keeps its target and its reason in the model's text (2).
- Equivalent (8): `data.get(..., None) or {}` for `capabilities` and `write_gate.open` (4); `getattr(spec,
  "permission", None)` or without a default (2), every `CapabilitySpec` has the field; `_refused(None, ...)` when the
  target is given (1); `_normal` with `len(path) > 2` (1), which changes only `//`: accepted as a directory today
  (the same as `/`), refused by the mutant. Not a gap (`/` is accepted and the deny floor applies); making `//`
  refused is a change under `argus/policy/` and waits for a teammate.
Consequences: across the five runs, 199 survivors killed, 42 equivalents named, no timeout left. The weekly CI job's
gate allows 42 survivors.
References: [OP-014](../../OPEN_PROBLEMS.md) step 9.

### Test state

`tests/test_op014_mutation_timeouts.py` 6 passed on the original code (with `test_op014_mutation_policy_decisions.py`
and `test_combined_capabilities.py`: 24 passed); each of the 13 mutants makes it fail.
