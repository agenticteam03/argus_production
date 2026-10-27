# Current test state

**Last updated:** 2026-10-12 (roll-up) · **Commit:** `main` after #96 (`817d88f`)

Red first for every fix (approval view and holds 6 failing, gateway import of `NotSent`, frontend 6 failing, the
protected-path case). Real images on a local Docker engine (29.8.0): both exit-proof tests pass; the gateway one failed
first (the proxy's socket) and passed after the image fix.
Then: phase 19 Python tests 33 passed; with phase 18, phase 16, UI contract and write-gate tests green; the UI
contract regenerated with only `reason` added (15 samples kept byte for byte). Postgres: 21 passed against a
throwaway `postgres:16-alpine` (the answer's and the release's audit rows in their transactions). Frontend: the approval, decision and adapter tests pass; three files fail only on this
laptop's stale `node_modules` (no `elkjs`).

No code change. On vm-095: 91/91 database checks, `AUDIT CHAIN OK: 327 rows chained`, `LAB BASELINE OK`.

`tests/test_phase16_security_alerts.py` (the job, the intake skip, the schedule entry, the compose files, the proxy
filter, the Telegram route) and the full suite pass locally.

Documentation only; no code changed.

On the VM: `91/91 database checks passed`; in the drill `AUDIT CHAIN BROKEN: 1 problem(s)` then `AUDIT CHAIN OK: 318
rows chained`; vm-095 and vm-166 `NO INTERFERENCE`. CI green on `6e87828`.

Red first: the four store refusals failed before the triggers. Phase 18, guards, graph, migration and Postgres tests:
87 passed, 20 skipped (no local Docker; CI runs Postgres); the migration checker passes on 016; Ruff clean. Removing the
stored `doubt` makes its test fail.

Baseline evaluation 68/72, hard checks 0; vm-095 `ref=b6e64eb`, `LAB BASELINE OK`, scheduler errors 0.

Phase 18, guards, graph and Postgres tests: 52 passed, 20 skipped (no local Docker); Ruff clean.

On the VM: `shipped 5 digest(s), 0 conflict(s)`, `VERIFIED 5/5`, `AUDIT CHAIN OK: 311 rows chained`. Locally:
`tests/test_phase16_step5_digest.py` passes with the schedule on.

Live: SC-03 1/1 PASS, SC-07 1/1 PASS; link rows as described; `LAB BASELINE OK`.

- The first UI integration made `ActionSuggestions.test.jsx` red on the missing component. After implementation,
  the three component assertions passed. The complete frontend run passed (47 files, 301 tests); frontend lint
  completed with no errors and 33 existing fast-refresh warnings; the production build passed. A Chromium acceptance
  test passed against the built app and produced a local screenshot with a synthetic candidate. The relevant Python
  UI-contract and action-incident tests passed (11) with an in-workspace pytest temporary directory; Brain lint and
  audit passed. A first full Python run hit the sandbox's inaccessible default pytest temporary directory. The rerun
  with an in-workspace directory completed with 30 failures in Linux shell-script tests (skill block, database backup,
  deploy, Phase 16 private path and token rotation); representative failures show Windows selecting WSL `bash.exe`
  or Git Bash paths that cannot create the test directory. Final-head Linux CI remains required. The cards use the existing `next_actions`
  incident response, so no new API route or UI contract shape is introduced.
- For local inspection, an opt-in mock incident (`VITE_ARGUS_PHASE19_DEMO=1`) shows a coherent stopped-cache
  suggestion while the ordinary demo is unchanged. Its test was red before the fixture existed and green after;
  the complete frontend suite now passes 303 tests in 48 files, lint has no errors, and the build passes. A local
  Chromium visit to the running demo confirmed the incident and card render and produced a screenshot.
- The Phase 19 Actions screen now renders a frozen approval and Approve / Deny controls. RED was observed for the
  missing card, private HTTP adapter, action-gated route and decision helper. GREEN tests cover proposal presentation,
  full-session gating, red target confirmation, exact request payload and WebAuthn step-up ordering; the local
  Chromium preview shows both controls disabled under a mock read session. The two private API routes were added to
  the UI contract and documented; the contract regeneration kept all 15 unchanged samples byte for byte.
- RED: the new answer-route test returned 404 before its implementation.
- GREEN: focused approval tests and existing authentication/write-gate tests passed locally. Full suite and
  exact-head CI remain to be recorded after the draft push.
- The first PR head `ab7091d` passed exact-head `test` and `frontend` CI. This continuation added holds and the
  closed gateway core. RED was observed for the missing hold route, missing gateway behavior, and absent cross-scope
  approval check; focused tests are green. The six Phase 16 allowlist-script failures on Windows are environmental:
  `bash.exe` enters WSL without `/bin/bash`. Ruff passed. Exact-head `test` and `frontend` CI passed on `d117994`;
  PostgreSQL ran as part of Linux CI. The later gateway listener/image scaffold needs its own final-head CI.
- A further RED showed that a global hold placed after the approval request still allowed an answer. The answer
  now refuses it before consuming step-up. The gateway's loopback HTTP contract also went red on its missing
  handler and green with exact-path authentication and journal-status tests against a fake proxy.
- The ACR-0019 journal contract exposed a single-row status update. RED showed no append-only event table; GREEN
  now records separate `received` and terminal events, with triggers refusing update/delete.
- The socket proxy's empty ACL and HTTP handler went RED then GREEN. A further RED showed raw Docker inspect fields
  crossing the proxy; it now returns only `Id`. The Unix transport rechecks identity immediately before POST.
  Closed image configuration refuses startup and no compose mounts an action token. Docker Desktop is unavailable
  locally, so image-level and PostgreSQL tests await Linux CI or a throwaway Docker host.

No code change. On the VM: 89/89 database checks, `AUDIT CHAIN OK: 273 rows chained`, health 200, NO INTERFERENCE.

No code change. On the VM: 56/56 database checks, `AUDIT CHAIN OK: 265 rows chained`, health 200, NO INTERFERENCE.

- RED: `tests/test_phase18_remediation.py` initially failed on the missing remediation module and SQLite methods; both were then implemented.
- GREEN: 21 focused phase-18 and graph tests passed on commit `666a990`. Ruff, Brain lint/audit, the migration checker and the judge-evaluation dry run also passed. Exact-head CI `test` and `frontend` checks passed; `main-guard` was skipped for this stacked PR.
- Full offline suite completed locally with 23 environment-bound failures: Windows resolved `bash` to WSL without `/bin/bash`, Git Bash subprocesses were denied by the sandbox, and placing pytest's temp root inside the checkout made deploy tests detect the parent repository. The exact-head CI test passed. PostgreSQL migration test was not run locally because Docker Desktop is unavailable and `ARGUS_TEST_PG_OWNER_DSN` is unset.
- Judge model comparison: only the harness (`ops/phase18_judge_eval.py`) and its 18 labelled cases exist; no run, live metric or winner is claimed (no API credential in this checkout). The task holds a provisional choice from the public catalog and prices.

- Full offline suite on the PR head: 1919 passed, 74 skipped, 1 deselected; exit 0.
- After merging `origin/main` at `7f8c14b`, the focused TASK-19, T-0047 and evaluation tests passed: 117 passed.
- Ruff, Brain lint/audit and `git diff --check` are clean. Brain `split_entry` validation is run for this entry.

- RED: `test_score_two_with_incomplete_task_and_no_recorded_corrections_is_valid` failed on the exact PR head with `score 2 requires a major correction`.
- GREEN: focused paired-evaluation tests passed after the validator change: 19 passed.
- Full offline suite (with the protocol exclusion): 1,997 passed, 74 skipped, 1 deselected in 1,085.68 seconds. Ruff, Brain lint/audit, `split_entry`, and `git diff --check` passed.

- RED: with replay.py and regrade.py from main, test_a_replay_keeps_the_final_ranked_list and the two regrade tests
  (new fields, old rows) failed on the missing fields.
- GREEN: the focused tests pass. They cover the 15 isolated variants, a rank flip, label-based ruled-out recall,
  per-class metrics, legacy rows, stdin input, the regrader with new and old rows, and a round trip of a row in the
  CLI shape through a JSONL file into the analyzer.
- Full offline suite on `299290f`: 1923 passed, 71 skipped, 1 deselected; the reviewer's independent run on the same
  head also exited 0.

- Red first: with the fixtures reverted, the replay test failed with `/docker/df: not found`.
- With the fixtures, the replay test (it globs every `disk-*` case) passes on the branch at current main (`106190b`).
- The replay, T-0037 and evaluation tests passed together (122); Ruff, Brain lint/audit and `split_entry` were clean.

The temporary restored-text assertions failed twice against the exact #310 source and passed twice after the revert.
Focused T-0047 tests: 108 passed. Ruff, Brain lint/audit and `git diff --check` passed. The full offline suite is
pending review clearance.

Red seen before the implementation: the three new cursor/history regressions failed for the expected reasons (missed
intermediate transitions, restart replay and missing cursor persistence). The focused L6 suite passes **11 tests**.
The full local pytest suite completed with 15 failures in Bash-backed tests: Windows selected its WSL launcher, which
reports `execvpe(/bin/bash) failed: No such file or directory`. CI's first run found a serialization-format assertion
in the new Postgres test (`Z` versus `+00:00`); commit `26aeb79` normalizes UTC to `Z`. On that commit, GitHub CI's
`test` job (including the Postgres runtime test) and frontend job both pass; `main-guard` is skipped by workflow rules.
Brain lint, audit, diff check and migration checker pass. The Postgres test remains skipped only in local Windows runs
because Docker is not running.
Review fixes: `tests/test_t0046_l6_sample_history.py` 10 passed and `tests/test_t0046_l6_eval.py` 2 passed; removing
either staleness block, the window bound for an `unknown` link (both silent-exporter tests) or the SQLite `at <= cursor` guard makes its new test fail.
Paired one-trial baseline evaluation on the same branch and 66 cases (stored in `execution/history/T-0046-l6/step-02/`):
control without the offer 57/66, treatment 62/66; the four hard checks are 0 in both; no class is lower;
`dependency_unavailable` 4/7 → 6/7, `health_check_failed` 10/11 → 11/11, `nginx_upstream_failure` 5/7 → 7/7. The
earlier "60/66 before" had no stored file and predates the tighter SC-08 labels; this run replaces it. Four unrelated
cases fail in both arms. The model arm is not measured. VM deployment remains pending.

- Red seen: `tests/test_action_incident.py::test_vm095_actions_are_denied_even_for_fully_valid_lab_candidate`
  failed because the policy returned `container.start` for `vm-095/container:argus-lab-cache`.
- Green: the focused action and write-gate tests passed (75 passed); Ruff, Brain lint/audit, and `git diff --check`
  are clean. The first focused run hit a local pytest temp-directory permission error; rerunning with a worktree-local
  `--basetemp` passed.
- The first full offline suite attempt used pytest's default temp root and finished with 937 passed, 71 skipped,
  1 deselected, and 979 errors in 816.74s. A representative setup traceback was pytest `tmp_path` failing with
  `PermissionError: [WinError 5]` while scanning the global user temp root.
- The corrected full offline suite used a dedicated basetemp directly under the workspace root, outside every
  worktree. It finished with 1,915 passed, 72 skipped, and 1 deselected in 1,188.18s, with no errors. This confirms
  the first run's setup errors came from access to the global temp root.

- OBSERVED RED: current main-guard reports MAIN RULE BROKEN for #303's missing final-head teammate review.
- The b8533b8 remerge diff is nonempty; d76f742 has an empty remerge diff.
- This is a records-only recovery; runtime behavior is unchanged. Journal/status, Brain lint/audit and whitespace
  checks passed. The Brain policy suite passed: 109 passed in 161.93 seconds. No new full-suite or runtime RED/GREEN
  claim is made for this record.
- Separately for #300, its original 130 focused regressions passed. After repairing the local Python environment
  and moving pytest temporaries outside the worktree, the six files containing the earlier local failures passed:
  64 passed, 2 skipped. This does not constitute a new full-suite pass.

- Red seen: the expected per-class report failed against an empty summary placeholder.
- Green: 26 synthetic paired-report tests passed; Ruff, Brain lint/audit and `git diff --check` are clean.
- Full offline suite (corrected workspace basetemp): 1 failed, 1,905 passed, 74 skipped, 1 deselected in 1,347.55 s.
  The sole failure is an unrelated timeout in
  `tests/skills/test_pr_review.py::test_a_later_changes_request_or_dismissal_cannot_leave_an_old_approval_active`.
- The first full-suite attempt used an in-worktree basetemp and caused seven `tests/test_deploy.py` clone-discovery
  failures; the corrected run moved basetemp outside all repositories, and those tests passed.

Red seen: `tests/test_phase16_step5c_check.py` failed against the 5b tree (no `check_digest_files`, no digest mounts, no
sink variable, the old memory limit). Green: that file (the series checked as a whole: clean, a single file, an edited digest,
another key, a missing day, a rewritten chain, a file that is not a digest, nothing to check; the compose file: only the
scheduler mounts the digest folder, read-only, never `secrets/agent/`, the sink variable, the memory limit) and the updated
`tests/test_compose_split.py`.

Review-fix RED observed on the original #314 head `5f7ed1c`: both added regressions failed. The function returned `[]`
for the edited body, and the CLI printed `DIGESTS OK` without raising `SystemExit`. GREEN after the fix: 65 passed,
2 skipped across the digest, OCI sink, audit-chain and compose modules. Brain lint/audit, Ruff and the architecture
version-line helper passed. Full offline suite: 1906 passed, 73 skipped, 16 failed. The failed shell simulations selected
the Windows WSL launcher, whose `/bin/bash` is missing (the allowlist prune then also lacked its expected output file).
All 16 failed cases passed when repeated with Git Bash first on PATH (24.67 seconds). No repository change was needed
for those environment failures; no clean single full-suite run is claimed. Docker Desktop is unavailable locally;
the relevant opt-in tests were skipped. Fresh exact-head CI remains required after publication.

Independent full-suite recheck on 2026-10-24: **1922 passed, 73 skipped**, exit 0 (1219.36 seconds), with Git Bash
first on PATH, temporary repositories outside the worktree and execution outside the Windows sandbox. OCI 2.189.0
was installed as declared by this branch; the dependency check passed. One pytest cache-write warning did not affect
the result. The tested runtime, tests, architecture, policies and compose files are byte-identical to published head
`737707e`; only task/journal prose differed between the isolated worktrees. This supersedes the earlier environment
failures and the lack of a single successful full-suite run. No runtime change is made by this evidence update.

Review correction on 2026-10-25: two missing-tail regressions failed on the prior implementation. After the fix,
`tests/test_phase16_step5c_check.py` passed (18 tests); Ruff, Brain lint and Brain audit were clean. The full offline
suite finished with exit 0 on the corrected tree, with Git Bash first on PATH. Exact-head CI is required after push.

- Brain split_entry accepted the journal heading, fields, and both optional sections.
- Brain lint: lint: clean (exit 0); Brain audit: audit: clean (exit 0).
- Ruff is not applicable to these Markdown-only changes.
- git diff --check: clean (exit 0, no output).
- All authored audit, journal, commit, and PR text lines are at most 120 characters.
- TASK-17 peer review: PASS WITH NOTES; the no-trace and header-ownership decisions remain with conantkd.
- Full offline suite: 1,912 passed, 74 skipped, 1 deselected in 1929.72s (0:32:09); exit 0.

- Alignment on 2026-10-24: merged `origin/main` at `106190b` (including #300 and the #320 main-guard recovery) into
  the #316 head `84c2ed9` in an isolated checkout. Git's automatic merge succeeded without conflicts; both the action
  policy wiring and main's audit-digest wiring are retained. Already-merged ACR-0018/ACR-0019 changes no longer appear
  as changes unique to #316. The staged code tree was checked against `git merge-tree` and matches Git's automatic
  result; additional edits only update this journal and the task status. Ruff, Brain lint/audit, journal/status validation
  and staged whitespace checks passed. Full local pytest passed: **1979 passed, 73 skipped in 1146.94 seconds**, using
  the repaired repository virtual environment, Git Bash first on PATH and default pytest temporary directories outside
  the checkout. Main and the source ref were refreshed after the suite and had not moved. No new runtime behavior or
  tests were introduced by the alignment. Exact-head GitHub checks are required after publication.
- RED seen:
  - `tests/test_action_preconditions.py`: `ModuleNotFoundError: No module named 'argus.actions'`
  - `tests/test_action_risk.py`: `ModuleNotFoundError: No module named 'argus.actions.risk'`
  - `tests/test_action_cards.py`: `ModuleNotFoundError: No module named 'argus.actions.cards'`
  - `tests/test_action_suggestions.py`: `ModuleNotFoundError: No module named 'argus.actions.suggestions'`
- GREEN:
  - `tests/test_action_preconditions.py`: 34 passed
  - `tests/test_action_risk.py`: 6 passed
  - `tests/test_action_cards.py`: 6 passed
  - `tests/test_action_suggestions.py`: 3 passed
  - `tests/test_write_gate_standing.py`: 10 passed (write gate remains strictly closed)
  - `tests/test_e2e2_evidence_gaps.py`: 12 passed
  - Total focused suite: 49 passed. Ruff clean, `brain.py lint` clean.
- Review corrections: regression tests were red for a missing-field negation, object-property access, an ungrounded
  candidate and the domain import boundary. The final selected suite passed **138 tests** (action modules, write-gate
  standing, evidence gaps, import boundaries, all baseline case labels and UI contract). Ruff passed on changed code;
  `brain.py lint` passed.
- C5 incident integration verification: focused action, incident, evaluation, write-gate and UI-contract suite passed
  **177 tests**; Ruff, `git diff --check` and `brain.py lint` passed. Evidence is archived at
  [`execution/history/T-0050/step-05/`](../execution/history/T-0050/step-05). The local test run used the installed
  Python 3.12 runtime because the repository virtual environment points to a removed interpreter. A full suite run
  completed with **1,934 passed, 10 failed, 7 errors, 7 skipped**. All 17 failures/errors were subprocess tests whose
  uv-managed interpreter lacked dependencies available only in `.venv/Lib/site-packages` (`pywintypes`, `yaml`).
- Final line-by-line review caught and fixed 8 issues: viewer-visible candidates, weak lab target identity, incorrect
  `status` keys in action guards (the observation field is `state`), incomplete action-card validation, incomplete
  inventory catalogue validation, incomplete service-card parsing, and arbitrary Python comparison methods reachable
  from precondition context. Focused regressions passed.
- `brain.py lint` is clean. `brain.py audit` reports an unrelated Windows-profile-path finding in
  `.review-pr297/review.txt`; that untracked review artifact was left untouched.
- After updating from the latest `origin/main` (`c8d8594`), `tests/test_evaluation.py`,
  `tests/test_t0049_r1_prior_incident_fixtures.py` and `tests/test_t0047_hypothesis_check_steps.py` passed **116 tests**;
  Ruff and `brain.py lint` are clean. The merge had one conflict in `argus/evaluation/replay.py`, resolved by retaining
  both T-0049 prior-incident seeding and Phase 17 `next_actions`. Per REVIEW_PROTOCOL, this manual conflict resolution
  requires a fresh review before merge.
- PR #316 is ready for review at head `be3043b`; the aligned merge commit is `13a54ae`. GitHub `test` and `frontend`
  checks passed; `main-guard` was skipped. `brain/execution/current/code.bash` contains unrelated edits and is excluded
  from this task commit.

Red seen: the new tests failed to import `DigestSinkError` on the 5a tree. Green: `tests/test_phase16_step5b_oci_sink.py`
(the sink against a fake client: created once, the same digest, another object, a retention refusal, a refusal with
nothing behind it, a failing HEAD, a transport error; the job's event; the setting; the key beside the config) and
`tests/test_phase16_step5_digest.py` pass. **Against the real bucket:** the opt-in test passed on conantkd's laptop
(2026-10-23, `1 passed`): a new name was created, the same bytes were recognised (`exists_same`) and other bytes under
the same name were recognised (`exists_different`), through the create-and-inspect credential. It left one object under
`selftest/`, kept by the retention rule until the rule is removed.

- After merging the current #303 head, the updated #311 head is pending GitHub `test` and `frontend` checks; no local tests were rerun after the conflict resolution.

Red seen: `tests/test_phase16_step5_digest.py` failed to import `argus.domain.audit_digest` before the code existed.
Green: 21 passed (the digest of a day, quiet days, out-of-order rows, rows before the chain, signing and tampering, the
check against a rewritten chain, the job: once per day, catch-up, a broken chain, a failing sink, a conflicting object,
no key or no sink, the local sink and its path rules, the schedule section, the scheduler loop, the key loader, the
sink setting).

- Main alignment on 2026-10-24: merged `origin/main` at `c8d8594`. The manual `ARCHITECTURE.md` resolution uses the version-line reconciler: it keeps the digest row at 1.8.32, ACR-0024 at 1.8.33, and preserves the complete version history. The only header normalization was the parenthesis formatting on the shared 1.8.31 entry. ACR-0018 now states that OCI uses a locked retention rule without versioning, and its `Not yet` list no longer names `policies/SECURITY.md`, which this step updates.
- Post-merge focused tests: **136 passed** (`test_phase16_step5_digest`, evaluation, T-0049 prior incidents, T-0047 hypothesis checks). Ruff, `git diff --check`, Brain lint/audit, and the version-line helper passed.
- GitHub CI for the updated head is pending after push; the previous head's test and frontend checks were green.

Documentation only. `brain.py lint` and `brain.py audit` clean.

T-0049 R1 prior-incident fixtures: `tests/test_t0049_r1_prior_incident_fixtures.py` 5 passed (red seen: 5 failed);
`tests/test_t0039_prior_incidents.py` and `tests/test_evaluation.py` pass with it. Full offline suite, with Git Bash
first on PATH: **1862 passed, 34 skipped, 1 deselected** (the known detached-CI Brain test), exit 0.
That ran on `8b40610`; on main `201cc7c` the fixture, T-0039 and evaluation tests: 110 passed.

Frontend: `src/build.test.js` now also requires ECharts' `registerPainter` in a real-mode build: red seen
(`expected ... to contain 'registerPainter'`), green after the fix. Vitest 298 passed (46 files); ESLint clean on the
changed files. Browser: the production build (`vite preview`) shows an incident's Metrics tab with 3 SVG charts and
no console error from the new chunk.

Red: the focused suite failed collection with `ModuleNotFoundError: services.terminal_broker` before the core existed.
Green: `tests/test_acr0020_terminal_broker.py` — 12 passed; Ruff, Brain lint, Brain audit and `git diff --check` —
clean. The four existing import-boundary cases also pass. The repository-wide suite is left to CI because its Docker
and Postgres services are part of that required run.

Frontend: Vitest 298 passed (the two new Security tests seen red first), ESLint 0 errors on the changed files.

Documentation only. `brain.py lint` and `brain.py audit` clean.

- RED then GREEN (S2): `test_a_model_run_records_provider_token_usage` failed until `RecordingLLM` recorded usage;
  `test_the_command_line_runs_the_model_and_writes_one_json_line_per_run` asserts the two new row fields.
- The offer's tests (`test_t0049_r1_offers.py`, the `test_t0037` offer assertion) were removed with the offer.
- Full offline suite on `8b40610` plus this change, Git Bash first on `PATH`: 1858 passed, 34 skipped, 1
  deselected. Ruff, Brain lint and audit, `git diff --check`: clean.

`tests/test_op014_mutation_second_factor.py` 19 passed, `tests/test_op014_mutation_audit_chain.py` 2 passed,
`tests/test_ui_contract.py` 4 passed (Docker `python:3.12-slim`); each of the 171 survivors fails the new tests.

T-0047 H4 hypothesis instructions: `tests/test_t0047_hypothesis_instructions.py` 7 passed (red seen: 5 failed); the
T-0047 H1, H2 and H4 test files and the two earlier prompt-rule test files pass with it. Full offline suite, with
Git Bash first on PATH, on `b22c669` plus this change: **1843 passed, 1 failed, 34 skipped, 1 deselected**. The
failure is `test_acr0011_ui_edge.py::test_what_passes_and_what_is_refused[GET-/api/v1/me-200]` (502 on the fake
API's first request); it fails the same way on `main` `8b40610` without this change, and this change touches neither
the edge nor the API.

- Red first: the six replay assertions failed because `/containers/argus-lab-worker/top` was missing and the fixture
  executor raised `ExecutorError: not_found`.
- On the branch before the latest main update, the R1b, T-0037 and evaluation tests passed; Ruff and Brain lint/audit
  were clean. The full offline suite passed once after S1's rule-7 pre-review.
- Brain's `split_entry` accepted the corrected heading and extracted the Test state and Next step sections.
- R1BF.1 reruns the focused R1b, T-0037 and evaluation tests, Ruff, Brain lint/audit, `split_entry` and diff-check after
  merging current main. The full suite is not repeated for this journal-only correction.

T-0047 hypothesis check steps: `tests/test_t0047_hypothesis_check_steps.py` 13 passed (red seen: 4 failed); the
T-0047 H1, H2 and H4 test files pass with it (54 passed). Full offline suite, with Git Bash first on PATH, on
`b22c669` plus this change: **1849 passed, 34 skipped, 1 deselected** (the known detached-CI Brain test), exit 0.

No code changed; analysis of the #274 result files only.

`tests/test_phase16_private_path.py` 20 passed on Windows with Docker: the real Nginx in public mode with the private
path on; no certificate, an unlisted address, a revoked or a foreign certificate → 404; a valid certificate from an
allowed address reaches the API; the public UI unchanged. On Linux, the scripts and static checks pass (the Docker
cases skip there). `tests/test_acr0011_ui_edge.py` 34 passed with Docker. `nginx -t` passes in loopback, public-off
and public-on modes. Shellcheck is clean.

- RED: both new focused tests failed before implementation. The ID regression kept `inc_77b419ffd2c4` instead of the
  shared `inc_7e49840f50fa`; the missing-position test showed the script returned success without restoring files.
- GREEN: all 15 tests in `tests/skills/test_ui_contract_samples.py` passed. Ruff and `git diff --check` passed.
- Full offline suite (Git Bash first on `PATH`, on `7a634c7` plus this change): 1815 passed, 34 skipped, 1
  deselected. Brain lint and audit: clean. Rebased on `a4ee19b` (#288, #291-#293 merged): `tests/skills` and
  `tests/test_ui_contract.py` passed again (250).
  S1 pre-reviewed the change (S3 was on another task).

Frontend: Vitest 205 passed (fleetStatus, mapModel, layout and the contract test seen red first), Playwright 25 passed
(the map test now tabs to a box, opens its drawer, closes it with Esc), ESLint 0 errors.

`check_migration.py 013_webauthn.sql`: FAIL (two tables) before, PASS after. `tests/test_postgres.py` and
`tests/skills/test_db_migration.py` on a throwaway Postgres 16: 42 passed (a first run caught a `\x00` escape typo).

- Documentation-only draft; no runtime or skill code changed. Brain lint and audit are clean; `git diff --check` is
  clean. The isolated S5.1 block passes `check_block.py` and parses with zero PowerShell errors without execution.
- No full offline suite was run, as requested for documentation-only changes.

Documentation-only; no runtime RED/GREEN claim. Brain lint and audit are clean. `check_block.py
brain/execution/current/code.bash` and the PowerShell parser both pass. The final-tree offline suite on main `f480152`:
`1727 passed, 63 skipped, 1 deselected`, exit 0 (1131.55 s). The only deselection is
`tests/brain/test_brain.py::test_lint_reads_the_pr_branch_from_ci_when_head_is_detached`. An earlier passing run on
`863dbf0` was superseded after main advanced with PR #285 during validation.

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

T-0047 H5 step 2 B: `tests/test_t0047_h5_anomaly_summary.py` 23 passed (red seen twice: offered to none, then to
both classes); offline evaluation 32/61 registered, 57/61 baseline, hard 0.

Model batch on vm-095 (run stamp `20261022T174900`): restart 0.97 → 1.00, dependency 0.52 → 0.84, hard after 1
(above). Full offline suite on the final tree (the tag on the restart class only, main `863dbf0` merged): **1701
passed, 63 skipped, 1 deselected**, exit 0.

- RED: the 9 focused tests in `tests/skills/test_ui_contract_samples.py` failed with the helper absent (the
  pure-function tests failed on import; the restore and SKILL tests failed on the missing files).
- GREEN: 13 passed. They cover:
  - the same shape keeps the bytes;
  - a new key or a type change is a change;
  - a list by its first item;
  - a value-only change is reported, times, ids and hashes alone are not, and `--keep-new` keeps the new bytes;
  - added and vanished samples;
  - the shape is the same as the contract test's;
  - restore writes only the kept files and refuses a path outside the folder;
  - a failed run puts back the samples and `ui-api.json` and removes new samples;
  - the SKILL names the switch.
  Ruff is clean.
- Full offline suite on main `77c4524`: 1714 passed, 63 skipped, 1 deselected (the known detached-CI Brain test),
  exit 0.

- **RED seen:** against a naive checker that only looked for the file, **16 failed, 8 passed**: a store table with no
  migration, a store column with no migration, a missing table and sequence grant, a missing SQLite table, either store
  never inserting, no db-check insert, a refusal before the insert, missing UPDATE/DELETE refusals and triggers, a wrong
  number or name, a new column the SQLite store ignores, and the CLI.
- GREEN: `tests/skills/test_db_migration.py` **24 passed**: committed migrations 007 to 012 pass; a complete new
  `widget` table passes; the CLI gives the same answer twice and leaves the fixture tree byte-identical. Ruff clean.
- Full offline suite on `6a72339` plus this change: 1656 passed, 62 skipped, 1 deselected, exit 0. After the
  fast-forward to main `95e67a7` (#282): **1662 passed, 62 skipped, 1 deselected in 973 s**, exit 0 (the known
  detached-CI Brain test). Brain lint clean.

- RED: 14 focused tests in `tests/skills/test_vm_deploy.py` failed with the helper absent.
- GREEN: 20 passed. These cover the order, the migration between the backup and the image, the UI-only and docs-only
  cases, vm-166's own lease, new compose variables, a new secret mount (and the real Ed25519 one), target and
  monitoring on both VMs, unmapped paths, a sha-only commit, git-only subprocesses, manual invocation and the CLI.
  Ruff is clean.
- Full offline suite on main `77c4524`: 1721 passed, 63 skipped, 1 deselected (the known detached-CI Brain test),
  exit 0.

- **RED seen:** against a naive checker that only looked the name up in the catalog, **23 failed, 3 passed**: a
  missing or bad `max_per_incident` (six forms), an initial class offer, a sensitive read without allowed fields,
  twelve wrong spec fields, an executor replay cannot answer, a read no test names, and the CLI.
- GREEN: `tests/skills/test_add_capability.py` **26 passed**. Running `--all` twice on the committed repository gives
  the same PASS (read-only, idempotent). `analysis.anomaly_summary` passes, and `container.status` fails as offered
  unless `--allow-offer`. Ruff clean.
- Full offline suite on `6a72339` plus this change: **1658 passed, 62 skipped, 1 deselected in 964 s**, exit 0 (the
  known detached-CI Brain test). Brain lint clean.

Redaction: `tests/test_redact_bearer_named_secret.py` 11 passed (red seen: 5 failed); the four redaction test files 68 passed; full offline suite 1503 passed, 62 skipped, 1 deselected.

Review change: `test_a_short_token_on_the_next_line_is_still_masked` (two inputs) replaces the same-line test. Red seen
on the PR head `8c1a79a`: 2 failed. After `\s+` is restored: the file 12 passed, the redaction-related tests 229 passed;
full offline suite **1510 passed, 62 skipped, 1 deselected**, exit 0.

- RED seen before implementation: the five focused tests failed because the validator was absent.
- GREEN after S3's paired review fixes: seventeen focused tests passed (missing/empty sections, unlinked status,
  missing row, linked versus unlinked completion in table, plain and marked-up forms, and three real task shapes).
  Brain lint/audit, Ruff and diff whitespace checks clean.
- Full offline suite on integrated main `6a72339`, after the final `done` guard: 1649 passed, 62 skipped,
  1 deselected (the known detached-CI Brain test), exit 0. S1 re-ran the 17 focused tests, Ruff and Brain lint
  on the final tree: clean. S1 reviewed the final `done` guard (S4 hit its quota before S3's clearance).

- **RED seen:** five behavior cases failed against the naive helper: parallel
  versions lost one branch, changelog rows stayed shuffled, conflicts were
  accepted, a missing row was accepted, and a missing ACR link was accepted.
- **RED seen:** the current architecture's embedded-pipe and legacy
  three-column changelog rows were rejected; Windows CLI output failed on
  a Unicode `≤` character.
- Focused GREEN: **11 passed**. The helper also read both inputs from the
  current real `ARCHITECTURE.md` successfully. The first full run was stopped
  when main advanced. The fresh integrated-main full suite on `6a72339` passed:
  **1643 passed, 62 skipped, 1 deselected in 1250.45s**, exit 0. The sole
  deselection is the known detached-CI Brain test. Ruff, Brain lint/audit,
  skill validation and whitespace checks passed.
- S3 pre-reviewed the real current document (27 rows, version value identical),
  simulated two parallel branches and a same-version collision, and cleared
  the documentation follow-ups. References now sit outside the roll-up sections;
  the skill explains the one-time sorting of the old `1.8.5`/`1.8.4` rows.

PHASE-16 step 3b: Vitest 219 passed (18 new: `webauthn.test.js` 5, `secondFactorAdapter.test.js` 8,
`Security.test.jsx` 5; the contract test covers the new calls); coverage floors hold; ESLint 0 errors (the 23 known
react-refresh warnings); `npm run build` passes.

PHASE-16 step 3a: `tests/test_acr0018_webauthn.py` 16 passed (a software authenticator: ECDSA P-256, "none"
attestation, real ceremonies). The tests cover the ticket (single-use, own person, expiry), a further key by step-up,
a login marking its own session only, privileged permissions only with two keys and this login, and the step-up token
(replay, another object, session or person, expiry). They also cover the challenges (replay, another ceremony,
expiry), another origin or relying party, a counter going back, another person's key, the reset, read and investigate
tokens, and no-delete tables. `tests/test_postgres.py::test_webauthn_and_step_up_migration_013` passes on a
throwaway Postgres 16, as does `argus db check`'s list (11 new checks). The authorization matrix declares the seven routes.
The read-token sweep exempts the ceremonies like logout. The full offline suite was run; its four failures, a Postgres
regex limit and three tests to update, are fixed. Ruff is clean.

- **RED seen:** with only the `GH_TRIES_5XX` name added, the new tests failed on behaviour: the 5xx, empty and
  `unexpected end of JSON input` cases raised after 3 tries, and the "keeps answering 5xx" and "never JSON" cases
  made 3 calls instead of 6 (**6 failed**).
- GREEN: `-k "gh_json or verify_main or check_main"`, **15 passed**. The old "gives up" test now uses an HTTP 403
  (not a server error) and checks it keeps 3 tries and the 2 s, 4 s waits.
- Full offline suite on `6a72339` plus this change: **1638 passed, 62 skipped, 1 deselected**, exit 0 (the known
  detached-CI Brain test). Brain lint clean, `git diff --check` clean.

OP-013 model runs on the held-out set (vm-095, `6c83da3`, 5 trials): dep `model_loop` 0.77, nginx `plan_then_reason` 0.87, baseline 0.50 each, hard 0.

Documentation only; no runtime change. Full offline suite on main `096bf90` plus this memo: passed, 0 failed
(1554 collected, only the known detached-CI Brain test deselected). Brain lint and audit clean. Peer pre-review
(S3): four findings, all applied.

- **RED seen:** the no-op CLI returned success for a head behind main despite CLEAN, a hidden behavior change
  in a conflict resolution, and a missing roll-up evidence line: **3 failed, 1 passed, 21 deselected in 8.13s**.
- First focused GREEN: **25 passed in 54.23s**. Tests use local synthetic Git histories and recorded API data.
- Added edge RED records: malformed nested file evidence leaked a traceback (**1 failed, 5 passed,
  25 deselected in 6.66s**); a malformed removed journal entry leaked Brain's parser exception
  (**1 failed, 31 deselected in 3.38s**). Both now return a sanitized, non-ready evidence diagnostic.
- Intermediate expanded GREEN: **31 passed in 58.80s**. GET-only pagination tests cover 205 comments
  and refuse incomplete file/check pages. A live read-only preview of PR #268 correctly identified its
  four protected source paths and refused the missing teammate approval, without posting or acting.
- Focused GREEN before the self-review correction: **32 passed in 90.16s**.
- Self-review RED: a 100-file unprotected PR was wrongly reported ready without a teammate
  (**1 failed, 1 passed, 32 deselected in 4.95s**). Full self-merge eligibility now delegates to
  Brain rather than considering protected paths alone. The earlier full run was intentionally
  interrupted for this source fix.
- Final focused GREEN after full policy delegation: **34 passed in 64.44s**.
- Complete offline suite on `9d65e1e`: **1505 passed, 62 skipped, 1 deselected in 823.67s**, exit 0.
  All eight source hashes matched the run snapshot. Process-local Git Bash selection and fixture Git
  isolation only; the sole deselection is the known detached-CI Brain case.
- Paired pre-review ran the same **34 tests successfully**. Its ordering wording finding is fixed:
  the helper checks each whole payload, while inter-entry chronology follows Brain's roll-up command.
  Added the requested disclosure that helpers run reviewed main's Brain module in-process.
- Paired re-review after the clarifications: clear (S3). Current-main validation: full offline suite on integrated main `096bf90` (run by S1 after S2's session ended): 1588 collected,
  1 failed, the rest passed or skipped. The failure is not in this PR: the property test
  `test_a_named_secret_is_masked_whatever_its_value` found that on main the Bearer rule of
  `argus/capabilities/redaction.py` swallows the next line's secret name (`Bearer
password=x` leaks `x`);
  it reproduces on main without this PR, and a separate fix PR handles it. Fast-forwarded to main `1105b6f`
  (#271 records, #272 a test file): `tests/skills`, `tests/brain` and the new test file pass.

`tests/test_op014_mutation_timeouts.py` 6 passed on the original code (with `test_op014_mutation_policy_decisions.py`
and `test_combined_capabilities.py`: 24 passed); each of the 13 mutants makes it fail.

Documentation only: no new runtime behavior and no runtime RED/GREEN claim. Implementation tests are a plan in
ACR-0029 §4.1. Full offline regression on main `9d65e1e` plus this proposal: **1471 passed, 62 skipped, 1 deselected**,
exit 0 (886.92 s); only the known detached-CI Brain test was deselected. The process used Git for Windows' Bash and
a fixture Git-discovery ceiling; no global configuration or additional exclusion changed. Peer fixes are wording
only; final Brain/link/whitespace checks after them are clean. Ruff (`argus services ops`) and Brain lint/audit are
clean; 11 relative links resolve, all 22 cited architecture subsections exist and the documentation uses LF.

T-0047 H5 step 2 A: `tests/test_t0047_h5_anomaly_summary.py` 17 passed (8 new, red seen: the replay answered the
dependency with the victim's series); offline evaluation identical before/after.

Frontend: Vitest 191 passed (chartOptions, refresh and format tests seen red first), Playwright 25 passed, ESLint 0
errors.

Frontend: Vitest 168 passed (format, build and switchTheme tests seen red first), Playwright 25 passed, ESLint 0
errors.

- **Red seen:** `test_rejects_known_traps[native-quotes]` asserted status 1 and observed status 0 with
  the no-op entry point. This was a behavior assertion, not a missing import or syntax failure.
- **Red seen:** six `test_rejects_unguarded_vm_mutation_in_read_looking_commands` cases likewise
  observed status 0 before checks for write-capable tools, expansion and redirection were tightened.
- **Red seen:** the whole-file fixture reproduced 12 false positives before header discovery was fixed.
- **Red seen after peer review:** `test_rejects_known_traps[vm-single-quote-backslash]` expected refusal
  (status 1) but observed status 0: **1 failed, 63 deselected in 1.66s**.
- **Green:** shared-venv `python -m pytest tests/skills -q -o addopts=`: **64 passed in 14.86s**.
- **Red seen for the current SESSION correction:** **9 failed, 16 passed, 64 deselected in 4.36s**.
  Two anchored guards and three allowed first-marker cases were refused; three inverted guards were
  wrongly accepted; the real two-field marker failed the local read-only template simulation.
- **Green for the current correction:** **89 passed in 11.81s**, including wrong-holder/prefix-collision
  simulation cases and 14 rejected variants of the marker exception. The simulation replaces both VM
  paths with local temporary files and intercepts `sudo`; no VM command or connection runs.
- **Red seen after the second peer review:** bare holder guards were wrongly accepted (**3 failed,
  2 passed, 89 deselected in 1.17s**); the real marker's `/dev/null` stdout redirect was wrongly refused
  (**2 failed, 98 deselected in 0.74s**). Require a holder boundary or a full-line two-field match,
  and admit only the authorized optional stdout redirect. Final focused result: **100 passed in 14.22s**.
- The whole-file and three original isolated fixtures still pass without executing their commands.
- `ruff check .claude tests/skills`: clean. Skill frontmatter validation: valid.
- All three PowerShell templates parse without execution; the Bash template passes `bash -n`.
- Brain lint, secret/address audit and whitespace checks are clean for the correction and approved archive.
- Full offline suite on unchanged `b997395`: **7 failed, 1474 passed, 62 skipped, 1 deselected in 1167.34s**.
  All seven failures selected the Windows WSL launcher, whose `/bin/bash` is unavailable, in
  `tests/test_t0033_rotate_token_script.py`. Selecting installed Git Bash only in the test process makes
  those seven tests pass (**7 passed in 8.18s**, verified in the governance worktree).
- The first peer correction passed its original-base full suite: **1482 passed, 62 skipped, 1 deselected
  in 965.03s**, exit 0.
- The first current-main run was intentionally interrupted for the second peer review's source fixes;
  it is not a full pass. The final-source run replaces it.
- Full offline regression of the final correction on integrated main `9d65e1e`: **1571 passed,
  62 skipped, 1 deselected in 742.16s**, exit 0. It uses process-local Git Bash selection and a Git
  discovery ceiling for temporary repositories. Only the known detached-CI lint case is deselected.
- Integrated-main validation on `808d46a` (main `096bf90`) with the final three-file record: full offline
  suite passed, 0 failed (1654 collected, only the known detached-CI lint case deselected); run by S1
  after S2's session ended.
- No runtime, database, CI or shared Brain summary changes; no VM command or external action executed.

OP-013: `tests/test_op013_heldout_cases.py` 4 passed; full offline suite 1475 passed, 62 skipped (main `9d65e1e`); baseline on the held-out set 6/12 (dep 3/6, nginx 3/6), hard 0.

- **Red seen:** all three new `.claude/skills/` cases in
  `test_a_self_merge_never_covers_a_protected_path` failed because `self_merge_problem` returned `None`.
- **Green:** the same cases: **3 passed, 100 deselected in 0.32s**.
- Brain suite before main integration: **102 passed, 1 deselected in 118.78s**. The excluded case is
  `test_lint_reads_the_pr_branch_from_ci_when_head_is_detached`, as the session board directs.
- Ruff over `argus services ops brain/tools/brain.py tests/brain/test_brain.py`: clean.
- Brain lint/audit and whitespace check: clean.
- First complete offline run: **7 failed, 1415 passed, 62 skipped, 1 deselected in 1164.35s**. All failures
  are the token-rotation script tests selecting the unavailable WSL Bash instead of installed Git Bash.
  The seven cases pass with process-local Git Bash selection (**7 passed in 8.18s**).
- Completed offline rerun on the original base: **1422 passed, 62 skipped, 1 deselected in 955.90s**.
  Process-local Git Bash selection and a Git discovery ceiling for temporary repositories resolved
  the environment issues without changing tests or global configuration.
- After integration with `9d65e1e`, the three skill-path cases passed again:
  **3 passed, 100 deselected in 0.59s**. Ruff is clean.
- Full offline validation on integrated main `9d65e1e`: **1474 passed, 62 skipped, 1 deselected in
  843.27s**, exit 0. This includes **102 passing Brain cases**. Only the known CI-specific case above
  is deselected, with the same process-local Git Bash selection and temporary-repository Git ceiling.

No code change. The workflow parses; this PR's own CI runs on the pinned actions.

`ruff check argus services ops`: all checks passed. `bandit -lll`: no issue. Full suite green.

No code change. The two audit commands pass locally (exit 0).

- `tests/test_t0045_b7_baseline_deploy.py` is new: ranges, baseline (values, window, sparse, failed read, read once),
  deploy events, the store and the CLI. All red first, except the unknown-range guard.
- `tests/test_deploy.py`: two new tests (the record call before the verdict; a failure never stops the deploy), seen
  red first. Its helper never reaches the machine's Docker.
- `tests/test_postgres.py`: `test_deploy_events_migration_008` (CI's Postgres).
- `tests/test_acr0017_incident_metrics.py`: the key set gains `baseline`; the cache test counts the chart's reads apart
  from the baseline's.
- `contracts/ui-api.json` and `incident-metrics.json` regenerated; the other samples untouched.
- Full offline suite green.

- `tests/brain/test_brain.py` gains six tests.
  - **Retries:** a cut-off answer is retried; a failure is retried then raised after `GH_TRIES`; a good answer is
    read once; a 404 is raised at once. The first two were seen red first (no retry).
  - **Merges (#183):** another branch merged after the approval, and main reaching the branch through another branch.
    Both pass on `main` as it is: they guard existing behaviour.
- `tests/brain` green locally.

New: `tests/test_op014_property_policy.py`, 11 tests, green. No code change. Full suite green.

No code change in this record. CI on `main` at `bdcd048`: `test` and `frontend` green on #195.

New: `tests/test_op014_property_based.py` (22 tests; up to 300 generated examples per property). Red seen: the
glued-token property and the 5 non-ASCII cases failed before the fix. Full suite green.

No code change.

New: 13 tests in `test_t0045_b8_link_reasons.py` (red seen: missing `kind`, `error_kind`, `argus_probe_error`).
`test_t0045_b3_topology.py`: the adapter now makes 3 queries. Full suite green.

No code change in this record. CI on `main` at `2c7248b`: `ci` success.

`test_db_check_proves_the_column_before_counting_its_refusals` (new, red seen first). The Postgres check
(`test_database_guarantees_check`) runs the new read in CI. Full offline suite green.

`tests/test_t0045_b6_target_metrics.py` and `tests/test_t0045_b6_overview.py` (new, red seen first: the modules did not
exist); the edge matrix and the UI contract list both routes; `tests/test_ui_access.py` passes `/target-metrics` its
required `target` (a read token reads every GET route); `contracts/ui-api.json` regenerated and
`contracts/samples/target-metrics.json` and `overview.json` added (the other samples untouched).

No code change in this record. CI on `main` at `dfa7332`: `main-guard` success.

No code change. `brain.py lint` and `audit` run in the commit hook.

Six new tests in `tests/brain/test_brain.py`, red seen first (the function did not exist): `check_main` keeps an
approval only through `keeps_approval` and never the author's own; with real git repositories, a clean merge of main
keeps it; a later commit, an edit inside the merge, a resolved conflict and a rewritten branch do not.

No code change (documentation only).

`tests/test_t0045_b5_recheck_lineage.py` (new, red seen first) and `test_recheck_lineage_migration_007` in
`tests/test_postgres.py`, run on a local throwaway Postgres 16 with the other Postgres tests. `contracts/ui-api.json`
regenerated; `incident.json` and `incidents.json` samples gain `parent_id`. Offline suite green locally (965 passed, 24 skipped; `tests/brain` 81 passed, with one git test that
hangs on the laptop deselected; CI runs it).

`tests/test_evaluation.py`: five new tests; `tests/test_acr0023_log_matches.py`: five (two red first, three guard what
must not change); `test_resume_inside_evidence_pack_does_not_repeat_completed_reads` now compares reads with their
parameters. Full offline suite green on the final commit.

No code change (documentation only).

`tests/test_t0045_b3_topology.py` (new; red seen first: `ProbeSample` did not exist); `contracts/samples/topology*.json`
regenerated. Full offline suite green.

`tests/test_t0045_b4_incident_verdict.py` (new; red seen first: `incident_view` did not exist). `contracts/samples/incident.json` gains the new
fields (its ids unchanged). Full offline suite green.

`tests/test_t0045_b2_incident_metrics.py` (new; red seen first: `KINDS` did not exist); `test_acr0017_incident_metrics.py`
(the series key set gains three fields); `contracts/samples/incident-metrics.json` regenerated. Full offline suite green.

No code change. The workflow is checked by its own run on this PR (`test` and `frontend` start; `main-guard` is
skipped). `brain.py lint` green.

`tests/test_t0045_b1_thresholds.py`: three new tests (red seen first for `unit` / `scale`: `Threshold` had no such fields; the bad
values were refused only as unknown fields). Full offline suite green.

`tests/test_t0045_b1_thresholds.py` (new, red seen first: the module did not exist), `tests/test_ui_host_metrics.py` (one
equality now ignores the new fields), `contracts/samples/host-metrics.json` regenerated. Full offline suite green.

No code change (documentation only).

No code change (specification only).

`tests/brain/test_brain.py`: red seen (21 failures against the previous `brain.py`: the new protected paths, the
rename, the author's `LOCAL CI PASS`, the three measured rules, the `(pr, sha, parents)` call); green after. New:
ordinary paths stay self-mergeable. `brain.py verify-main --ref origin/main` with the new code: see the PR.

`tests/brain/test_brain.py::test_draft_pull_requests_are_listed_as_work_in_progress_not_for_review` (new). This pull
request's own CI is the check for the trigger: one run (`pull_request`) per push.

No code change in this record. CI on `main` at `19b1085`: `test`, `frontend` and `main-guard` success.

No code change in this push (the Brain only). The existing tracing and compose tests were green on the PR.

`tests/brain/test_brain.py`: 6 new test functions (19 cases) for the self-merge check (green checks and ordinary files accepted; each
required check missing or not `success` refused; every protected path refused; 100 or more files refused; a
`LOCAL CI PASS` for the last push accepted, for an earlier push or a `FAIL` refused; `check_main` reports why).

Red seen: `test_injected_text_cannot_close_its_evidence_tag` (5 `</evidence>` for 4 blocks) and
`test_injected_text_cannot_open_a_fake_runbook_passage` (`<passage runbook=\"RB-999` in the context) before the
escape; both green after it. The three other injection cases were green before (guards that keep them so).

`tests/test_acr0011_ui_edge.py::test_the_dockerfile_builds_the_map_and_metrics_calls_in`: red seen (no flag in the
Dockerfile), green after the line.

`frontend/`: `npm test` 23 files / 131 tests (the contract test now calls both routes plus the overlay; two new
adapter tests; two new map-style tests), `npx playwright test` 21/21 (5 new ACR-0017 tests: Map/Metrics tabs,
Dashboard map, operator overlay, viewer plain map, refused-overlay fallback), `npm run lint` 0 errors,
`npm run build` green. Red seen: the new contract/style/overlay assertions and the 5 new e2e tests before the
wiring.

No code change.

`tests/test_acr0017_topology.py`: 13 (red seen: 13 of 13 before the code). Full suite in the PR.

`tests/test_acr0017_incident_metrics.py`: 17 (red seen: 16 of 17 before the code). Full suite in the PR.

One new test, `test_the_worker_alone_takes_the_tracing_endpoint_private_by_default` (red seen: `KeyError:
'ARGUS_TRACING_ENDPOINT'`); the tracing and compose tests green.

No code change.

- `frontend` scope: unit 127/127, acceptance 17/17, ESLint 0 errors, Vite build green.
- The Python suite is not affected by this change (frontend-only); Linux CI's `test` job remains the authority.

No code and no tests in this step (architecture proposal + documentation). The existing suite is untouched.

No code change.

Focused Langfuse exporter and graph-runner tests passed after the model-span addition.
The model-span test was red before implementation. The Agent summary unit test, frontend lint of new files, and
production build passed. The browser-rendered desktop demo was inspected from a local offline preview. Full backend
verification remains pending because automatic approval review exhausted its usage limit while authorizing execution
in the isolated worktree. VM ingestion and capacity validation await a lease.

Documentation-only proposal. Brain lint, audit and PR CI verify the record. LF-1 startup and one native OTLP batch were observed; full coexistence remains unverified after a concurrent Argus recreation.

No code change. brain.py lint and audit run at commit.

- `tests/test_acr0012_investigate.py` 16 (12 red seen); edge tests 29; contract 3.
- Frontend: unit 85, acceptance 14 (stable four times), lint 0 errors.

`tests/test_acr0011_ui_edge.py`: 25 (1 new, red seen).

No code change.

No code change in this step beyond `ops/ui-cert.sh` and the timer (in #144).

`npm test`: 14 files, 74 tests (2 new files, both red seen). No backend change.

`npm test`: 15 files, 76 tests; `npm run e2e`: 9 passed (three runs in a row); `npm run lint`: 0 errors.

No code change in this step.

- New: `tests/test_acr0011_edge_login.py` (10, red seen) and `tests/test_acr0011_ui_edge.py` (24; Docker).
- Frontend: `npm test` 80, `npm run e2e` 10, `npm run lint` 0 errors.

No code change. Review correction: brain.py lint and audit clean; git diff --check clean.
The full pytest suite is being checked before the review is requested again.

`tests/test_t0037_docker_read_verbs.py`: 11 new pattern cases; red on `main`'s pattern (4 failed), green with the fix
(23 passed).

`tests/test_d003_class_registry.py`: 4 (red seen: 2 of 4 on the old registry). `test_evaluation.py` and
`test_knowledge_runbook.py` adjusted (a baseline class makes no model call; the branch-runbook test pins its class to
`model_loop`).

No code change.

No code change.

`npm test`: 12 files, 70 tests passed; `npm run build`: 351 modules. No backend change.

Frontend only, Vitest run deferred (as asked): `sessionStore.test.js` (renamed; token round-trip + JWT-`exp`), the
`httpAuthAdapter`/`httpArgusAdapter` session cases, and the new `paging.test.js`. `npm test` is still to run before
any merge.

`npm test` (frontend): **12 files, 70 tests passed**; `vite build`: 351 modules. Red seen this run:
`sessionStore.test.js` → `TypeError: tokenExpiry is not a function` (a module-private helper, exported in `1c6b7da`).
This closes the deferred red/green of the four 2026-10-13 units.

`tests/test_e2e9_sc12_host_probe.py`: 10 (red seen). Runner tests: 60 passed.

No code change. The runner's results stay outside the repository (`e2e8-batch-1.jsonl`, `e2e8-batch-2.jsonl`).

`tests/test_t0035_monitoring_heartbeat.py`: 3 new tests (red seen): the `platform` route, the default when only
another family has one, and `load_routing` (a file with a `platform` route, no file, an unknown family refused).

No code change. Local CI unchanged.

`tests/test_t0039_prior_incidents.py`: 7 tests (red seen: no capability).

`tests/test_t0037_docker_read_verbs.py`: 12 tests (red seen: no route, no capability).

`tests/test_t0043_missing_scrape_jobs.py`: 4 tests (red seen); one promtool case; the T-0027 signal check updated.

`tests/test_t0042_routing.py`: 10 tests (red seen: no `route` in the notification).

`tests/test_t0040_trace_request_path.py`: 6 tests (red seen: no capability).

`tests/test_t0038_compare_baseline.py`: 14 tests (red seen: no capability).

`tests/test_t0036_metric_histories.py`: 14 tests (red seen: no `mounts` parameter in the Prometheus client).

`tests/test_e2e8_catalogue.py` 11 (red seen), `tests/test_e2e_runner.py` 39 unchanged, green.

`tests/test_eval4_health_wording.py`: the word list updated; 1 test added with the two answers seen (pass) and a
diagnosis naming no check (still fails).

`tests/test_t0033_rotate_token_script.py`: 3 tests added (red seen: `db_probe` refused).

`tests/test_t0035_monitoring_heartbeat.py`: 22 tests (red seen: no `argus.application.monitoring`);
`tests/test_postgres.py`: 1 test added (the state and the escalated incident under the runtime role; runs on CI).

`tests/test_local_ci.py`: 1 test added (red seen: the HEAD mode checked this checkout).

23 floor paths refused by both the agent and the probe with an allow-everything list (16 were allowed: red seen); 5
ordinary paths still allowed; name patterns on directories; the open uses `O_NOFOLLOW` (red seen); a symlink swapped
in after the walk is refused (Linux only, skipped on Windows); a stale probe copy still gets the floor.

`tests/test_redaction_paths.py`: 8 tests added (red seen: the URL and the other-path cases unmasked, and a token under
the declared directory kept); 5 declared paths at a path start still readable.

`tests/test_redaction_paths.py`: 18 tests (red seen: the three URL-path secrets unmasked on `main`, and no
`declared_paths`).

`tests/test_local_ci.py`: 9 tests (red seen: no `ops/local_ci.py`).

`tests/brain/test_brain.py`: 2 tests added (red seen: the merge of main after a roll-up refused; a summary edited during
the merge still refused).

`tests/test_redaction_paths.py`: 8 tests (red seen 3/3 on the paths); the core and knowledge tests that use the
redactor pass.

`tests/test_t0019_batch3c_network.py`: 15 tests (red seen: no `/connectivity` route, no `attempts`, no capability, no
case answers).

Review of #101 (`juanbetancurm`): `/tcp` attempts now share an 8 s budget (under the agent's 10 s client
timeout; each attempt waits `min(3 s, what is left)`, `budget_exhausted` when spent); before, 5 attempts to
a port that never answers could take 17 s and end the read `timeout`. One more test (16), red seen. The
scope of `to` (allowlisted, same host, not checked against the incident's scope) is noted in the task file.

`tests/test_t0019_batch3b_host_verbs.py`: 18 tests (red seen: no routes, no capabilities, no case answers; the symlink
test runs where symbolic links can be made, CI).

`tests/test_combined_capabilities.py`: 8 tests (red seen: no `max_subcalls`, no snapshot, no `refs_of`).

`tests/test_tool_allowed_values.py`: 3 tests (red seen: no `allowed_values`, the probes offered on every target).

`tests/test_eval4_health_wording.py`: 4 tests (red seen 3/4 with the old labels).

`tests/test_t0033_rotate_token_script.py`: 4 tests (red seen 3/4: hard-coded paths, mode 0400 after a rollback,
"recreated" after a failed compose); the mode check runs where the filesystem has POSIX modes (CI).

`tests/test_t0019_batch3a_inspection.py`: 33 tests (red seen: no `argus.policy.inspection`), green. `tests/test_sc07_network.py`'s render test now copies `policy.yaml` too (the renderer has two inputs).
Full suite green on the laptop (pytest exit 0).

No new tests (a model evaluation). Model evaluation on vm-095, 55 cases × 5: 0.96 (core 0.99), abstention 0.98, hard
0 0 0 (EVAL-2 E.4: 0.93, 0.95, 0.96).

**2026-10-12, `main` `2fa4d01` (#91-#94), full suite on a laptop (roll-up, `conantkd`):** green, 20 skipped (Postgres
and environment). New since EVAL-2: `tests/test_op012_incident_budget.py` 3 (red seen: 16 `container.status` reads
under LangGraph, the policy allows 8), `tests/test_eval3_sigkill.py` 3 (red seen 2/3: the baseline answered
`diagnosed`), `tests/test_t0033_token_rotation.py` 4 (red seen: no reload in `Dispatcher`). The MCP benchmark
(`test_mcp_child.py`, p95 overhead < 100 ms) can fail on a loaded laptop; alone it passes.

**T-0033 step 2, 2026-10-12:** No new tests (a VM proof). Main's CI green on `244453b`; T-0033's 4 tests and OP-012's 3
run in CI.

**T-0019 batch 2, 2026-10-12 (`task/T-0019-batch2-host-probe`):** `tests/test_t0019_host_probe_batch2.py` 36 tests
(red seen for each step: probe verbs, capabilities, policy, memory bounds, walk share, case answers, prompt rule,
invalid-decision reasons); full suite 555 passed, 20 skipped. Model evaluation on vm-095 (EVAL-2 + batch 2, 5 trials):
0.92 (core 0.95), abstention 1.00, disk 1.00, hard 0 0 0.

**EVAL-2, 2026-10-12 (`task/EVAL-2-model-trials`):** `tests/test_eval2_fixes.py` 7 new (red seen: no round for a
stopped writer, no prompt rule, two contradictory fixtures, a store left behind); full suite green. Model evaluation on
vm-095, 55 cases × 5: 0.93 (core 0.95), abstention 0.96, hard 0 0 0; baseline 52/55.

**EVAL-1, 2026-10-11:** red seen (the baseline escalated the writer cases; after the review, it named the writer
with empty logs); `tests/test_evaluation.py`, `test_e2e5_confirm_writer.py`, `test_t0024_sc05_disk.py` green (108);
baseline evaluation 55 cases, 52 pass, `disk_pressure` 7/8 (the declared miss), hard 0 0 0.

**E2E-5, 2026-10-11 (`task/E2E-5-confirm-writer`):** 7 tests in `tests/test_e2e5_confirm_writer.py` (red seen: no
strategy; the skeleton test fails with `model_loop`, the filler's logs never read); SC-05 class test updated to the new
strategy; core, graph and evaluation tests green.

**LANES-2 follow-up, 2026-10-11:** `test_rollup_orders_same_day_entries_by_when_they_reached_the_branch` (red seen:
file-name order); the roll-up tests pass; replayed on `main` before #73: the hand-set order of #73.

**E2E-3, 2026-10-11 (`task/E2E-3-container-mounts`):** 5 tests in `tests/test_e2e3_container_mounts.py` (red seen
4/5: no `host_mounts` from the gateway or in `container.status`); gateway, SC-05/06/07/08 and evaluation tests green;
baseline evaluation 45/47, hard 0 0 0. Review (`conantkd`): + 1 test, the tool's description and "when" name the
host mounts (red seen); full suite green on the laptop.

**E2E-2 step 2 (2026-10-10, `conantkd`):** both VMs on `main` `0f076f2`, vm-095's agent rebuilt. Runner batch: SC-07
5/5, SC-05 4/5 (the miss read and explained), 0 errors, NO INTERFERENCE after every run.

**T-0031 (phase 8), 2026-10-10 (`task/T-0031-write-gate-standing`):** 25 write-gate tests in CI
(`tests/test_write_gate_standing.py`, `tests/test_write_gate_check.py`); the standing cases pin existing behaviour,
red seen by three mutations; the check's cases red before the module and script existed (and the host-only
fail-open on a failed `docker ps`). `WRITE GATE CLOSED` on vm-095 and, host-only, on vm-166.

**E2E-2 follow-up (2026-10-10, `task/E2E-2-disk-partial`):** 4 more tests in `tests/test_e2e2_evidence_gaps.py` (12
in all), red seen 2/4; the offline suite passes.

**E2E-2, 2026-10-10 (`task/E2E-2-evidence-gaps`):** 8 tests in `tests/test_e2e2_evidence_gaps.py` (red seen 6/8:
no `networks` on `TargetInfo`, `host.disk_usage` read `/` by default); SC-05, SC-07, core and evaluation tests green;
baseline evaluation 45/47 (the two known baseline misses), hard 0 0 0.

**E2E-1 (phase 12), 2026-10-10:** runner batches on vm-166, both VMs on `main`: SC-04 5/5, SC-06 5/5, SC-07 6/10,
SC-05 6/10 (two evidence gaps, E2E-2); 0 errors, NO INTERFERENCE after every run.

**LANES-2, 2026-10-10 (`task/LANES-2-journal-rollup`):** 7 new tests in `tests/brain/test_brain.py` (red seen: no
`rollup`, no lint rule; the CI case reproduced with `GITHUB_HEAD_REF` set), all brain tests pass.

**T-0032 (phase 13), 2026-10-10 (`task/T-0032-prometheus-down`):** 3 tests in
`tests/test_t0032_prometheus_down.py` (both runners and the real adapter; red seen by removing the
`MetricsUnavailable` handling in each runner). On vm-095: UNDIAGNOSABLE for vm-095, HEALTHY for vm-166.

**T-0030 (phase 13), 2026-10-10 (`task/T-0030-pg-restart`):** 3 tests in `tests/test_t0030_pg_restart.py` (red seen: a
database error from `recover()` or the claim ended the worker's loop). Full suite on the laptop: green.

**T-0029 (SC-08), 2026-10-10 (`task/T-0029-sc08-nginx`):** 12 tests in `tests/test_t0029_sc08_nginx.py` (red seen
12/12: no probe, signal, class, alert, lab or inventory entries); 6 evaluation cases `tests/eval/cases/nginx-*.yaml`
(baseline 6/6, hard 0 0 0). Full suite on the laptop: green.

**OP-008, 2026-10-09 (`task/OP-008-backup-retention`):** three new retention/verification tests and the changed
snapshot-consistency test failed before implementation, then passed. `tests/test_db_backup.py`: 15 passed locally,
including two real Docker/PostgreSQL cases; one writes to the live throwaway database between snapshot export and
`pg_dump`, then restores successfully. The Windows full suite with Docker had one unrelated OD-3 timing-benchmark
failure (448.6 ms p95 overhead against 100 ms); every other executed test passed, with seven Linux/Postgres skips.
Linux CI and the VM dry run are pending. Review notes of PR #51 (2026-10-10): three new prune tests red seen (no
checksum gate, no `newest verified` line, leftovers not listed), then green: 16 passed, 2 real-Docker skipped. VM dry run done (OP-008 step 02).

**T-0027, 2026-10-09 (`task/T-0027-blind-spot`, the stack and `main` up to #53 merged in):** 10 tests in
`tests/test_t0027_blind_spot.py` (red seen: no class; a check of a host with node-exporter down ended `no_incident`),
5 evaluation cases `tests/eval/cases/blind-*.yaml` (baseline: 5/5, 0 model calls, hard 0 0 0), and
`test_every_registered_class_has_its_cases_or_is_listed_as_awaiting_them` (red seen without the cases;
`disk_pressure` listed as awaiting). Full suite on the laptop: green (Postgres tests skipped; the stack branches below
it passed with a throwaway Postgres). Stage 7: `inc_263f471e33e3` on vm-166, escalated as `monitoring_blind_spot`,
resolved after the exporter came back; NO INTERFERENCE.

**T-0026, 2026-10-09 (`task/T-0026-alert-resolution`):** 16 new tests in `tests/test_t0026_alert_resolution.py`
(red seen 14/16: a `resolved` notification was `ignored`; `active_alerts`, `resolve_absent` and `resolved_at` were
missing; the silenced-alert and the received-before guards were green from the start) and
`tests/test_postgres.py::test_alert_occurrence_resolution` (migration 005: forward only, column grant, no DELETE), plus
five `argus db check` lines. Full suite on the laptop with a throwaway `postgres:16-alpine`: **301 passed**, 3 skipped;
the OD-3 timing benchmark failed once in the full run and passed alone (the known Windows timing flake).
Stage 7 (2026-10-09, both VMs on `ea01c68`): `argus db check` 20/20; SC-03 `inc_ed6a85ccd28f`, both occurrences
resolved one pass after the alerts cleared, the incident unchanged; NO INTERFERENCE.

**OP-005, 2026-10-09 (`task/OP-005-young-restarts`):** three new unit tests were red against the old exporter/signal,
then passed. Five PromQL synthetic-series cases passed with Prometheus 3.5.0 `promtool test rules` (young, old with
scrape gap, old with continuous history, recreated same name, and missing creation metric). The full local Windows
worktree suite finished with 6 unrelated failures: 5 `tests/test_deploy.py` fixtures see their temporary `app` as an
existing Git clone; the OD-3 timing benchmark measured 155 ms p95 overhead against its 100 ms budget. Review of PR #41
(`main` merged in, + 1 test: the restart alert counts like the signal, red seen): 228 passed, 9 skipped on the laptop
(237); the only failure is the same timing-flaky benchmark (passes alone; green in CI). The VM checks follow.

**OP-004, 2026-10-09 (`task/OP-004-checkpoint-cleanup`):** six new tests pass against a throwaway PostgreSQL 16 and
the manual/timer wrapper. Three PostgreSQL cases were red before the command existed. VM dry run and CI are pending. 2026-10-10: the wrapper test now requires the container to run as the secret's
owner (red with `--user 0:0`, green after); VM dry run done (OP-004 step 02).

| Stage | Result | Where / when |
|---|---|---|
| 3. Offline suite | **286 passed**, 3 skipped with a throwaway Postgres (`ARGUS_TEST_PG_OWNER_DSN`, as in CI) on `task/OP-011-correlation` after ACR-0004 (2026-10-09): + 4 tests in `test_op011_correlation.py` (an alert that started before the incident closed joins it, not reopened; an escalated incident too; a recurrence, another class or an old close → a new incident; SC-03 with the alerts one pass apart → one incident; red seen 3/4, the negative case was already green), `latest_concluded_incident` in `test_postgres.py`. Before: **275 passed**, 10 skipped on the laptop on `task/OP-011-correlation` (OP-011, 2026-10-09): + 9 `test_op011_correlation.py` (two alerts on one target and class → one incident, `attached`, evidence version 2; still `duplicate` after the incident closes; audited; another class, stale metrics, no class, another dependency, closed or outside the window → a new incident; one SC-03 pull pass → `started` 1, `attached` 1; the webhook the same; red seen 9/9) and + 1 `test_postgres.py::test_alert_occurrences` (migration 004; red seen `relation "alert_occurrence" does not exist`, then the 7 Postgres tests green against a throwaway `postgres:16-alpine`). The OD-3 timing benchmark failed once on Windows and passed on rerun. Before: **273 passed**, 2 skipped (275 with the Postgres tests, as in CI, after #41; on the laptop 265 passed, 9 skipped) on `task/T-0024-sc05-disk` after merging OP-010 (with T-0022 and `main`): + 15 `test_t0024_sc05_disk.py` (disk signals per declared mount, `$mounts` from the inventory and validated, `disk_pressure` with time to full, host scope, RB-005 metadata, the alert on every real filesystem, `rslave`, the host-probe refuses an unmounted mount, the bounded filler, the mount script; red seen 15/15). Before: **254 passed**, 2 skipped (256 with the Postgres tests, as in CI) on `task/OP-010-reserved-slot` after merging T-0022 (with `main`): + 6 `test_op010_reserved_slot.py` (the lab reserves a slot for the monitoring role only, SC-04 sized for 100 %, the probe counts the reserved slot and reports `monitor_slot_reserved`, the query reads only `pg_roles`, the health text warns without it; red seen 6/6). Before: **252 passed**, 2 skipped (254 with the Postgres tests, as in CI, after #41; on the laptop 244 passed, 9 skipped, plus the timing-flaky `test_benchmark_compares_direct_and_mcp_on_the_same_read` under load) on `task/T-0022-alerting` after merging `main` (#38, #39, #40): + 17 `test_t0022_alerting.py` (alert intake shared by webhook and pull, identity `fingerprint + startsAt`, host-level alerts, refused targets audited, the Alertmanager source keeps only its host, reconciliation survives a host that is down, the pull config, inventory `alertmanager`, the monitoring stack, Alertmanager sends nothing, Prometheus alerting and scrape jobs, the tunnel forward, the new signals; red seen 16/17). Before: **231 passed**, 2 skipped (233 with the Postgres tests, as in CI; on the laptop 224 passed, 9 skipped) on `task/T-0020-sc04-pg-connections` after merging `main` (#39, #40): + 13 `test_sc04_pg_connections.py` (T-0020, including the review of PR #38: a query that fails after connecting is `argus_db_up 0`, red seen). Before: **218 passed**, 2 skipped (220 with the Postgres tests, as in CI; on the laptop 211 passed, 9 skipped) on `task/T-0023-e2e-runner` after merging `main` (#39: the T-0021 review fixes). Before: **217 passed**, 2 skipped (Postgres tests in CI) on `task/T-0023-e2e-runner` after the review of PR #40: + 6 `test_e2e_runner.py` (red seen 6/6: a view without evidence/audit passed; a reset ran with nothing started). Before: **211 passed**, 2 skipped (Postgres tests included) on `task/T-0023-e2e-runner`: + 27 `test_e2e_runner.py` (T-0023: step 1, red seen: the runner did not exist; then 5 for a dropped connection, red seen 4). Before: **183 passed**, 2 skipped (185, Postgres tests included) on `task/T-0021-tool-isolation` `a5f330a` (T-0014 merged in): + 8 `test_mcp_tools.py`, 6 `test_mcp_child.py`, 6 `test_tool_isolation.py` (+1 needs Docker), 1 `test_compose_split.py` (T-0021 steps 1-5, red seen in each). Before: **162 passed**, 1 skipped (163, Postgres tests included) on `task/T-0014-worker-scheduler` `169ca07`: + `test_a_running_worker_takes_back_a_claim_that_expires_later` (red seen: `recover_every_s` missing). Before: **161 passed**, 1 skipped (162, Postgres tests included with a throwaway `postgres:16-alpine`) on `task/T-0014-worker-scheduler` after merging `main`: + 8 `test_worker_lease.py`, 7 `test_worker_loop.py`, 16 `test_scheduler.py`, 4 `test_compose_split.py`, 1 `test_deploy.py` (T-0014 steps 1-4, red seen in each step). Before: **119 passed**, 6 skipped (125) on `task/T-0019-db-probe`: + 15 `test_db_probe.py` (red seen 15/15). Before: **104 passed**, 6 skipped (110) on `task/op-007-restarting-probe-fix`: + `test_exporter_keeps_the_probe_of_an_owner_in_a_restart_loop` (OP-007, red seen: `owner_active` missing). Before: **103 passed**, 6 skipped (109; the 5 Postgres tests and the real-Docker backup test): 89 before + 7 `test_sc07_network.py` + 7 `test_knowledge_runbook.py` (T-0018: `query_runbook` reads the library in-worker, refuses unknown/malformed ids, is limited by policy, and the context names the branch runbooks) | laptop, 2026-10-07 (OP-007 / T-0018) |
| 3. Frontend unit tests | **20 passed** (Vitest: `parseRunbook` 11, `routes` 4, `mockAuthAdapter` 5) and `vite build` OK Base branch: **39 passed** (Vitest: `httpAuthAdapter` 4, `httpArgusAdapter` 6, `session` 3, `index` 2, `fileRunbooksAdapter` 1, `parseRunbook` 11, `routes` 6, `mockAuthAdapter` 6) and `vite build` OK (348 modules) | CI job `frontend` (T-0016, PR #24) |
| 4. Postgres integration | **95 passed, 0 skipped** (full suite with `ARGUS_TEST_PG_OWNER_DSN` against a throwaway `postgres:16-alpine` and `ARGUS_TEST_DOCKER=1`: the 5 Postgres tests and the real-Docker backup test included) on `task/T-0017-pg-backup-drill` after merging `main`; container removed afterwards | laptop, 2026-10-06 (T-0017, PR #25) |
| 5. CI | first run on `9ccc61d`: audit, lint, gitleaks ✓; tests ✗ (runbook library not available in CI) → fixed in PR #1 (pinned runbooks checkout with a read-only deploy key) | GitHub, 2026-10-02 |
| 7. Deployment validation | OP-011 on both VMs (2026-10-09): migration 004 applied after `BACKUP OK`; SC-03 on vm-166 → **one** incident `inc_8a4cf92444ae` DIAGNOSED, occurrences `DependencyProbeFailed started` + `ContainerUnhealthy attached` (pulled after the incident closed, started before: ACR-0004), then `duplicate` 2; NO INTERFERENCE. Before (step 02, open incidents only): the same run gave two incidents. Before: T-0024 on both VMs (2026-10-09): SC-05 lab fs to 92.6 %, `HostDiskPressure` pulled, `inc_4d78232433a1` DIAGNOSED (`disk_pressure`, root cause the filler); NO INTERFERENCE. Before: OP-010 (2026-10-09): SC-04 at 100 % on vm-166, `argus_db_up=1` throughout, the pulled `DbConnectionsExhausted` opened `inc_03e42714762f` DIAGNOSED (root cause the leaker); NO INTERFERENCE. Before: T-0022 on both VMs (2026-10-09): monitoring on vm-095, alerts pulled from both Alertmanagers every 60 s; SC-03 alert → 2 incidents DIAGNOSED (OP-011), never twice per alert; SC-02 on vm-095 alert → DIAGNOSED; TOOLS ISOLATION OK; NO INTERFERENCE. Before: OP-005 on both VMs (2026-10-09): young SC-01 container at counter 3 -> `restarts_10m` 3 (old expression 1), `ContainerRestartLoop` firing, `inc_312b18f2d8a8` DIAGNOSED; exporter restart with an old container -> 0, no alert; TOOLS ISOLATION OK on vm-095; NO INTERFERENCE. Before: T-0023 step 2 (2026-10-09, both VMs): the scenario runner, SC-01 **5/5** and SC-03 **5/5** PASS, H-1, H-2, SC-09, SC-11 1/1, NO INTERFERENCE after every run. Before: T-0021 step 5e on vm-095 (2026-10-09): the review fixes `6f45218` deployed, the launcher with `cd /` and `python -I`, `isolation_check` with the planted-package probe **TOOLS ISOLATION OK**, NO INTERFERENCE. Before: T-0021 on vm-095 (2026-10-08): worker in `mcp` mode, tokens readable only by `argus-tools`, `isolation_check` **TOOLS ISOLATION OK**, SC-02 DIAGNOSED through the tools process, **OD-3 OK** (p95 overhead 45.7 ms `container.status`, 43.1 ms `container.logs`), NO INTERFERENCE. T-0020 on vm-166 (2026-10-07): **SC-04 DIAGNOSED** (`inc_075fb0006098`, root cause `argus-lab-leaker`, RB-004), gate 94 % for 5 min and alert firing, LAB BASELINE OK, NO INTERFERENCE after removing the leaker's two anonymous volumes. T-0014 on vm-095 (2026-10-08): api / worker / scheduler running; H-1 HEALTHY through the worker; worker killed mid-run (SC-02), run **resumed from its checkpoint** (`incident.resumed`) and DIAGNOSED; schedule submitted once per slot, not resubmitted after a scheduler restart, `schedule.coalesced` while busy; NO INTERFERENCE. T-0019 batch 1 on both VMs (2026-10-07): `phase3_check` **33/33** (5 new db-probe checks), `inspect_database_health` ok through the agent's code path, NO INTERFERENCE. T-0018 on both VMs (2026-10-07): H-1 on vm-166 `HEALTHY`; **SC-07 DIAGNOSED** (`inc_fb92d115abb2`), NO INTERFERENCE. T-0017 on vm-095 (2026-10-06): `BACKUP OK`, `VERIFY OK: 11 tables, 4603 rows match`, NO INTERFERENCE. T-0013 on vm-095 (2026-10-04): `argus db check` 15/15; H-1, SC-09, SC-01 on LangGraph, each checkpointed in Postgres; NO INTERFERENCE on both VMs. Earlier: `phase3_check` 28/28 (2026-10-01) | VMs |

## Currently red

Nothing (`main-guard` green again since PR #9).

## Notable tests

- `test_deployable_files_have_unix_line_endings` — blocks CRLF in files that go to Linux.
- `test_runbook_library_lives_in_the_repository` — D-002: 21 runbooks + index + conventions load from `argus/runbooks/`, the
  default location; no `/opt/argus-runbooks` mount, no `runbooks.lock`. Red seen: the default still pointed to the old
  sibling folder.
- OP-006 (`tests/test_graph_runner.py`): the recursion limit is 100 with the default budgets; a 20-step x 5-read
  budget ends `escalated` (budget exhausted), not with `GraphRecursionError`. Red seen: `GraphRecursionError:
  Recursion limit of 100 reached`.
- Lab baseline (`tests/test_deploy.py`, 3 tests): `deploy.sh status` prints `LAB BASELINE OK` only when every
  `argus-lab-*` container runs and none is unhealthy; it names the stopped/unhealthy ones; without docker it says
  so and never claims OK. Red seen: none of the three found any lab line.
- `test_provider_error_escalates_at_once`, the freshness-gate and identity tests — see `tests/test_core.py`.
- `tests/brain/test_brain.py` — lease claim/refusal/race/expiry/renew/handoff/release, audit (planted secrets,
  addresses, files), lint, archive-step, checkpoint. Red seen: every lease test failed first (a Windows text-mode
  pipe turned LF into CRLF in the `git mktree` input) → fixed by feeding git bytes.
- `tests/test_postgres.py` — contract, forward-only states, SQLite import, a full run on Postgres (needs
  `ARGUS_TEST_PG_OWNER_DSN`).
- The 4 `verify-main` / `guard-push` tests (PR #1) were written **after** the code — no red seen; recorded honestly.
- `tests/test_deploy.py` — `ops/deploy.sh` against a throwaway bare repository: init keeps the old folder, session check,
  newer commit + rebuild hints, local modifications refused, unknown ref refused, status. Red seen: all 6 failed before
  the script existed. Runs with Git for Windows' bash locally and bash in CI.
- `tests/test_db_backup.py` (T-0017) — `ops/db-backup.sh` with a fake `docker`: session check; dump + sha256 +
  fingerprint, root-only; a database that changes during the dump is refused; `verify` restores into a
  network-less tmpfs `argus-lab-pgrestore`, never touches the live database and always removes the container;
  mismatch and tampered dump refused; `verify latest`. Plus one real-Docker test (`ARGUS_TEST_DOCKER=1`). Red seen:
  6 failed against a stub (`assert 1 == 0`); `verify latest` failed with `VERIFY STOP: no such dump: latest`.
- `tests/test_graph_runner.py` (T-0013) — LangGraph runner = plain runner in 5 scenarios; resume after a crash without
  repeating completed reads; the `ARGUS_RUNNER` switch. Red seen: the runner was still `SkeletonRunner`.
- `test_graph_runner_resumes_from_postgres_after_a_restart` (T-0013) — a new app resumes a crashed run from the Postgres
  checkpoint without repeating reads; `test_checkpoint_migration_covers_every_library_migration` guards library upgrades.
- `test_resume_inside_act_does_not_repeat_completed_reads` / `..._inside_evidence_pack_...` (T-0013 review) — a crash
  between two reads of one step resumes with only the missing read. Red seen: completed reads ran twice.
- `tests/test_ui_access.py` (T-0015, ACR-0001) — a `scope=read` token is refused (403, audited) on every non-GET
  route, found by walking the registered routes, and accepted on every `/api/` GET; old tokens count as full; `/me`;
  CORS only for `ARGUS_UI_ORIGINS`. Red seen per step.
- `tests/test_ui_contract.py` (T-0015) — the API's UI routes match `contracts/ui-api.json`; a scripted SC-03-like
  run keeps the shapes of `contracts/samples/*.json`. Red seen: files missing. Regenerate deliberately with
  `ARGUS_UPDATE_UI_CONTRACT=1`.
