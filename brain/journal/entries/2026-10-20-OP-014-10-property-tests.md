## 2026-10-20 — OP-014 step 10: property-based tests for redaction and target parsing; a redaction gap fixed

Type: implementation
Who: conantkd (+ agent, autonomous night work)
Context: OP-014 lists what a green CI does not yet cover under the self-merge rule. Step 10 asks for property-based
tests (Hypothesis) of redaction, target parsing and the policy engine.
Decision / result:
- `tests/test_op014_property_based.py`: generated inputs, checked for properties that must always hold:
  - no 40+ character token survives in any text, spaced or glued to its neighbours;
  - a named secret (`password=`, `token:`, …), a `Bearer` token and a password in a connection URL are always masked;
  - redacting twice changes nothing more; text with nothing secret-like is unchanged;
  - a secret key is masked at any depth of dicts and lists; a declared directory keeps its files readable;
  - a target parses back to itself; any text parses to a valid target or a `ValueError`.
- **A real gap found:** a token glued to a non-ASCII letter (`é<token>`, `<token>ж`) was not masked. Python's Unicode
  `\b` treats that letter as a word character, so the high-entropy rule found no boundary. The same held for `sk-`
  keys and `Bearer`. Fixed with `re.ASCII` on those three rules in `argus/capabilities/redaction.py`: it only masks
  more, never less.
- `pyproject.toml`: `hypothesis` added to the `test` extra (CI installs `.[test]`).
- The policy engine (`argus/policy/`) is a protected path: its property tests are left for a teammate-reviewed PR.
Consequences:
- Model-bound, stored and view-bound text masks such tokens from the next deploy of the agent image.
- No evidence that such a token ever reached the model or the store: it needs a secret written with no space after a
  non-ASCII letter.
References: OP-014 step 10 in `OPEN_PROBLEMS.md`.

### Test state

New: `tests/test_op014_property_based.py` (22 tests; up to 300 generated examples per property). Red seen: the
glued-token property and the 5 non-ASCII cases failed before the fix. Full suite green.

### Next step

A teammate's post-merge look at the redaction change (safety-relevant, although outside the protected paths). The fix
reaches vm-095 with the next agent deploy (B7 + B8). Property tests for `argus/policy/` in a reviewed PR.
