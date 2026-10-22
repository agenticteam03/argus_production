## 2026-10-22 — The Bearer rule no longer leaves a named secret's value in clear

Type: fix (security)
Who: juanbetancurm (+ agent)
Context: the full suite on main `096bf90` failed the OP-014 property test
`test_a_named_secret_is_masked_whatever_its_value`: `Redactor().text("Bearer\npassword=hunter2xyz\n")` returned
`Bearer [REDACTED]hunter2xyz`. The Bearer rule's `\s+` crossed the newline, its token class (no `=`) took `password` as
the token, and the named-secret rule never saw the key: the value reached the output (model context, storage, views).
Decision / result:
- `argus/capabilities/redaction.py`: the Bearer rule skips a named secret assignment (`password=...`, `api_key: ...`)
  after `Bearer`, on the same line or the next, and the named-secret rule then masks its value. Both rules share one key
  pattern (`_SECRET_NAME`). A real Bearer token is masked as before.
- Review (conantkd, #278): the first version also took the token from the same line only (`[ \t]+`). That left a short
  token alone on the next line (`Authorization: Bearer\nabc123def456ghi`) in clear, since the high-entropy rule needs
  40+ characters. `\s+` is restored: over-masking a log line after the word "Bearer" is better than a short token in
  clear.
- `tests/test_redact_bearer_named_secret.py` (new): the reported input, `BEARER\npassword=0`, the same line, a tab, a
  quoted value; real tokens (JWT, base64 with padding, a token containing "token"); a short token on the next line is
  masked. Red seen: 5 failed. A 20 000-example fuzz of "... Bearer" + whitespace + a named secret found no leak, before
  and after the review change.
Consequences: the line after a bare `Bearer` is masked as its token, even an ordinary log line. No rule order
change (masking the named secret first would leave `token: Bearer <jwt>`'s token in
clear). The property test that found it is green again.
References: [OP-014](../../OPEN_PROBLEMS.md) step 10 (property tests), ARCHITECTURE §10.8.

### Test state

Redaction: `tests/test_redact_bearer_named_secret.py` 11 passed (red seen: 5 failed); the four redaction test files 68 passed; full offline suite 1503 passed, 62 skipped, 1 deselected.

Review change: `test_a_short_token_on_the_next_line_is_still_masked` (two inputs) replaces the same-line test. Red seen
on the PR head `8c1a79a`: 2 failed. After `\s+` is restored: the file 12 passed, the redaction-related tests 229 passed;
full offline suite **1510 passed, 62 skipped, 1 deselected**, exit 0.

### Next step

Redaction fix: conantkd reviews the PR (security-relevant); then the next deploy carries it.
