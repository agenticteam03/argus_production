# STEP T-0050.C5 — Incident integration local verification

**Date:** 2026-10-23
**Where:** Windows laptop, PowerShell
**Scope:** Offline code, configuration and evaluation only. No VM lease or VM changes were needed.

## Expected

The stored incident view and baseline replay should offer only runbook-grounded actions for the diagnosed root cause,
based on a fresh successful `container.status` observation. Missing, stale, untimestamped or protected-target evidence
must produce no candidate. Suggestions stay non-executable and the write gate stays closed.

## Observed

- Focused action, incident, evaluation, write-gate-standing and UI-contract pytest command: **177 passed**, exit 0.
- Ruff on the changed action, domain, adapter, application and evaluation modules: `All checks passed!`.
- `brain.py lint`: `lint: clean`.
- `git diff --check`: exit 0.
- `brain.py audit` separately reported a Windows-profile-path finding in the unrelated untracked
  `.review-pr297/review.txt`; the artifact was left untouched.
- Full suite: **1,934 passed, 10 failed, 7 errors, 7 skipped**. The 17 failures/errors are subprocess tests because
  the uv-managed interpreter lacks dependencies installed only in `.venv/Lib/site-packages` (`pywintypes`, `yaml`).
- No VM commands were run; `NO INTERFERENCE` was not probed because this was code-only work.

## Environment note

The repository `.venv` points to a Python 3.12.10 installation that is no longer present. Verification used the
installed uv-managed Python 3.12.15 with the existing `.venv/Lib/site-packages` on `PYTHONPATH`. Some test fixtures
replace `PYTHONPATH` for subprocesses, so those subprocesses require a correctly provisioned virtualenv. CI is pending
for the C5 push.
