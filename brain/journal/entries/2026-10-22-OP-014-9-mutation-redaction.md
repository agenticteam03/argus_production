## 2026-10-22 - OP-014 step 9: mutation run on the redactor; 42 survivors killed

Type: tests
Who: conantkd (+ agent)
Context: the first mutation run (#260) left the redactor (`argus/capabilities/redaction.py`, §10.8) for later.
Decision / result:
- mutmut 3.3.1 in a container on `main` `e034c18`, against the four test files that import the redactor: 204
  mutants, 136 killed, 58 survived, 10 timed out.
- The survivors were in the part that keeps declared paths readable: a path under a declared directory found only
  once (or only after the first characters of the text), a declared file inside a URL or followed by `_old`, `Old` or
  `old`, a file declared with no directory, overlapping spans (a declared file under a declared directory), markers
  already in the input, and the counts `value()` returns.
- `tests/test_op014_mutation_redaction.py` (9 tests, no code changed): each survivor re-run against it with
  `MUTANT_UNDER_TEST`: 42 of 58 now fail. The 16 left are equivalent: the length sort of declared paths and its
  direction (the spans are sorted again before merging), a directory also tried as a file, `lstrip`/`rstrip("XX/XX")`
  on paths that start with `/`, `find` from `start + 2` (a path starting with `/` cannot recur one character later),
  and `<` for `<=` when merging spans that only touch (the restored text is the same).
- No defect found: every survivor was an unpinned behaviour that was already right.
Consequences: OP-014 step 9 has its three modules run once; left are the timeouts and a weekly CI job.
References: [OP-014](../../OPEN_PROBLEMS.md), #260.
