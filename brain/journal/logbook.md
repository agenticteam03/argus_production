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

## 2026-10-08 — SC-04 verified, reviews, T-0020 ready for review (T-0020)

Type: verification
Who: conantkd (+ agent)
Context: T-0020 enables `postgresql_connection_exhaustion` (RB-004): the db-probe publishes `/metrics`, vm-166's
Prometheus scrapes it, the signal `db_connection_usage` and the alert `DbConnectionsExhausted`; SC-04's leaker holds
16 of 17 usable slots on `argus-lab-db`.
Decision / result: run 1 (2026-10-07) was invalid: the lab's `pids_limit: 32` stopped the leaker at ~10 sessions; the
diagnosis honestly answered UNSUPPORTED. Run 2: `inc_075fb0006098` DIAGNOSED, root cause `argus-lab-leaker`, RB-004,
the database read, no restart proposed; RB-004 `last_tested` 1.0.2. nonint-check found two anonymous volumes from the
leaker image's `VOLUME`: removed by ID after approval, and the leaker now uses a tmpfs. Session of 2026-10-08:
reviews first — #34 and #35 approved and merged, #36 (T-0021) **changes requested** (a worker can plant a module in
its working folder and run it as `argus-tools` through the sudo launcher, reproduced with fake tokens; an ACR is
needed for `setpriv` → `sudo`), after-merge reviews of #33 and #37 posted. OP-009 opened from the #33 review.
Consequences: T-0020 is done and waits for review. vm-095 runs T-0021 without T-0020, so the class reaches the agent
when vm-095 is back on `main`. Phase 11 at 70 %.
References: `tasks/current/T-0020-sc04-pg-connections.md`, `execution/history/T-0020/`, OPEN_PROBLEMS OP-009, PRs #33-#37.

## 2026-10-08 — phase 7 on vm-166, OP-010 verified, SC-05 coded (T-0022, OP-010, T-0024)

Type: verification
Who: conantkd (+ agent)
Context: after T-0020 (#38) and the OP-009 branch, `conantkd` chose all of phase 7: D-001 decided as transport
profiles (ACR-0003, this deployment `restricted-ssh`, alerts pulled), Argus-owned Alertmanager, node-exporter and
cAdvisor.
Decision / result: T-0022 steps 1-3 (ACR-0003, architecture 1.8.3, the alert intake shared by webhook and pull, the
scheduler's reconciliation, the monitoring stack; 186 passed). Step 4 on vm-166: all jobs up, the root filesystem
seen (`pid: host`), 1 Alertmanager, nothing firing; nonint showed only the new listener 18091. OP-010: the lab
database reserves a slot for `argus_monitor` and the probe reports `monitor_slot_reserved` (general: a real database
without it is visible); SC-04 at 16 of 16 ordinary slots on vm-166: the probe stayed up, usage 1.0, the alert fired
and reached vm-166's Alertmanager. A mis-extracted block (the T-0020 AFTER-MERGE `M.1`) ran only a SESSION grep and
`nonint-check before`, then stopped on its `<you>` placeholder: nothing changed. T-0024 (SC-05) step 1: signals per
declared mount, `disk_pressure`, `rslave`, the bounded filler and the lab mount script (207 passed); the scripted
diagnosis showed the filler outside a host incident's scope, fixed with `depends_on` (the §5 rule).
Consequences: vm-166 on `task/OP-010-reserved-slot`; T-0024 local only; PRs wait for #38 and for `conantkd`'s
order; vm-095 work waits for #36. Session closed, lease released.
References: `tasks/current/T-0022-alerting.md`, `tasks/current/T-0024-sc05-disk.md`, OPEN_PROBLEMS OP-010,
`execution/history/T-0022/step-04/`, `execution/history/OP-010/step-01/`.

## 2026-10-08 — OP-009: a worker that loses its lease stops its run (OP-009)

Type: fix
Who: conantkd (+ agent)
Context: the after-merge review of PR #33 found that the renewer only logged a lost claim, and died silently on a
database error, while the run went on; with two workers the same incident could run twice.
Decision: cooperative cancel instead of fencing every write: the worker owns the decision (retry while the lease
lasts, then cancel), the runner checks one signal at its node boundaries, before reads and before the final record.
The LangGraph checkpoint stays at the last completed node, so the new owner resumes. One clock per lease in Postgres.
Consequences: a second worker is safe from double runs. Code only, no VM change; reaches vm-095 with the next agent
rebuild. Branch on top of T-0020 (PR #38), because OP-009 is written there.
References: OPEN_PROBLEMS OP-009, `tests/test_op009_lease_loss.py`.
## 2026-10-09 — T-0021: review fixes of PR #36, and ACR-0002 (T-0021)

Type: implementation + architecture change (proposed)
Who: juanbetancurm (+ agent)
Context: `conantkd` requested changes on PR #36: a compromised worker could still get code to run as `argus-tools`
(sudo keeps the working folder, `python -m` puts it first on `sys.path`; reproduced with fake tokens), and the
switch from `setpriv` to a sudo rule changes the mechanism behind a safety principle (secrets), so it needs an ACR.
Decision / result: the launcher runs `cd /` and `python -I -u`; `isolation_check` plants an `argus` package and
starts the launcher from that folder (old launcher: STOP, fixed launcher: OK, on the agent image). ACR-0002
(proposed) records the sudo launcher in §12.6 and closes OD-3 with "keep MCP" (architecture 1.8.2). A tools process
that hangs is now replaced after the call times out. vm-095's compose defaults to `mcp`. 185 passed, 2 skipped.
Consequences: PR #36 needs the re-review and the ACR's second approval; vm-095 gets the fixed launcher with a
redeploy of the branch and a new isolation check (step 5e, with the lease).
References: `architecture/changes/ACR-0002-tools-uid-sudo-launcher.md`, `tasks/current/T-0021-tool-isolation.md`,
PR #36.

## 2026-10-09 — T-0021: step 5e on vm-095, and PR #36 merged before its re-review (T-0021)

Type: verification + incident (review rule)
Who: juanbetancurm (+ agent)
Context: the review fixes of PR #36 (`6f45218`) had to reach vm-095, and the PR needed `conantkd`'s re-review.
Decision / result: step 5e on vm-095: the fixed launcher deployed, `isolation_check` with the planted-package probe
TOOLS ISOLATION OK, NO INTERFERENCE. Meanwhile PR #36 was merged into `main` (`a9b4df8`) at its earlier head
`289bb0d`, before the fixes and the re-review: `main-guard` red, and `main` has the old launcher.
Consequences: per REVIEW_PROTOCOL, a follow-up PR (`task/T-0021-review-fixes`) brings the fixes, ACR-0002 and the
step 5e record to `main` and gets the missing review (no force push, no fast-track: ACR, safety principle). Until it
merges, `main` must not be deployed on vm-095.
References: `execution/history/T-0021/step-05e/evidence.md`, `tasks/current/T-0021-tool-isolation.md`, PR #36.

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

## 2026-10-09 — OP-001 runbook detector metadata alignment

Type: implementation
Who: conantkd (+ agent)
Context: the authored runbooks retained an old detector name or null metadata despite architecture §1.3 assigning
every runbook to an incident class.
Decision / result: 18 changed runbooks now name their architecture class, with patch versions and `last_reviewed`
updated; RB-002, RB-003, and RB-004 already matched and stayed unchanged. The index names all 21 mappings, and a
test compares both surfaces with the architecture table (red before, green after). No detector was enabled or runbook
promoted.
Consequences: review the corpus-only PR. Library metadata revision is v1.1.1; the §1.3 v1.1.0 citation remains its
original design baseline.
References: `tasks/current/OP-001-runbook-detectors.md`, OPEN_PROBLEMS OP-001, `argus/runbooks/RUNBOOK-INDEX.md`.

## 2026-10-09 — OP-005 offline implementation: young restart counts

Type: implementation
Who: conantkd (+ agent)
Context: SC-01 can be missed when the container restarted before Prometheus's first scrape; the old range expression
undercounts. The approved OP-005 design requires a creation-time guard so a scrape gap on an old container never
becomes a false incident.
Decision / result: the exporter publishes Docker's creation time and `restarts_10m` uses the young branch first.
Three unit tests were red, then green. Five `promtool` synthetic-series cases pass and are added to CI. This is
offline verification only; PR #38 and vm-166's T-0020 checkout must be reconciled before VM deployment and SC-01.
References: `tasks/current/OP-005-restart-signal.md`, `tests/test_op005_young_restarts.py`,
`tests/promql/op005_test.yml`, OPEN_PROBLEMS OP-005.

## 2026-10-09 — OP-005 verified on both VMs; PR #41 reviewed and fast-tracked (OP-005)

Type: verification + review
Who: conantkd (+ agent)
Context: PR #41 implemented the accepted OP-005 design offline; the VM proof was pending. `conantkd` asked to verify
it and fast-track it.
Decision / result: review fixes first: the alert `ContainerRestartLoop` now counts like `restarts_10m` (test first);
the CI step for the PromQL cases moved to PR #43, because a change under `.github/workflows/` cannot be fast-tracked.
On the VMs: vm-095 on `b26effa` (`main` + OP-005), vm-166 on a proof branch (the unmerged OP-010 stack + `main` +
OP-005, so its Argus-owned Alertmanager and the reserved slot stay). At a young SC-01 container's counter 3 the new
signal gave 3, the old one 1; the alert fired; `inc_312b18f2d8a8` DIAGNOSED. An exporter restart with an old
container invented no restart. `/opt/argus-v18/secrets/prometheus` created on purpose on vm-095 (#38 review).
NO INTERFERENCE on both.
Consequences: OP-005 fixed. PR #43 (CI step) needs `juanbetancurm`. vm-166 runs `task/OP-005-vm166-proof` until the
T-0022 and OP-010 PRs merge.
References: `tasks/current/OP-005-restart-signal.md`, `execution/history/OP-005/step-02/evidence.md`, PRs #41, #43.

## 2026-10-09 — T-0022 verified on both VMs: firing alerts are pulled and open incidents (T-0022)

Type: verification
Who: conantkd (+ agent)
Context: T-0022 steps 5-6 waited for #36; `main` now has #38-#41. Both VMs got `50f33ae` (T-0022 + OP-010 + `main`).
Decision / result: vm-095 runs its Argus-owned Alertmanager, node-exporter and cAdvisor, and the tunnel forwards
vm-166's Alertmanager (18091); the scheduler reads both every 60 s. SC-03 on vm-166 and SC-02 on vm-095: each firing
alert opened one incident (principal `alertmanager@<host>`), all DIAGNOSED, and the next passes reported `duplicate`.
Two alerts on one target (SC-03) opened two incidents: §6.4 correlation is not implemented, recorded as OP-011.
NO INTERFERENCE on both.
Consequences: T-0022 done; its PR needs `juanbetancurm`'s second approval of ACR-0003. Next: OP-011, the OP-010
DIAGNOSED run at 100 %, T-0024 (SC-05).
References: `tasks/current/T-0022-alerting.md`, `execution/history/T-0022/step-05/`, `step-06/`, OPEN_PROBLEMS OP-011.

## 2026-10-09 — OP-010 fixed: SC-04 at 100 % DIAGNOSED from the pulled alert (OP-010)

Type: verification
Who: conantkd (+ agent)
Context: OP-010's fix (a reserved slot for the monitoring role) was verified on vm-166 on 2026-10-08; the diagnosis
waited for vm-095 to pull alerts (T-0022 step 5, done today).
Decision / result: with 16 of 16 ordinary slots taken the probe kept `argus_db_up=1`; `DbConnectionsExhausted` fired
after 5 minutes; the scheduler pulled it and opened `inc_03e42714762f`, DIAGNOSED (`postgresql_connection_exhaustion`,
root cause `argus-lab-leaker`, the database the victim). No password was needed: the alert opened the incident.
NO INTERFERENCE on both.
Consequences: OP-010 fixed; its PR (stacked on T-0022) is ready.
References: OPEN_PROBLEMS OP-010, `execution/history/OP-010/step-02/evidence.md`.

## 2026-10-09 — SC-05 DIAGNOSED on vm-166 from the pulled alert (T-0024)

Type: verification
Who: conantkd (+ agent)
Context: T-0024 (SC-05, `disk_pressure`, RB-005) was coded on 2026-10-08; with T-0022 on both VMs the alert path is
complete.
Decision / result: both VMs on `b049086`. vm-166 got the lab filesystem (`/srv/argus-lab-fill`, 224 MiB loop mount,
testing only, not in fstab). The filler took it to 92.6 %; after 5 minutes `HostDiskPressure` fired, the scheduler
pulled it and `inc_4d78232433a1` was DIAGNOSED (`disk_pressure`, root cause `argus-lab-filler`), with no unscoped
deletion advised. Reset; the lab filesystem stays mounted and empty. RB-005 1.0.2. NO INTERFERENCE on both.
Consequences: T-0024 done; phase 11 at 80 % (SC-06, SC-08 left). The time to full lags a stop by up to 15 minutes.
References: `tasks/current/T-0024-sc05-disk.md`, `execution/history/T-0024/step-02/evidence.md`.

## 2026-10-09 — OP-011: alert correlation deployed; ACR-0004 (the same episode) accepted

Type: decision
Who: conantkd (+ agent)
Context: OP-011 (two alerts on one target opened two incidents). Step 01 implemented ARCHITECTURE §6.4 in the alert
intake (webhook and pull) with migration 004 (`alert_occurrence`); step 02 deployed it on both VMs and ran SC-03.
Decision / result: SC-03 still gave two incidents: the alerts started 30 s apart and were pulled one pass apart, and
the first incident was diagnosed and closed in 31 s, so §6.4 (open incidents only) did not apply. The second alert
started 9 s before the first incident closed. `conantkd` accepted ACR-0004 (architecture 1.8.4): an alert that started
at or before the latest concluded incident of its target and class closed, within the window and compatible, is
attached to it, without a new run and without reopening it. Rejected: a grouping wait (latency on every alert) and
keeping §6.4 as written.
Consequences: step 03 deploys the rule and repeats SC-03 (done when one incident). No safety principle touched.
References: OPEN_PROBLEMS OP-011, `architecture/changes/ACR-0004-correlation-same-episode.md`,
`execution/history/OP-011/step-02/evidence.md`.

## 2026-10-09 — OP-011 fixed: SC-03 gives one incident (OP-011, ACR-0004)

Type: verification
Who: conantkd (+ agent)
Context: ACR-0004 (an alert of the same episode joins the concluded incident) was implemented after step 02.
Decision / result: both VMs on `task/OP-011-correlation` `cb300df`. SC-03 reproduced step 02's timing: the incident
`inc_8a4cf92444ae` was DIAGNOSED and closed at 13:36:22; `ContainerUnhealthy` (started 13:36:01) was pulled at 13:36:57
and **attached** to it (`concluded, same episode`); the next pass said `duplicate` twice. One incident, one diagnosis,
evidence version 2. LAB BASELINE OK, NO INTERFERENCE on both.
Consequences: OP-011 fixed; its PR is stacked on T-0024 (with migration 004 and ACR-0004). Both VMs run it.
References: OPEN_PROBLEMS OP-011, `execution/history/OP-011/step-03/evidence.md`.

## 2026-10-09 — T-0026: resolved alerts (T-0026, ACR-0005)

Type: implementation + architecture change
Who: conantkd (+ agent)
Context: §6.4 "Resolution" was not implemented, and this deployment pulls alerts, so Argus never receives a
`resolved` notification: a resolved alert just stops being listed by the Alertmanager.
Decision: ACR-0005 (accepted by `conantkd`): in a pull profile an occurrence resolves when its alert is absent from a
successful read of the host's active alerts (silenced and inhibited included); an unreadable host resolves nothing.
When all of an incident's alerts resolve: queued → closed `resolved_externally` without a run; running → it finishes;
concluded → unchanged. Migration 005: `resolved_at`, `UPDATE (status, resolved_at)` forward only for the runtime role.
Consequences: code and tests done (301 passed, 3 skipped with Postgres); the VM step (migration 005 on vm-095, SC-03
on vm-166) is next. Stacked on OP-011 (#48).
References: `tasks/current/T-0026-alert-resolution.md`, `architecture/changes/ACR-0005-pull-alert-resolution.md`.

## 2026-10-09 — T-0026 verified: SC-03's alerts resolve when the cache is back (T-0026, ACR-0005)

Type: verification
Who: conantkd (+ agent)
Context: step 01 implemented §6.4 "Resolution" with ACR-0005 (pull: absence from a successful read of every active
alert).
Decision / result: backup, migration 005 and the agent image on vm-095 (`ea01c68`), `argus db check` 20/20; vm-166
checkout. SC-03: one incident `inc_ed6a85ccd28f` (DIAGNOSED, two occurrences, nothing resolved while the alerts were
active); the cache started at 18:46:13, the alerts cleared at 18:46:54, and the pass at 18:46:56 resolved both
occurrences (`absent_from_pull`), audited, the concluded incident unchanged. LAB BASELINE OK, NO INTERFERENCE.
Consequences: T-0026 done; its PR is stacked on #48. Both VMs run `task/T-0026-alert-resolution`.
References: `tasks/current/T-0026-alert-resolution.md`, `execution/history/T-0026/step-02/evidence.md`.

## 2026-10-09 — T-0025: the §21.2 evaluation, step 1 (T-0025)

Type: implementation (offline)
Who: juanbetancurm (+ agent)
Context: the four enabled classes were enabled on lab runs, ahead of the §21.2 evaluation that §3 "Enablement" asks
for. Nobody owned it, and it needs no VM.
Decision / result: `argus/evaluation/` replays a labeled case through the real wiring with fixture executors and a
fixed metric snapshot, grades it, and counts the hard rules (no dispatched action, no planted secret in a model
request, no cross-host read). The replay is pinned to fixtures, SQLite and no environment model, so it can later run
inside the worker container without touching anything real. 7 cases; the 6 safety cases pass offline, recall@3 1.00.
Consequences: step 2 adds the deterministic baseline strategy and 5 cases per enabled class; step 3 runs the real
model's trials on vm-095 and gives each class its gate (or the baseline strategy).
References: `tasks/current/T-0025-evaluation.md`, `tests/eval/`.

## 2026-10-09 — T-0025: the deterministic baseline and 29 evaluation cases (T-0025)

Type: implementation (offline)
Who: juanbetancurm (+ agent)
Context: §21.2 measures every model strategy against a deterministic baseline on the same labeled cases.
Decision / result: `baseline` is a registered strategy (fixed reads per class, a rule per class, escalation when no
rule decides). 29 cases: 5+ per enabled class, 2 ambiguous, 1 tool failure, 6 safety. Baseline: 29/29 PASS,
accuracy 1.00, safe abstention 1.00, hard 0 0 0. The cases and rules were written together, so this proves
consistency, not generality; the class registry is unchanged (all four classes still `model_loop`).
Consequences: step 3 runs the configured model on the same cases on vm-095 (lease), ≥ 5 trials each; a class whose
model results do not match the baseline switches to `baseline` in the registry (a data change).
References: `tasks/current/T-0025-evaluation.md`, `tests/eval/`.

## 2026-10-09 — T-0025: the configured model measured on the §21.2 cases (T-0025)

Type: verification
Who: juanbetancurm (+ agent)
Context: the four enabled classes had lab runs only; §3 "Enablement" asks for the §21.2 evaluation.
Decision / result: 30 cases × 5 trials on vm-095, in a one-off container with only the model key, the cases and the
config (no executor token, no database; the VM checkout and running containers untouched). Hard 0 0 0; core accuracy
0.92 (strict 0.86); abstention 0.86 (threshold 0.9 not met). Per class (core, model vs baseline): database 1.00/1.00,
health 1.00/1.00, restart loop 0.87/0.83, dependency 0.84/1.00. Five earlier tries found and fixed harness and dataset
problems (missing config, missing metric history, incomplete fixtures, a harness word reaching the model, over-strict
and one wrong label); every fix is recorded in the task file.
Consequences: proposal for the team: `dependency_unavailable` → `baseline` (the rule of §21.2), the others stay
`model_loop`, with the bias caveat (the baseline's rules and the cases were written together). Open: the abstention
gap and a rubric for evidence support.
References: `tasks/current/T-0025-evaluation.md`, `tests/eval/`.

## 2026-10-09 — T-0027: the monitoring blind spot class; phase 7 complete (T-0027)

Type: implementation + verification
Who: conantkd (+ agent)
Context: phase 7 lists four detectors; the blind spot (RB-014) was missing, and the freshness gate only watched
`argus-v18-exporter`: with node-exporter down, a host check ended `no_incident`, unknown read as healthy (G-007).
Decision / result: `monitoring_blind_spot` for host targets (before `disk_pressure`, `evidence_pack`, no model) on
`scrape_targets_down = count(up{argus_host} == 0)`, and the alert `ArgusScrapeTargetDown` (2 minutes). 5 evaluation
cases; the enabled-classes test now reads the registry, `disk_pressure` listed as awaiting its cases. To get there the
stack (#46-#48, T-0026) was brought up to `main` (#49, #50, #53): Brain conflicts, RB-005 bumped to 1.0.3 (both sides
had bumped it), `wiring.py` and `test_postgres.py` kept both sides. On the VMs (`c27546f`): node-exporter stopped on
vm-166 → `inc_263f471e33e3` escalated as `monitoring_blind_spot`, evidence pack, 0 model calls; resolved after restart.
NO INTERFERENCE.
Consequences: phase 7 complete. Open: absent scrape targets need a pinned expected-jobs list; `disk_pressure` needs
its 5 cases (quality lane). PR stacked on T-0026.
References: `tasks/current/T-0027-blind-spot.md`, `execution/history/T-0027/step-02/evidence.md`.

## 2026-10-10 — T-0030: a Postgres restart is a pause, never a crash (T-0030)

Type: fix + verification
Who: conantkd (+ agent)
Context: phase 13 asks that failures become escalations, never crashes. Reading the loops before the VM test: the
scheduler guarded its database calls, the worker's `run_forever` did not (a database error ended it).
Decision / result: the worker logs, waits and retries (tests first, red seen). On vm-095: Postgres restarted during an
SC-03 run (the run DIAGNOSED) and stopped 30 s (the worker logged one retry, the scheduler resumed, the api answered);
no Argus container restarted; NO INTERFERENCE.
Consequences: phase 13's Postgres restart is done. Next: Prometheus down on one host; token rotation. vm-095 runs
`task/T-0030-vm-proof` `a56f014`, vm-166 `task/T-0029-vm-proof` `eebfa72`.
References: `tasks/current/T-0030-pg-restart.md`, `execution/history/T-0030/step-02/evidence.md`.

## 2026-10-09 — T-0016 step 3: connect the read-only UI to the real API (T-0016)

Type: implementation
Who: juanes6554 (+ agent)
Context: PR #24 (the mock UI, steps 1-2) was reviewed by juanbetancurm (next-step list) and conantkd (ACR-0001 scope:
a UI only reads and shows a control only when /me lists its action). The HTTP/contract work was waiting for T-0015,
which has merged; the code needs no VM lease.
Decision: added the HTTP adapters (form-encoded POST /api/v1/auth/token with scope=read, then GET /api/v1/me; and
GET incidents list/detail/events with the overview built from the list), an in-memory token store where any 401
forgets the token, the VITE_ARGUS_MOCK switch (mock is the default), the dev proxy /api -> 127.0.0.1:18000, a
username login, the viewer/operator/approver roles with the write screens (approvals, simulator, scheduler) removed
from the menu, and runbooks read from argus/runbooks (demoRunbooks deleted). Tests first: 7 red, then 39 green plus
the Vite build.
Consequences: the frontend needs CI `frontend` green and a reviewer (fast-track, since it does not touch
`.github/workflows/` or `contracts/`). Approvals, the agent chat that starts an investigation, the simulator, the
scheduler and the health data stay mock-only until the new ACR agreed in the PR #24 comments. Open: Playwright
acceptance, the read-only network guard and the contracts/ui-api.json check.
References: `frontend/README.md`, `docs/API-FOR-UI.md`, `tasks/current/T-0016-frontend.md`.

## 2026-10-10 — T-0028: SC-06 DIAGNOSED on vm-166; two defects found by the lab (T-0028)

Type: implementation + verification
Who: conantkd (+ agent)
Context: phase 11's SC-06: a burner under a 0.3-core quota; `cpu_saturation` (RB-006), the container trigger only.
Decision / result: the first run found two defects the offline tests could not: (1) cAdvisor's samples are 35-53 s
apart, so a 1m rate was empty and the alert never fired (now 3m); (2) the throttled share alone fired for the bursty
`argus-lab-api` on both hosts (61 % throttled at 4 % of its quota) and two api incidents were wrongly diagnosed (now
the quota used must be ≥ 80 % too, a new signal; checked on vm-166's Prometheus). Second run: `inc_39bbec3df928`
DIAGNOSED with high confidence (quota-constrained, RB-006 H5; "do not restart or kill speculatively"), no false
positive, resolved after the burner was removed. NO INTERFERENCE.
Consequences: SC-06 done (phase 11). Both VMs run `task/T-0028-vm-proof` `ed689b0` (T-0027 + T-0028) until the stack
merges. The busy-host CPU trigger stays open (needs the host-scope ACR).
References: `tasks/current/T-0028-sc06-cpu.md`, `execution/history/T-0028/step-02/evidence.md`.
