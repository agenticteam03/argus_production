## 2026-10-21 - OP-014 step 4 for the frontend: Vitest coverage floors

Type: implementation
Who: conantkd (+ agent)
Context: OP-014 step 4 (coverage) was done for Python; the frontend waited for Vitest 5 (OP-017, #242).
Decision / result:
- `@vitest/coverage-v8` 5.0.5; `npm test` = `vitest run --coverage`, so CI's `frontend` job applies it with no
  workflow change and `SELF_MERGE_CHECKS` is unchanged.
- Coverage counts every file under `src/` (Vitest 5 counts only loaded files by default): lines 33.9 %, statements
  33.8 %, functions 28.7 %, branches 26.6 %. Floors 33 / 33 / 28 / 26 in `vite.config.js`. Red seen: a floor of 90 %
  fails `npm test` (exit 1).
Consequences: a frontend change that drops coverage fails CI. The floors go up with new tests; the low figure is
mostly pages, covered by Playwright instead.
References: [OP-014](../../OPEN_PROBLEMS.md).
