## 2026-10-20 — OP-014 step 5: static analysis in CI (ruff, bandit)

Type: CI
Who: conantkd (+ agent, autonomous night work)
Context: OP-014 step 5 asks for static analysis of the Python code in CI.
Decision / result:
- `ruff` with its default rules on `argus/`, `services/` and `ops/`:
  - 5 findings: two unused imports (removed) and three named lambdas;
  - E731, the named-lambda rule, is style only and ignored in `pyproject.toml`, rather than rewriting working code.
- `bandit`:
  - no high-severity finding;
  - the medium ones were reviewed: SQL built from constant table names and `?`/`%s` placeholders, the API's
    `0.0.0.0` bind inside its container, URL reads of allowlisted targets. Not a gate yet.
- CI: one step at the end of the `test` job (so `SELF_MERGE_CHECKS` is unchanged) runs both, pinned.
- `tests/` is left out: ruff reports 211 F811 there, the pytest fixture pattern.
Consequences:
- A new pyflakes error or a high-severity bandit finding in the production code fails the build.
- This pull request changes `.github/` and `ops/`, so it needs a teammate's approval.
References: OP-014 step 5 in `OPEN_PROBLEMS.md`.

### Test state

`ruff check argus services ops`: all checks passed. `bandit -lll`: no issue. Full suite green.

### Next step

A teammate reviews and merges. Later: a bandit gate at medium severity once each finding has a reviewed `# nosec` with
its reason.
