## 2026-10-20 — OP-014 step 10: property-based tests for the policy engine

Type: tests
Who: conantkd (+ agent, autonomous night work)
Context: the first part of OP-014 step 10 (#195) covered the redaction and the target parsing. This part covers the
policy engine, with tests only, so no protected path changes.
Decision / result:
- `tests/test_op014_property_policy.py` (11 tests, up to 300 generated examples each) against the real
  `config/policy.yaml`:
  - `PolicyEngine.check`:
    - an allow means every condition held (known capability, level, safety class, incident scope, per-incident
      limit);
    - an unknown capability is always refused;
    - a non-empty write gate refuses startup.
  - The inspection policy:
    - a path with `..`, `.` or an empty segment, or a relative path, is never readable;
    - a deny-floor name anywhere in the path (any case), or a floor directory, is never readable, even under an
      allowlist of `/`;
    - an allowed read is always inside the allowlist;
    - the data's deny list only adds to the floor;
    - the journal reads only a listed unit within its line limit;
    - a target without an entry allows no inspected read.
- No gap found. As a check that the tests can fail, three bugs injected in memory were each caught: no scope check,
  no deny list, no path normalization.
Consequences:
- OP-014 step 10 is done; steps 4 to 9 and 11 to 13 remain (most touch `.github/`, a protected path).
References: OP-014 in `OPEN_PROBLEMS.md`.

### Test state

New: `tests/test_op014_property_policy.py`, 11 tests, green. No code change. Full suite green.

### Next step

OP-014 steps 4 to 7 (coverage on changed lines, SAST, dependency audit, workflow linting) need `.github/` changes and
a teammate's review.
