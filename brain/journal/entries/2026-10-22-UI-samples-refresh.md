## 2026-10-22 — UI contract sample refresh

Type: fixture refresh (no runtime change)
Who: juanbetancurm (+ Codex); review: conantkd
Context: The frontend uses `contracts/samples/` as its fake API. Those
responses retained the correct shape but stale values compared with current
API output on `main`.

Decision / result:
- Regenerate only `events.json`, `incident.json` and
  `incident-metrics.json` with the current scripted contract run and
  `--keep-new`; unchanged sample bytes and `ui-api.json` were preserved.
- `events.json` now includes `postgresql_connection_exhaustion`,
  `nginx_upstream_failure` and `cpu_saturation`, registered by PRs #38,
  #60 and #59.
- `incident.json` now reflects PR #44's runbook library 1.1.1 / RB-001
  1.0.1 metadata and current passage scores, plus the ranked hypothesis
  response added by PR #237.
- `incident-metrics.json` now contains 63 points per series (61 in the
  stale sample); this is the current scripted 30-minute response from the
  metrics route introduced by PR #174 and extended by PR #188.

The shape-only contract test missed these updates because list shape uses
only each list's first item; `incident.json`'s new `hypotheses`,
`hypothesis_problems` and `chosen` fields sit in later list items, while
the other changes keep the same shape. The samples were regenerated with
S1's `keep_unchanged_samples.py --keep-new` helper from PR #290, not merged
yet.

Consequences: UI tests now consume current values through their fake API.
The contract remains shape-only and unchanged. No frontend source, API
contract, runtime code, VM, or other sample changed. Since `contracts/`
is protected, the PR requests conantkd's review.

Follow-up (S1, after CI): the Playwright test "the list opens an incident" failed on the PR. The regeneration gave
the incident and its evidence new ids, but `incidents.json` and `evidence.json` kept the old ones, and the frontend's
tests name `inc_7e49840f50fa` and `ev_f5de798421654c48`. The three refreshed samples now carry the original ids again
(the incident, two evidence and two observation ids, paired by kind and capability), so every generated id in them
exists on main. Only the ids changed; the values stay refreshed.

References: [T-0049](../../tasks/current/T-0049-agent-skills.md),
[API for UI](../../../docs/API-FOR-UI.md),
[ACR-0001](../../architecture/changes/ACR-0001-ui-read-access.md).

### Test state

- `npm test` from `frontend/`: 219 passed across 37 files;
  juanes6554's frontend tests were run against the refreshed samples.
- `python -m pytest -o addopts= -q tests/test_ui_contract.py` without the update switch: 3 passed.
- `python brain/tools/brain.py lint`, Ruff and `git diff --check`: clean.
- The one full offline suite on final tree `f480152`: 1717 passed, 63
  skipped, 1 deselected and 10 failed. All failures attempted the Windows
  WSL `bash.exe`, which could not find `/bin/bash`. The exact 10 failed
  cases passed with Git Bash first on `PATH` (10 passed); the full suite
  was not rerun.

- After the id fix: `npm test` 219 passed; the contract test 3 passed. Playwright's browser is not installed on the
  laptop, so CI runs the acceptance tests.

### Next step

Post READY with the reviewed commit block. The PR awaits conantkd's
protected-path review and CI on the Linux runner.
