# Logbook

Append-only, **oldest first, newest at the bottom**. One entry per significant decision, result, deployment or
infrastructure change. Never secrets, addresses or personal names. The past before this repository is condensed in
[`history.md`](history.md).

```text
## YYYY-MM-DD — Title (T-xxxx)
Type: architecture | implementation | capability | infrastructure | deployment | testing | incident | decision
Who: <github-handle> (+ agent)
Context:      why this came up (1–3 lines)
Decision:     what was decided or changed
Consequences: what is now true; what it affects
References:   files, PR #, commits, ACR
Learned:      (optional) the lesson, if any
```

---

## 2026-10-02 — Shared repository and Brain created (B1–B4)

Type: decision
Who: juanbetancurm (+ agent)
Context: three developers with different AI agents must share one verified source of truth.
Decision: `argus_production` holds the code (from the last verified implementation), the sanitized Brain
(`brain/`), and the rules for sessions, reviews, tests and commands. Private addresses moved to VM-local
`hosts.env`; runbook pin in `config/runbooks.lock`; architecture imported as v1.8.0.
Consequences: next are B5 (tools, CI) and B6 (audit, first push, branch protection, deploy keys); then the pilot T-0013.
References: `brain/CURRENT_STATE.md` §6, `brain/journal/history.md`.

## 2026-10-02 — First push; no branch protection on the free plan → soft review rules (bootstrap PR #1)

Type: decision
Who: juanbetancurm (+ agent)
Context: `9ccc61d` pushed to `main`. The first CI run passed audit, lint and gitleaks, but the tests failed because the
runbook library (private repo) is not on the CI machine. Branch protection was refused with HTTP 403: the organization
is on GitHub's free plan, which does not protect private repositories.
Decision (owner):
- **Stay on the free plan with soft rules.** The pre-push hook refuses pushes to `main`. `brain.py verify-main`
  checks that every commit on `main` came from a PR approved on its last push by a non-author; it runs as CI job
  `main-guard` and as a warning in `brain.py start`. Exceptions are recorded in `brain/policies/main-exceptions.txt`.
- **CI gets the runbooks** at the commit in `config/runbooks.lock`, through a read-only deploy key stored as the
  secret `RUNBOOKS_DEPLOY_KEY`. The tests read `ARGUS_RUNBOOKS_DIR`.
- **PR #1 (this change) is merged by its author** as the one recorded bootstrap exception.
Consequences: GitHub does not stop an owner from merging unreviewed work; the tools make it visible. Upgrading to
GitHub Team later would allow real protection (re-run legacy step B6.5).
Learned: check the plan's limits before designing around a platform feature.

## 2026-10-02 — D-002 done: the runbook library moves into the repository

Type: decision
Who: juanbetancurm (+ agent)
Context: CI still could not read the runbooks: deploy keys are disabled for the whole organization ("Deploy keys are
disabled for this repository", HTTP 422), so the read-only key planned above was never accepted. Architecture 2.4 puts
the library in the code repository anyway.
Decision (owner):
- D-002 is done now, on the bootstrap PR #1. The 21 runbooks, `RUNBOOK-CONVENTIONS.md` and `RUNBOOK-INDEX.md` are
  imported from `agenticteam03/runbooks` @ `056b36e` into `argus/runbooks/`. Line endings were normalized to LF;
  nothing else changed. Provenance is in its README.
- This replaces the CI deploy key above:
  - `config/runbooks.lock` is retired;
  - the compose mount and `ARGUS_RUNBOOKS_COMMIT` are removed;
  - the image ships the library;
  - the runbook steps are removed from CI;
  - the unused secret `RUNBOOKS_DEPLOY_KEY` is deleted.
Consequences:
- The VM agent keeps reading `/opt/argus-runbooks/056b36e` (same content) until its next redeploy.
- Recall section hashes change because of LF, and the library version now comes from `RUNBOOK-INDEX.md`.
- The VMs pulling this private repository still needs deploy keys (org setting) or another method; that decision
  comes with the deploy step.
Learned: an empty list of deploy keys does not prove that deploy keys are allowed.

## 2026-10-02 — PR #1 merged; deploy method: org deploy keys + ops/deploy.sh (Task B6d)

Type: decision
Who: juanbetancurm (+ agent)
`OBSERVED`:
- PR #1 merged: `main` = `bf24fac`;
- CI on `main` is green: `test` and `main-guard`;
- `verify-main` is clean (PR #1 is the recorded exception).
Decision (owner):
- The VMs pull this repository with one read-only deploy key per VM.
- The owner allows deploy keys in the organization's settings.
New: `ops/deploy.sh` (status, init, deploy):
- it refuses when the session marker is not yours, when the VM checkout has local modifications, or when the ref is
  unknown;
- it checks out the exact commit and writes `DEPLOYED`;
- it prints the rebuild hints and never restarts anything.
Tests: `tests/test_deploy.py`, 6 tests (red seen); 53 pass in total.
Commands: Task B6d in `execution/current/code.bash`. Part 1 covers the keys, the GitHub host key pin and the access
test. Part 2 (`deploy.sh init`) runs after a teammate reviews and merges this PR.

## 2026-10-03 — Task B6d part 1: read-only deploy keys on both VMs

Type: infrastructure
Who: juanbetancurm (+ agent)
`OBSERVED`:
- Each VM has its key in `/opt/argus-v18/secrets/deploy/` (0700), with GitHub's ed25519 host key pinned
  (`SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU`).
- Both keys are registered on GitHub as read-only.
- `git ls-remote` works from vm-095 and from vm-166.
- NO INTERFERENCE on both VMs.
- PR #2 is open with green CI and a review requested.
Problems on the way:
- The VM session marker depended on pasting a separate line, and that step was missed twice. Now the laptop block
  B6d.M renews the lease and writes the marker on both VMs over SSH, reading the session id from the lease.
- The vm-166 step said "paste the B6d.2 block again" and was misread; it is now a full block.
- B6d.4 sent an empty key for a VM without a key file, and its message blamed the org setting. It now skips
  registered keys, refuses to send a missing key, and reports the real cause.
Learned: a code.bash step must never depend on text the developer has to carry over by hand.

## 2026-10-04 — T-0013 verified on vm-095: the skeleton runs on LangGraph with Postgres checkpoints (T-0013)

Type: deployment
Who: juanbetancurm (+ agent); PRs #2 and #4 merged by conantkd, PR #3 by juanbetancurm
Context: Phase 9 first slice; the pilot of the shared-Brain protocol.
Decision / result (`OBSERVED`):
- `/opt/argus-v18/app` is a git checkout on both VMs (`deploy.sh init`). vm-095 runs this branch; vm-166 runs `main`.
- Migration 002 is applied; `argus db check` passes 15/15.
- The agent was rebuilt with `ARGUS_RUNNER=langgraph`, and the runbooks now ship inside the image.
- H-1, SC-09 and SC-01 give the same outcomes as before, and each run is checkpointed in Postgres.
- NO INTERFERENCE on both VMs.
- Compose now defaults to `langgraph`.
Consequences:
- Phase 9 is at 50 %.
- An interrupted run can resume from its checkpoint, but nothing triggers that automatically yet; that comes with the
  worker (T-0014).
- After the merge, vm-095 must be put back on `main` with `deploy.sh main`.
References: `tasks/completed/T-0013-langgraph-skeleton.md`, `execution/history/T-0013/step-05/evidence.md`.
Learned: a readiness gate must wait on the data the agent reads (Prometheus), not on its source (Docker).

## 2026-10-05 — T-0013 review by conantkd: step 5 re-verified, login test done, one real gap fixed (T-0013)

Type: testing
Who: conantkd (review), juanbetancurm (+ agent)
Context: the closing commit of T-0013 had not been pushed. The reviewer saw the branch at the step-5 commands, ran
step 5 again on the VMs and recorded it on `task/T-0013-step5-verify`, now merged into the T-0013 branch.
Decision / result (`OBSERVED`):
- Step 5 re-verified with the same outcomes.
- The per-user login test (legacy 12b.2) is done: all three users get HEALTHY.
- Review findings:
  - the `ARGUS_RUNNER` default and the missing Brain items were already in the unpushed closing commit;
  - **real gap fixed:** a crash in the middle of `act` repeated the reads already completed in that step. Now one read
    runs per graph step, in `act` and in `evidence_pack`.
  - Two proposals go to separate PRs for the team to approve: OP-004, a retention cleanup for checkpoints; OP-005, a
    restart signal that does not undercount.
Consequences: criterion 1 ("without repeating completed tool calls") now holds at read granularity; 63 tests pass.
Learned: push the closing commit before handing over; a reviewer can only review what is on GitHub.

## 2026-10-05 — T-0013 final review: approved and merged; recursion limit follow-up (T-0013)

Type: decision
Who: conantkd (review, + agent)
Context: final review of PR #6 at `5a1b765` (the one-read-per-graph-step fix).
Decision / result (`OBSERVED`): 63 passed / 5 skipped locally (Postgres tests green in CI); red seen reproduced for
both new tests on the previous `graph_runner.py`; Brain consistent; no secrets. Approved and merged as is.
Consequences:
- One follow-up, recorded as OP-006: the fixed LangGraph `recursion_limit` (100) can be too small for larger step
  budgets now that each read is a graph step. Agreed fix: `max(100, formula)`.
- The fix itself has not run on the VMs yet (vm-095 runs `c87d76c`): repeat H-1 / SC-09 / SC-01 after `deploy.sh main`.
References: `tasks/completed/T-0013-langgraph-skeleton.md` (finding 6), `OPEN_PROBLEMS.md` OP-006.
Learned: when a change multiplies graph steps, check the framework's own step limit too.

## 2026-10-05 — OP-004 accepted: checkpoint retention, with review conditions (OP-004)

Type: decision
Who: conantkd (review of PR #7 by juanbetancurm)
Decision / result: the checkpoint retention proposal is accepted with three conditions, recorded in
`OPEN_PROBLEMS.md` OP-004: an Argus command run with the owner DSN (not a standalone script), dry-run first, and
"ended" defined as `body->>'closed_at'`.
Consequences: a later task implements it; until then checkpoints keep growing (small at today's volume).
References: `OPEN_PROBLEMS.md` OP-004, PR #7.

## 2026-10-05 — Temporary fast-track for self-merged pull requests; PR #4 recorded as an exception

Type: decision
Who: juanbetancurm (+ agent)
Context: the course presentation came earlier than planned; waiting for a teammate review on every pull request
would block the work. `main-guard` was red because PR #4 had no recorded approval.
Decision: PR #4 is added to `policies/main-exceptions.txt` (documentation only). Until 2026-10-12, `juanbetancurm`
may merge their own pull requests under the conditions in `agents/REVIEW_PROTOCOL.md` ("Temporary fast-track"):
still a PR from a task branch, CI `test` green, agent review report posted, the PR lists itself in
`main-exceptions.txt`, and no change to a safety principle, `SECURITY.md`, an ACR or the enforcement itself.
Consequences: `brain.py`, CI and the hooks are unchanged; every self-merge is listed and reviewed by a teammate
after the merge. Teammates may object in any PR, which ends the fast-track.
References: `agents/REVIEW_PROTOCOL.md`, `policies/main-exceptions.txt`.

## 2026-10-05 — SC-03 shown in the class demo on the LangGraph runner (DEMO-SC03)

Type: testing
Who: juanbetancurm (+ agent)
Context: a class demo: stop the lab Redis, the api turns unhealthy, Argus must blame the cache, not the api.
Decision / result: reported successful by the developer (root cause = `argus-lab-cache`). The output was not
archived, so `CURRENT_STATE.md` lists it as reported, not verified. Demo commands archived in
`execution/history/demo-SC03/step-01/`.
Learned: a block that releases the lease must never sit in a file that is run twice (dry run, then class); and
helpers defined in one VM shell fail confusingly when a block is pasted on the other VM: label blocks with the
VM prompt name and avoid shell helpers in demo scripts.
References: `execution/history/demo-SC03/step-01/evidence.md`.

## 2026-10-05 — OP-006 fixed: the LangGraph recursion limit follows the budgets (OP-006)

Type: implementation
Who: juanbetancurm (+ agent)
Context: `recursion_limit` was fixed at 100; a class with a larger step budget would stop with `GraphRecursionError`
although Argus was still inside its own budget (found in the T-0013 review).
Decision / result: `GraphRunner.recursion_limit = max(100, max_steps_cap × (1 + max(max_reads_per_step, largest
plan)) + 4 + 10)`, as agreed in the review. Unchanged (100) with today's configuration. Tests: 65 passed, 5
skipped (Postgres, in CI); red seen. No VM change needed (same behaviour with the deployed budgets).
References: `OPEN_PROBLEMS.md` OP-006, `tests/test_graph_runner.py`.
## 2026-10-05 — Frontend planned: T-0015 (read access, API side) and T-0016 (the frontend, test-driven)

Type: decision
Who: juanbetancurm (+ agent)
Context: `juanes6554` will build a web frontend in his own framework; operators choose console or browser.
Decision: the frontend lives in `frontend/` of this repository and only reads. Argus enforces it: a login with
`scope=read` gives a token that every non-`GET` route refuses (T-0015). `GET /api/v1/me` lists the actions a token
may use, and the frontend shows only those, so later levels (start an investigation, a container map, approving
Argus's proposals) add server actions instead of rewriting the frontend. A versioned UI contract
(`contracts/ui-api.json` + sample responses) is tested on the API side. The frontend is test-driven: `juanes6554`
writes guidelines, the agent writes the tests first (Playwright acceptance with a network read-only guard, contract,
unit), a CI job `frontend` enforces them. It starts with ACR-0001 (OD-10).
References: `tasks/current/T-0015-ui-read-access.md`, `tasks/current/T-0016-frontend.md`.

## 2026-10-05 — Unintended practice-lab files removed from main

Type: incident
Who: juanbetancurm (+ agent)
Context: the OP-006 commit (`e0fc766`, PR #11) also carried 8 unrelated, untracked files
(`argus/runbooks/practice/RB-002/`) because the agent staged whole folders (`git add -A argus …`).
Decision / result: removed by this pull request. No secrets in them (loopback addresses only), so the history is
not rewritten (no force-push of `main`). They were also inside the agent image built from that commit; nothing
was redeployed from it.
Learned: stage explicit file paths, never whole folders; check `git status` for untracked files before a commit.
References: PR #11, this pull request.

## 2026-10-05 — Session end (juanbetancurm): handoff to conantkd

Type: decision
Who: juanbetancurm (+ agent)
Context: end of a long session: class demo, fast-track rule, OP-006, frontend plan, a cleanup.
Decision / result: merged today (fast-track): #9 rule, #10 demo record, #11 OP-006, #12 frontend plan (T-0015,
T-0016), #13 removal of files committed by mistake. Open: PR #8 (OP-005, waiting for `conantkd`). Found at the
end: vm-095 still runs `c87d76c`, older than `main` (no T-0013 review fix, no OP-006), so the old note "same code,
nothing to rebuild" was wrong; task DEPLOY-MAIN is ready in `execution/current/code.bash`. Lease released.
Next: `NEXT_STEP.md` (reviews first, then DEPLOY-MAIN, then T-0015 to unblock the frontend).
References: `CURRENT_STATE.md`, `NEXT_STEP.md`, `policies/main-exceptions.txt`.

## 2026-10-06 — DEPLOY-MAIN: both VMs on main, SC-03 verified on LangGraph

Type: deployment
Who: conantkd (+ agent)
Context: vm-095 ran `c87d76c` (T-0013 branch, without the review fix and OP-006); vm-166 ran `8eff994`.
Decision / result: both VMs on `main` `09f5ab1`; the agent rebuilt (LangGraph, db check 15/15, no new migration).
The first H-1 said DIAGNOSED `dependency_unavailable`: `argus-lab-cache` had been stopped for about 7 hours, so
Argus was right. With the cache already down, SC-03 ran directly: DIAGNOSED, root cause the cache, the api the
victim, reads on vm-166 only. Cache restarted, H-1 `HEALTHY`, NO INTERFERENCE on both VMs.
Learned: `docker exec -i` in a pasted block reads the terminal and hangs; use `< /dev/null` and no `| tail`
(TROUBLESHOOTING #18). Scenarios must end with their undo and a health check; the state probe should list
`argus-lab-*` health (#19).
References: `execution/history/DEPLOY-MAIN/step-01/evidence.md`.

## 2026-10-06 — LAB-BASELINE: deploy.sh status reports the lab baseline

Type: change
Who: conantkd (+ agent)
Context: DEPLOY-MAIN found `argus-lab-cache` stopped for ~7 hours and nothing flagged it.
Decision / result: `deploy.sh status` lists every `argus-lab-*` container and ends with `LAB BASELINE OK` or
`LAB BASELINE NOT OK: <names>`. 3 tests (red seen), suite 68 passed / 5 skipped. Deployed as the task branch on
both VMs: `LAB BASELINE OK`, NO INTERFERENCE, nothing rebuilt. The state probe in `AGENT_PROTOCOL.md` uses it.
References: `execution/history/LAB-BASELINE/step-01/evidence.md`.

## 2026-10-06 — LGS: every plain-runner scenario now passes on LangGraph

Type: verification
Who: conantkd (+ agent)
Context: on LangGraph only H-1, SC-09, SC-01 and SC-03 had real runs; the rest relied on parity tests.
Decision / result: H-2, SC-02, the identity proof, SC-10, SC-11 and SC-12 re-run on the final `main` agent, one run
each, all as expected (outcomes cross-checked in Postgres). SC-12 escalated at step 2 (plain runner: step 3).
LAB BASELINE OK and NO INTERFERENCE on both VMs at the end. Note: SC-02's text called the worker a "read gateway"
(wording slip; root cause and class right).
Next: Phase 12 repeated runs (≥ 5 per scenario).
References: `execution/history/LGS/step-01/evidence.md`.

## 2026-10-06 — After-merge review of fast-track PRs #9 and #13

Type: review
Who: conantkd (+ agent)
Context: `REVIEW_PROTOCOL.md` ("Temporary fast-track"): a teammate reviews each self-merged PR after the merge.
Decision / result: #13 (removal of the practice-lab files) has no findings: only the 8 files were removed, they
contain no secrets (loopback addresses only), nothing references them, and the agent image was rebuilt from a
later commit by DEPLOY-MAIN. #9 (the fast-track rule) meets its own conditions. It approved itself and the `pr 4`
exception without a teammate, so this review is their first one: accepted, no objection. Follow-up in this PR:
the `main-exceptions.txt` header no longer contradicts the fast-track lines, and `CURRENT_STATE.md` lists which
after-merge reviews are done (#9, #13) and which are pending (#10, #11, #12).
References: PR #9, PR #13, this pull request.

## 2026-10-06 — conantkd asks to join the temporary fast-track

Type: decision
Who: conantkd (+ agent)
Context: the same deadline that motivated the fast-track (PR #9) applies to `conantkd`'s VM and Brain work.
Decision / result: `conantkd` is added to the fast-track "Who" list in `REVIEW_PROTOCOL.md`, with the same
conditions and the same end date (2026-10-12). It is a change to the review rule, so it takes effect only when
`juanbetancurm` approves PR #16; it is not self-merged.
References: PR #9, PR #16.

## 2026-10-06 — After-merge review of fast-track PRs #10, #11 and #12

Type: review
Who: conantkd (+ agent)
Context: the remaining after-merge reviews of the temporary fast-track.
Decision / result: no defects. #11 (OP-006): the formula covers the worst case (the model path and the evidence-pack
path never mix; an invalid decision also consumes a step); its two numbers are now named and explained in
`GraphRunner` (`FIXED_NODES = 4`: detect, recall, final investigate, record; `SAFETY_MARGIN = 10`: deliberate slack),
behaviour unchanged. #10: honest "reported, not verified", now superseded by DEPLOY-MAIN. #12: plan fine; T-0015's
ACR-0001 pull request cannot be fast-tracked (the rule excludes ACRs) and its token code should get a teammate's review.
All fast-track PRs #9–#13 are now reviewed.
References: PRs #10, #11, #12, this pull request.

## 2026-10-06 — juanes6554 joins the temporary fast-track (frontend)

Type: decision
Who: juanbetancurm (+ agent)
Context: `juanes6554` starts the frontend (T-0016) with the same deadline (2026-10-12).
Decision / result: `juanes6554` is added to the fast-track "Who" list, effective once his onboarding is done. Same
conditions and end date. The rule now names `.github/workflows/` as enforcement, so the PR that adds the CI job
`frontend` still needs a teammate, and so does any change to `contracts/` (shared with the API side). A change to the
review rule, so it is not self-merged: it takes effect when `conantkd` approves this pull request.
References: `agents/REVIEW_PROTOCOL.md`, `tasks/current/T-0016-frontend.md`, PR #16 (same precedent).

## 2026-10-06 — T-0017: the Postgres backup is proved restorable (phase 5 complete)

Type: task
Who: conantkd (+ agent)
Context: phase 5 lacked only a backup/restore drill; a backup nobody restored is only a hope.
Decision / result: `ops/db-backup.sh` (tests first). `backup` dumps the live database read-only and stores a
per-table fingerprint taken before and after the dump (refused if they differ); `verify` restores into a throwaway
`argus-lab-pgrestore` (no network, no port, tmpfs) and compares. On vm-095: 11 tables, 4603 rows, `VERIFY OK`, NO
INTERFERENCE. Lesson: `sudo ls folder/*.dump` fails on a root-only folder because the operator's shell expands the
glob before sudo; the script now offers `verify latest`. Dumps hold password hashes: root-only, never off the VM.
Follow-ups: schedule + retention; an encrypted off-VM copy.
References: `tasks/completed/T-0017-pg-backup-drill.md`, `execution/history/T-0017/`.

## 2026-10-06 — juanes6554's pre-existing UI prototype integrated into `frontend/` (T-0016 steps 1–2)

Type: implementation
Who: juanes6554 (+ agent)
Context: `juanes6554` had already built a mock-driven React UI outside the repository (with Claude on the web).
T-0016 starts with his guidelines; its official gate is T-0015 steps 1–5 merged, and PR #22 (T-0015) is still a
draft. The prototype touches nothing outside its own folder and makes no network calls.
Decision / result: integrated on `task/T-0016-frontend` as steps 1–2: `frontend/GUIDELINES.md` (drafted by the
agent from his code, approved by him), 20 Vitest unit tests with red seen (missing test harness; one fixture
corrected to match the parser), the CI job `frontend` (unit tests + production build; the workflow change needs
a teammate and is excluded from the fast-track), `frontend/README.md`, `.gitignore` entries (`node_modules/`,
`frontend/dist/`), stray files removed, login hero image 3.8 MB PNG → 136 KB JPEG. Deviation recorded in the
task file: the task started before T-0015 merged because the UI is mock-only; the HTTP/contract work still
waits for T-0015. Known follow-ups in `frontend/README.md` (react-router 6→7 audit findings, `demoRunbooks/`
removal with the mock adapter).
Consequences: `frontend/` is tracked with tests; the `frontend` CI job runs on every push; Playwright
acceptance tests and the fake API from `contracts/samples/` are the next steps of T-0016.
References: `tasks/current/T-0016-frontend.md`, `frontend/GUIDELINES.md`, `frontend/README.md`, this pull request.

## 2026-10-06 — T-0015 steps 2-5: read-only tokens, /me, UI origins, the UI contract

Type: implementation
Who: juanbetancurm (+ agent)
Context: ACR-0001 (proposed, PR #22) lets user interfaces use the API with read-only tokens.
Decision / result: `scope=read` at login gives a token with the claim `access: read`, refused on every non-GET route
whatever the role (403, audited). `GET /api/v1/me` lists the actions a token may use; a UI shows only those.
`ARGUS_UI_ORIGINS` enables CORS for listed origins only (none by default). The UI contract is
`contracts/ui-api.json` plus sample responses, guarded by `tests/test_ui_contract.py` and described in
`docs/API-FOR-UI.md`. Red seen in every step. The main laptop now runs the offline suite in Docker because Windows
Smart App Control blocks a native LangGraph dependency. Step 6 (deploy on vm-095) needs the VM lease.
References: ACR-0001, T-0015, PR #22.

## 2026-10-06 — Review of PR #24 (T-0016 steps 1-2) and the UI runbooks decision

Type: review
Who: juanbetancurm (+ agent)
Context: the frontend is mock-only. Its fake API assumes routes Argus does not have: email login, an `admin` role,
approvals, a simulator, a scheduler, chat and health.
Decision / result:
- PR #24 approved. The CI job `frontend` uses no secrets and doesn't touch other jobs.
- The review lists the smallest change set to connect to the real API (T-0016 step 3): username login with
  `scope=read`, then `/me`; token in memory only; roles viewer/operator/approver; pages without routes hidden; a Vite
  proxy to `127.0.0.1:18000`, so no CORS.
- **Runbooks:** the UI reads the reviewed library in `argus/runbooks/` at build time, instead of its demo copies,
  which are byte-identical. `parseRunbook` parses all 21 runbooks. No API route and no ACR change are needed.
References: PR #24, PR #22, ACR-0001, `docs/API-FOR-UI.md`.

## 2026-10-06 — Review of PR #22: ACR-0001 accepted, UIs read-only in this release

Type: review
Who: conantkd (+ agent)
Context: ACR-0001 said a UI "may" hold a read-only token, while its alternative A rejected full tokens for a UI. The
architecture allowed both readings.
Decision / result: ACR-0001 accepted. In this release a UI holds only read-only tokens: it shows incidents,
timelines, evidence and escalations, and never starts an investigation or answers an approval. This is not a
permanent limit: a later ACR may add UI actions (for example starting investigations or answering approvals), using
the `actions` list of `GET /api/v1/me`; approvals in a UI touch a safety principle and need a second approval. OD-10
and §17.3 now say so.
Checked: full suite green on the branch, the read-token check sits in the shared principal dependency, no secrets.
References: ACR-0001 §5, PR #22, T-0015.

## 2026-10-06 — PR #25 (T-0017) fast-tracked; vm-095 back on main

Type: deployment
Who: conantkd (+ agent)
Context: T-0017 (Postgres backup/restore drill) was finished; vm-095 still ran the T-0017 branch checkout.
Decision / result: PR #25 merged by fast-track (`main-exceptions.txt` line, review report posted, CI green; full
suite 95/95 locally with Postgres and real Docker). AFTER-MERGE: vm-095 checkout on `main` `f126272`, nothing
restarted, `LAB BASELINE OK`, NO INTERFERENCE. `deploy.sh` hinted an agent rebuild because `main` now holds T-0015;
left for T-0015 step 6. Also today: PR #22 (ACR-0001 accepted) and PR #24 (UI prototype) reviewed and merged; a future
ACR for UI actions is recorded in `NEXT_STEP.md`.
References: PR #25, PR #22, PR #24, `execution/history/AFTER-MERGE-T-0017/step-01/evidence.md`.

## 2026-10-07 — T-0018: SC-07 verified on vm-166 (a healthy backend on the wrong network)

Type: implementation
Who: conantkd (+ agent)
Context: SC-07 was planned on vm-095 with a new class. `conantkd` moved it to vm-166 (Host T, the lab host) and chose
a second lab network over a backend with no network, because it is the realistic mistake.
Decision / result:
- New Argus lab network `argus-lab-iso` `172.30.3.0/24`, after a read-only check that it is free on vm-166 (the
  protected deployment uses `172.17`–`172.21`). The Argus network rule is now `172.30.0–3.0/24`; the teammates are
  tagged in the PR.
- The read gateway's container status carries `networks` (names only), and the model sees it. Dependency probes run
  only while their owner runs, so the SC-07 probe does not keep `DependencyProbeFailed` firing outside the scenario.
- Tests first (6 red, then green; 95 passed). Deployed on both VMs (the agent steps were run over SSH by the agent at
  `conantkd`'s request; the password-protected checks by `conantkd`).
- SC-07 `inc_fb92d115abb2`: DIAGNOSED, root cause the backend "not attached to the client's application network",
  no restart advised. RB-009 was not recalled (branch runbook), so its `last_tested` stays `null`: follow-up.
References: T-0018, `execution/history/T-0018/`, `docs/INCIDENTS.md` SC-07.

## 2026-10-07 — T-0018: branch runbooks through `knowledge.runbook` (RB-009 tested in SC-07)

Type: implementation
Who: conantkd (+ agent)
Context: in the first SC-07 run RB-009 was not recalled. Recall is one TF-IDF search at the start; the
architecture's way to reach a branch runbook later (§3, §10.5: the in-worker capability `knowledge.runbook`) was not
implemented. `conantkd` chose the general mechanism over a per-case class, so every class with branch runbooks
(11 of the 20 in §3) benefits.
Decision / result: `query_runbook` (executor `argus_internal`, `runs_in="worker"`, max 3 per incident) goes through
InvokeCapability like every read; the context names the class's branch runbooks. The orchestration flow did not
change. Tests first (5 red, then green; 100 passed). The redactor masked full sha256 values as high-entropy secrets,
so passages carry a 16-character prefix. SC-07 run 2 (`inc_21f900ee6139`): the model read RB-009 after the TCP probe
failed and diagnosed the name-resolution layer, no restart. RB-009 `last_tested: 2026-10-07` (read in version 1.0.0; the metadata then became 1.0.1; still
draft). Next agreed: enable more classes under the §3 "Enablement" rule.
References: T-0018 step 7, `execution/history/T-0018/step-07/evidence.md`, ARCHITECTURE §10.5, §12.

## 2026-10-07 — T-0018: SC-07 runs 3-4, what the model needs to see

Type: analysis
Who: conantkd (+ agent)
Context: run 3 (RB-009 1.1.0) read neither RB-009 nor any container status. The stored evidence of runs 1-3 showed the
precise diagnosis came only when the model read the status of both sides, and the tool description did not say it
returns networks.
Decision / result: of five suggestions (network-named probe text, tool description, RB-003 step 2, a detector finding
naming the failing edge and layer, "Decide now" in the context), `conantkd` chose only the tool description. Run 4
(`inc_6a1511e19269`): status of both sides in step 1, RB-009 1.1.0 read, misattachment named with both networks, no
restart. The other suggestions stay open (recorded in the T-0018 task file); quality needs ≥ 5 runs (Phase 12).
References: `execution/history/T-0018/step-08/`, `step-09/`.

## 2026-10-07 — Reviews of PR #27, #25, #26; OP-007 opened

Type: review
Who: juanbetancurm (+ agent)
Context: `conantkd` asked for a review of PR #27 (T-0018, SC-07 and `knowledge.runbook`); PRs #25 and #26 were
fast-tracked and owed after-merge reviews.
Decision / result: PR #27 approved. `max_tool_level: 3` follows ARCHITECTURE §12.2, and `knowledge.runbook` is the
only Level 3 capability in the policy, so every future Level 3 line in `policy.yaml` needs a careful review. #25 and
#26: no defects. Notes for later: backup retention once backups are scheduled, and the scheduler (T-0014) will make
the backup's before/after fingerprint differ often. One question on #27 became **OP-007**: a dependency probe
disappears while its owner restarts, which can hide the cause of a crash loop; to fix with T-0019 (same service).
References: PR #27, PR #25, PR #26, `OPEN_PROBLEMS.md` OP-007.

## 2026-10-07 — T-0019 batch 1: the db-probe and database.health deployed (T-0019)

Type: capability
Who: conantkd (+ agent)
Context: phase 3 lacked the database probe of ARCHITECTURE §4.6, and SC-04 (connection exhaustion, RB-004) needs it.
`conantkd` split the remaining §4.6 verbs into 3 batches, one PR each (db-probe; host-probe Level 2; deep reads +
network connectivity, which also closes the SC-07 network-probe gap).
Decision / result: `ROLE=db_probe` reads only system views through `argus_monitor` (`pg_monitor`, limit 3), in a
read-only session, never rows or SQL text; own token and image target (`pg8000` pinned by hash). `database.health`
(`inspect_database_health`) at Level 3, policy max 3. `argus-lab-db` on vm-166 is **for testing only**. Tests 15/15
red then green (119 passed); deployed on both VMs over SSH; `phase3_check` 33/33; the agent reads it through its
own code path; NO INTERFERENCE. Also: OP-007 fixed and deployed (PR #29), AFTER-MERGE T-0018 done (PR #30), OP-008
proposed (PR #31).
References: `tasks/current/T-0019-db-probe.md`, `execution/history/T-0019/`, OPEN_PROBLEMS OP-007, OP-008.

## 2026-10-07 — SC-07 class demo; T-0015 step 6 proved (T-0015)

Type: deployment
Who: juanbetancurm (+ agent)
Context: class demo of SC-07 on the VMs (conantkd's lease released, both VMs on `task/T-0020-sc04-pg-connections`),
then the last open step of T-0015 while holding the lease.
Decision: SC-07 run live twice (`inc_bc5efb15381f` and the replay): DIAGNOSED as a network misattachment, no
restart advised; the advised human fix (`docker network connect argus-lab-app argus-lab-backend`) followed by
`--check` gave HEALTHY; lab reset, LAB BASELINE OK, NO INTERFERENCE. T-0015 step 6: a `scope=read` token reads (200)
and is refused on `POST /api/v1/investigations` (403) on the deployed API; no rebuild needed.
Consequences: T-0015 is done. The demo showed the ACT results cut on a narrow terminal: fixed in PR #34.
References: `brain/execution/history/T-0015/step-06/evidence.md`, PR #34.

## 2026-10-07 — T-0014 steps 1-4: api, worker and scheduler from one image (T-0014)

Type: implementation
Who: juanbetancurm (+ agent)
Context: one container ran the API and the investigations; a crash took both down, and a restart took back every
running run. Phase 9 needs a real worker and scheduler (ARCHITECTURE §3, §6.2, §6.5, §6.6, §7.3).
Decision: the worker's claim is a renewable lease (migration 003); `argus api`, `argus worker` and `argus scheduler`
run from the one agent image as three containers on vm-095; the scheduler is a driver only (rule 15 import guard),
reads `deploy/scheduler/schedules.yaml` (shipped with no enabled schedule) and gets only the database credential.
`argus serve` stays as the rollback (`ARGUS_AGENT_CMD=serve`). The backup quiet window is not needed: OP-008 (PR #31)
fixes the backup check with one exported snapshot.
Consequences: deploying it needs migration 003 before the worker starts; step 5 (vm-095, VM lease) proves a killed
worker's run resumes and a schedule is submitted once and coalesced while busy. 161 passed, 1 skipped.
References: `brain/tasks/current/T-0014-worker-scheduler.md`, `deploy/vm-095/compose.core.yml`,
`deploy/migrations/003_worker_lease.sql`, PR #31 (OP-008).

## 2026-10-08 — T-0014 step 5: a killed worker's run resumes; the scheduler coalesces (T-0014)

Type: verification
Who: juanbetancurm (+ agent)
Context: steps 1-4 split the agent into `argus api`, `argus worker` and `argus scheduler`; step 5 had to prove it on
vm-095 (vm-166 left untouched on `task/T-0020-sc04-pg-connections`).
Decision / result: before the crash test, reading the loop showed the worker recovered expired claims only at start,
so a run whose worker crashed would stay `running` forever (Docker restarts the worker before its lease expires);
fixed with a periodic re-check (`recover_every_s`, 30 s, red then green, 162 passed). On vm-095: H-1 HEALTHY through
the worker; the worker killed with `kill -9` in the middle of SC-02, the same incident requeued ~5 min later and
**resumed from its checkpoint** (`incident.resumed`, nothing before the kill repeated), DIAGNOSED. A temporary
`*/5` schedule: one incident per slot, none resubmitted after a scheduler restart, `schedule.coalesced` while the
target was busy, the queued check run when the worker came back; shipped file restored. NO INTERFERENCE.
Consequences: T-0014 is done and waits for review and merge (PR #33); then vm-095 back to `main` (checkout only),
and T-0021 step 4 (compose for the tools process) can start. Phase 13 "kill the worker mid-run" is covered.
References: `tasks/current/T-0014-worker-scheduler.md`, `execution/history/T-0014/step-05/evidence.md`.

## 2026-10-08 — T-0021: target-side reads in an MCP tools process under its own user (T-0021)

Type: implementation + verification
Who: juanbetancurm (+ agent)
Context: the worker held every executor token and ran every read itself; ARCHITECTURE §12.5/§12.6 want the reads in
a separate tools process that alone can read the tokens, and OD-3 asks what that costs per call.
Decision / result: an MCP tools server over stdio (`mcp` 2.3) publishes only the `tools_child` read capabilities and
refuses unpublished names, out-of-inventory targets and bad arguments before executing; the worker keeps policy,
audit and evidence. It runs as `argus-tools` (uid 10011), started through one sudo rule (the root-owned launcher, no
arguments); the api mounts no token. On vm-095 the tokens and their folders now belong to `argus-tools`, the worker
runs `ARGUS_TOOL_CATALOGUE=mcp`: TOOLS ISOLATION OK, SC-02 DIAGNOSED through the tools process, OD-3 p95 overhead
~45 ms per read (budget 100 ms), NO INTERFERENCE. A false STOP of the isolation check (it listed folders the worker
can no longer list) was found on the VM and fixed with a test. 183 passed, 2 skipped.
Consequences: PR #36 needs a teammate's review (safety model). Until it merges, vm-095 must not get `main` without
the rollback (its api and worker would not start). The code default stays `direct`; flipping it is for the review.
References: `tasks/current/T-0021-tool-isolation.md`, `execution/history/T-0021/step-05/evidence.md`, PR #36.

## 2026-10-09 — T-0023: a runner for repeated end-to-end scenario runs (T-0023)

Type: implementation (step 1, offline)
Who: juanbetancurm (+ agent)
Context: phase 12 needs at least 5 graded runs per scenario; every run so far was a set of manual blocks.
Decision / result: `ops/e2e/run.py` runs catalogued scenarios from the laptop (ssh for the reviewed commands, the
HTTP API on the tunnel for the investigation), waits on the detector's own signal (pre-gate and gate, no fixed
sleeps), always resets, stops the batch on interference or a failed reset, grades outcome, class, root cause, first
runbook, model use and the host of every read, and writes one JSON line per run outside the repository. Catalogue:
H-1, H-2, SC-01, SC-02, SC-03, SC-07, SC-09, SC-11. 22 new tests; 206 passed, 2 skipped.
Consequences: step 2 is the first real batch with the lease (H-1, H-2, SC-09, SC-11 once; SC-01 and SC-03 × 5).
References: `tasks/current/T-0023-e2e-runner.md`, `ops/e2e/scenarios.yaml`.

## 2026-10-09 — T-0023: the first real batch of the scenario runner (T-0023)

Type: verification
Who: juanbetancurm (+ agent)
Context: step 2 of T-0023, the runner's first batch on vm-095 and vm-166.
Decision / result: H-1, H-2, SC-09, SC-11 1/1; **SC-03 5/5** and **SC-01 5/5 PASS** (class, root cause, first runbook
and the host of every read graded), NO INTERFERENCE after every run. One SC-01 run lost the laptop's API tunnel: it
was reset and checked clean, the batch stopped as designed, and the runner now keeps its own tunnel and retries a
dropped connection (`4f8ae43`).
Consequences: phase 12 has its first repeated runs. Next: SC-02 and SC-07 × 5; each new scenario (SC-04 after #38)
gets a catalogue entry and 5 runs.
References: `tasks/current/T-0023-e2e-runner.md`, `execution/history/T-0023/step-02/evidence.md`.
## 2026-10-09 — review of PR #40: two runner fixes made by the reviewer (T-0023)

Type: review
Who: conantkd (+ agent)
Context: review of PR #40 (`juanbetancurm`'s end-to-end runner). REVIEW_PROTOCOL: small fixes are made by the
reviewer on the same branch, journaled.
Decision / result: (1) an incident view without `evidence` and `audit` (the runner's user not an operator) is an ERROR,
never a PASS; before, the model and host checks passed on nothing. (2) The reset runs only once a start was attempted;
SC-07's reset succeeds when its network is already gone. 6 new tests, red seen; `test_e2e_runner.py` 33 passed.
Consequences: run the batches as an operator user. Every catalogued reset must be idempotent.
References: `tasks/current/T-0023-e2e-runner.md`, PR #40.
