## 2026-10-20 — OP-014 step 6: dependency audit in CI; the frontend's advisories recorded as OP-017

Type: CI
Who: conantkd (+ agent, autonomous night work)
Context: OP-014 step 6 asks for a dependency audit on every pull request.
Decision / result:
- Ran locally:
  - `pip-audit`: no known vulnerability.
  - `npm audit`: React Router 6 (moderate, shipped in the UI), and Vite, esbuild, Vitest and tinypool (dev tooling,
    up to critical). Every fix is a major upgrade.
- CI gets two steps, inside the existing jobs so that `SELF_MERGE_CHECKS` and `verify-main` stay as they are:
  - `pip-audit` in `test`;
  - `npm audit --omit=dev --audit-level=high` in `frontend`.
  Both pass today.
- OP-017 records the frontend advisories and the upgrade order. The upgrades belong to the frontend lane (T-0016)
  and were not done at night without a review.
Consequences:
- A new high advisory in a Python package or in what the UI ships fails the build.
- This pull request changes `.github/`, so it needs a teammate's approval.
References: OP-014 and OP-017 in `OPEN_PROBLEMS.md`.

### Test state

No code change. The two audit commands pass locally (exit 0).

### Next step

A teammate reviews and merges. The frontend lane upgrades React Router, then Vite and Vitest (OP-017).
