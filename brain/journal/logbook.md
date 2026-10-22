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
References: `tasks/completed/T-0015-ui-read-access.md`, `tasks/current/T-0016-frontend.md`.

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
References: `tasks/completed/T-0019-db-probe.md`, `execution/history/T-0019/`, OPEN_PROBLEMS OP-007, OP-008.

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
References: `brain/tasks/completed/T-0014-worker-scheduler.md`, `deploy/vm-095/compose.core.yml`,
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
References: `tasks/completed/T-0014-worker-scheduler.md`, `execution/history/T-0014/step-05/evidence.md`.

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
References: `tasks/completed/T-0021-tool-isolation.md`, `execution/history/T-0021/step-05/evidence.md`, PR #36.

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
References: `tasks/completed/T-0020-sc04-pg-connections.md`, `execution/history/T-0020/`, OPEN_PROBLEMS OP-009, PRs #33-#37.

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
References: `tasks/completed/T-0022-alerting.md`, `tasks/completed/T-0024-sc05-disk.md`, OPEN_PROBLEMS OP-010,
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
References: `architecture/changes/ACR-0002-tools-uid-sudo-launcher.md`, `tasks/completed/T-0021-tool-isolation.md`,
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
References: `execution/history/T-0021/step-05e/evidence.md`, `tasks/completed/T-0021-tool-isolation.md`, PR #36.

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
References: `tasks/completed/T-0023-e2e-runner.md`, `ops/e2e/scenarios.yaml`.

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
References: `tasks/completed/T-0023-e2e-runner.md`, `execution/history/T-0023/step-02/evidence.md`.

## 2026-10-09 — review of PR #40: two runner fixes made by the reviewer (T-0023)

Type: review
Who: conantkd (+ agent)
Context: review of PR #40 (`juanbetancurm`'s end-to-end runner). REVIEW_PROTOCOL: small fixes are made by the
reviewer on the same branch, journaled.
Decision / result: (1) an incident view without `evidence` and `audit` (the runner's user not an operator) is an ERROR,
never a PASS; before, the model and host checks passed on nothing. (2) The reset runs only once a start was attempted;
SC-07's reset succeeds when its network is already gone. 6 new tests, red seen; `test_e2e_runner.py` 33 passed.
Consequences: run the batches as an operator user. Every catalogued reset must be idempotent.
References: `tasks/completed/T-0023-e2e-runner.md`, PR #40.

## 2026-10-09 — OP-004 offline checkpoint retention implementation

Type: implementation
Who: conantkd (+ agent)
Context: LangGraph checkpoint rows grow indefinitely, including failed runs whose incidents are final. The accepted
OP-004 proposal keeps runtime DELETE forbidden and requires a dry run before any live cleanup.
Decision / result: `argus db prune-checkpoints` defaults to a read-only preview; `--apply` uses the owner role and one
transaction to remove the three checkpoint tables' eligible rows and append `maintenance.checkpoints_pruned` to audit.
The one-off wrapper mounts only the owner credential; the daily systemd timer is shipped but not installed. Six tests
pass with throwaway PostgreSQL 16; no live database rows have been deleted.
Consequences: VM dry run and review of its counts and backup evidence are next; apply and timer enablement remain
pending.
References: `tasks/current/OP-004-checkpoint-retention.md`, `tests/test_checkpoint_retention.py`, OPEN_PROBLEMS OP-004.

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
References: `tasks/completed/OP-001-runbook-detectors.md`, OPEN_PROBLEMS OP-001, `argus/runbooks/RUNBOOK-INDEX.md`.

## 2026-10-09 — OP-008 offline backup retention and snapshot consistency

Type: implementation
Who: conantkd (+ agent)
Context: T-0017's backup compared fingerprints before and after `pg_dump`, so a busy database could reject a valid
consistent dump; backup files had no retention policy.
Decision / result: a read-only exported PostgreSQL snapshot now supplies both the fingerprint and `pg_dump`.
`verify` writes a `.verified` marker only after the restored copy matches. `prune` previews by default, preserves the
newest N sets and the newest verified set, and requires `--apply` plus the VM session marker to delete complete older
sets. The tests were red before the change; 15 now pass, including a throwaway PostgreSQL write during the dump.
Consequences: no live backup was deleted. A VM dry run and teammate review of its counts and backup evidence are
required before any apply. Backup scheduling is still undecided.
References: `tasks/current/OP-008-backup-retention.md`, OPEN_PROBLEMS OP-008, `tests/test_db_backup.py`.

## 2026-10-09 — OP-005 offline implementation: young restart counts

Type: implementation
Who: conantkd (+ agent)
Context: SC-01 can be missed when the container restarted before Prometheus's first scrape; the old range expression
undercounts. The approved OP-005 design requires a creation-time guard so a scrape gap on an old container never
becomes a false incident.
Decision / result: the exporter publishes Docker's creation time and `restarts_10m` uses the young branch first.
Three unit tests were red, then green. Five `promtool` synthetic-series cases pass and are added to CI. This is
offline verification only; PR #38 and vm-166's T-0020 checkout must be reconciled before VM deployment and SC-01.
References: `tasks/completed/OP-005-restart-signal.md`, `tests/test_op005_young_restarts.py`,
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
References: `tasks/completed/OP-005-restart-signal.md`, `execution/history/OP-005/step-02/evidence.md`, PRs #41, #43.

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
References: `tasks/completed/T-0022-alerting.md`, `execution/history/T-0022/step-05/`, `step-06/`, OPEN_PROBLEMS OP-011.

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
References: `tasks/completed/T-0024-sc05-disk.md`, `execution/history/T-0024/step-02/evidence.md`.

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
References: `tasks/completed/T-0026-alert-resolution.md`, `architecture/changes/ACR-0005-pull-alert-resolution.md`.

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
References: `tasks/completed/T-0026-alert-resolution.md`, `execution/history/T-0026/step-02/evidence.md`.

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
References: `tasks/completed/T-0025-evaluation.md`, `tests/eval/`.

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
References: `tasks/completed/T-0025-evaluation.md`, `tests/eval/`.

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
References: `tasks/completed/T-0025-evaluation.md`, `tests/eval/`.

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
References: `tasks/completed/T-0027-blind-spot.md`, `execution/history/T-0027/step-02/evidence.md`.

## 2026-10-10 — T-0029: SC-08 DIAGNOSED on vm-166; phase 11's planned scenarios done (T-0029)

Type: implementation + verification
Who: conantkd (+ agent)
Context: SC-08, nginx in front of a slow upstream (`nginx_upstream_failure`, RB-015). Argus had no HTTP signal.
Decision / result: a synthetic HTTP probe in the exporter (every declared `http_endpoints` of an active container;
502/504 count as gateway errors, an app's 503 does not), the class (plan_then_reason) and `HttpGatewayErrors`. The
access-log option (real traffic, per route) was left out: it needs a new Host T component and an ACR. On vm-166:
nginx answered 504, the api's probe 200; `inc_46cdffa78fdb` DIAGNOSED with high confidence, root cause
`argus-lab-slow` (the model cited the upstream's 5 s answers and nginx's timeout), nginx the victim; no side alert;
resolved after the scenario went down. NO INTERFERENCE.
Consequences: SC-08 done; with SC-06 (T-0028) the planned scenarios of phase 11 are done. Both VMs run
`task/T-0029-vm-proof` `eebfa72`. Open: `http_errors_latency` (RB-011), the access-log metrics (ACR).
References: `tasks/completed/T-0029-sc08-nginx.md`, `execution/history/T-0029/step-02/evidence.md`.

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
References: `tasks/completed/T-0030-pg-restart.md`, `execution/history/T-0030/step-02/evidence.md`.

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
References: `tasks/completed/T-0028-sc06-cpu.md`, `execution/history/T-0028/step-02/evidence.md`.

## 2026-10-10 — OP-004: checkpoint retention dry run on vm-095; the owner secret is not root's (OP-004)

Type: verification + fix
Who: conantkd (+ agent)
Context: step 02 of OP-004, the dry run before any deletion; vm-095 lease only, the deployed checkout unchanged.
Decision / result: the first run stopped with `missing credential`: the owner secret on vm-095 is `0400`, owned by
uid 70 (the Postgres image's user), and the wrapper's root container has no capabilities to bypass that. The wrapper
now runs the container as the secret's owner. Then the 30-day dry run found nothing eligible; a 1-day preview counted
88 threads (783 checkpoints, 1825 blobs, 3900 writes). No row deleted, NO INTERFERENCE.
Consequences: the first `--apply` waits for a teammate's review of the counts; the timer stays uninstalled.
References: `tasks/current/OP-004-checkpoint-retention.md`, `execution/history/OP-004/step-02/evidence.md`.

## 2026-10-10 — OP-008: backup verify and prune dry run on vm-095 (OP-008)

Type: verification
Who: conantkd (+ agent)
Context: step 02 of OP-008 after the review notes of PR #51 (checksum-gated protection, leftovers listed).
Decision / result: `verify latest` restored `argus-20261010T023316Z.dump` in the throwaway container (`VERIFY OK`,
12 tables, 12225 rows) and wrote its marker. `prune` with the default `KEEP=7`: nothing to remove (four sets); a
`KEEP=2` preview lists the two oldest and keeps the verified one. No file deleted, NO INTERFERENCE.
Consequences: the first `prune --apply` waits for a teammate's review; scheduling stays a team decision.
References: `tasks/current/OP-008-backup-retention.md`, `execution/history/OP-008/step-02/evidence.md`.

## 2026-10-10 — LANES-1: one lease per VM

Type: implementation
Who: juanbetancurm (+ agent)
Context: PARALLEL_LANES (PR #52) change 1. One lease covered both VMs, so every VM run waited for one person.
Decision / result: `brain.py start --vm vm-095|vm-166|both` (default both); `session.json` keeps one lease per VM
under `vms`, and the old top-level fields as a summary, so a `brain.py` older than this one stays out of a VM someone
else holds. The old format holds both VMs: the lease held at the merge stays valid. 8 new tests (red seen); all 27
brain tests pass. This is the first journal entry written as its own file (PARALLEL_LANES change 2): the shared
summaries are not edited by this task.
Consequences: after the merge, `git pull` on `main`; claim only the VM you need. A change to the agent on vm-095
still needs both leases.
References: [`../tasks/completed/LANES-1-lease-per-vm.md`](../tasks/completed/LANES-1-lease-per-vm.md),
[`../policies/PARALLEL_LANES.md`](../policies/PARALLEL_LANES.md).

## 2026-10-10 — E2E-1: SC-04, SC-05, SC-06 in the runner catalogue

Type: implementation
Who: juanbetancurm (+ agent)
Context: phase 12 needs repeated runs; the three scenarios proven by hand on vm-166 (T-0020, T-0024, T-0028) were not
in `ops/e2e/scenarios.yaml`, so the runner could not repeat them.
Decision / result: the catalogue entries use the commands of the VM proofs and gate on the detector's own signal and
threshold. Resets remove only the lab container the scenario started (`rm -f`). 4 new test cases (red seen); the 36
runner tests pass. No VM was touched.
Consequences: a 5-run batch on vm-166 (step 2) needs that VM's lease. The shared summaries are left to the roll-up.
References: [`../tasks/completed/E2E-1-catalogue-sc04-06.md`](../tasks/completed/E2E-1-catalogue-sc04-06.md).

## 2026-10-10 — E2E-1 step 2: the runner's first batch on vm-166, 17/20 (E2E-1)

Type: verification
Who: juanbetancurm (+ agent)
Context: phase 12 asks for repeated runs. Both VMs on `main` `ebbe9c9`; vm-166's lease for the batch (the first use
of the lease per VM, LANES-1), vm-095's held by conantkd without touching the agent.
Decision / result: an SC-04 trial passed, then 5 runs each: SC-04 5/5, SC-06 5/5, SC-07 4/5, SC-05 3/5; 0 errors,
every reset clean, NO INTERFERENCE after every run. Detection, class and first runbook were right in all 20; the
misses are the model's: SC-07 once named the client instead of the backend (a wrong root cause), SC-05 twice
escalated without naming the filler (a safe abstention).
Consequences: read the three incidents' evidence before changing anything; then a second batch of SC-07 and SC-05,
and SC-02 when vm-095 is free. Phase 12: SC-01, SC-03, SC-04, SC-06 at 5/5.
References: [`../tasks/completed/E2E-1-catalogue-sc04-06.md`](../tasks/completed/E2E-1-catalogue-sc04-06.md),
[`../execution/history/E2E-1/step-02/evidence.md`](../execution/history/E2E-1/step-02/evidence.md).

## 2026-10-10 — T-0032: Prometheus down on one host (phase 13)

Type: verification
Who: conantkd (+ agent)
Context: phase 13 asks "partition ⇒ escalation for one host only"; T-0030 left Prometheus down on one host as next.
Decision / result: `tests/test_t0032_prometheus_down.py` (3, both runners and the real adapter; red seen by removing
the handling in each runner). On vm-095 Prometheus was stopped about 2 min: a vm-095 check ended UNDIAGNOSABLE
(`ConnectError`, no model call), a vm-166 check HEALTHY, no Argus container restarted, vm-095 HEALTHY after the start;
LAB BASELINE OK, NO INTERFERENCE. No code change was needed.
Consequences: no alert fires while a host's own Prometheus is down; a cross-host watcher or dead-man alert is a
follow-up. The shared summaries are left to the roll-up.
References: [`../tasks/completed/T-0032-prometheus-down.md`](../tasks/completed/T-0032-prometheus-down.md),
[`../execution/history/T-0032/step-02/evidence.md`](../execution/history/T-0032/step-02/evidence.md).

## 2026-10-10 — LANES-2: journal entries as files and brain.py rollup (LANES-2)

Type: implementation
Who: juanbetancurm (+ agent)
Context: PARALLEL_LANES change 2. Every PR of the 2026-10-10 merge queue needed a by-hand fix of the logbook,
CURRENT_TEST_STATE and NEXT_STEP, one after the other, because every task appends to them.
Decision / result: a task writes `journal/entries/<date>-<task>.md` (with optional `### Test state` and `### Next
step` sections); `brain.py rollup` folds the entries into the three files after the merges and removes them; `brain.py
lint` refuses those three edits on task branches made after this rule (roll-up branches and older branches exempt).
6 new tests (red seen); the roll-up was tried on a clean copy of `main`. Review fix (`conantkd`): the tests clear CI's
`GITHUB_HEAD_REF`, and a 7th pins the CI case (detached HEAD, PR branch from that variable).
Consequences: after the merge, agents write entry files; whoever merges last that day runs the roll-up on a
`task/rollup-<date>` branch.
References: [`../tasks/completed/LANES-2-journal-rollup.md`](../tasks/completed/LANES-2-journal-rollup.md).

## 2026-10-10 — E2E-1 step 3: the misses are two evidence gaps; batch 2 (E2E-1)

Type: verification
Who: juanbetancurm (+ agent)
Context: batch 1 missed SC-07 once and SC-05 twice. Before changing anything, the three incidents were read from the
store on vm-095 (read-only) and SC-07 and SC-05 ran 5 more times on vm-166.
Decision / result: SC-07 6/10 and SC-05 6/10 over both batches; 0 errors, NO INTERFERENCE. Not model noise: in SC-05
every disk read hit `/` (28 %) while the detector fired on the lab mount (92.6 %), so the model saw a contradiction
and escalated; in SC-07 the backend's assigned network exists only in comments, so the model guessed which container
was misplaced. The labels are right.
Consequences: E2E-2 (code): `host.disk_usage` without a mount reports every declared mount; the inventory declares each
container's networks and `container.status` shows a container that is not on them. Then a rebuild of vm-095's agent
(both leases) and 5 runs each of SC-05 and SC-07.
References: [`../execution/history/E2E-1/step-03/evidence.md`](../execution/history/E2E-1/step-03/evidence.md).

## 2026-10-10 — E2E-2: the model gets the facts it was missing in SC-05 and SC-07 (E2E-2)

Type: implementation
Who: juanbetancurm (+ agent)
Context: E2E-1 found SC-05 and SC-07 at 6/10 each; reading the incidents showed two evidence gaps, not model noise:
every disk read hit `/` while the detector fired on the lab mount, and the backend's assigned network was only a
comment.
Decision / result: `host.disk_usage` without a mount reads every declared mount; the inventory declares a container's
`networks` and `container.status` says when it is not on them (declared for SC-07's client and backend). 8 new tests
(red seen 6/8); the baseline evaluation is unchanged (hard 0 0 0).
Consequences: after the merge, rebuild vm-095's agent (both leases) and run SC-05 and SC-07 five times each.
References: [`../tasks/completed/E2E-2-evidence-gaps.md`](../tasks/completed/E2E-2-evidence-gaps.md).

## 2026-10-10 — E2E-2 follow-up: an unmounted disk is a stated fact, not a failed read (E2E-2)

Type: implementation
Who: conantkd (+ agent)
Context: #70's review. Without a mount `host.disk_usage` reads every declared mount, but one 409 from the host-probe
(the lab filesystem not mounted) failed the whole read, so the model would also lose `/`.
Decision / result: a mount that cannot be read is reported as `unavailable (<reason>)` and the others are still read;
the read fails only when every mount fails; an explicit mount fails as before; `source_time` is the oldest read. 4
tests (red seen 2/4). No VM step of its own: it ships with E2E-2's step 2 rebuild.
Consequences: SC-05's re-run is unaffected while the lab filesystem is mounted; when it is removed, the model still
sees the root disk and is told the lab mount is missing.
References: [`../tasks/completed/E2E-2-evidence-gaps.md`](../tasks/completed/E2E-2-evidence-gaps.md).

## 2026-10-10 — T-0031: the standing write-gate test (phase 8)

Type: implementation + verification
Who: conantkd (+ agent)
Context: §22.2 asks for a standing test in every build while no write is released, and a deployment check; phase 8
listed it as the open item.
Decision / result: `tests/test_write_gate_standing.py` injects four forms of a `container.restart` proposal on both
runners: always `no_action_escalated`, a security event, no approval or write node, no request beyond reads. Red seen
by three mutations (open gate accepted, an unoffered tool accepted, a write safety class registered).
`ops/write-gate-check.sh` (read-only) on vm-095: `WRITE GATE CLOSED` for agent, worker and scheduler; NO INTERFERENCE.
Step 3 (both leases): `--host-only` on vm-166, the Host T where §2 would place the action gateway: `WRITE GATE
CLOSED` (no action container, mount, variable or credential); the extended check again on vm-095: `WRITE GATE CLOSED`.
Consequences: phase 8's standing test is done. The code is stricter than §12 (`container.restart` is not registered at
all). The shared summaries are left to the roll-up.
References: [`../tasks/completed/T-0031-write-gate-standing.md`](../tasks/completed/T-0031-write-gate-standing.md),
[`../execution/history/T-0031/step-02/evidence.md`](../execution/history/T-0031/step-02/evidence.md),
[`../execution/history/T-0031/step-03/evidence.md`](../execution/history/T-0031/step-03/evidence.md).

## 2026-10-10 — E2E-2 step 2: SC-07 5/5, SC-05 4/5 after the agent rebuild (E2E-2)

Type: verification
Who: conantkd (+ agent)
Context: E2E-2 (#70, #71) gave the model the facts E2E-1 found missing: every declared mount in `host.disk_usage`, the
declared networks in `container.status`. They live in the agent image on vm-095.
Decision / result: with both leases, vm-166 to `main` (checkout only) and vm-095 backed up, on `main` `0f076f2` with
agent, worker and scheduler rebuilt (20/20 db checks, WRITE GATE CLOSED, NO INTERFERENCE). `run.py --runs 5 SC-05
SC-07`: SC-07 5/5, SC-05 4/5, 0 errors, NO INTERFERENCE after every run (before: 6/10 each). The one miss
(`inc_de65a12688bc`) read the right mount but not the filler's logs, so it named the host as root cause and said the
writer was unproven.
Consequences: both evidence gaps are closed. A new, smaller one is open: nothing but the logs links a container to
the filesystem it fills. The general fix, `container.status` reporting the container's host mounts, is
recorded as the pending task E2E-3 (not started).
References: [`../tasks/completed/E2E-2-evidence-gaps.md`](../tasks/completed/E2E-2-evidence-gaps.md),
[`../tasks/completed/E2E-3-container-mounts.md`](../tasks/completed/E2E-3-container-mounts.md),
[`../execution/history/E2E-2/step-02/evidence.md`](../execution/history/E2E-2/step-02/evidence.md).

## 2026-10-11 — E2E-3 step 1: container.status names the declared filesystems a container mounts (E2E-3)

Type: implementation
Who: juanbetancurm (+ agent)
Context: after E2E-2, SC-05 was 4/5: the one miss read the right mount but nothing linked the filler to it except its
logs (`conantkd`'s E2E-3 plan, PR #74).
Decision / result: the read-gateway's `inspect()` matches each bind to the host's declared mounts and returns only the
declared mount with `rw`/`ro` and a count of the other binds; `container.status` shows
`host_mounts=/srv/argus-lab-fill(rw)`. Matching in the gateway (not the catalogue) keeps every undeclared host path on
the VM. 5 new tests (red seen 4/5); the baseline evaluation is unchanged.
Consequences: after the merge, both leases: rebuild vm-166's read-gateway and vm-095's agent, then SC-05 × 5.
References: [`../tasks/completed/E2E-3-container-mounts.md`](../tasks/completed/E2E-3-container-mounts.md).

## 2026-10-11 — LANES-2 follow-up: the roll-up keeps the merge order within a day (LANES-2)

Type: fix
Who: juanbetancurm (+ agent)
Context: the first roll-up (PR #73) put the nine 2026-10-10 entries in file-name order (E2E-1 step 3 before steps 2
and 1); `conantkd` reordered them by hand and listed the follow-up.
Decision / result: `brain.py rollup` sorts by the date in the file name, then by when each entry reached the branch
(its first first-parent commit: on `main`, its PR's merge), then by name; an entry not committed yet comes last.
Replayed on `main` before #73, it gives exactly the order set by hand in #73. 1 new test (red seen).
Consequences: no hand reordering in the next roll-ups.
References: [`../tasks/completed/LANES-2-journal-rollup.md`](../tasks/completed/LANES-2-journal-rollup.md).

## 2026-10-11 — E2E-4: SC-08 in the runner catalogue (E2E-4)

Type: implementation
Who: juanbetancurm (+ agent)
Context: SC-08 (T-0029) was the one planned scenario the runner could not repeat.
Decision / result: its catalogue entry uses T-0029's start command and gates on the detector's own signal
(`http_gateway_error_ratio_5m` ≥ 0.5); the reset removes only `argus-lab-nginx` and `argus-lab-slow` (never
`compose down`). 2 new test cases (red seen); 37 runner tests pass.
Consequences: `run.py --runs 5 SC-08` on vm-166 (its lease) completes phase 12's catalogue except SC-10/SC-12.
References: [`../tasks/completed/E2E-4-catalogue-sc08.md`](../tasks/completed/E2E-4-catalogue-sc08.md).

## 2026-10-11 — E2E-3 step 2: both VMs on main with host_mounts; SC-08 5/5, SC-05 3/5 (the misses read) (E2E-3)

Type: verification
Who: conantkd (+ agent)
Context: #75 (the read-gateway names the declared host filesystems a container has mounted) and #77 (SC-08 in the
runner catalogue) merged; vm-166's target services and vm-095's agent needed a rebuild.
Decision / result: both VMs on `main` `e3286df` (backup `argus-20261011T131837Z.dump`, 20/20 db checks, WRITE GATE
CLOSED, LAB BASELINE OK, NO INTERFERENCE). Batch: SC-08 5/5, SC-05 3/5, 0 errors. Both SC-05 misses saw
`host_mounts=/srv/argus-lab-fill(rw)` and called the filler the likely writer, but named the host. They concluded
without reading the filler's logs, so the gap is a confirmation read, not a fact.
Consequences: proposed E2E-5, a rule-planned confirmation read of the suspected writer, as the next step.
References: [`../tasks/completed/E2E-3-container-mounts.md`](../tasks/completed/E2E-3-container-mounts.md),
[`../execution/history/E2E-3/step-02/evidence.md`](../execution/history/E2E-3/step-02/evidence.md),
[`../tasks/completed/E2E-5-confirm-writer.md`](../tasks/completed/E2E-5-confirm-writer.md).

## 2026-10-11 — E2E-5 step 1: confirm_then_reason, a rule-planned confirmation round (E2E-5, ACR-0007)

Type: implementation + architecture change
Who: juanbetancurm (+ agent)
Context: after E2E-3, SC-05 was 3/5: in both misses the model saw the filler mounting the full filesystem read-write,
called it the likely writer, and named the host without reading its logs (`conantkd`'s E2E-5 proposal, option 1).
Decision / result: a new strategy, `confirm_then_reason` (ACR-0007, architecture 1.8.6): the model loop, but when the
evidence names a suspect (a running container with the full declared filesystem mounted rw) the next round reads its
logs and resources by rule, once; `disk_pressure` uses it. No skeleton, domain, policy or capability change. 7 new
tests (red seen: no strategy; an end-to-end run through the skeleton reads the logs only with the new strategy).
Consequences: after the merge, rebuild vm-095's agent (both leases) and run SC-05 five times; then the `disk_pressure`
evaluation cases (a separate PR).
References: [`../architecture/changes/ACR-0007-confirm-then-reason.md`](../architecture/changes/ACR-0007-confirm-then-reason.md).

## 2026-10-11 — E2E-6 step 1: the runner queries vm-095's Prometheus inside its container (E2E-6)

Type: fix
Who: juanbetancurm (+ agent)
Context: the first SC-02 batch through the runner gave 5 × ERROR, `pre-gate never clean: … JSONDecodeError`. The
runner asked `127.0.0.1:18090` on the scenario's host; only vm-166 publishes its Prometheus there, vm-095's has no
host port. Nothing was started; NO INTERFERENCE after every run.
Decision / result: on vm-095 the gate's PromQL runs inside `argus-v18-prometheus` (`docker exec … wget`, the query
URL-encoded by the runner); vm-166 unchanged. Checked read-only on vm-095 first. No deploy change, no new port.
Tests: 2 new, red seen; runner tests 39/39.
Consequences: SC-02 × 5 can run (step 2, vm-095's lease).
References: [`../tasks/completed/E2E-6-prom-gate-vm095.md`](../tasks/completed/E2E-6-prom-gate-vm095.md).

## 2026-10-11 — EVAL-1: the disk_pressure cases and baseline rule (§21.2) (EVAL-1)

Type: implementation
Who: juanbetancurm (+ agent)
Context: `disk_pressure` was the one registered class still listed in `AWAITING_CASES` (T-0025 follow-up, quality
lane): §3 "Enablement" needs at least 5 labeled cases and a baseline to measure the model against.
Decision / result: 8 cases (`tests/eval/cases/disk-*.yaml`). Four where the right answer names the filler: it
writes the full lab filesystem read-write (report, check, full and no longer growing), and it has stopped but its logs
show it filled the mount (the data stays, so it is still the cause). Four where nobody can be named and the right
answer escalates: the writer stopped with no history in its logs, a read-only mount, the full filesystem is `/` while
the filler writes another, and the only rw writer has empty logs (a rw mount shows access, not who wrote the data).
The baseline reads the candidate's logs in a second round and names it only when exactly one running container writes
a full declared mount (E2E-5's `disk_suspects`) AND that read returned lines (Argus's own line count, never the log
text); else it escalates. The stopped writer with history is a declared baseline miss (`BASELINE_MISSES`): the baseline
names only running writers; reading that history is the model's job. `AWAITING_CASES` is empty. Baseline: 55 cases,
52 pass (the three declared misses), `disk_pressure` 7/8, hard 0 0 0.
Consequences: the model's run on these cases (vm-095, the configured model × 5) goes with the next evaluation batch.
References: [`../tasks/completed/T-0025-evaluation.md`](../tasks/completed/T-0025-evaluation.md).

## 2026-10-11 — E2E-6 step 2: SC-02 5/5 on vm-095 (E2E-6)

Type: test result
Who: juanbetancurm (+ agent)
Context: the runner's Prometheus gates on vm-095 now query inside `argus-v18-prometheus` (#81). SC-02 had given
5 × ERROR before.
Decision / result: `run.py --runs 5 SC-02` on vm-095's current agent (`e3286df`): 5/5 PASS, all
`container_restart_loop` → `argus-lab-worker`, RB-008. E2E-6 is done.
Tests: none (a VM batch).
Consequences: SC-02 passes Phase 12's five-run bar. The remaining Phase 12 scenario is SC-05, after #82 and vm-095's
agent rebuild on main (E2E-5).
References: [`../tasks/completed/E2E-6-prom-gate-vm095.md`](../tasks/completed/E2E-6-prom-gate-vm095.md).

## 2026-10-12 — EVAL-2: the configured model on all 55 evaluation cases, and the fixes it showed (EVAL-2, ACR-0008)

Type: test result + implementation + architecture change
Who: conantkd (+ agent)
Context: the model had run on 30 cases (2026-10-09); 25 more exist since (cpu, nginx, blind spot, dependency, disk).
Decision / result: on vm-095, in one-off containers (the running agent untouched): before 0.83 (core 0.87),
disk_pressure 0.45. Fixes: `confirm_then_reason` reads an exited writer's logs too (ACR-0008, architecture 1.8.7); a
system-prompt rule (a host-level symptom is not a root cause; three versions tried, the first two over-escalated); two
contradictory disk fixtures fixed (labels unchanged); each replay removes its throwaway store (275 runs filled the
container's 64 MiB /tmp). After, 5 trials: **0.93 (core 0.95), abstention 0.96, disk 0.97**, hard 0 0 0, NO
INTERFERENCE. The VMs' hostnames are now `argus-vm095` / `argus-vm166` (START_HERE updated).
Tests: 7 new in `tests/test_eval2_fixes.py` (red seen), E2E-5's "stopped is not a suspect" case moved there; full
suite green; baseline unchanged (52/55, the three declared misses).
Consequences: §3 "Enablement" now has a model measurement for every registered class. Per class against the baseline:
cpu, blind spot, postgres match; disk beats; nginx, dependency, restart loop, health are 0.04-0.20 under (escalations
and wording); the registry decision is the team's. A host-wide `docker image prune` ran during the clean-up (no
non-Argus change); next time remove the Argus image by name only.
References: [`../tasks/completed/EVAL-2-model-trials.md`](../tasks/completed/EVAL-2-model-trials.md),
[`../architecture/changes/ACR-0008-stopped-writer-suspect.md`](../architecture/changes/ACR-0008-stopped-writer-suspect.md).

## 2026-10-12 — T-0019 batch 2: the host-probe's diagnosis verbs (load, io, top processes, sockets, directory sizes, kernel OOM records)

Type: implementation + test result
Who: conantkd (+ agent)
Context: phase 3's last open item: the §4.6 `host-probe` verbs not built yet (batch 2 of T-0019; batch 3, files and
logs under the inspection policy, comes after).
Decision / result: step 01 (read-only, vm-166): the probe container already reads everything batch 2 needs (every
pid, pid 1's network namespace, PSI, `/sys/block`, `kern.log`) without a new mount or privilege. Design: six probe
routes, seven Level 2 capabilities; containers named by their 12-hex id (the probe has no Docker socket); kernel OOM
records from rsyslog's `kern.log` (no `journalctl` in the probe, `/dev/kmsg` needs `CAP_SYSLOG`).
Step 02 (code, tests first): six probe routes (`/load`, `/io`, `/processes`, `/sockets`, `/directory_sizes`, `/oom`)
and seven Level 2 capabilities with their policy lines; `container.status` shows the container `id=`;
`phase3_check` covers every new route. 30 new tests (29 red seen); full suite green except `test_mcp_child`'s timing
benchmark, which also fails on `main` on a loaded laptop.
Step 03 (both VMs): deployed and verified; four problems found and fixed, each test first: the 64 MiB probe was
OOM-killed answering (the log tail is now streamed, the walk capped at 20 000 entries: peak 22 MiB under parallel
load); the walk of `/` never reached `var/` (each child now gets a share of the budget); the worker and scheduler kept
the old image (the block now rebuilds agent, worker and scheduler together); in the evaluation the cases could not
answer the new tools, and once they could, the model concluded from a big file in the abstain disk cases (prompt rule:
where the space went is not who wrote it). The branch was rebased on `task/EVAL-2-model-trials` for that rule, so its
PR stacks on #89. Model, 5 trials on the 55 cases: **0.92 (core 0.95), abstention 1.00, disk 1.00, hard 0 0 0**
(EVAL-2 E.4: 0.93 (0.95), 0.96, 0.97). The new `get_kernel_oom_records` found a real OOM kill (the probe's own, row 1
of the evidence). Both VMs on `040b827`, `phase3_check` 55/55, NO INTERFERENCE.
References: [`../tasks/completed/T-0019-db-probe.md`](../tasks/completed/T-0019-db-probe.md),
[`../execution/history/T-0019/step-04/evidence.md`](../execution/history/T-0019/step-04/evidence.md).

## 2026-10-12 — AFTER-MERGE of #88, #89, #90: both VMs on main (AFTER-MERGE-T-0019)

Type: deploy
Who: juanbetancurm (+ agent)
Context: #88 (ACR-0007 accepted), #89 (EVAL-2, ACR-0008) and #90 (T-0019 batch 2, host-probe verbs) merged into
`main` `45dda69`, every one approved on its last push; CI all green, `main-guard` too. Both VMs ran
`task/T-0019-batch2-host-probe` `040b827`; the code difference to `main` was `argus/evaluation/replay.py` and tests.
Decision / result: both leases (session f3734af7cf36), the block modelled on `conantkd`'s S3.5. vm-166: `DEPLOY OK
45dda69`, 5 target services up. vm-095: backup OK, `DEPLOY OK 45dda69`, 4 target services up, agent, worker and
scheduler recreated together on one image (restarts 0), health 200, no startup errors, 20/20 database checks,
`phase3_check` 55/55, `disk_pressure strategy: confirm_then_reason`, both prompt rules present, WRITE GATE CLOSED. Both:
`ref=main`, LAB BASELINE OK, NO INTERFERENCE. Leases released.
Tests: none (a deploy).
Consequences: both VMs run `main` with EVAL-2 and the host-probe verbs.
References: [`../execution/history/AFTER-MERGE-T-0019/step-01/code.bash`](../execution/history/AFTER-MERGE-T-0019/step-01/code.bash).

## 2026-10-12 — E2E-5 step 2: SC-05 5/5 on vm-095 (E2E-5)

Type: test result
Who: juanbetancurm (+ agent)
Context: E2E-5 (#80, ACR-0007) makes `disk_pressure` read the suspected writer's logs and resources before the model
decides. SC-05 was 3/5 after E2E-3 (the misses named the host).
Decision / result: vm-095's agent, worker and scheduler on `main` `2a5f06b` (2026-10-11, all checks passed), then
`run.py --runs 5 SC-05`: 5/5 PASS, all `disk_pressure` → `vm-166/container:argus-lab-filler`, RB-005. The deploy ran
while `main-guard` was red and before ACR-0007's acceptance was on record (the user's decision); closed afterwards by
#86 and #88.
Tests: none (a VM batch).
Consequences: Phase 12's five-run bar is met for SC-05 (and SC-02, E2E-6). E2E-5 is done. ACR-0008 (#89) extends the
same round to an exited writer.
References: [`../tasks/completed/E2E-5-confirm-writer.md`](../tasks/completed/E2E-5-confirm-writer.md).

## 2026-10-12 — OP-012 step 1: the per-incident read limit holds under the LangGraph runner (OP-012)

Type: fix
Who: juanbetancurm (+ agent)
Context: `GraphRunner` built a fresh `InvocationContext` in every `act` / `evidence_pack` step and runs one read per
step, so the per-capability counters of `max_per_incident` (config/policy.yaml) restarted at zero for every read. A
scripted model asking `container.status` twice a step got 16 reads; the policy allows 8. The plain runner was right.
Decision / result: the graph runner rebuilds the counters from the incident's checkpointed evidence (executed reads
only), so the limit holds for the whole incident and across a resume. No ACR: the code now matches §12.4 and the
policy file.
Tests: 3 new (red seen), both runners and a resume; related suites 143 passed.
Consequences: the deployed agent gets the fix with its next rebuild on `main` (step 2, both leases).
References: [`../tasks/completed/OP-012-incident-read-budget.md`](../tasks/completed/OP-012-incident-read-budget.md).

## 2026-10-12 — EVAL-3 step 1: an exit 137 without an OOM kill escalates (EVAL-3)

Type: decision
Who: juanbetancurm (+ agent)
Context: EVAL-2 (#89) left `restart-sigkill-01` as "a RB-008 question": the model escalated it 5/5; the label wanted
`diagnosed` with the worker as root cause of a SIGKILL that came from outside.
Decision / result: RB-008 (written before the evaluation) keeps unexplained kills unresolved, so the label is now
`no_action_escalated` (abstain, no root cause) and the baseline escalates exit 137 without OOM. Fixtures unchanged. The
label changed after seeing the model's answers; recorded here and in the task, justified by RB-008's text.
Tests: 3 new (red seen); related suites 138 passed. Baseline unchanged: 52/55, hard 0 0 0.
Consequences: the model's escalation of an unexplained kill counts as right; `container_restart_loop` should rise in
the next evaluation batch.
References: [`../tasks/completed/EVAL-3-sigkill-label.md`](../tasks/completed/EVAL-3-sigkill-label.md).

## 2026-10-12 — T-0033 step 1: a rotated executor token is picked up without a restart (T-0033)

Type: feature
Who: juanbetancurm (+ agent)
Context: Phase 13 "token rotation". The target services and the agent's tools process read their tokens once, at
start; after a rotation every read of that executor was refused until the worker restarted.
Decision / result: the dispatcher re-reads a rejected executor token from its file and retries once if it changed;
the tools process and the direct mode wire it to `Settings.secret`. `ops/rotate-token.sh` rotates one token on a target
host (never printed, `.prev` kept, the one service recreated, `--rollback`). No ACR.
Tests: 4 new (red seen); full suite green locally (see the PR).
Consequences: a rotation becomes a short window of `forbidden` reads (escalations), then recovery without a restart.
References: [`../tasks/completed/T-0033-token-rotation.md`](../tasks/completed/T-0033-token-rotation.md).

## 2026-10-12 — T-0033 step 2: a token rotated on vm-166, picked up without a restart; #91–#95 deployed (T-0033)

Type: test result
Who: juanbetancurm (+ agent)
Context: T-0033 step 1 (#94) lets the tools process re-read a rejected executor token. Main `244453b` also carries
OP-012 (#92) and EVAL-3 (#93); the VMs ran `45dda69`.
Decision / result: vm-095's agent, worker and scheduler on `244453b` (backup, 20/20, 55/55, WRITE GATE CLOSED);
vm-166 checkout only. vm-166's `host_probe` token rotated with `ops/rotate-token.sh`: the agent's reads were refused
(`forbidden`, escalated, no crash) until its copy was replaced, then succeeded again with the worker not restarted.
Leases released. One correction while running (T.4's hash lines), recorded in the evidence.
Consequences: Phase 13's token rotation is covered for `docker_read`, `host_probe` and `network_probe`; `db_probe`
also needs its Prometheus scrape token and stays manual.
References: [`../tasks/completed/T-0033-token-rotation.md`](../tasks/completed/T-0033-token-rotation.md),
[evidence](../execution/history/T-0033/step-02/evidence.md).

## 2026-10-12 — EVAL-3 step 2: the model escalates the unexplained SIGKILL 5/5; 0.96 on the 55 cases (EVAL-3)

Type: test result
Who: conantkd (+ agent)
Context: EVAL-3 step 1 (#93) relabelled `restart-sigkill-01` `no_action_escalated` (RB-008). Step 2 runs the configured
model on the 55 cases, the first model run on `main` after OP-012 and T-0033.
Decision / result: vm-095, `ops/eval-run.sh` with its defaults (the deployed image and checkout, `main` `244453b`), 5
trials: 0.96 (core 0.99), abstention 0.98, `restart-sigkill-01` 5/5, restart loop 1.00, disk 1.00, hard 0 0 0.
`health_check_failed` 0.72 (8 of the 10 misses with `ambiguous-health-no-cause`), nginx 0.92. NO INTERFERENCE.
Consequences: EVAL-3 is done. The health class is the weakest: the "health check" wording question has numbers now.
References: [`../tasks/completed/EVAL-3-sigkill-label.md`](../tasks/completed/EVAL-3-sigkill-label.md),
[evidence](../execution/history/EVAL-3/step-02/evidence.md).

## 2026-10-12 — T-0019 batch 3a: the inspection policy (§4.7) before any file, journal or process read (T-0019)

Type: feature
Who: conantkd (+ agent)
Context: T-0019 batch 3 adds host-probe verbs that read files, service configuration, the journal and process details.
§4.7 says a per-target inspection policy decides what they may touch; none existed. Batch 3 is split in three PRs
(3a policy, 3b host verbs, 3c network verbs) so the policy is reviewed on its own.
Decision / result: `config/policy.yaml` gains `inspection:` (`files` empty everywhere; nginx's `default.conf` as
`service_config`; journal `docker.service`/`containerd.service` 200 lines; `processes` on both hosts; deny list;
`arbitrary_exec: false`). `argus/policy/inspection.py` decides each read (deny wins, a built-in deny floor, paths
refused unless already normal); the engine applies it as rule `inspection`; `build()` refuses entries outside the
inventory or the host's declared mounts; each probe's rendered config carries its host's part. `journal` will read
`/var/log/syslog` (rsyslog) filtered by unit, as `kern.log` in batch 2. No ACR (§4.7, §12.2).
Consequences: nothing reads the policy until 3b's verbs exist; no deploy for 3a alone. Touches what Argus may read: a
teammate's approval is required.
References: [`../tasks/completed/T-0019-db-probe.md`](../tasks/completed/T-0019-db-probe.md).

## 2026-10-12 — T-0033 follow-up: rotate-token.sh keeps the mode on a rollback and reports a failed recreate (T-0033)

Type: fix
Who: conantkd (+ agent)
Context: the review of #94 found two gaps in `ops/rotate-token.sh`, both on the error paths: `--rollback` left the live
token with `.prev`'s mode 0400, and a failed `docker compose` recreate was hidden and still reported "recreated".
Decision / result: the rollback writes `.prev`'s content into a new file with the live file's owner and mode; the
recreate's exit status is checked: on failure the script prints the error, says the service still holds the previous
token and how to roll back, and exits 1. The script takes `ARGUS_DEPLOY_HOME`, `ARGUS_DOCKER`, `ARGUS_HOSTNAME` for tests.
Consequences: no deploy needed (the script runs from the checkout; it reaches the VMs with the next `deploy.sh main`).
References: [`../tasks/completed/T-0033-token-rotation.md`](../tasks/completed/T-0033-token-rotation.md).

## 2026-10-12 — E2E-8 planned: close Phase 12 (five runs of every scenario) for juanbetancurm (E2E-8)

Type: decision
Who: conantkd (+ agent)
Context: Phase 12 is at 80 %: SC-01 … SC-08 are 5/5; H-1, H-2, SC-09, SC-11 ran once; SC-10, SC-12 and the identity
proof are not in the runner catalogue (they stop Argus's own services, or need two incidents at once).
Decision / result: task file `E2E-8-phase12-close.md` written for `juanbetancurm`: prerequisites (the merge order of
#97–#103 and an AFTER-MERGE of both VMs to `main`), the catalogue entries for SC-10, SC-12 and the identity proof
(tests first; the identity proof needs a small runner change), and five runs of each.
Consequences: Phase 12 reaches 100 % when every line is 5/5. `conantkd` released both leases after T-0019 step 08.
References: [`../tasks/current/E2E-8-phase12-close.md`](../tasks/current/E2E-8-phase12-close.md).

## 2026-10-12 — EVAL-4: health diagnoses may name the failing check in other words; strict accuracy 0.96 → 0.99 (EVAL-4)

Type: fix
Who: conantkd (+ agent)
Context: EVAL-3 step 2 (#99): `health_check_failed` 0.72 strict, 0.99 core overall; 6 of the 8 health misses had the
right root cause and class but wrote "health probe" or "unhealthy" instead of "health check".
Decision / result: the five health cases accept `health check`, `healthcheck`, `health probe`, `unhealthy` (relabelled
after seeing the answers, disclosed). New `argus.evaluation.regrade` grades a stored results file again without a model
call. EVAL-3 step 2's 275 runs: 265 → 271 passed, 0.96 → 0.99 (core 0.99), health 0.72 → 0.96; the old labels
reproduce the run's own summary exactly.
Consequences: the health wording question is closed. Real misses left: one health escalation with the cause in the
logs, one abstain miss, two nginx runs without the upstream as root cause.
References: [`../tasks/completed/EVAL-4-health-wording.md`](../tasks/completed/EVAL-4-health-wording.md).

## 2026-10-12 — EVAL-5: the model sees which URL and port each target allows (EVAL-5)

Type: fix
Who: conantkd (+ agent)
Context: EVAL-3 step 2 and T-0019 batch 3c: `check_http_endpoint` was called 11 times on `argus-lab-slow`, which has
no HTTP endpoint in the inventory (TCP 8080 only); every call failed as `invalid_args`, and the three nginx misses
escalated or named no root cause after it ("the direct probe was invalid").
Decision / result: `InvestigationView.allowed_values` carries, per target in scope, the inventory's `http_endpoints`
(`url`) and `tcp_ports` (`port`), filled by both runners. In the tool definitions, a probe with such an argument is
offered only on targets with allowed values, the argument gets an enum, and the description lists them ("Allowed:
vm-166/container:argus-lab-nginx: http://argus-lab-nginx:8080/"). A probe with no allowed target is not offered.
Consequences: the model can no longer ask a URL or port the probe would refuse. Not yet measured with the model (both
leases were released; the next evaluation batch on vm-095 measures it, nginx cases first).
References: `argus/tooling/model_harness.py`, `argus/orchestration/runner.py`.

## 2026-10-12 — T-0034: combined capabilities (§12.7) and the first one, the diagnostic snapshot (T-0034)

Type: feature
Who: conantkd (+ agent)
Context: §12.7's combined capabilities had no mechanism (T-0019 3c chose not to build it for one network verb).
Decision / result: `CapabilitySpec.max_subcalls`; `InvokeCapability` runs a combined capability with a read-only
sub-invoker: each sub-read goes back through `InvokeCapability` (caller `capability:<name>`, shared budget, policy,
audit, evidence); past `max_subcalls` or nested = refused and audited; the result references its sub-reads, and both
runners keep them as citable evidence (`refs_of`). First use `analysis.diagnostic_snapshot` (Level 3, 6 sub-reads),
offered to no class until an evaluation batch measures it. No ACR (§12.7 as written).
Consequences: Phase 4's open item (combined capabilities) has its mechanism; `analysis.timeline` and
`analysis.trace_request_path` can follow on it.
References: [`../tasks/completed/T-0034-combined-capabilities.md`](../tasks/completed/T-0034-combined-capabilities.md).

## 2026-10-12 — T-0019 batch 3b: file, configuration, journal and process reads under §4.7; phase 3 complete (T-0019)

Type: feature
Who: conantkd (+ agent)
Context: batch 3a (#98) put the §4.7 inspection policy in `config/policy.yaml`; batch 3b adds the host-probe verbs
that use it. EVAL-3 step 2 and 3c: nginx misses where the model could not see the configured timeout.
Decision / result: four Level 3 capabilities (`host.read_file`, `host.service_config`, `host.journal`,
`host.process_details`); the probe re-checks the policy from its rendered copy (same rules, a parity test), refuses
symbolic links and non-regular files, bounds lines and bytes; the journal is rsyslog's text by program; process details
never read `cmdline` or `environ`. Only `host.service_config` is offered (to `nginx_upstream_failure`). The six nginx
cases answer it with the lab's `default.conf`. Every `host-probe` verb of §4.6 now exists: phase 3 is complete.
Consequences: verified on both VMs before the merge; the PR is stacked on #98.
References: [`../tasks/completed/T-0019-db-probe.md`](../tasks/completed/T-0019-db-probe.md).

## 2026-10-12 — T-0019 batch 3c: why two containers cannot reach each other, and repeated TCP (T-0019)

Type: feature
Who: conantkd (+ agent)
Context: batch 3 split in 3a (inspection policy, #98), 3b (host verbs) and 3c (network verbs). SC-07 (T-0018): the
model sees a failing DNS/TCP from the app network, and has to infer from two statuses that the backend sits on
another network.
Decision / result: `network.connectivity` (Level 2, read gateway `GET /connectivity`): both sides' networks and the
shared ones, names only; offered to `dependency_unavailable` only. `network.tcp_connect` takes `attempts` (1-5) with
each attempt's latency. Option A2 (decided by `conantkd`); the §12.7 combined capability was not built for one use.
`listening_ports` is left out (it needs a container's network namespace: two executors). The 6 dependency evaluation
cases answer the new route from their own status fixtures.
Verified on both VMs (`030690a`, both leases): the routes from the host, the agent's code path, and the model on the
55 cases × 5: 0.96 (core 0.99), hard 0 0 0; `check_connectivity` used in 25 runs; SC-07's case read in 2 reads with
the cause stated (4.16 → 3.40 reads per dependency run). LAB BASELINE OK, NO INTERFERENCE.
Consequences: both VMs run the branch until it merges (then AFTER-MERGE to `main`).
References: [`../tasks/completed/T-0019-db-probe.md`](../tasks/completed/T-0019-db-probe.md).

## 2026-10-12 — The redactor masks secrets, not file paths (REDACT-paths)

Type: fix
Who: conantkd (+ agent)
Context: T-0019 batch 3b step 08: `inspect_service_config` on vm-095 showed nginx's configuration path as
`/[REDACTED HIGH-ENTROPY].conf`; the high-entropy rule (40+ characters of `[A-Za-z0-9+/_=-]`) took
`opt/argus-v18/app/deploy/lab/nginx/default` for a token.
Decision / result: a high-entropy match that is a run of lower-case path segments (at most 32 characters each, no `+`
or `=`, optionally after `key=`) is left as is; everything else is masked as before. On all 853 fixture strings of the
55 evaluation cases the new redactor gives exactly the old output; tokens (mixed case, base64, long hex) stay masked.
Consequences: paths in observations (configuration files, mounts, logs) reach the model readable.
References: `argus/capabilities/redaction.py`, `tests/test_redaction_paths.py`.

## 2026-10-12 — ACR-0009 proposed: a monitoring heartbeat per host (ACR-0009)

Type: decision
Who: conantkd (+ agent)
Context: Phase 13's last item (T-0032's "not covered"): when a host's Prometheus stops, nothing tells anyone, and the
host's application alerts expire after about 4 minutes, so `resolve_absent` (ACR-0005) records resolutions that never
happened and closes queued incidents `resolved_externally`.
Decision / result: ACR-0009 proposed (document only). An always-firing `ArgusMonitoringHeartbeat` alert per host,
checked on every reconcile tick by renewal (`updatedAt`, `endsAt`), not presence, silences included; a lost heartbeat
opens one incident per host and episode (`monitoring_blind_spot`, RB-014, "Host monitoring unavailable"), escalated at
once with no run and no model call; no resolution of that host's alerts while lost; recovery after two fresh ticks;
explicit, time-bounded maintenance by CLI; state in Postgres; a bounded readiness read of the host's Prometheus to
refine the cause. Alternatives (cross-host watching, direct Prometheus polling, relying on investigations, a new class)
recorded in the ACR.
Consequences: implementation T-0035 after acceptance, in its own PR (it applies the ACR to `ARCHITECTURE.md`, 1.8.8),
then a VM proof with both leases.
References: [`../architecture/changes/ACR-0009-monitoring-heartbeat.md`](../architecture/changes/ACR-0009-monitoring-heartbeat.md).

## 2026-10-12 — brain.py lint lets a task branch merge main after a roll-up (LINT-merge-base)

Type: fix
Who: conantkd (+ agent)
Context: merging `main` into #101 and #103 (after the roll-up #97) was refused by the pre-commit lint: "a task branch
does not edit the shared summaries" for `logbook.md`, `CURRENT_TEST_STATE.md` and `NEXT_STEP.md`. While `git merge`
is in progress HEAD is still the branch's old tip, so `merge-base(HEAD, origin/main)` is the old base and the
summaries changed by main's roll-up looked like the branch's own edits. Any task branch merging `main` after a
roll-up hits it.
Decision / result: `summary_edits` judges from `MERGE_HEAD` when a commit of `main` is being merged: only what the
branch changes on top of it counts. A summary edited by the branch during the merge is still refused. Not skipped with
`--no-verify`: the merges of #101 and #103 wait for this fix.
Consequences: touches the enforcement (`brain.py`): needs a teammate's approval. After the merge, `main` is merged into
#103 and #101.
References: `brain/tools/brain.py` (`summary_edits`), `tests/brain/test_brain.py`.

## 2026-10-12 — Local CI: the checks of ci.yml on a laptop when GitHub Actions does not run (LOCAL-CI)

Type: process
Who: juanbetancurm (+ agent)
Context: the runs on `main` after #103, #101 and #107 did not start (GitHub Actions jobs "not started"). The merges
had been checked on a laptop (full suite, lint, render, `verify-main` on `5b01397`), but nothing in the protocol said
how, or what counts as the merge check then.
Decision / result: `ops/local_ci.py` runs the steps of `.github/workflows/ci.yml` on an exact commit (a PR's last push
in a clean temporary worktree, `origin/main` with `verify-main`, or a clean HEAD) and prints one `LOCAL CI PASS|FAIL
<commit>` block; `--post` comments it on the PR. A missing tool is `skipped`, never a pass; a test that fails in the
full run and passes alone is `flaky`; a test on the `KNOWN_LOCAL` list (failing only on a laptop, today the MCP timing benchmark) is `known-local`, named. `REVIEW_PROTOCOL.md` ("When CI does not run"): the reviewer's `LOCAL CI PASS`
comment on the approved commit replaces the green CI in the merge check; after merging, `--main` replaces
`main-guard`. `TDD.md` stages 5-6 and `AGENT_PROTOCOL.md` point to it.
Consequences: every developer and agent follows the same steps while Actions does not run; when it runs again, its CI
is the merge check again.
References: `ops/local_ci.py`, `tests/test_local_ci.py`, `brain/agents/REVIEW_PROTOCOL.md`.

## 2026-10-12 — AFTER-MERGE: both VMs on main d34f0cb (#97–#111)

Type: deployment
Who: conantkd (+ agent; the agent ran the blocks over ssh)
Context: the VMs ran `task/T-0019-batch3b-host-verbs` `9ac49ec` (3a + 3b) while #97–#111 were merged. `juanbetancurm`
asked in #110 not to deploy `main` before #110 (redactor: only declared paths readable) and #109 (`/tcp` 8 s budget).
Both merged; #111 (local CI) adds only `ops/local_ci.py` and docs.
Decision / result: both VMs on `main` `d34f0cb`: target services rebuilt on both; on vm-095 one backup, then agent,
worker and scheduler recreated together on one image. Checks: 20/20 database, 55/55 phase 3, write gate closed,
LAB BASELINE OK and NO INTERFERENCE on both; the 3c routes and the agent's 3c reads answer; the snapshot is in the
catalogue; the redactor keeps the declared nginx path and masks a URL-path secret.
Consequences: the deployment matches `main` again. Next on the VMs: measure EVAL-5 and the snapshot (model calls).
References: [evidence](../execution/history/AFTER-MERGE-main/step-01/evidence.md), session `4f8a9d4f8dc1`.

## 2026-10-13 — The redactor keeps only the paths Argus declared readable (REDACT-declared-paths)

Type: fix
Who: juanbetancurm (+ agent)
Context: #107 (REDACT-paths) left every run of lower-case path segments unmasked, so the nginx configuration path of
T-0019 3b reached the model readable. The review of #107 found that it also let lower-case secrets in URL paths
through (an API key in `/api/v1/keys/<32 hex>`, a webhook URL, a presigned download path), which `main` before #107
masked. #107 was merged on the condition that this is fixed before `main` is deployed to the VMs.
Decision / result: `Redactor(declared=...)` sets aside only the paths Argus itself declared before the high-entropy
rule and puts them back after it: the inspection policy's `service_config` and `files` entries and the inventory's
mounts (as directories; `/` declares nothing), from `wiring.declared_paths`, in both places the redactor is built
(`build`, `tools_dispatcher`). Every other path is masked as before #107. On the 899 fixture strings of the
evaluation cases, the new redactor differs from the one before #107 only on the 6 strings that are the declared nginx
`default.conf` path.
Consequences: the nginx configuration path stays readable for the model; a secret in any undeclared path is masked
again. Declaring a new `files` entry in the policy also makes its path readable.
References: `argus/capabilities/redaction.py`, `argus/infrastructure/wiring.py`, `tests/test_redaction_paths.py`.

## 2026-10-13 — Task files brought up to date with the merged pull requests

Type: process
Who: conantkd (+ agent)
Context: many files in `tasks/current/` still said `in progress`, `in review` or "waits for review" after their pull
requests had merged (checked against GitHub's merged list, #7-#112); two ACRs applied to the architecture still said
`proposed`.
Decision / result:
- 31 finished tasks moved to `tasks/completed/` with their final status and PR numbers (the rule in
  `tasks/completed/README.md`); every link to them rewritten (`lint` clean).
- 5 stay in `tasks/current/`: E2E-8 (planned, `juanbetancurm`), OP-004 and OP-008 (the first `--apply` waits for a
  teammate's review of the dry run), T-0016 (Playwright, the network guard and the contract check still open,
  `juanes6554`), T-0019 (its deny-floor follow-up #114 is in review). OP-004's status said "VM dry run pending": it
  was done 2026-10-10.
- T-0023 step 3 is done through E2E-1 to E2E-6 (SC-01 to SC-08 at 5/5); E2E-4's step 2 was E2E-3 step 2's SC-08 5/5.
- ACR-0003 `accepted` (`juanbetancurm`'s approval of #45, 2026-10-09) and ACR-0008 `accepted` (approval of #89,
  2026-10-12): both were already applied (architecture 1.8.3 and 1.8.7).
- The class-registry question of T-0025 and EVAL-2 is now an open decision of its own: D-003 in `OPEN_PROBLEMS.md`.
  OP-001 there: PR #44 merged.
Consequences: Brain only, no code. Done on the roll-up branch because `NEXT_STEP.md` links to some of the moved files.
References: `brain/tasks/completed/`, `brain/OPEN_PROBLEMS.md` (D-003).

## 2026-10-12 — REDACT-declared-boundary: a declared path counts only where a path starts (review of #110)

Type: fix
Who: conantkd (+ agent)
Context: the non-blocking finding of the #110 review. A declared directory was matched anywhere in the text and kept
everything under it, so these stayed unmasked: `https://hooks.example.com/srv/argus-lab-fill/<40-char token>` (the
declared directory inside a URL), `/evil/srv/argus-lab-fill/<token>` (after another path) and
`/srv/argus-lab-fill/<token>` (a token as a name under the declared directory).
Decision / result: in `Redactor._kept`:
- a declared file or directory counts only where a path starts: the character before it is not a path or URL
  character (`[A-Za-z0-9._/:~%-]`); `path=`, a quote, a bracket or a space before it are fine;
- under a declared directory the kept span stops before the first segment that holds a token (40+ token characters):
  the high-entropy rule masks that segment, the declared prefix stays readable.
Consequences: stricter only; every declared path written at a path start reads as before. Touches redaction (a safety
principle): needs a teammate's approval.
References: `argus/capabilities/redaction.py`, `tests/test_redaction_paths.py`.

## 2026-10-12 — T-0019: the inspection deny floor closed before any path is added to `files` (review of #98 / #103)

Type: fix
Who: conantkd (+ agent)
Context: `juanbetancurm`'s non-blocking notes on #98 (3a) and #103 (3b): close the gaps of the built-in deny floor
before any path is added to a `files` allowlist; open with `O_NOFOLLOW` in the probe's `_real_file`; the flaky `NOW`
in `tests/test_t0019_host_probe_batch2.py`. Today every `files` list is empty, so no read was exposed.
Decision / result:
- `BUILTIN_DENY` adds `/proc/`, `/var/lib/docker/`, `/etc/shadow-`, `/etc/gshadow`, `/etc/gshadow-`, `/etc/sudoers`,
  `/etc/sudoers.d/`, `.ssh`, `id_*`, `*.env`, `*token*` (was only in the data).
- A pattern without `/` now matches **any component** of the path, not only the file name (`/srv/tokens/x`,
  `~/.ssh/config` were allowed). Case-insensitive as before.
- The probe carries the same floor (`INSPECT_FLOOR`, a test keeps it equal to `BUILTIN_DENY`) and applies it whatever
  its rendered `target.json` says.
- `_real_file` opens with `O_NOFOLLOW` and checks "regular file" on the open descriptor: a link put in place between
  the walk and the open is refused (ELOOP → 403). It returns the open file; `_tail` and `service_config` read from it.
- `now` is a fixture taken when each OOM test starts (a ~10-minute suite moved the 50-minute-old record out of the
  60-minute window).
- `deploy/target/config/*.json` re-rendered (only the `deny` list changes).
Consequences: touches a safety principle (secrets, host inspection): needs a teammate's approval. The VMs get the new
probe and config at the next AFTER-MERGE (needs the lease). Kept local until CI ran again.
References: `argus/policy/inspection.py`, `services/target/service.py`, `tests/test_t0019_batch3b_host_verbs.py`,
`tests/test_t0019_host_probe_batch2.py`.

## 2026-10-12 — LOCAL-CI: every mode checks a clean worktree of the commit (review of #111)

Type: fix
Who: conantkd (+ agent)
Context: the #111 review. Without `--pr` / `--main`, `ops/local_ci.py` ran the checks in the developer's own checkout,
so gitleaks (`--no-git`, a directory scan) also read the checkout's ignored files (`.venv`, `node_modules`,
`brain/execution/current/output.bash`): false positives, and files that are never committed were scanned. The other
note of that review ("PASS when every step is skipped") was overstated: `audit`, `lint` and `tests` never skip (they
need only Python); only `secrets`, `promql` and `frontend` can, and the protocol leaves those to the reviewer. Not
changed.
Decision / result: every mode checks a temporary `git worktree` of the commit (HEAD needs a clean working tree, as
before; the PR's last push or `origin/main` as before), removed at the end.
Consequences: the HEAD mode now sees exactly the commit's files, as CI does; it installs the frontend's packages in
the worktree (`npm ci` did that already).
References: `ops/local_ci.py` (`_commit`, `main`), `tests/test_local_ci.py`.

## 2026-10-12 — T-0035 step 1: the monitoring heartbeat per host (ACR-0009), code and architecture

Type: feature
Who: conantkd (+ agent)
Context: ACR-0009 accepted by `juanbetancurm` in #108, with three notes: measure the real `updatedAt` renewal before
fixing `stale_after` (a kept-but-not-renewed copy is the important test); two consecutive fresh ticks for recovery
and to leave the startup grace; the verification includes a queued application incident that stays open.
Decision / result: the heartbeat rule on every host; `AlertNotification.updated_at`; `MonitoringWatch` in the
reconcile tick (fresh / starting / alive / lost, one escalated incident per episode with no run and no model, two
fresh ticks to recover); no resolution on a tick without a fresh heartbeat; the heartbeat never reaches intake; state
per host (migration 006, both stores); `argus monitoring maintenance`; `ARCHITECTURE.md` 1.8.8 (§6.4, §7.3); the
ACR marked accepted and applied. The check ships **off** (`monitoring_heartbeat.enabled: false`) until the rule is on
both hosts.
One correction to the first version: it stopped resolving only once the loss was declared, so an application incident
was resolved in the minutes between the last renewal and the loss. The ACR's rule is "while its heartbeat is not
fresh"; `observe` now blocks resolution on every tick without a fresh heartbeat.
Consequences: step 2 needs both leases (migration, the rule on both Prometheus, the scheduler; measure `updatedAt`
before turning the check on); step 3 verifies it as T-0032 did.
References: [task](../tasks/completed/T-0035-monitoring-heartbeat.md), [ACR-0009](../architecture/changes/ACR-0009-monitoring-heartbeat.md).

Added 2026-10-13: the loss incident also enqueues its escalation notification (§15.2), which the first
version forgot (it is stored already escalated, so the runner's `record` never sees it).

## 2026-10-13 — T-0041: `rotate-token.sh` rotates `db_probe` (and Prometheus's copy)

Type: feature
Who: conantkd (+ agent)
Context: T-0033 left the `db_probe` rotation manual: vm-166's Prometheus scrapes the db-probe with the same token.
Decision / result: `rotate-token.sh db_probe` writes the new token to the service's and to Prometheus's copy (owner and
mode kept), recreates the service, and a rollback restores both; no Prometheus copy = no change. Prometheus reads the
file at every scrape: no restart.
Consequences: Phase 13's last open rotation; a real rotation on vm-166 after the merge.
References: [task](../tasks/current/T-0041-db-probe-rotation.md).

## 2026-10-13 — EVAL-6: the health endpoint / handler named counts as naming the failing check

Type: evaluation label
Who: conantkd (+ agent)
Context: of the 10 misses of the evaluation on `main` `d34f0cb` (EVAL-main, #118), two were right diagnoses of
`health-api-vm166-01` (trials 2 and 3: "its health endpoint returns HTTP 500 because settings.load() raises KeyError:
'FEATURE_FLAGS'"; "failing its health handler") graded as misses because the wording list (EVAL-4) had only "health
check", "healthcheck", "health probe", "unhealthy". The case's failing check is the Docker health check that calls
that endpoint.
Decision / result: the five health cases also accept "health endpoint" and "health handler". The outcome, class and
root-cause target are still required. Re-graded without a model call (`argus.evaluation.regrade`):

| run | before | EVAL-6 |
|---|---|---|
| `main` `d34f0cb` (EVAL-main) | 0.96 (265/275), health 0.88 | **0.97 (267/275), health 0.96** |
| snapshot offered (EVAL-snapshot, #121) | 0.94, health 0.72 | 0.94, health 0.72 (its misses are escalations) |

The other misses, left as they are: `dep-backend-wrong-network` ×2 (the model blames the client, not the backend on
the wrong network: `network.connectivity` does not say which side is off its inventory-assigned network — a
capability improvement for later); `nginx-slow-check` ×2 (nginx's 2 s timeout vs the upstream's 5 s: a label question
for the team); four abstentions / an exhausted step budget (model behaviour).
Consequences: health is no longer the weakest class on `main`; the snapshot decision (#121) stands.
References: `tests/eval/cases/health-*.yaml`, `tests/test_eval4_health_wording.py`.

## 2026-10-13 — EVAL on main d34f0cb: 0.96 (core 0.97), abstention 0.98, hard 0 0 0

Type: evidence
Who: conantkd (+ agent)
Context: after the AFTER-MERGE of #97–#111 (both VMs on `main` `d34f0cb`), the configured model on the 55 evaluation
cases, 5 trials, as at T-0019 3c step 07.
Decision / result: 265 / 275 passed; accuracy 0.96 (core 0.97), abstention 0.98, recall@3 1.00, 3.8 reads per
incident, hard metrics 0 0 0. Same overall accuracy as step 07; dependency and nginx one run lower each (0.92),
health 0.88. Within the noise of 5 trials; no class regressed by more than one run.
Consequences: `main` is a good baseline for the snapshot measurement (offering `capture_diagnostic_snapshot` to a
class) and for T-0035. Follow-up: the two `dep-backend-wrong-network` misses, from the results file on vm-095.
References: [evidence](../execution/history/EVAL-main/step-01/evidence.md).

## 2026-10-13 — EVAL-snapshot: the snapshot offered to health_check_failed lowers it (0.88 → 0.72); not offered

Type: evidence / decision
Who: conantkd (+ agent)
Context: T-0034 offered `capture_diagnostic_snapshot` to no class until measured.
Decision / result: offered to `health_check_failed` on a branch and measured against `main` (55 cases, 5 trials, same
model): the model used it in 19 of 25 health runs, read more (7.8 vs 4.6 per run) and escalated more:
`health_check_failed` 0.88 → 0.72, overall 0.96 → 0.94, hard 0 0 0 both. The offer is reverted; the snapshot stays in
the catalogue, offered to no class.
Consequences: the same rule for the other new reads (T-0036–T-0039): each offered to a class only with a batch that
shows it helps.
References: [evidence](../execution/history/EVAL-snapshot/step-01/evidence.md).

## 2026-10-13 — ACR-0010 proposed: a combined capability may read the current incident's own record

Type: architecture proposal
Who: conantkd (+ agent)
Context: `analysis.timeline` (`correlate_incident_timeline`) is the last §12 read capability not built. It needs the
incident's alert occurrences and stored evidence references, which a combined capability cannot reach (§12.7 gives
it `read` only).
Decision / result: proposed: the §12.7 invoker gains `incident_record()` — the current incident's alerts and evidence
references only, read-only, redacted, counted against `max_subcalls`, audited; then `analysis.timeline` on it.
Alternative D (drop the capability from §12) is offered to the reviewer.
Consequences: nothing is implemented before acceptance.
References: [ACR-0010](../architecture/changes/ACR-0010-incident-timeline.md).

## 2026-10-13 — E2E-8 step 1: SC-10, SC-12 and the identity proof in the runner's catalogue

Type: feature
Who: conantkd (+ agent), on `juanbetancurm`'s E2E-8 plan
Context: Phase 12 needs five runs of every scenario through `ops/e2e/run.py`; SC-10, SC-12 and the identity proof
were not in the catalogue (they stop Argus's own services or need two hosts at once).
Decision / result:
- The runner takes commands and gates on another host (`{host: ..., run: ...}`, gate `host:`), lists of gates, and
  several investigations per run, sent together and each graded; every touched host must be in `hosts`.
- SC-10 stops vm-095's `argus-v18-node-exporter` (the `monitoring_blind_spot` class of T-0027), not the gate exporter
  of the LGS run (that one ends `undiagnosable` before any class). SC-12 stops vm-166's read gateway during SC-01's
  loop: escalated, never `diagnosed`, and vm-095 still answers. ID-1 runs SC-01 and SC-02 together through YAML
  anchors. Their reset starts the stopped service first.
- `on:` was the first key name for a command's host: PyYAML (YAML 1.1) reads it as `true`; renamed `host:`.
Consequences: no VM change; the runs (E2E-8 step 2) need both leases.
References: `ops/e2e/run.py`, `ops/e2e/scenarios.yaml`, `tests/test_e2e8_catalogue.py`.

## 2026-10-13 — T-0036 step 1: CPU, disk and network histories (§12 Level 2)

Type: feature
Who: conantkd (+ agent)
Context: §12 lists `get_cpu_history`, `get_disk_history` and `get_network_history` next to `get_memory_history`;
only memory and restarts existed.
Decision / result: three signal templates and three capabilities on the `_history` pattern (Level 2, safe,
`prometheus`, `max_per_incident` 4): CPU per container (cores) or host (busy share), disk over the host's declared
mounts (none = NO DATA), network per container (bytes/s). `PrometheusClient` fills `$mounts` from the inventory,
plain paths only. Offered to no class until measured.
Consequences: no architecture change; step 2 reads them on the VMs from a one-off container.
References: [task](../tasks/current/T-0036-metric-histories.md).

## 2026-10-13 — T-0038 step 1: `compare_incident_baseline` (§12 Level 3)

Type: feature
Who: conantkd (+ agent)
Context: one of the four §12 capabilities still missing after T-0036 and T-0037.
Decision / result: `metrics.compare_baseline`: a named metric (memory, cpu, restarts, disk, network) now and over the
same window 1 h / 24 h / 3 d earlier; mean, max and the change; the signal chosen by the target kind, an impossible
pair refused; no stored baseline. `PrometheusClient.range` takes `end_offset_s`. Offered to no class.
Consequences: stacked on T-0036 (#119); no architecture change.
References: [task](../tasks/current/T-0038-compare-baseline.md).

## 2026-10-13 — T-0040: `trace_request_path` (§12 Level 3, combined)

Type: feature
Who: conantkd (+ agent)
Context: one of the last two §12 capabilities (with `analysis.timeline`).
Decision / result: a combined capability on T-0034's mechanism: per declared same-host container dependency (≤ 3),
`container.status`, `network.connectivity` and `network.resolve_dns`, each through `InvokeCapability`; other-host or
host dependencies listed, never read. Offered to no class. TCP to the dependency's port left out (the impl does not
see the dependencies' inventory entries).
Consequences: `analysis.timeline` needs alerts and stored evidence inside a combined impl, which extends the §12.7
invoker (`read` only today): a design decision for the team, not taken here.
References: [task](../tasks/current/T-0040-trace-request-path.md).

## 2026-10-13 — T-0042: escalation routing as data (`routing.yaml`, §15.2)

Type: feature
Who: conantkd (+ agent)
Context: §15.2 and §4 name `config/routing.yaml`; it did not exist, so an escalation's notification did not say where
it went (Phase 8, "routing data").
Decision / result: `Routing` (alert name, then class family, else default; `channel:` or `peer:` targets), validated
at startup; `config/routing.yaml` sends everything to `channel:operators` (as before); every escalation notification
carries `route`.
Consequences: no architecture change; a team or a peer agent gets its share by editing the file.
References: [task](../tasks/completed/T-0042-routing.md).

## 2026-10-13 — T-0043: a scrape job that disappears is a blind spot too

Type: feature
Who: conantkd (+ agent)
Context: Phase 7's open item: a job gone from a host's Prometheus left no `up` series, so nothing fired and
`scrape_targets_down` read 0.
Decision / result: `external_labels: {argus_host}` per host; `ArgusScrapeTargetMissing` (`absent()` of the exporter,
node-exporter and cAdvisor jobs, 2 minutes); `scrape_targets_down` counts those missing jobs too, so RB-014 matches.
`db-probe` (vm-166 only) not covered by a shared rule.
Consequences: both Prometheus recreated at the AFTER-MERGE; existing alerts keep their labels.
References: [task](../tasks/completed/T-0043-missing-scrape-jobs.md).

## 2026-10-13 — T-0037 step 1: processes, Docker disk use, windowed and searched logs (§12 Level 2)

Type: feature
Who: conantkd (+ agent)
Context: of the 44 read capabilities of §12, 8 were missing; these are the four on the read gateway.
Decision / result: four gateway routes and four capabilities, offered to no class: `get_container_processes` (PID,
PPID, command name; never arguments), `get_docker_disk_usage` (totals, no names), `get_detailed_logs` (1–120 min,
≤ 500 lines, a stream), `search_logs` (a fixed set of named patterns, never free text).
Consequences: no architecture change; the target services need a rebuild at the AFTER-MERGE. Still missing from
§12: `metrics.compare_baseline`, `knowledge.prior_incidents`, `analysis.timeline`, `analysis.trace_request_path`.
References: [task](../tasks/current/T-0037-docker-read-verbs.md).

## 2026-10-13 — T-0039: `query_prior_incidents` (§10.5, §12 Level 3)

Type: feature
Who: conantkd (+ agent)
Context: one of the three §12 capabilities still missing after T-0036–T-0038.
Decision / result: `knowledge.prior_incidents`, in-worker over `IncidentMemoryPort.similar_incidents`: closed
incidents of the same target and class, newest first (date, outcome, confidence, root cause, diagnosis ≤ 300 chars);
an unknown class refused; no memory = unavailable. The worker's `KnowledgeClient` now gets the store. Offered to no
class.
Consequences: no architecture change; no target read (Argus's own store), so no VM step before the merge.
References: [task](../tasks/current/T-0039-prior-incidents.md).

## 2026-10-13 — AFTER-MERGE: both VMs on main ad72617 (#113-#131)

Type: deployment
Who: conantkd (+ agent)
Context: E2E-8 step 2 must run on `main`. Both VMs ran `task/T-0035-monitoring-heartbeat` `239e1d6` (T-0035 step 3),
with migration 006 applied and the heartbeat rule loaded.
Decision / result: both VMs on `main` `ad72617`: target services rebuilt; on vm-095 a backup, migrations (001–006,
nothing new) and agent, worker and scheduler recreated together (20/20, 55/55, WRITE GATE CLOSED); then both
Prometheus recreated (10 rules, heartbeat loaded, every target up). `monitoring_state` alive on both hosts, no
incident opened. LAB BASELINE OK and NO INTERFERENCE on both.
Consequences: blocks sent over `ssh … bash -s` need `</dev/null` on each command (one read the rest of the block).
References: [evidence](../execution/history/AFTER-MERGE-main-2026-10-13/step-01/evidence.md).

## 2026-10-13 — T-0035: a monitoring loss takes the `platform` route of routing.yaml

Type: fix
Who: conantkd (+ agent)
Context: #127 review (`juanbetancurm`): the loss notification of T-0035 (`argus/application/monitoring.py`) still sent
the fixed `channel:operators`; its comment said it would take the `platform` family's route once `routing.yaml`
(T-0042) was merged, and it was.
Decision / result: `MonitoringWatch` takes the validated `Routing` and routes a loss by the family of
`monitoring_blind_spot` (`platform`), else the default. `load_routing` (wiring) reads `routing.yaml` for the agent and
the scheduler alike (fail closed: an invalid file stops the scheduler as it stops the agent). Today's file has no
`by_family` entry, so the route on the VMs stays `channel:operators`.
Consequences: vm-095's scheduler gets it at the next AFTER-MERGE; no migration, no Prometheus change.
References: [task](../tasks/completed/T-0035-monitoring-heartbeat.md).

## 2026-10-13 — E2E-8 step 2: every scenario five times; Phase 12 closed

Type: test
Who: conantkd (+ agent)
Context: Phase 12 needs five runs of every scenario through the runner. SC-01 … SC-08 had them; H-1/H-2, SC-09 …
SC-12 and the identity proof had one run each (LGS). Step 1 (#131) put SC-10, SC-12 and ID-1 in the catalogue.
Decision / result: both VMs on `main` `ad72617` (#132). Batch 1: H-1, H-2, SC-09, SC-11 5/5 each. Batch 2: SC-10 5/5
(blind spot, RB-014, no model call), ID-1 5/5 (each host's own root cause), SC-12 4/5. 0 errors, NO INTERFERENCE
after every run. SC-12 run 1 was `diagnosed`: with the read gateway down the model read the host probe's kernel OOM
records and named the worker correctly; the "never `diagnosed`" expectation predates the host probe.
Consequences: Phase 12 done (every miss read). SC-12's expectation is corrected in its own task (option a: `diagnosed`
only with no successful read of the stopped gateway and the right root cause). A pre-gate on a 10-minute restart
window makes each SC-01-based run last ~11 min.
References: [task](../tasks/current/E2E-8-phase12-close.md),
[evidence](../execution/history/E2E-8/step-02/evidence.md).

## 2026-10-13 — E2E-9: SC-12 accepts a diagnosis made without the stopped gateway

Type: test
Who: conantkd (+ agent)
Context: E2E-8 step 2, SC-12 run 1 FAIL: `diagnosed` through the host probe's kernel OOM records while the read gateway
was stopped, a correct and evidenced diagnosis. The expectation predated the host probe.
Decision / result: option (a). The runner's `if_diagnosed: {root_cause, executor_down}` passes a `diagnosed` only with
the right root cause, no successful read through the stopped executor and one successful read through another; SC-12
uses it with `docker_read`.
Consequences: SC-12 run 1 of E2E-8 would pass under the new rule; the next SC-12 runs are graded with it.
References: [task](../tasks/current/E2E-9-sc12-host-probe.md).

## 2026-10-13 — T-0016: the incident page reads again, the colours breathe, and the Vitest run closes

Type: fix
Who: juanes6554 (+ agent)
Context: after the real-API run, the incident detail page rendered only the page gradient — an audit entry's `detail` is
a JSON object on the real API but a string in the demo fixtures, so React threw and, with no error boundary, the whole
app unmounted. With that fixed, the owner found the page dense (values truncated, a wall of JSON in the audit), and the
status colours, muted a turn earlier, now looked grey. The Vitest suite had been deferred every turn and never run.
Decision / result: `utils/format.js` gained `auditDetail()` (object → JSON text) and a new per-route `ErrorBoundary`
keeps a future render error from blanking the app; the status shades' chroma is raised in `frontend/src/index.css`
(same hues, still below Tailwind's defaults, so class names and layout are untouched); the incident page no longer
truncates fact values, gets a little more rhythm and dividers, and puts each audit entry's JSON behind the same
"Details" toggle the evidence list already uses. The deferred suite then ran: one red (`tokenExpiry` was module-private
in `sessionStore.js` while its test imported it), fixed by exporting the helper → **12 files / 70 tests green**,
`vite build` 351 modules.
Consequences: a render error now shows an error card instead of a blank page; the audit trail stays scannable; the
red/green that four earlier units had deferred is now closed. Reviewer: the only new interaction is the audit
"Details" toggle — say the word to show the detail inline again.
References: [task](../tasks/current/T-0016-frontend.md), [API-FOR-UI](../../docs/API-FOR-UI.md).

## 2026-10-13 — T-0016: reload keeps the session; the incident list pages 30 at a time

Type: feature
Who: juanes6554 (+ agent)
Context: after the real-API run worked, a page reload ended the session (the previous turn had persisted only the
mock session, leaving the real token in memory only), and the incidents page showed the newest 30 with no way to see
more.
Decision / result: `mockSessionStore.js` became `sessionStore.js`, storing `{ user, token, expiresAt }` in
`sessionStorage` (never `localStorage`/cookies/URL); `httpAuthAdapter` saves the token at login, restores it on load,
and clears it on sign-out and on `401`, and `expiresAt` takes the earlier of `VITE_ARGUS_SESSION_TTL_MIN` and the
token's own JWT `exp`. **Rule 4 is amended deliberately** ("in memory only" → "never `localStorage`/cookies/URL; may
be in this tab's `sessionStorage`"), because the owner wants a reload to keep the login; the rule was changed in the
task file and `frontend/README.md`. The incident list fetches the newest rows once (up to 1000; the API has no
`offset` and no total) and shows 30 at a time with a **Show more** button plus a line giving the visible count and the
real total (`src/utils/paging.js`).
Consequences: a real session now survives a reload in the same tab, bounded by the token's expiry; a proper server
page cursor + total still needs a contract change (recorded in `frontend/README.md`). Reviewer: this changes a
documented security rule — say the word to revert to a memory-only token.
References: [task](../tasks/current/T-0016-frontend.md).

## 2026-10-13 — T-0016: the #137 review follow-ups

Type: fix
Who: conantkd (+ agent)
Context: review of #137 (`juanes6554`), approved and merged with two small findings left for a follow-up.
Decision / result: `frontend/vite.config.js`: the dev server's `fs.allow` entry `"../../../argus/runbooks"` pointed
outside the repository (dead: `searchForWorkspaceRoot` already covered the repo root); it now names
`argus/runbooks` resolved from the config file itself, and the file ends with a newline. The task file's bullet
"rule 4 is exactly as written" is marked as superseded by the rule 4 amendment (accepted in the #137 review).
Consequences: none at run time: the dev server still serves the runbooks (200) and refuses a file outside the
workspace (403); the production build is unchanged.
References: [task](../tasks/current/T-0016-frontend.md), PR #137.

## 2026-10-13 — ACR-0011 proposed: the read-only UI on public HTTPS (Nginx on vm-095:443)

Type: architecture proposal
Who: conantkd (+ agent)
Context: the team wants users to open the UI in a browser without an SSH account. It decided on Nginx on vm-095:443,
Argus's own login with read tokens, no mandatory second gate, and no ngrok or Cloudflare Tunnel.
Decision / result: ACR-0011 `proposed` (second approval required: least privilege and secrets). Read-only facts seen
on vm-095:
- nothing listens on :80/:443;
- the host `INPUT` chain accepts only tcp/22, and Docker-published ports bypass it, so the rule goes in `DOCKER-USER`;
- vm-095 has no public address on its interfaces;
- the login has no rate limit and no audit of failed logins, although §17.3 promises both;
- a login without `scope=read` gets a full token;
- `limit` is uncapped;
- a real-mode build ships the runbooks and the mock adapter's demo password;
- all three human principals are `operator`.

The ACR proposes:
- a contract allowlist at Nginx;
- read-only logins through the edge;
- login rate limits and an audit of failed logins;
- runbooks served only after login;
- Let's Encrypt with a renewal timer;
- a rollback that leaves the SSH path intact.

T-0016 gets a proposed step 4 (4a–4f) next to the current one.
Consequences: nothing is built before the acceptance and the pending data (domain, public address, who opens 443/80,
DNS administration, certificate choice, the user accounts).
References: [ACR-0011](../architecture/changes/ACR-0011-public-https-ui.md),
[T-0016](../tasks/current/T-0016-frontend.md).

## 2026-10-13 — T-0041: the first real db_probe rotation; OP-004 / OP-008 dry runs for review

Type: operation
Who: conantkd (+ agent)
Context: closing Phases 9 and 13. T-0041's script (#126) was merged; one real rotation on vm-166 was left. OP-004 and
OP-008 wait for a teammate's review of their dry runs before the first `--apply`.
Decision / result: `rotate-token.sh db_probe` on vm-166: both copies (service and Prometheus) `804c84827c26`, `up` back
to 1 with no alert; the agent's copy on vm-095 replaced (hashes equal), `database.health` ok again without a worker
restart. Dry runs on `main`: OP-004 nothing older than 30 days; OP-008 would remove 9 of 16 dumps, the newest verified.
NO INTERFERENCE on both VMs.
Consequences: Phase 13's last item done. OP-004 and OP-008 `--apply` wait for the teammate review of the evidence.
References: [rotation](../execution/history/T-0041/step-02/evidence.md),
[dry runs](../execution/history/OP-004/step-03/evidence.md).

## 2026-10-13 — D-003 decided: `dependency_unavailable` and `nginx_upstream_failure` run the baseline

Type: decision
Who: juanbetancurm (+ agent)
Context: §21.2: a class keeps a model strategy only if it matches or beats the deterministic baseline on the
evaluation cases. D-003 was pending since T-0025; E2E-8 step 2 had to finish first, so that its runs did not mix two
registries.
Decision / result: counted on all of a class's cases (ambiguous ones included), 5 trials: dependency 0.90 vs 1.00 and
nginx 0.92 vs 1.00 switch to `baseline`; health keeps `model_loop` (0.97 vs 0.83: the baseline diagnoses
`ambiguous-health-no-cause`); restart loop, disk, CPU, Postgres and the blind spot keep theirs. The new capabilities
stay offered to no class.
Consequences: those two classes no longer call the model; an incident their rules do not decide escalates. Needs an
AFTER-MERGE (worker) and a check on the VMs: SC-03 and SC-07 (dependency), SC-08 (nginx). OP-013: re-decide with
held-out cases.
References: [D-003](../OPEN_PROBLEMS.md), `tests/test_d003_class_registry.py`.

## 2026-10-14 — EVAL-search-logs: search_logs offered to health_check_failed is not used; the error pattern fixed

Type: evaluation (+ fix)
Who: conantkd (+ agent)
Context: T-0037 step 3: offer `container.search_logs` to a class with an evaluation batch. `health_check_failed` was
chosen: the class with the most room, and a targeted read where the broad snapshot had lowered it (EVAL-snapshot).
Decision / result: measured on vm-095 from a local branch, 55 cases × 5 trials:
- overall 0.98 (270/275) against `main`'s 0.97 re-graded;
- health 0.92 against 0.96;
- **the tool was used in 1 of 30 health runs**, so the differences are noise of 5 trials.

It is not offered. The cases' logs are 2–3 lines, and the tail already returns them, so log tools need long-log cases
before they can be measured. Found on the way, and fixed in the gateway with tests (red seen): the `error` pattern
missed exception class names (`KeyError`, `ValueError`, `RuntimeException`) and plurals, so a real search answered
"0 matched" for a log with a `KeyError`.
Consequences: the fix reaches the VMs when the target services are rebuilt at the next AFTER-MERGE. The offer, the
replay change and the search fixtures are not merged. On vm-095 the image `argus-v18-agent:evalsl` and `/tmp/evalsl`
are left, used by no service.
References: [evidence](../execution/history/EVAL-search-logs/step-01/evidence.md),
[T-0037](../tasks/current/T-0037-docker-read-verbs.md).

## 2026-10-14 — A second fast-track window proposed (2026-10-14 to 2026-10-16)

Type: process proposal
Who: conantkd (+ agent)
Context: the fast-track of `REVIEW_PROTOCOL.md` expired on 2026-10-12. Since then, small changes (records, a
one-line gateway fix with its tests: #138, #141) wait a day or more for a review.
Decision / result: proposed a second window, 2026-10-14 to 2026-10-16 inclusive, with the same people and conditions.
Review correction (PR #142): juanbetancurm requested an end date of 2026-10-16 inclusive, the delivery date.
All seven files now use that date; the people, conditions and approval requirement are unchanged.
The conditions:
- a task branch;
- CI green and up to date;
- the agent's review report posted;
- the PR's own line in `main-exceptions.txt`;
- never a safety principle, an ACR or the enforcement.

The window exists only if a teammate approves this pull request, which is not fast-tracked because it changes the
rule. Any teammate's objection ends it. Updated together: `REVIEW_PROTOCOL.md`, `GIT_WORKFLOW.md`, the header of
`main-exceptions.txt`, `PARALLEL_LANES.md`, `CURRENT_STATE.md`, T-0016's note.
Consequences: nothing in `brain.py` or CI changes (no date is coded there). Until the approval, #138 and #141 follow
the normal review.
References: [`REVIEW_PROTOCOL.md`](../agents/REVIEW_PROTOCOL.md).

## 2026-10-14 — ACR-0011 built in #144: the public UI edge, offline (4a–4c)

Type: feature (API, frontend, deployment files)
Who: conantkd (+ agent)
Context: `conantkd` asked to build ACR-0011 as if accepted. It has one approval (`juanes6554`, #140); the second
approval is still required (least privilege and secrets). #144 therefore cannot merge before both approvals, and
nothing is deployed.
Decision / result:
- **API:** edge logins are read-only; failed logins are audited and limited per username and address, with a
  lockout; `limit` is capped.
- **Frontend:** the runbooks load from the edge after login, and the real bundle has none.
- **The edge** `argus-v18-ui`:
  - Nginx without root, in `loopback` and `public` modes;
  - the contract allowlist, limits and security headers;
  - `/runbooks/` checked against `/api/v1/me`;
  - certbot with a renewal timer, `DOCKER-USER` connection limits, and `nonint-check` aware of its ports.
- **Documents:** ARCHITECTURE 1.8.10, `environment.md`, `SECURITY.md` and `API-FOR-UI.md` updated.
- **Verified:** with the real Nginx image (tests and a local run of the built image in both modes).

Two differences from the ACR text, recorded in its §9:
- the `DOCKER-USER` rule is a per-address connection limit, because Docker already restricts a published port to its
  container;
- `nonint-check` needed a port exclusion, not a firewall one.
Consequences: the root `.dockerignore` is new (the build context no longer sends `node_modules`, `.venv`, `.git`).
4d (vm-095 loopback) needs the lease; 4e needs ACR-0011 §8's data.
References: [ACR-0011](../architecture/changes/ACR-0011-public-https-ui.md),
[T-0016](../tasks/current/T-0016-frontend.md).

## 2026-10-14 — T-0016 4d: the UI edge on vm-095's loopback, in front of the real API

Type: deployment (loopback only)
Who: conantkd (+ agent)
Context: ACR-0011 is built in #144 but not accepted yet (one approval of two), so 4d deploys the task branch and no
public port.
Decision / result:
- **Deployed:** vm-095 on `task/T-0016-playwright` `d5d992c`, with the agent recreated (20/20, 55/55, WRITE GATE
  CLOSED) and `argus-v18-ui` healthy on `127.0.0.1:18010`.
- **The curl matrix through the tunnel:** allowed and refused routes as designed; runbooks 401 without a valid
  token; security headers; no mock or runbook in the bundle.
- **Logins:** Nginx's rate limit stops a burst, and the API locks a username after 5 failures (429, `Retry-After`),
  audited `via: edge`.
- NO INTERFERENCE on both VMs.

Consequences:
- The audited client address is Docker's bridge gateway behind the userland proxy, so the per-address limit is
  shared by every tunnel user. Check it on the public port before 4e: publishing in host mode, or disabling the
  userland proxy, is a host decision because the protected deployment shares the daemon.
- vm-095 stays on the branch until #144's AFTER-MERGE (rollback: `deploy.sh main`, compose down).

References: [evidence](../execution/history/T-0016/step-04d/evidence.md).

## 2026-10-14 — T-0016: Playwright acceptance tests, the read-only guard, the contract check and ESLint

Type: tests (frontend)
Who: conantkd (+ agent)
Context: T-0016's open items since step 3: the acceptance tests, the read-only network guard, the
`contracts/ui-api.json` check, and the linter of its test table.
Decision / result:
- **Acceptance tests:** nine Playwright tests on the real-mode build, with the API faked from `contracts/samples/`.
- **The guard:** in every test, any non-`GET` API call except the login, or any other origin, fails the test.
- **The contract check:** a Vitest test runs the real adapters and requires every route, method and query parameter
  to be declared in the contract.
- **ESLint:** 0 errors.
- **CI job `frontend`:** lint, unit, build, then Playwright.
- **Fixed on the way:** the restricted notice named an "admins" role that Argus does not have.
Consequences: a UI change that writes, calls another origin or uses an undeclared route now fails CI. The CI job
installs Chromium (`npx playwright install --with-deps chromium`).
References: [T-0016](../tasks/current/T-0016-frontend.md).

## 2026-10-14 — T-0016: a real build without mock code; a gentler polling budget

Type: feature (frontend)
Who: conantkd (+ agent)
Context: ACR-0011 found that a real-mode build ships the mock adapters (the demo password) and that the UI polls
the 1-vCPU VM every 5 s for up to 1000 incidents. Neither waits for the ACR's second approval.
Decision / result:
- `"sideEffects": ["**/*.css"]` in `frontend/package.json` lets the real build drop the mock modules. A test builds
  in real mode and greps the bundle.
- The dashboard and the incident list poll every 30 s, both paused while the tab is hidden; the list asks for at most
  200 incidents.
- The intervals live in `src/utils/polling.js`.
Consequences: a demo build is unchanged. The runbooks still ship in the bundle until Nginx's checked `/runbooks/`
exists (ACR-0011, after its second approval).
References: [T-0016](../tasks/current/T-0016-frontend.md), [ACR-0011](../architecture/changes/ACR-0011-public-https-ui.md).

## 2026-10-14 — T-0016 4e: the read-only UI is public on vm-095 (HTTPS, a Let's Encrypt IP certificate)

Type: deployment (public)
Who: conantkd (+ agent)
Context: the team wants the UI reachable from a browser without SSH. ACR-0011 is built in #144 with one approval of
two. The OCI rule for 443/80 was opened by the team.

Decisions (`conantkd`): deploy with one approval (the team assumes the second); a certificate for the IP address (no
domain); the shared `operator` accounts stay for now, an accepted risk.

Result:
- vm-095 on `task/T-0016-playwright` `8ee48c4`.
- `argus-v18-ui` public on 443/80: uid 101, read-only, `DOCKER-USER` connection limits.
- A Let's Encrypt `shortlived` certificate for the address, certbot 5.8.0 `--ip-address`, renewed by a timer at 3
  days or less.
- **Verified from the Internet:** a trusted chain; HTTP→HTTPS; the headers; the allowlist (`/docs` and
  `POST /investigations` 404); the API and the runbooks 401 without a token; the real client address in the audit.
- NO INTERFERENCE on both VMs. The address is kept out of Git.

Consequences:
- The Argus login is on the Internet. It is protected by read-only edge tokens, the per-username lockout, the
  per-address limits and the audit, but the accounts are shared.
- vm-095 runs the branch until #144's AFTER-MERGE.

References: [evidence](../execution/history/T-0016/step-04e/evidence.md),
[ACR-0011](../architecture/changes/ACR-0011-public-https-ui.md).

## 2026-10-14 — ACR-0012 proposed: the UI may start an investigation

Type: architecture proposal
Who: conantkd (+ agent)
Context: the UI is public and read-only (ACR-0011). Starting an investigation still needs the CLI or Swagger, so SSH.
Facts read for the proposal:
- `POST /api/v1/investigations` has no limit at all, neither per principal nor on the queue;
- only a full token can call it;
- an investigation costs about 3.5 model calls and 3.8 reads;
- the UI's accounts are shared.

Decision / result: ACR-0012 `proposed`. It needs a second approval (least privilege). It proposes:
- **A third token kind `investigate`:** every GET plus `POST /api/v1/investigations` only.
- **The edge:** it may issue such tokens and proxy that one POST under its own rate limit.
- **Server quotas:** 10/h and 2 queued per principal, 20 queued in all; alerts are never blocked.
- **A target list instead of free text:** `GET /api/v1/targets`.
- **The UI:** a Diagnose button shown only when `/me` lists the action.

Consequences: nothing is built. The team decides on per-person accounts before enabling it on the public UI.
References: [ACR-0012](../architecture/changes/ACR-0012-ui-start-investigation.md).

## 2026-10-14 — AFTER-MERGE: both VMs on main; the public edge's 502 after an agent recreate, fixed

Type: deployment + fix
Who: conantkd (+ agent)
Context: #141, #144–#147 merged.
- vm-166 was on `main` `ad72617`.
- vm-095 was on the T-0016 branch (the public UI edge).

Decision / result:
- **Both VMs on `main` `ccc810e`**:
  - the read gateway with #141's `error` pattern;
  - the agent with D-003 (`dependency_unavailable` and `nginx_upstream_failure` on `baseline`): 20/20, 55/55,
    WRITE GATE CLOSED;
  - NO INTERFERENCE on both.
- **Found:** the public UI's API answered **502** after the agent was recreated, because Nginx had resolved the name
  once at start. Restored by a reload within about 2 minutes.
- **Fixed:** the upstream re-resolves through Docker's DNS (`resolver 127.0.0.11`, `server … resolve`), with a test
  on real Nginx (red, then green). Deployed on vm-095: a later agent recreate without a reload kept the API
  answering. Docker happened to reuse the address that time, so the test is the proof.

Consequences: every deployment of the agent recreates it, so without the fix the public UI would have broken on
each AFTER-MERGE.
References: [evidence](../execution/history/AFTER-MERGE-main-2026-10-14/step-01/evidence.md).

## 2026-10-14 — ACR-0012 built on a local branch: the UI may start an investigation

Type: feature (API, edge, frontend)
Who: conantkd (+ agent)
Context: ACR-0012 is proposed (#147 merged the record, not its acceptance). `conantkd` asked to build it without a
PR yet, on `task/ACR-0012-impl`.
Decision / result:
- **The `investigate` token:** every GET and `POST /api/v1/investigations` only. The edge issues `read` or
  `investigate`, never full.
- **Quotas for investigate tokens:** 10 an hour and 2 queued per account, 20 queued in all, answering 429 with
  `Retry-After`.
- **`GET /api/v1/targets`.**
- **The audit:** `investigation.requested` and `investigation.quota_refused`.
- **The contract and the edge:** one POST location with its own limit.
- **The UI:** a form on the dashboard, "Investigate again" on an incident, shown only when `/me` allows it, and a
  guard that allows that one POST only then.
- ARCHITECTURE 1.8.11 applied on the branch.

**One difference from the ACR, recorded in its §7:** the quotas apply to investigate tokens only. A full token is
loopback only (the CLI and the E2E runner) and is not limited.

Consequences: nothing deployed; the public UI still runs read-only `main`. Before enabling it in public, the shared
`operator` accounts mean an investigation cannot be attributed to a person (ACR-0012 §4).
References: [ACR-0012](../architecture/changes/ACR-0012-ui-start-investigation.md),
[T-0016](../tasks/current/T-0016-frontend.md).

## 2026-10-14 — T-0016 / PR #151 host metrics

### Scope

The user requested operational dashboard metrics and a chat answer to “Check Host T memory usage”, plus a way to
start an investigation from chat. Proposed ACR-0014 accompanies the implementation in PR #151; independent review
is required for the added public read route. No VM was touched.

### Local evidence

- Red: `tests/test_ui_host_metrics.py` failed with 404; the frontend parser/sample tests failed on missing modules.
- The API now reads only fixed host signals already present in the catalogue, through MetricsPort.
- The UI distinguishes an immediate named metric read from a queued full investigation, and links the latter to
  its incident. Missing metric data is never presented as zero.
- Green: host-metrics API tests (3); UI contract (3); edge allowlist tests (Docker-backed checks skipped on this
  Windows host); frontend Vitest 91/91, Chromium acceptance 16/16, Vite build and ESLint (0 errors, 14 existing
  fast-refresh warnings), Brain lint. `git diff --check` clean.
- Full Python suite reached 100% but returned seven failures, all in `tests/test_t0033_rotate_token_script.py`:
  WSL cannot start `/bin/bash` on this Windows host (`execvpe(/bin/bash) failed: No such file or directory`). The
  affected shell script and test were not changed. The targeted API/contract/edge checks pass; Linux CI remains
  the authoritative full-suite result after the push.

## 2026-10-14 — OP-004 and OP-008: the approved applies on vm-095, run without a Brain lease

Type: VM operation record
Who: conantkd (run on the VM) + agent (record)
Context: juanbetancurm approved in PR #138 one OP-008 `prune --apply` with `KEEP=7` and one OP-004 `--apply` at 30
days, with the daily timer off.
Decision / result: a fresh backup first (`VERIFY OK: 13 tables, 29001 rows match`).
- OP-008: the dry run and the apply named the same 12 backup sets (the approved 9 plus 3 that aged out since), and
  7 sets remain, the newest verified among them.
- OP-004: dry run and apply both `threads=0 checkpoints=0 blobs=0 writes=0`: no final incident is 30 days old yet.
- NO INTERFERENCE.

**Deviation:** no Brain lease was claimed. The lease of AFTER-MERGE-main was released at 06:59Z, and the run was
about 16:25Z. `/opt/argus-v18/SESSION` on vm-095 still named conantkd from that morning, so the scripts' marker check
passed. Nobody else held a lease at the time, so there was no conflict. The marker check proves only that the last
session was yours, not that you hold the lease now: claim with `brain.py start` and rewrite the marker every session.
Consequences: OP-004 has no apply left until its timer is decided. OP-008 still needs `sha256sum -c` on the newest
verified dump after the prune (reviewer's after-check), at the next VM session with a lease.
References: [`OP-004/step-04`](../execution/history/OP-004/step-04/evidence.md),
[`OP-008/step-03`](../execution/history/OP-008/step-03/evidence.md), PR #138.

## 2026-10-14 - LF-2: proposed Langfuse agent observability architecture

Type: architecture proposal
Who: conantkd (+ agent)
Context: the user selected Langfuse on the Argus VM, chose separate databases initially, left Argus PostgreSQL reuse open if performance requires it, and requested that ACR-0013 cover the full agent observability integration.
Decision / result: proposed a six-service Langfuse stack on Host A and optional, filtered OTLP spans from the Argus worker for investigation attempts, graph nodes, model and capability calls. No raw evidence, prompts or secrets are exported by default. Telemetry failure does not block investigations or audit. Langfuse starts with its own PostgreSQL service; the existing Argus server is a gated separate-database fallback. No deployment or architecture version change in PR #150.
References: [task](../tasks/current/LF-2-langfuse-db-architecture.md), [ACR](../architecture/changes/ACR-0013-langfuse-agent-observability.md).

## 2026-10-14 — LF-3 local implementation

Status: work in progress on an isolated local branch. The Argus worker emits bounded metadata-only OTLP spans; the
Agent page shows recent run activity and trace correlation IDs from the existing read-only API. A private six-service
Langfuse Compose stack and VM acceptance procedure are prepared. No PR, push or VM execution is part of this session.

## 2026-10-14 — DEPLOY-151: vm-095 on main 37822c9 (the UI starts investigations, host metrics)

Type: deployment
Who: juanbetancurm (+ agent)
Context: #151 (ACR-0012 and ACR-0014) and #153 merged; conantkd was busy, so juanbetancurm deployed vm-095 with
conantkd's AFTER-MERGE blocks.
Decision / result: vm-095 on `main` `37822c9`: backup, agent, worker and scheduler on one image (20/20, 55/55, WRITE
GATE CLOSED), the UI edge rebuilt in public mode; the new routes answer 401 without a login, `/docs` 404, NO
INTERFERENCE. In the browser, after a new login, the investigation form and live host metrics work; a report on an
absent container ended `undiagnosable` with an evidence pack, as designed. The same day, SC-07 through the alert path
was diagnosed by the baseline (D-003) with no request and no model call.
Consequences: a session from before a UI deployment must log in again to get the investigate token. Follow-ups: the
quota test from the UI; the outdated "Read-only in this release" note for operators.
References: [evidence](../execution/history/DEPLOY-151/step-01/evidence.md).

## 2026-10-14 — T-0044: propose evaluating a locally-hosted Weaviate for hybrid runbook retrieval behind `KnowledgePort` (ACR-0015)

Type: architecture proposal
Who: juanes6554 (+ agent)
Context: runbook recall is pure TF-IDF at `k=3` (§21.2 target recall@3 ≥ 0.9); the lab wants a stronger retriever and a
TF-IDF-vs-RAG comparison. A vector store was forbidden by §15.3, so the change is proposed as ACR-0015 before any code.
Decision / result: ACR-0015 (proposed) — §15.3 "no vector store" becomes "a hybrid (BM25 + a vector store) behind
`KnowledgePort`, selected by `ARGUS_RETRIEVAL`"; the store under evaluation is **Weaviate run locally** (open source,
self-hosted on Host A as its own container, no managed/cloud API and no API key), recorded in a §16.1 row; §21.2
"TF-IDF recall@3 ≥ 0.9" becomes the baseline the Weaviate hybrid must beat. This pull request is the ACR and its
documentation only; `juanes6554` hands the evaluation, the code and the deployment to a teammate.
Consequences: a new `argus-v18-*` Weaviate container to operate locally (port, network, resource limits); only the
embeddings provider is called externally at index time; the index is derived and rebuildable, so nothing in the
evidence/audit path is affected; the agent changes nothing until the implementation lands and `ARGUS_RETRIEVAL=hybrid`
is set.
References: [task](../tasks/current/T-0044-rag-pgvector.md), [ACR-0015](../architecture/changes/ACR-0015-rag-hybrid-retrieval.md).

## 2026-10-15 — T-0016 / the incident and dashboard visual redesign

### Scope

`juanes6554` redesigned the UI with Claude (outside the repo) and asked his agent to test it, document it and open
its pull request. The change is **frontend-only** (`frontend/`): no `argus/`, no `contracts/`, no
`.github/workflows/`. The incident page is reorganised into tabs (**Incident & Diagnosis**, optional **Map** and
**Metrics**, **Runtime Timeline**, **Evidence**, **Audit**), the dashboard shows a load level per host metric, and
the form/list controls are themed. The **Map** and **Metrics** tabs read two routes Argus does not serve yet
(`GET /api/v1/topology`, `GET /api/v1/incidents/{id}/metrics`): the HTTP adapter calls them only with
`VITE_ARGUS_INSIGHTS=1` (off by default) and the page hides the tabs until they answer, so a normal build never
requests a missing route. The request and the exact shapes are in `frontend/BACKEND-REQUESTS.md`.

### Local evidence

- Red: `npm run e2e` → **5 failed** against the redesign (stale assertions: `selectOption` on a control that is now
  a custom combobox, `.check()` on a button group, `"60.0%"` exact-matched before the value gained its
  screen-reader level suffix, and the evidence/timeline assertions before those sections moved into tabs).
- Green: `npm run e2e` → **17/17** (the 5 updated, plus one new test that the page groups its sections into tabs and
  that Map/Metrics appear only when their routes answer); `npm test` → **23 files / 127 tests** (two new unit files,
  `components/SystemMap.test.js` and `components/RunbooksRead.test.js`); `npm run lint` → 0 errors (20 existing
  fast-refresh warnings); `npm run build` → green.
- No VM was touched; no lease was needed (code-only, no VM change). `VITE_ARGUS_INSIGHTS` is unset in the e2e build,
  so the read-only network guard confirms the app still sends only GETs (plus the login/investigation POSTs allowed
  by ACR-0012).
- The Brain is updated on the branch: `tasks/current/T-0016-frontend.md` (status + the new evidence bullet) and this
  entry.

## 2026-10-15 — ACR-0017 proposed: system map and incident metrics routes for the UI

Type: architecture (proposal)
Who: juanbetancurm (+ agent)
Context: the UI redesign (#158) draws a system map and charts around an incident, hidden in a real build until the
API serves them; `frontend/BACKEND-REQUESTS.md` lists the two routes.
Decision / result: ACR-0017 proposes `GET /api/v1/topology` (inventory targets, declared dependencies with their
ports, Docker networks and live state from the dependency probe and named signals; an `incident_id` overlay from the
incident's stored evidence, operator/approver only) and `GET /api/v1/incidents/{id}/metrics?range=15m|30m|1h`
(a fixed signal list per class, the incident's host only, at most ~130 points per series), plus an optional `end`
on `MetricsPort.range`. Never VM addresses, Argus's internal endpoints or secrets. No new host read.
Consequences: needs a teammate's acceptance and the second approval (least privilege, host isolation) before the
implementing PRs merge.
References: [ACR-0017](../architecture/changes/ACR-0017-ui-topology-and-incident-metrics.md),
`frontend/BACKEND-REQUESTS.md`.

## 2026-10-15 — LF-3 step 02: vm-095 on main 5d4b347; the self-hosted Langfuse failed its capacity gate; ACR-0016 proposes Langfuse Cloud (EU)

Type: deployment + architecture proposal
Who: conantkd (+ agent)
Context: #152 (ACR-0013's tracing code, off by default) and #154 merged. ACR-0013 put six Langfuse services on vm-095
and made enablement wait for a capacity gate.
Decision / result: vm-095 moved to `main` `5d4b347` (backup, one image for agent/worker/scheduler, 20/20, 55/55, WRITE
GATE CLOSED, UI healthy, NO INTERFERENCE). The Langfuse stack started (health 200 in about 60 s, about 2.1 GiB) and the
worker's tracing was switched on, but about 15 minutes later a ClickHouse merge was OOM-killed at its 768 MiB limit and
the host's disk saturated (I/O pressure 99 %, load 176). Argus stayed up but slowed. The stack was stopped (volumes
kept), tracing rolled back and the keys removed; Argus recovered within a minute. The worker reaches Langfuse Cloud
(4.59, EU and US). ACR-0016 proposes the EU Cloud with the same allowlisted spans; the endpoint becomes a worker-only
compose setting (`ARGUS_TRACING_ENDPOINT`, default the private stack).
Consequences: no tracing on vm-095 until ACR-0016 is decided. Two lessons for code.bash: vm-095's `install` is uutils
(refuses a numeric owner: use `umask` + `chown`), and compose names the Langfuse containers
`argus-v18-langfuse-argus-v18-langfuse-<service>-1` (stop them by service name). vm-166's `argus-lab-cache` was found
stopped (since about 22:07, not by this session) and left as found.
References: [evidence](../execution/history/LF-3/step-02/evidence.md),
[ACR-0016](../architecture/changes/ACR-0016-langfuse-cloud.md).

## 2026-10-16 — ACR-0017 step 1: the incident metrics route (`GET /api/v1/incidents/{id}/metrics`)

Type: implementation
Who: juanbetancurm (+ agent)
Context: ACR-0017 (accepted in #159, `juanes6554`) gives the UI's Metrics tab and "Around the incident" card their
data. The API's `PrometheusMetrics.range` was a stub ("history is served by the metrics.* capabilities").
Decision / result: `GET /api/v1/incidents/{id}/metrics?range=15m|30m|1h` for any authenticated role. A fixed signal
list per class in `config/ui-incident-signals.yaml` (validated at startup like `routing.yaml`; `default` for an
incident without a class), read with `MetricsPort.range` on the incident's host only; the window runs from
`opened_at − range` to `closed_at + 2 min` (or now); at most ~130 points per series (the step grows); `null` for a
missing sample; a series that cannot be read is all gaps and the others still answer; one shared answer per
(incident, range) for 30 s while open, 10 min once closed. `MetricsPort.range` gains an optional `end`, and
`PrometheusMetrics.range` is implemented (`query_range`). Contract, sample, the edge's allowlist, `API-FOR-UI.md` and
ARCHITECTURE 1.8.14 updated.
Consequences: the frontend can call the route once deployed (`VITE_ARGUS_INSIGHTS=1`, `juanes6554`). The topology
route of ACR-0017 is the next step.
References: [ACR-0017](../architecture/changes/ACR-0017-ui-topology-and-incident-metrics.md),
`tests/test_acr0017_incident_metrics.py`.

## 2026-10-16 — ACR-0017 step 2: the system map (`GET /api/v1/topology`)

Type: implementation
Who: juanbetancurm (+ agent)
Context: the second route of ACR-0017, for the UI's Map tab, "Where it broke" card and Dashboard live map. Stacked on
the incident-metrics PR (#160), which touches the same files.
Decision / result: `GET /api/v1/topology` for any authenticated role, and `?incident_id=<id>` for operator/approver.
Nodes from the inventory (one per target), edges from the declared `depends_on` with the dependency's port; status
from `restarts_10m` and `health_unhealthy`; the edge's state from `dependency_probe_min` (`ok`/`broken`; `unknown`
when there is no sample, the dependency has no TCP port, or an owner with several dependencies fails: the probe's
minimum names none). A host whose Prometheus cannot be reached makes all its targets `unknown`. The overlay takes the
incident's target and root cause from their stored `container.status` evidence: state (exited → stopped), real
networks, restarts, memory limit, exit code, OOM; their link becomes "no shared network" when their networks do not
meet (SC-07). `ARGUS_HOME_HOST` (vm-095 in `deploy/vm-095/compose.core.yml`) marks Argus's host and its reads.
Never VM addresses, Argus's internal endpoints or secrets (a test scans both answers); no new read on the hosts;
shared for 20 s (the overlay 10 min once the incident is closed).
Consequences: with #160, both routes of ACR-0017 exist; after the deployment `juanes6554` connects the frontend.
References: [ACR-0017](../architecture/changes/ACR-0017-ui-topology-and-incident-metrics.md),
`tests/test_acr0017_topology.py`.

## 2026-10-16 — DEPLOY-161: vm-095 on main 0b3b4e8 (ACR-0017: incident metrics and the system map)

Type: deployment
Who: juanbetancurm (+ agent)
Context: #160 and #161 (ACR-0017) merged; deployed after the class demo so the demo ran on the version it was
rehearsed on.
Decision / result: vm-095 on `main` `0b3b4e8`: backup, agent, worker and scheduler on one image (20/20, 55/55, WRITE
GATE CLOSED, `ARGUS_HOME_HOST` vm-095), the UI edge rebuilt in public mode. Without a login both new routes answer 401
through the edge; logged in, the map (15 nodes, 6 edges), one incident's metrics (67 points) and the incident overlay
answer 200, with no address in any answer. LAB BASELINE OK and NO INTERFERENCE on both hosts. On the way: the deploy
needed both leases (PARALLEL_LANES.md), SC-01's worker left running by the demo was removed on vm-166, and an empty
marker on vm-095 made the first attempts skip themselves; the blocks now check the marker without `exit`.
Consequences: the frontend can switch the Map and Metrics tabs on (`VITE_ARGUS_INSIGHTS=1`). Check both labs before
a deploy that follows a demo or a scenario run.
References: [evidence](../execution/history/DEPLOY-161/step-01/evidence.md),
[ACR-0017](../architecture/changes/ACR-0017-ui-topology-and-incident-metrics.md).

## 2026-10-16 — T-0016: the frontend connection to ACR-0017's map and metrics routes

Type: implementation
Who: juanes6554 (+ agent)
Context: ACR-0017's two read routes were deployed in DEPLOY-161 (agent on main `0b3b4e8`). The 2026-10-15 redesign
(#158) had drawn the Map and Metrics tabs, but the real adapter called only the plain topology, never the
`?incident_id=` overlay; the Dashboard had no map; and neither route was exercised by the contract test. The
backend author asked for the wiring plus the two calls in the contract tests.
Decision / result: `httpArgusAdapter.getTopology(incidentId)` sends `?incident_id=` and reads `VITE_ARGUS_INSIGHTS`
per call (so a test can turn it on without reloading the module); `useTopology(incidentId)` refetches on the id and,
if the overlay is refused (403 — the API allows operators and approvers only), falls back to the plain map, because
the API decides permissions, never the UI (ACR-0001). `IncidentDetail` asks for the overlay for operators and
approvers; `Dashboard` gained the live **System map** card; `SystemMap` gained a first-class **`unknown`** node and
edge state so an unknown edge is never drawn as the green **ok** (the real samples are all `unknown`), a shared
`MapLegend`, and a read-only `SystemMapCard`; the mock adapter mirrors the overlay call. Nothing is requested unless
`VITE_ARGUS_INSIGHTS=1` (off by default), and the hooks hide what they cannot draw, so an older API is unaffected.
Care points honoured: a `null` metric sample stays a gap and `fired` stays red (already in `MetricChart`); the SC-07
"no shared network" link now shows because the overlay is fetched; no IPs/URLs/secrets (server-side).
Consequences: the two Map/Metrics tabs, the "Where it broke" card and the Dashboard map are now fed by the real
routes; a real-mode click-through on vm-095 and the deploy build passing the flag remain.
References: [ACR-0017](../architecture/changes/ACR-0017-ui-topology-and-incident-metrics.md),
`frontend/BACKEND-REQUESTS.md`, `brain/tasks/current/T-0016-frontend.md`.

## 2026-10-16 — T-0016: the UI image is built with the Map and Metrics calls on

Type: implementation
Who: conantkd (+ agent)
Context: PR #163 wired the frontend to ACR-0017's routes behind `VITE_ARGUS_INSIGHTS=1`, and its review left one
follow-up: the deploy build did not pass the flag, so the real UI image would still hide both tabs. The Nginx edge
already serves `GET /api/v1/topology` and `GET /api/v1/incidents/{id}/metrics`.
Decision / result: `deploy/ui/Dockerfile` sets `ENV VITE_ARGUS_INSIGHTS=1` next to `VITE_ARGUS_MOCK=0`. Reversal:
remove the line and rebuild; the UI hides the tabs again (ACR-0017, "How to reverse it").
Consequences: nothing changes on vm-095 until the image is rebuilt and the UI edge redeployed; the real-mode
click-through (Map, Metrics, Dashboard map, operator overlay) is still to be done by a person after that.
References: [ACR-0017](../architecture/changes/ACR-0017-ui-topology-and-incident-metrics.md), PR #163,
`brain/tasks/current/T-0016-frontend.md`.

## 2026-10-17 — TEST-HARDEN-1: Docker tests in CI, prompt-injection cases (and the escape they found), a robust timing test

Type: implementation
Who: juanbetancurm (+ agent)
Context: the self-merge rule (`task/SELF-MERGE-rule`, OP-014) relies on a green CI meaning "safe to merge". OP-014
lists where it does not yet; this pull request closes its first three gaps.
Decision / result:
- **Docker tests in CI.** `ci.yml` sets `ARGUS_TEST_DOCKER=1` on the `test` job (the Linux runner has Docker; timeout
  15 → 25 min), so the credential-isolation check of the agent image, the real-Docker backup tests and the real-Nginx
  edge tests run instead of being skipped. `ops/local_ci.py` sets it too when Docker is present, as `ci.yml` does.
- **Prompt-injection regression cases** (`tests/test_op014_prompt_injection.py`, replayed offline through the real
  wiring from `restart-oom-01` with instructions planted in the worker's logs). They found a real defect: target text
  could write a literal `</evidence>` (or open a `<passage …>`) into the model's context and so end its data block
  early, against §10.8. `orchestration/runner.py` now escapes the `<` of `evidence` / `passage` / `reported` tags in
  every piece of untrusted text it puts in the context (`as_data`). A model that obeys an injection with a write tool
  or with a root cause outside the scope is refused, no action happens, and a planted secret still never reaches it.
- **The flaky timing test.** `test_benchmark_compares_direct_and_mcp_on_the_same_read` asserted the 100 ms OD-3
  verdict on 4 samples, which fails on a loaded machine. It now checks the mechanics (both ways measured, every read
  ok, a verdict printed); the budget rule stays in `test_benchmark_verdict`, and the real budget is measured on vm-095.
Consequences: the agent image changes (the context escape), so vm-095's agent, worker and scheduler need a redeploy
after the merge (both leases). The PR touches `.github/` and `ops/local_ci.py`, so it needs a teammate's approval.
References: OP-014 (`brain/OPEN_PROBLEMS.md`, added by `task/SELF-MERGE-rule`), ARCHITECTURE §10.8 and §22.3 item 10.

## 2026-10-17 — SELF-MERGE: authors may merge their own pull requests when the required checks are green

Type: decision
Who: juanbetancurm (+ agent)
Context: the temporary fast-track windows (2026-10-05 to 2026-10-12, 2026-10-14 to 2026-10-16) showed that small,
well-tested pull requests waited a day or more for a review. The team wants a standing rule instead of windows.
Decision / result: a standing **self-merge** rule in `agents/REVIEW_PROTOCOL.md`: the author may approve and merge
their own pull request when the CI jobs `test` and `frontend` are green on its last push (or a `LOCAL CI PASS`
comment names that commit), the branch is up to date with `main`, and it changes none of the protected paths
(architecture and ACRs, the security and review rules, the enforcement, `config/policy.yaml`, `config/inventory.yaml`,
the public edge, the UI contract). `brain.py verify-main` (`main-guard`) now checks those conditions through the
GitHub API (`self_merge_problem`, `SELF_MERGE_PROTECTED`), so a valid self-merge needs no `main-exceptions.txt` line.
The rule starts when a teammate approves this pull request: it changes the enforcement, so it cannot be self-merged.
Consequences: the review protocol, `GIT_WORKFLOW.md`, `AGENT_PROTOCOL.md`, `PARALLEL_LANES.md`, `HOW_WE_WORK.md`,
`START_HERE.md` and the Brain README say the same. The gaps where a green CI does not yet mean "safe to merge", and
the checks to add, are OP-014; the first three (Docker tests in CI, prompt-injection cases, the flaky timing test) go
in `task/TEST-HARDEN-1`. VM changes still need their lease, `code.bash` and `nonint-check.sh`.
References: [review protocol](../agents/REVIEW_PROTOCOL.md), [OP-014](../OPEN_PROBLEMS.md).

## 2026-10-18 — LF-3 step 03: vm-095's worker exports to Langfuse Cloud (EU), ACR-0016 applied

Type: deployment
Who: conantkd (+ agent)
Context: ACR-0013 and ACR-0016 were accepted in the review of #156 (juanbetancurm); this push applies them
(`ARCHITECTURE.md` 1.8.16, Hobby plan with two named users) and records the deployment.
Decision / result: vm-095 runs 7e6e33c (the head of #156, deployed before its merge because the compose line for
`ARGUS_TRACING_ENDPOINT` is only there). The worker traces to Cloud: a healthy check and an SC-02 crash loop produced
traces whose attributes are exactly the allowlist (no input or output); with Cloud unreachable SC-02 still passed, one
dropped-telemetry line, same duration, full audit. The self-hosted stack, its volumes, images and secrets were
removed. The team keeps option C (no prompts, results or tool arguments in Langfuse; audit in Argus).
Consequences: operators open the trace from the incident view; the Agent page shows only the trace id. Takeover of an
EXPIRED lease of juanbetancurm (DEPLOY-164) on both VMs. The next deploy of `main` replaces 7e6e33c.
References: [evidence](../execution/history/LF-3/step-03/evidence.md),
[ACR-0016](../architecture/changes/ACR-0016-langfuse-cloud.md).

## 2026-10-18 — DEPLOY-166: vm-095 on main 19b1085 (#165 self-merge rule, #166 prompt-injection escape)

Type: deployment
Who: conantkd (+ agent)
Context: #166 (TEST-HARDEN-1) and #165 (SELF-MERGE) were approved by conantkd and merged the same day; #166 changes
the agent image (the model context now escapes `evidence` / `passage` / `reported` tags in untrusted text).
Decision / result: vm-095 moved from `7e6e33c` to `main` `19b1085` (backup, nothing to migrate, agent, worker and
scheduler rebuilt on one image, 20/20, 55/55, WRITE GATE CLOSED, tracing to Langfuse Cloud still on, NO
INTERFERENCE). The first image build failed on a transient PyPI timeout and changed nothing; the second passed.
Consequences: the scheduler is now on the same image as the agent and worker (it had an older one since 2026-10-16).
vm-166 was not changed. The follow-ups on the self-merge rule that conantkd left in the review of #165 (renamed files,
unprotected safety paths, who may post `LOCAL CI PASS`, the two unchecked rules) are still open.
References: [evidence](../execution/history/DEPLOY-166/step-01/evidence.md).

## 2026-10-18 — CI-ONE-RUN: one CI run per push, and a draft pull request from a task branch's first push

Type: implementation
Who: juanbetancurm (+ agent)
Context: `ci.yml` ran on every `push` to any branch **and** on every `pull_request`, so each push to a branch with an
open pull request started two identical runs (seen on #165 and #166: a `push` run and a `pull_request` run of the same
commit, each with `test` and `frontend`). `GIT_WORKFLOW.md` asked for a push after every checkpoint "so CI runs", but
opened the pull request only when the task was complete, so the `push` trigger was what tested work in progress.
Decision / result:
- `ci.yml` triggers on `pull_request` and on `push` to `main` only (`main-guard` needs that one). Same jobs and steps.
- **New rule (`GIT_WORKFLOW.md` step 3):** every task branch has a pull request from its first push, opened as a draft
  (`gh pr create --draft`) and marked ready (`gh pr ready`) when the task is complete. Drafts run the same
  `pull_request` CI, so work in progress is still tested, once per push.
- `brain.py start` / `status` list draft pull requests apart, as tasks in progress, not under "waiting for review"
  (`format_prs`).
- The merge check and `brain.py verify-main` read the check runs of the pull request's head commit, which the
  `pull_request` run reports; `policies/TDD.md` (stage 5) and the Brain README follow.
Consequences: half the CI runs for the same checks; the board shows which tasks are in progress.
References: [git workflow](../policies/GIT_WORKFLOW.md), [TDD policy](../policies/TDD.md).

## 2026-10-18 — SELF-MERGE-2: the four gaps conantkd found in the self-merge rule

Type: implementation
Who: juanbetancurm (+ agent)
Context: `conantkd` approved #165 (the self-merge rule) with four follow-ups: a renamed file escapes the protected-path
check; safety-relevant paths are not protected; anyone, including the author, can post the `LOCAL CI PASS` that
replaces CI; rules 3 (up to date) and 5 (merge commit, branch kept) are only text.
Decision / result: `brain.py verify-main` closes all four.
- **Renames:** `changed_paths` adds `previous_filename`, so a protected file moved out of a protected folder still
  counts as a protected change.
- **More protected paths:** all of `brain/policies/` and `brain/agents/`, `ops/`, `deploy/*/compose*.yml`,
  `deploy/migrations/`, the code that enforces the write gate and the rails (`argus/policy/`,
  `invoke_capability.py`, `gate_report.py`, `isolation_check.py`) and their tests (`tests/brain/`, the write-gate,
  tool-isolation and prompt-injection tests).
- **`LOCAL CI PASS`:** it counts only when posted by a developer other than the PR's author.
- **Rules 3 and 5, measured:** the merge commit must have two parents, main's commit before the merge must be in the
  merged branch, and the branch must still exist.
`agents/REVIEW_PROTOCOL.md` lists the same paths and conditions. Ordinary paths (application code, the frontend,
`deploy/ui/Dockerfile`, ordinary tests, journal entries, docs) stay self-mergeable.
Consequences: more PRs need a teammate (every `ops/` or rail-test change). When CI does not run, a self-merge needs a
teammate's local CI run.
References: [review protocol](../agents/REVIEW_PROTOCOL.md), the review of #165.

## 2026-10-18 — T-0045 proposed: the backend for the redesigned UI's charts, map and verdict (ACR-0021)

Type: decision (proposed)
Who: juanbetancurm (+ agent)
Context: the redesigned UI prototype ("ui-graphs": verdict card, ECharts charts with thresholds and events, 2D/3D map
with live health, dashboard fleet view) needs fields the API does not serve. A review of the code against the draft
plan found: the target exporter already exports `argus_probe_success` and `argus_probe_duration_seconds` per
`owner` and `dependency`, but the topology reads only the per-owner minimum (an owner with two dependencies shows both
links `unknown`); `series.key` is the signal name and the topology's time field is `observed_at`, so the plan adds
fields (`kind`) instead of renaming.
Decision / result: proposed [ACR-0021](../architecture/changes/ACR-0021-ui-insights-v2.md) (new fields on the
ACR-0017 routes, two new routes `GET /api/v1/overview` and `GET /api/v1/target-metrics`, one `MetricsPort` method,
migration 007) and [T-0045](../tasks/current/T-0045-ui-insights-backend.md), the step-by-step specification
(B1–B8) with the ground truth, contracts, rules and tests an agent implements from.
Consequences: no code changes in this PR. B1–B4 need no new route; B5–B7 need the ACR accepted (migration, routes).
References: [ACR-0021](../architecture/changes/ACR-0021-ui-insights-v2.md),
[T-0045](../tasks/current/T-0045-ui-insights-backend.md), ACR-0017.

## 2026-10-18 — NEXT-PHASE proposal: human-approved remediation, an operator terminal, operator access and audit, more autonomous investigation

Type: decision (proposed)
Who: juanbetancurm and conantkd (+ agents)
Context: Argus diagnoses and recommends; humans repair outside it. The team wants supervised remediation, with a human
operator as the final approver. ARCHITECTURE §14 designs Argus-executed actions but none of it is built (OP-015); the
access model was designed for a read-only UI (password, non-revocable tokens, a shared password still listed in
`SECURITY.md`, OP-016). Two proposals existed: this one (security, terminal, responsibility) and `conantkd`'s "Argus
actúa" (catalogue, cards, colours, prediction, judge, memory, research, scenarios). This PR merges them.
Decision / result: proposed, for team review before any implementation:
- [ACR-0018](../architecture/changes/ACR-0018-operator-access-and-audit.md): one account per person, WebAuthn,
  step-up, revocable sessions, explicit permissions, an audit hash chain copied off Host A, privileged routes only on
  a private path;
- [ACR-0019](../architecture/changes/ACR-0019-human-approved-remediation.md): a closed catalogue; service and
  action cards; cited grounds with a computed basis (model-only becomes a suggestion); risk colours that only go up; a
  mandatory prediction and alternatives; a judge that can only make it stricter; a human approves the frozen proposal;
  the worker executes (dispatch reads only frozen rows); verification of the prediction; a memory of verified actions;
  shadow mode for later autonomy; scenario answer keys; lab targets only;
- [ACR-0020](../architecture/changes/ACR-0020-operator-terminal.md): a recorded, human-only terminal through a
  broker with an SSH CA; "Insert" limited to what the cards allow;
- [ACR-0022](../architecture/changes/ACR-0022-autonomous-investigation.md): open investigations, follow-up checks,
  new reads, a curated reference corpus and isolated research, all reads and suggestions only.
The plan (phases 15–23, lanes, gates, open decisions) is the task file
[NEXT-PHASE](../tasks/current/NEXT-PHASE-supervised-remediation.md).
Consequences: nothing changes in the code, the configuration or on the VMs. Earned autonomy, more action families
(PostgreSQL, configuration, rollback, Linux, generated tools) and other runtimes are deferred to later ACRs.
References: [task](../tasks/current/NEXT-PHASE-supervised-remediation.md), OP-015, OP-016.

## 2026-10-18 — T-0045 B1: thresholds in the signal catalogue; host-metrics thresholds and heartbeat

Type: implementation
Who: conantkd (+ agent)
Context: the redesigned UI draws warning and critical lines on its gauges and charts; the API served only the values.
Step B1 of [T-0045](../tasks/current/T-0045-ui-insights-backend.md) (no new route, so it does not wait for ACR-0021).
Decision / result:
- `config/signals.yaml` gains an optional `thresholds:` map (`warning`, `critical`, `direction`) for nine signals, validated at
  startup by `argus/application/thresholds.py` (unknown signal, non-number, bad direction, warning past critical, unknown
  field: the API refuses to start). `read_signals` keeps it out of the PromQL templates.
- `GET /api/v1/host-metrics`: each row adds `thresholds` for `cpu_busy_ratio`, `memory_used_ratio` (the available-ratio lines
  flipped to used: 0.75 / 0.90) and `disk_used_ratio`, plus `heartbeat_age_s` and `heartbeat_stale` from the stored
  monitoring state (`last_beat_at`). Stale = older than 150 s, twice the 60-75 s renewal measured in T-0035. No heartbeat
  recorded = `null` for both, never fresh. Computed per answer, outside the 20 s reading cache.
- Open decision 3 of T-0045 (heartbeat staleness) is answered with 150 s; the initial thresholds are the spec's table.
Consequences: additive fields only; the UI ignores them until it reads them. `critical` equals each detector's threshold,
pinned by a test, so a detector change that is not mirrored in `signals.yaml` turns CI red.
References: [ACR-0021](../architecture/changes/ACR-0021-ui-insights-v2.md), `docs/API-FOR-UI.md`.

## 2026-10-18 — T-0045 B1 follow-up: the two code notes from the review of #173

Type: implementation
Who: conantkd (+ agent)
Context: `juanbetancurm` approved #173 (B1) with three non-blocking notes. Notes 1 and 2 are code; note 3 (the status line of
[T-0045](../tasks/current/T-0045-ui-insights-backend.md)) is his follow-up.
Decision / result:
- **Note 1, `unit` and `scale`:** the threshold entries of `config/signals.yaml` now accept the optional `unit` (non-empty text) and
  `scale` (a positive number) the spec allows, validated like the rest. They are display hints: kept in the answer when given, absent
  when not (the shipped entries set neither, so no answer changes), and carried through the memory flip.
- **Note 2, the 150 s heartbeat staleness:** kept as a constant, now pinned by a test to the scheduler's configuration
  (`deploy/scheduler/schedules.yaml`): it must be at least two reconcile ticks (`every_s`, 60) and below the loss threshold
  (`stale_after_s`, 180). A schedule change that crosses it turns CI red. Deriving it at runtime was not chosen: the API does not read
  the scheduler's file today, and the test keeps the two in step without a new dependency.
Consequences: no change to any answer with the shipped configuration.
References: review of #173; the B1 entry above (2026-10-18, "T-0045 B1").

## 2026-10-18 — CI-COST: main runs main-guard alone; a new push cancels the PR's run in progress

Type: decision
Who: conantkd (+ agent)
Context: the organisation's GitHub Actions minutes went past the plan's 3000 included minutes in October (about 3700
used). Each PR push costs about 6 minutes (`test` and `frontend`) and each merge about 9 more on `main` (the same two
jobs again, plus `main-guard`); 38 runs on 2026-10-18 alone, several of them for a PR pushed twice in a row.
Decision / result: two changes in `.github/workflows/ci.yml`.
- **`test` and `frontend` run on pull requests only.** A merge already needs both green on the PR's last push with the
  branch up to date with `main` (REVIEW_PROTOCOL.md), so the run on `main` tested the same code. A push to `main` now
  runs `main-guard` alone (about 3 minutes instead of 9).
- **`concurrency`:** one group per pull request; a new push cancels that PR's run still in progress (its result no
  longer counts, only the last push does). Runs on `main` are never cancelled, so every merge gets its `main-guard`.
Consequences: about 6 minutes saved per merge, plus the unfinished part of every superseded PR run. A cancelled run
shows "cancelled", not failed. What `main` no longer gets is a second run of the tests after the merge commit; a
check on `main` itself stays available with `python ops/local_ci.py --main`. Changing `.github/` is a protected path:
this needs a teammate's approval.
References: [REVIEW_PROTOCOL.md](../agents/REVIEW_PROTOCOL.md).

## 2026-10-18 — T-0045 B2: incident metrics with kind, thresholds, events, the incident band and a summary

Type: implementation
Who: conantkd (+ agent)
Context: step B2 of [T-0045](../tasks/current/T-0045-ui-insights-backend.md); builds on B1 (thresholds, #173).
Decision / result:
- `config/ui-incident-signals.yaml`: every entry has a `kind` (`memory`, `restarts`, `cpu`, `latency`, `health`, `disk`,
  `database`, `network`, `other`), validated (default `other`).
- `GET /api/v1/incidents/{id}/metrics`: per series `kind`, `thresholds` (B1's lines scaled like the values) and
  `detector_threshold` (the scaled critical line, on the `fired` series only); at the top `incident_from`, `incident_to`
  (`null` while open), `events` and a template `summary`.
- Events: `restart` where `container_restart_count` rises and `oom_kill` where `oom_killed` goes 0 to 1 (container targets
  only; read even when the class chart does not draw them; a failed read leaves no event, not a broken answer);
  `alert_fired` / `alert_resolved` from the incident's `alert_occurrence` rows that fall inside the window. `deploy` waits
  for B6. A first sample already at 1 is not a new OOM.
- Summary: one template per class and per fired state (`SUMMARIES`), filled with the extreme of the judged series;
  an unreadable series says the state is unknown, never healthy. No address, URL or model text.
Consequences: additive; the UI ignores the new fields until it reads them. Up to two extra range reads per container
incident, inside the existing 30 s / 10 min shared cache.
References: [ACR-0021](../architecture/changes/ACR-0021-ui-insights-v2.md), `docs/API-FOR-UI.md`.

## 2026-10-18 — T-0045 B4: the incident verdict fields

Type: implementation
Who: conantkd (+ agent)
Context: step B4 of [T-0045](../tasks/current/T-0045-ui-insights-backend.md). The UI's verdict card needs a summary, a severity, a cause with
a confidence, the top evidence, what could not be checked and the path to the cause; the incident route served only the raw record.
Decision / result:
- `IncidentClassSpec.severity` (`critical`; `warning` for `monitoring_blind_spot`).
- `argus/application/incident_view.py::build_verdict`: a pure function of the incident, its class, its evidence, the evidence the conclusion cites
  (the `incident.recorded` audit event) and the declared dependencies. `GET /api/v1/incidents/{id}` adds `severity`, `summary`, `cause`,
  `evidence_highlights`, `not_checked`, `cause_path`, `duration_ms`, `next_actions` (`[]`), `hypotheses` (`[]`) for every role.
- Severity: the class's; `warning` for `undiagnosable` / `unsupported_escalated`; `ok` for `no_incident`; `null` while no class is known.
- Summary: `<problem> on <name>: <first finding>` for a diagnosis (the runner's `<class>: ` prefix stripped), else the first sentence of the
  diagnosis, else a sentence per outcome. Cause: confidence 0.9 / 0.6 / 0.3 and its label; `null` without a root cause.
- `not_checked`: each evidence with a status other than `ok`, each missing signal, and `metrics · stale or unavailable` (the exception text is not repeated).
- A viewer's `evidence_highlights` is `[]` (its view carries no evidence text); the other fields carry no evidence text.
- `cause_path` is a small BFS over the declared dependencies, the same rule as the topology's (B3, #175); the two can share one function
  once both are merged.
Consequences: additive; two more store reads per incident view (evidence and audit were already read for operators).
References: [ACR-0021](../architecture/changes/ACR-0021-ui-insights-v2.md), `docs/API-FOR-UI.md`.

## 2026-10-18 — T-0045 B3: topology with box health, problems, one state per dependency link, roles and the cause path

Type: implementation
Who: conantkd (+ agent)
Context: step B3 of [T-0045](../tasks/current/T-0045-ui-insights-backend.md); builds on B1's thresholds (#173). Until now an
owner with two dependencies showed both links `unknown` (the topology read only the per-owner minimum of the probe).
Decision / result:
- `MetricsPort.dependency_probes(target) -> {dependency: ProbeSample(success, duration_s, at)}`; the Prometheus adapter reads the
  exporter's `argus_probe_success` and `argus_probe_duration_seconds` through two new catalogue signals
  (`dependency_probe_success`, `dependency_probe_duration_s`), on the target's own host; older than `max_staleness_s` is missing.
  No exporter change. Every fake returns `{}`.
- Inventory: optional `profile: scenario` (the seven scenario-only containers of vm-166: nginx, slow, burner, filler, leaker, client,
  backend) and `link_warning_ms`, both validated.
- Nodes: `health`, `idle`, `networks`, `problems` (restarts and CPU quota against B1's lines, an unhealthy check as a warning,
  memory against the limit from the incident's evidence, `stale_metrics` for a running box with no fresh sample), `role`.
- Edges: `id`, `kind` (`dependency` | `argus_reads`), the state of that dependency's probe (`ok`, `slow` above 100 ms or the owner's
  `link_warning_ms`, `broken`, `unknown`), `checked_at` (the read time: an instant query stamps the evaluation time, not
  the probe's; review of #175), `latency_ms`, `reason`. "No shared network" still overrides.
  With no per-dependency sample and a single dependency, the old per-owner minimum still decides.
- With `incident_id`: `cause_path` (BFS over declared dependencies; `[target]` if it is its own cause; `[]` without a cause).
- Decisions taken here: memory problems warn at 80 % and are critical at 90 % of the limit (no B1 line exists for memory);
  CPU-quota problems are shown in percent; a restarting box is `degraded` even below the restart warning (the spec's rule).
Consequences: additive; two more reads per container with dependencies in the 20 s shared build (cache unchanged); the memory and
quota signals join the per-container snapshot.
References: [ACR-0021](../architecture/changes/ACR-0021-ui-insights-v2.md), `docs/API-FOR-UI.md`.

## 2026-10-19 — ACR-0021 accepted: the backend for the redesigned UI may continue past B4

Type: decision
Who: juanbetancurm (+ agent); accepted by the two approvals of this pull request
Context: [ACR-0021](../architecture/changes/ACR-0021-ui-insights-v2.md) was proposed in #172 with
[T-0045](../tasks/current/T-0045-ui-insights-backend.md). B1 to B4 add fields only, so they were built before acceptance
(B1 merged in #173 and #177; B2 to B4 in review in #174 to #176). B5 (migration 007), B6 (the two new public routes) and B7
wait for acceptance. The T-0045 status line said the whole task waited, which disagreed with its own order section.
Decision / result:
- ACR-0021 is `accepted` by `conantkd` and `juanes6554` through their approvals of this pull request, the second one
  for least privilege (two new routes on the public edge). It merges only with both.
- T-0045's four open decisions are answered from the reviewed steps: the spec's thresholds; the seven scenario-only
  containers are `idle`; links warn above 100 ms (`link_warning_ms` per target); the heartbeat is stale after 150 s. The
  baseline window stays open until B7.
- `ARCHITECTURE.md` is applied in one pull request once B4 has merged; until then `SUMMARY.md` records the difference.
- The T-0045 status line now says `in progress` and agrees with its order section.
Consequences: B5 to B7 may start. No code, configuration or deployment changes in this pull request.
References: #172, #173, #177, #174, #175, #176.

## 2026-10-19 — EVAL-offers: the unoffered capabilities measured; ACR-0023 proposed; four replay fixes; long-log cases

Type: evaluation
Who: conantkd (+ agent, unattended overnight on vm-095)
Context: `cpu_history`, `disk_history`, `request_path`, `search_logs` and `baseline` are offered to no class until an
evaluation batch measures them. One batch per offer, each the base plus one tag, 61 cases × 5 trials.
Decision / result:
- No capability is offered to a class. `cpu_history` and `disk_history` are used and change nothing; `request_path`
  0.72 → 0.74; `search_logs` is called in 4 of 50 health runs; `baseline` in 1 of 25 cpu runs. Health alone moves
  between 0.66 and 0.82 in batches that do not touch it, so a class-level number is read with the mechanism.
- Proposed: [ACR-0023](../architecture/changes/ACR-0023-log-read-pattern-matches.md). `container.logs` also
  brings the last 30 min's lines that match a named failure pattern and are not in its tail. Measured (H1): it changes
  the evidence of 3 cases; in `health-api-vm166-01-longlog` 1/5 → 5/5, every diagnosis citing the line outside the
  tail. The agent finds a buried cause without a runbook telling it to search.
- The replay now answers like the gateway in four places: an earlier metric window is its own fixture (it was the
  current one), a fixture is stamped with the time it is read (a fixed date read as a week-old sample), `/connectivity`
  is built from the two status fixtures, and a long log answers `logs`, `logs_window` and `search`. Two vm-166 health
  cases answered their own health URL with 200 against their health check; they now agree.
- 6 `-longlog` twins of the health cases (the cause outside the log's tail) and derived cpu and disk history fixtures.
- The OpenAI account ran out of credits during one batch; it and a partial one were discarded and rerun.
- Also here (asked by conantkd): `main-guard` gets `checks: read`. It has been red on every push to `main` since #177,
  the first self-merge: `verify-main` reads the commit's check runs to validate a self-merge and got
  `Resource not accessible by integration (HTTP 403)`. A permission gap, not a broken review rule.
Consequences: with ACR-0023 accepted, each log read makes up to 6 more gateway requests and carries up to 6 more
redacted lines; architecture 1.8.17. The evaluation has 61 cases; `ambiguous-health-no-cause-longlog` joins
`BASELINE_MISSES`.
References: [evidence](../execution/history/EVAL-offers/step-01/evidence.md).

## 2026-10-19 — T-0045 B5: re-check lineage (`parent_id`, migration 007)

Type: implementation
Who: juanbetancurm (+ agent)
Context: the redesigned UI offers "Re-check" on an incident and shows the re-checks under it; the API had no link between
the two. Step B5 of [T-0045](../tasks/current/T-0045-ui-insights-backend.md), which waits for ACR-0021's acceptance
(PR #180) because it adds a migration and a query parameter.
Decision / result:
- `POST /api/v1/investigations` accepts an optional `parent_id` (`^inc_[A-Za-z0-9_-]+$`, at most 64 characters). It must
  name an existing incident, else 422 and nothing is created. Every role reads every incident, so "readable by the caller"
  is "exists". The `investigation.requested` audit records it. Quotas are unchanged: a re-check is a manual incident.
- The incident keeps `parent_id`; the detail and every list row return it (`null` when it re-checks nothing).
  `GET /api/v1/incidents?parent_id=<id>` lists that incident's re-checks, newest first; a malformed id is 422.
- Postgres: `deploy/migrations/007_incident_parent.sql` adds `incident.parent_id` (foreign key to `incident.id`, indexed
  with `opened_at`) and extends the forward-only trigger: the parent never changes, like the other identity columns. No
  new grant. Two new `db-check` checks: a missing parent and a changed parent are both refused. `import_sqlite` copies
  the column when the old file has it.
- SQLite: an older file gains the column at start, like `claimed_by`.
Consequences: additive fields only. The UI ignores them until it reads them. Deploying needs `ops/db-migrate.sh` (007)
before the new image.
References: [ACR-0021](../architecture/changes/ACR-0021-ui-insights-v2.md), `docs/API-FOR-UI.md`.

## 2026-10-19 — ACR-0021: the acceptance record corrected (the least-privilege approval is pending)

Type: decision
Who: conantkd (+ agent)
Context: #180 recorded ACR-0021 as accepted by `conantkd` and `juanes6554` and said it would merge only with both
approvals. conantkd asked to merge it with conantkd's approval only; it merged that way (comment on #180). The record then
named an approval that had not been given.
Decision / result:
- ACR-0021's rows now say what happened: accepted by `conantkd` (#180); the second approval, required for least privilege
  (two new routes on the public edge, B6), is **pending** and is `juanes6554`'s approval of this pull request.
- T-0045's status line is brought up to date: B1, B2 and B4 merged; B3 in review (#175); B5 in draft (#181); B6 waits
  for the least-privilege approval.
Consequences: B5 (migration, no public route) and B7 are not affected by the pending approval; B6 does not start until
this pull request is approved and merged.
References: #180, [ACR-0021](../architecture/changes/ACR-0021-ui-insights-v2.md).

## 2026-10-19 — Review rule: an update that only brings in main keeps the approval

Type: decision
Who: juanbetancurm (+ agent)
Context: a pull request merges only when it is up to date with `main` and approved on its last push. Every merge puts
the other open pull requests behind, and "Update branch" is a new push, so their approvals stopped counting. #174 and
#176 were approved and fell behind when #178 merged; updating them would have needed a new review although their code
had not changed (in the end they were merged without the update).
The T-0045 steps all touch `contracts/`, a protected path, so the self-merge rule does not help them.
Decision / result:
- An approval stays valid after later pushes when each commit after the approved one is a merge with `main` that git
  made without a conflict (its tree is git's automatic merge of its parents). A resolved conflict, any extra edit, any
  other commit or a rewritten branch needs a new approval. CI green on the last push and up to date are unchanged.
- `brain.py verify-main` (CI `main-guard`, `brain.py start`) checks it with `only_main_merged_since` and
  `git merge-tree --write-tree`; `check_main` takes it as `keeps_approval`.
- `REVIEW_PROTOCOL.md`: the rule, why, and how it is enforced; `GIT_WORKFLOW.md`: the "Never" line refers to it.
Consequences: the reviewer can update an approved pull request and merge it without a new review round. It changes
the enforcement, so it starts when a teammate approves this pull request.
References: `brain/agents/REVIEW_PROTOCOL.md`, `brain/tools/brain.py`.

## 2026-10-19 — ACR-0021 applied to ARCHITECTURE.md as built through B5 (1.8.18)

Type: decision
Who: conantkd (+ agent)
Context: ACR-0021 is accepted (#180) with its least-privilege approval (#182). §6 asked for one pull request that
applies the text once B4 had merged. B1 to B5 are now merged (#173, #177, #174, #175, #176, #181).
Decision / result:
- `ARCHITECTURE.md` 1.8.17 → 1.8.18. It describes only what is built:
  - §5.8: `IncidentClassSpec.severity`;
  - §7.1, host metrics: thresholds and the heartbeat age;
  - §7.1, incident metrics: `kind`, thresholds, the incident window, events from counters and alert occurrences, and a
    summary, with "not yet" for `baseline`, `deploy` events and the 6h/24h ranges;
  - §7.1, topology: per-node health, problems, roles and the cause path, and one state per dependency link, with
    `checked_at` as the read time;
  - §7.1, incidents: the verdict fields, `parent_id` on the incident and the list, and `parent_id` on a new
    investigation;
  - §8.1: `MetricsPort.dependency_probes`;
  - §16.1: `incident.parent_id` (migration 007).
- Left for their steps: the two new routes and `locations.conf` (B6, #184), and `baseline`, `deploy` events and the
  `deploy_event` migration (B7). Each adds its own text and bumps the version.
- ACR-0021's rows now say the least-privilege approval was given (#182) and the text is applied. `SUMMARY.md`'s
  "Known differences" row is resolved, and T-0045's status line is current.
Consequences: documentation only; no code, configuration or deployment change.
References: [ACR-0021](../architecture/changes/ACR-0021-ui-insights-v2.md), #180, #182, #181.

## 2026-10-19 — DEPLOY-176: vm-095 on main dfa7332 (T-0045 B1 to B5, migration 007, ACR-0023)

Type: deployment
Who: conantkd (+ agent)
Context: since `19b1085` (DEPLOY-166), the following merged:
- T-0045 B1 to B5: thresholds and heartbeat (#173, #177), incident metrics (#174), topology (#175), the verdict (#176),
  re-check lineage with migration 007 (#181);
- ACR-0023, the log read with pattern matches (#179).

The rest is CI and Brain.
Decision / result:
- vm-095 moved from `19b1085` to `main` `dfa7332`:
  - backup taken;
  - **migration 007 applied before the new image**;
  - agent, worker and scheduler rebuilt on one image;
  - checks: 22/22, 55/55, WRITE GATE CLOSED, LAB BASELINE OK, NO INTERFERENCE.
- vm-166 was not changed.
Consequences:
- The UI's new fields (thresholds, heartbeat, chart context, map health and links, the verdict, `parent_id`) are
  served on vm-095.
- `container.logs` now brings pattern matches from outside the tail.
- The deploy of `77002a7` prepared earlier the same day was not run (not authorized then); nothing changed on the VMs.
References: [evidence](../execution/history/DEPLOY-176/step-01/evidence.md).

## 2026-10-19 — T-0045 B6: `GET /api/v1/target-metrics` and `GET /api/v1/overview`

Type: implementation
Who: juanbetancurm (+ agent)
Context: the redesigned UI has a dashboard and, for one box of the map, a drawer with its recent charts. Step B6 of
[T-0045](../tasks/current/T-0045-ui-insights-backend.md) adds the two routes. `/target-metrics` was built first (it
depended on no open pull request); `/overview` after B3 (#175) and B4 (#176) merged. ACR-0021's least-privilege
approval for the two public-edge routes was given by `juanes6554` on #182.
Decision / result:
- `GET /api/v1/target-metrics?target=<host/kind:name>&range=15m|1h` (`argus/application/target_metrics.py`): a fixed
  series list per kind, read with `MetricsPort.range` on the target's own host only. A container gives
  `container_cpu_quota_used_ratio_5m` and `container_memory_bytes`. A host gives `host_cpu_busy_ratio`,
  `host_memory_used_ratio` (1 - the available ratio, its lines flipped as in `/host-metrics`) and
  `host_disk_used_ratio`. Another kind gives no series yet. Each series carries `kind`, `unit`, `max` and the B1
  `thresholds` (or `null`); at most ~130 points; missing is `null`, an unreadable series is all gaps. Shared 30 s per
  (target, range). A target not in the inventory is 404; a malformed target or another range is 422 before any read.
- `GET /api/v1/overview` (`argus/application/overview.py`): `status` (the worst open severity, `ok` when nothing is
  open), `open_incidents` by severity, the 5 newest open incidents (severity and summary from B4; `info` while the class
  is unknown; `next_action` `null` until B4's `next_actions` are filled), `hosts` (the `/host-metrics` rows: one shared
  20 s snapshot for both routes), `fleet` (boxes by B3 `health`), `links` (`ok`/`total` of the declared dependencies),
  `last_closed_at`. Built from the newest `incidents_limit_cap` incidents and the topology and host-metrics snapshots:
  no new host read, no executor call. Shared 15 s.
- Any authenticated role for both; no PromQL, address or internal URL in or out.
- Edge: `location = /api/v1/target-metrics` and `location = /api/v1/overview` (GET only, rate-limited); the contract,
  two samples and `API-FOR-UI.md`.
- Built in `build_api` from the existing metrics port, thresholds, store and topology, so `wiring.py` is unchanged.
- `ARCHITECTURE.md` 1.8.18 → 1.8.19: the two §7.1 rows, the public-edge paragraph and the changelog; ACR-0021's
  rows say applied through B6. The `GET /api/v1/incidents` row loses filters the route never had (`limit` and
  `parent_id` only).
Consequences: two more public read routes; the browser chooses only an inventory target and one of two ranges.
References: [ACR-0021](../architecture/changes/ACR-0021-ui-insights-v2.md), `docs/API-FOR-UI.md`.

## 2026-10-19 — T-0045 B5 follow-up: `db-check` proves migration 007; SQLite's missing foreign key written down

Type: implementation
Who: conantkd (+ agent)
Context: the review of #181 (B5, merged) left two non-blocking notes. The two new `db-check` refusals also "passed" on a
database without migration 007: the column is missing, the statement fails, and a failure counts as refused. SQLite
enforces no foreign key for `parent_id`.
Decision / result:
- `CHECKS_SQL` gains a read that must succeed, `re-check lineage column present (migration 007)`, before the two
  refusals. `argus db check` now fails on a database that lacks 007, so the refusals prove the protection. The count
  goes from 22 to 23.
- `sqlite_store.py` says where a re-check's parent is checked: by the API only (SQLite runs without
  `PRAGMA foreign_keys`, and an added column has no `REFERENCES`); in Postgres by 007's foreign key.
- Not changed: `parent_id` is also kept inside `body`, and the trigger guards only the column; no code changes it.
Consequences: a deploy record shows 23 database checks once B5 is on a VM.
References: #181, [T-0045](../tasks/current/T-0045-ui-insights-backend.md).

## 2026-10-20 — DEPLOY-189: vm-095 on main 2c7248b (T-0045 B6, the UI with Map and Metrics)

Type: deployment
Who: conantkd (+ agent)
Context: since `dfa7332` (DEPLOY-176), the following merged:
- T-0045 B6 (#184): `/api/v1/target-metrics` and `/api/v1/overview`;
- the B5 follow-up (#185): `db-check` proves migration 007.

The UI image built with `VITE_ARGUS_INSIGHTS=1` (#164, merged 2026-10-17) had never been deployed: DEPLOY-166 and
DEPLOY-176 rebuilt the agent image only.
Decision / result:
- vm-095 moved from `dfa7332` to `main` `2c7248b`:
  - backup taken; no migration (008 comes with B7, #188);
  - agent, worker and scheduler rebuilt on one image;
  - `argus-v18-ui` rebuilt: the Map and Metrics calls are in the bundle, and the edge serves the two B6 routes;
  - checks: 23/23, 55/55, WRITE GATE CLOSED, LAB BASELINE OK, NO INTERFERENCE.
- vm-166 was not changed.
Consequences:
- The real UI shows the Map and Metrics tabs and the Dashboard map (ACR-0017).
- The B6 routes are served, behind a login.
- The browser click-through (D.4) is still to be done by a person.
References: [evidence](../execution/history/DEPLOY-189/step-01/evidence.md).

## 2026-10-20 — T-0045 B8: finer link reasons on the system map

Type: implementation
Who: conantkd (+ agent)
Context: a broken dependency link on the map said only "not reachable" (B3). The exporter knows why a probe failed.
Decision / result:
- `services/target/service.py`: `tcp()` returns a `kind` from the exception type (`refused`, `timeout`, `dns`,
  `other`), and the exporter adds `argus_probe_error{owner,dependency,kind} 1` while a probe fails.
- `config/signals.yaml`: `dependency_probe_error`. `ProbeSample` gains `error_kind`; the Prometheus adapter reads it
  with the same staleness rule as the other probe series.
- `topology.py`: a broken link's `reason` and `label` say `connection refused`, `timeout` or `name not resolved`;
  `other` and a missing kind stay `not reachable`. An `ok` link ignores a leftover kind.
Consequences:
- No new route, no migration, no new field (only `reason`'s values).
- `ARCHITECTURE.md` (the topology row's `reason` values, `ProbeSample.error_kind` in the `MetricsPort` row) is
  updated in a separate pull request: it is a protected path, and this one is self-merged.
- The deploy rebuilds the target exporter on both hosts and the agent image (both leases).
References: `tests/test_t0045_b8_link_reasons.py`.

## 2026-10-20 — CLEANUP-eval-offers: EVAL-offers leftovers removed from vm-095

Type: maintenance
Who: conantkd (+ agent)
Context: EVAL-offers (2026-10-19) left 13 images `argus-v18-agent:eo-*` and `/tmp/eo-*` on vm-095, used by no
service. Its results are archived in its evidence. NEXT_STEP listed their removal as a small item.
Decision / result:
- Listed first: no container used an `eo-` image.
- 13 images and every `/tmp/eo-*` removed; about 2 GB of disk freed.
- Services unchanged; LAB BASELINE OK; NO INTERFERENCE before and after.
Consequences:
- vm-095 holds only the images of the running services and its build cache.
References: [evidence](../execution/history/CLEANUP-eval-offers/step-01/evidence.md).

## 2026-10-20 — OP-014 step 10: property-based tests for redaction and target parsing; a redaction gap fixed

Type: implementation
Who: conantkd (+ agent, autonomous night work)
Context: OP-014 lists what a green CI does not yet cover under the self-merge rule. Step 10 asks for property-based
tests (Hypothesis) of redaction, target parsing and the policy engine.
Decision / result:
- `tests/test_op014_property_based.py`: generated inputs, checked for properties that must always hold:
  - no 40+ character token survives in any text, spaced or glued to its neighbours;
  - a named secret (`password=`, `token:`, …), a `Bearer` token and a password in a connection URL are always masked;
  - redacting twice changes nothing more; text with nothing secret-like is unchanged;
  - a secret key is masked at any depth of dicts and lists; a declared directory keeps its files readable;
  - a target parses back to itself; any text parses to a valid target or a `ValueError`.
- **A real gap found:** a token glued to a non-ASCII letter (`é<token>`, `<token>ж`) was not masked. Python's Unicode
  `\b` treats that letter as a word character, so the high-entropy rule found no boundary. The same held for `sk-`
  keys and `Bearer`. Fixed with `re.ASCII` on those three rules in `argus/capabilities/redaction.py`: it only masks
  more, never less.
- `pyproject.toml`: `hypothesis` added to the `test` extra (CI installs `.[test]`).
- The policy engine (`argus/policy/`) is a protected path: its property tests are left for a teammate-reviewed PR.
Consequences:
- Model-bound, stored and view-bound text masks such tokens from the next deploy of the agent image.
- No evidence that such a token ever reached the model or the store: it needs a secret written with no space after a
  non-ASCII letter.
References: OP-014 step 10 in `OPEN_PROBLEMS.md`.

## 2026-10-20 — DEPLOY-195: both VMs on main bdcd048 (T-0045 B8, the redaction fix)

Type: deployment
Who: conantkd (+ agent; run by the agent while conantkd was away, authorized)
Context: since `2c7248b` (DEPLOY-189), the following merged:
- T-0045 B8 (#192): finer link reasons;
- the redaction fix found by OP-014 step 10's property tests (#195).

B7 (#188) is still in review, so B7 and B8 were not deployed together as prepared (`task/DEPLOY-B7-B8-prep`).
Decision / result:
- vm-095 moved from `2c7248b` to `bdcd048`:
  - backup taken; no migration;
  - agent, worker and scheduler rebuilt on one image;
  - the target services rebuilt.
- vm-166 moved from `ccc810e` to `bdcd048`: its target services rebuilt (B8's exporter).
- Checks: 23/23, 55/55, WRITE GATE CLOSED; the glued token masked in the worker; LAB BASELINE OK and NO INTERFERENCE
  on both VMs.
Consequences:
- A broken dependency link on the map says `connection refused`, `timeout` or `name not resolved` when the exporter
  knows why.
- Model-bound, stored and view-bound text masks a token glued to a non-ASCII letter.
- The B7 deploy now needs only B7: migration 008, the agent image and `argus deploy record`. The prepared code.bash
  still rebuilds the target services; that step can be dropped.
References: [evidence](../execution/history/DEPLOY-195/step-01/evidence.md).

## 2026-10-20 — OP-014 step 10: property-based tests for the policy engine

Type: tests
Who: conantkd (+ agent, autonomous night work)
Context: the first part of OP-014 step 10 (#195) covered the redaction and the target parsing. This part covers the
policy engine, with tests only, so no protected path changes.
Decision / result:
- `tests/test_op014_property_policy.py` (11 tests, up to 300 generated examples each) against the real
  `config/policy.yaml`:
  - `PolicyEngine.check`:
    - an allow means every condition held (known capability, level, safety class, incident scope, per-incident
      limit);
    - an unknown capability is always refused;
    - a non-empty write gate refuses startup.
  - The inspection policy:
    - a path with `..`, `.` or an empty segment, or a relative path, is never readable;
    - a deny-floor name anywhere in the path (any case), or a floor directory, is never readable, even under an
      allowlist of `/`;
    - an allowed read is always inside the allowlist;
    - the data's deny list only adds to the floor;
    - the journal reads only a listed unit within its line limit;
    - a target without an entry allows no inspected read.
- No gap found. As a check that the tests can fail, three bugs injected in memory were each caught: no scope check,
  no deny list, no path normalization.
Consequences:
- OP-014 step 10 is done; steps 4 to 9 and 11 to 13 remain (most touch `.github/`, a protected path).
References: OP-014 in `OPEN_PROBLEMS.md`.

## 2026-10-19 — MAIN-GUARD hardening: `gh_json` retries; #183's open test case

Type: implementation
Who: conantkd (+ agent)
Context: main-guard once went red on `unexpected end of JSON input` (a cut-off `gh api` answer) and passed on a
rerun. The review of #183 left one case untested: a clean merge of a branch other than `main` after an approval.
Decision / result:
- **Retries:** `gh_json` tries a failed call or a non-JSON answer again, `GH_TRIES` = 3 in all, 2 s then 4 s apart. A
  real failure still raises `BrainError` after the last try.
- **404 is final:** a 404 is an answer, not a glitch (`verify-main` reads a deleted branch that way: not kept), so it
  raises at once with no wait.
- **#183's open case:** two tests pin that only a merge with `main` keeps an approval.
  - A clean merge of another branch needs a new approval.
  - The same code arriving through a branch that merged `main` first also needs one.
  - `only_main_merged_since` already refused both; the tests keep it so.
Consequences: no rule changes. `brain/tools/brain.py` and `tests/brain/` are protected, so a teammate approves.
References: `brain/agents/REVIEW_PROTOCOL.md` ("An update that only brings in main"), #183.

## 2026-10-19 — T-0045 B7: baseline, the 6h and 24h ranges, deploy events (migration 008)

Type: implementation
Who: conantkd (+ agent)
Context: the redesigned UI's incident charts draw a "normal" band, a longer lead-in and deploy markers. Step B7 of
[T-0045](../tasks/current/T-0045-ui-insights-backend.md), after ACR-0021's acceptance and B5.
Decision / result:
- **Ranges:** `GET /api/v1/incidents/{id}/metrics` accepts `6h` and `24h`, with at most ~130 points per series as
  before. The answer lists `ranges_available`.
- **Baseline:** each series gains `baseline`, `{p50, p95, from, to}`.
  - It covers the same signal over the 24 h that end an hour before the incident opened, scaled like the values.
  - It is `null` when under half of that window has samples, or when the read fails: unknown, never a guessed band.
  - It takes one 289-sample `MetricsPort.range` read per incident and signal, kept for the incident's life. The
    quantiles are computed in Python (linear between ranks, as `quantile_over_time`), so there is no new port method.
  - This answers T-0045's open decision 4 (the window and its cost).
- **Deploy events:**
  - `deploy_event` (migration **008**; B5 took 007), insert-only for the runtime role, with the commit checked as hex.
  - `argus deploy record --commit --ref --as [--host]` validates against the inventory and the formats, writes it and
    audits it (`deploy.recorded`).
  - `ops/deploy.sh` calls it through the running agent before its `DEPLOY OK` line. It is never fatal: on the deploy
    that first brings the verb (the old image still runs), or on vm-166 (no agent), it prints the command to run after
    the rebuild.
  - The charts show the incident host's deploys inside the window, labelled with ref and short commit, never who.
- `db-check` gains three checks: the insert succeeds; an UPDATE and a DELETE are refused.
Consequences:
- Additive fields only. ARCHITECTURE 1.8.20 (§7.1, §16.1; B6 took 1.8.19).
- **Deploying this step:** `db-migrate.sh` (008) before the image; then record that deploy itself with
  `argus deploy record` after the rebuild.
- vm-166's deploys are recorded from vm-095 with `--host vm-166`, since the database lives there.
References: [ACR-0021](../architecture/changes/ACR-0021-ui-insights-v2.md), `docs/API-FOR-UI.md`.

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

## 2026-10-20 — OP-014 step 7 (part): CI actions pinned by commit SHA; the gitleaks download verified

Type: CI
Who: conantkd (+ agent, autonomous night work)
Context: OP-014 step 7 asks to pin every action by commit SHA. A tag can be moved to other code; the Trivy action
was compromised that way in March 2026.
Decision / result:
- `.github/workflows/ci.yml`: the four actions pinned by commit SHA, each with its tag in a comment:
  - `checkout` v4.4.0, `setup-python` v5.6.0, `setup-node` v4.4.0, `upload-artifact` v4.6.2;
  - each SHA was resolved on 2026-10-20 from the major tag the workflow used, so the code that runs is unchanged.
- The gitleaks archive is checked against the release's published SHA-256 before it runs.
Consequences:
- A moved tag or a swapped release archive cannot change what CI runs.
- Updating an action means changing its SHA in a reviewed PR.
- This PR changes `.github/`, so it needs a teammate's approval.
References: OP-014 step 7 in `OPEN_PROBLEMS.md`.

## 2026-10-20 — DEPLOY-B7: vm-095 to main 999b5bb (T-0045 B7, migration 008)

Type: deployment
Who: conantkd (+ agent)
Context: #188 (T-0045 B7: the baseline, the 6h and 24h ranges, deploy events) merged; the deploy was prepared in
`task/DEPLOY-B7-B8-prep`.
Decision / result:
- vm-095 runs `main` `999b5bb`: backup, `008_deploy_event` applied (schema 001 to 008), agent, worker and scheduler on
  one image, the deploy recorded in `deploy_event`.
- Checks: `26/26` database checks, `55/55`, `WRITE GATE CLOSED`, `LAB BASELINE OK`, `NO INTERFERENCE` on both VMs.
  vm-166 unchanged (`bdcd048`).
- D.3 (logged in, by conantkd): ranges 15m to 24h, a baseline on the host CPU and memory series.
Consequences: T-0047 step 0 can start (`metrics.compare_baseline` has B7's baseline on vm-095). #203 comes with the
next deploy.
References: [evidence](../execution/history/DEPLOY-B7/step-01/evidence.md), #188, #203.

## 2026-10-20 — T-0045 B7 follow-up: a failed baseline read is not kept

Type: implementation
Who: juanbetancurm (+ agent)
Context: the review of #188 (B7, merged): when the baseline's Prometheus read failed, `IncidentMetrics._baseline`
stored the `None` for the incident's life, so one hiccup hid the "normal" band on every later answer.
Decision / result:
- A failed read (`MetricsUnavailable`, `StaleMetrics`, `ValueError`) returns `None` without storing it; the next
  answer reads it again. "Under half the samples" is still kept, since that window never moves.
- `tests/test_t0045_b7_baseline_deploy.py`: `test_a_failed_baseline_read_is_not_kept_and_the_next_answer_reads_it_again`,
  seen red first.
- Not changed: `008_deploy_event.sql` says the verb runs "after `DEPLOY OK`" (it runs just before that line).
  `db-migrate.sh` refuses a migration whose file changed after it was applied, so the comment stays as it is.
Consequences: no route, field or contract change; reaches vm-095 with the B7 deploy.
References: #188, [T-0045](../tasks/current/T-0045-ui-insights-backend.md).

## 2026-10-20 — T-0045 B8: its line in the 1.8.20 changelog

Type: documentation
Who: juanbetancurm (+ agent)
Context: #193 described B8's finer link reasons in `ARCHITECTURE.md` (§7.1, §8.1) without a version bump, leaving
the bump and the changelog line to whichever of #193 and #188 merged second. #188 merged second as 1.8.20 for B7
only.
Decision / result: the 1.8.20 version line and changelog row also record B8 (the topology's broken-link reason from
`argus_probe_error`; `ProbeSample.error_kind`). No other text changes.
Consequences: none beyond the record.
References: #193, #188, [ACR-0021](../architecture/changes/ACR-0021-ui-insights-v2.md).

## 2026-10-20 — ACR-0024 (hypotheses and cause ranking) and ACR-0025 (live dependency graph) proposed

Type: decision proposal
Who: juanbetancurm (+ agent)
Context: the next-phase plan had areas B (dependency graph with live checks), C (reasoning and cause ranking), G
(memory and feedback) and F (external knowledge). #170 kept the remediation, access, terminal and autonomous
investigation parts and called B and C "separate tracks", but no ACR or task file recorded them, so they dropped out
of the backlog. The incident answer still returns `"hypotheses": []`, and five built reads are offered to no class.
Decision / result:
- [ACR-0024](../architecture/changes/ACR-0024-hypotheses-and-cause-ranking.md) (`proposed`, second approval:
  evidence integrity): hypotheses with evidence for and against in the decisions, checked by the harness (a supported
  cause needs an observation of its own target); a support score computed in code from configured weights, never a
  percentage, never changing the conclusion; an insert-only `incident_hypothesis` table (a new migration); the
  incident answer fills `hypotheses`; `analysis.anomaly_summary`; evaluation labels and the hard check
  `unsupported_root_cause`.
- [ACR-0025](../architecture/changes/ACR-0025-live-dependency-graph.md) (`proposed`, no safety principle): the
  scheduler records link-state transitions from the probes the exporter already runs (insert-only `link_event`,
  a new migration); the map gets `since` and `required`, the incident charts get link events, and a Level 2 read
  `network.link_states` gives them to the investigation. No new target traffic.
- Tasks: [T-0046](../tasks/current/T-0046-live-dependency-graph.md) (B),
  [T-0047](../tasks/current/T-0047-hypotheses-cause-ranking.md) (C; the built reads, which EVAL-offers found change little
  when offered alone, are measured again with hypotheses in H4), [T-0048](../tasks/current/T-0048-incident-feedback.md) (G, waits for
  ACR-0018). F stays in ACR-0022 §3.4–3.5. NEXT-PHASE links them.
Consequences: no code before acceptance.
References: #170, [NEXT-PHASE](../tasks/current/NEXT-PHASE-supervised-remediation.md).

## 2026-10-20 — Phase 15 foundations: OP-015 and OP-016 fixed, the action path protected

Type: implementation
Who: conantkd (+ agent)
Context: phase 15 of the [NEXT-PHASE plan](../tasks/current/NEXT-PHASE-supervised-remediation.md) (#170 merged):
fix OP-015 and OP-016, and extend `SELF_MERGE_PROTECTED` before anything can act. Three items, one pull request.
Decision / result:
- **OP-015 fixed:** ARCHITECTURE §14 says the approval and action machinery is **designed, not built** (1.8.21); the
  plan's phase 9 and its "Escalation / approval" exit line no longer list HITL against a fake endpoint (phase 18).
- **OP-016 fixed:** `policies/SECURITY.md` lists "Each developer's Argus password (one account per person, no
  shared login)" instead of a shared team password. The read-only `principal` query on vm-095 (run by conantkd)
  shows five personal `human` principals, two of them disabled (`conantkd-viewer`, `olav`); no shared account.
- **`SELF_MERGE_PROTECTED`** gains the action path before it exists: `config/actions/`, `config/risk.yaml`,
  `config/ranking.yaml` (ACR-0024), `argus/capabilities/write_contract.py`, and the reserved names `argus/actions/`
  (the dispatch module) and `services/action-gateway/`. `REVIEW_PROTOCOL.md` lists them; `tests/brain` covers each.
- The NEXT-PHASE status says the plan is approved (its ACRs are still `proposed`).
Consequences: the first PR that builds the dispatch module or the gateway uses those names, or updates the list in
the same PR. Nothing left for OP-015 or OP-016.
References: [OPEN_PROBLEMS](../OPEN_PROBLEMS.md) OP-015, OP-016; ACR-0019; #170.

## 2026-10-20 — OP-002 reviewed: the eight P0 gaps against ARCHITECTURE 1.8.20 and the code

Type: review
Who: conantkd (+ agent)
Context: OP-002 (open since 2026-09-30) held a first, unverified assessment of the library's eight P0 gaps. Phase 17
and the NEXT-PHASE ACRs depend on several of them.
Decision / result: every gap checked against the text, the code on `main` and the proposed ACRs (table in
OPEN_PROBLEMS OP-002):
- **G-008 closed:** tools come only from the catalog; runbook text never offers one; the standing write-gate test.
- **G-002, G-004 assigned to ACR-0019** (action-card preconditions with a minimal interpreter; the frozen proposal
  and its preview in the digest).
- **G-005:** ACR-0019 gives each card a verify window but no provisional/final recovery; asked as an addition in its
  review.
- **G-001, G-003, G-007 built but not in the text** (the code calls them "lab additions"): the policy profile, the
  observation provenance fields, "unknown is never healthy". One small ACR writes them down. `config/policy.yaml`
  says `profile: production` on the lab, which matters once ACR-0018 ties separation of duties to the profile.
- **G-006 open:** redaction exists, field allowlists do not; its own ACR after ACR-0026.
Consequences: OP-002 stays open with an owner per gap. Next: the ACR for G-001, G-003 and G-007.
References: [OPEN_PROBLEMS](../OPEN_PROBLEMS.md) OP-002, [ACR-0019](../architecture/changes/ACR-0019-human-approved-remediation.md),
[ACR-0018](../architecture/changes/ACR-0018-operator-access-and-audit.md).

## 2026-10-20 — PR #212 self-merged while behind main; main-guard red, recorded as an exception

Type: incident
Who: conantkd (+ agent)
Context: #212 (the OP-002 review, documentation only, no protected path) was self-merged once its CI was green.
`juanbetancurm` merged #207 while that CI ran, so #212 was one push behind main at its merge, which breaks condition
3 of the self-merge rule. `main-guard` on `fb3b28b` went red: "the branch was not up to date with main when it was
merged".
Decision / result: the content is unaffected (#207 does not touch the OP-002 section; the merged diff is the same
two files). Per REVIEW_PROTOCOL ("If `main-guard` is red"), this pull request adds a `retroactive` line to
`policies/main-exceptions.txt` and asks a teammate to review #212's content with it.
Cause: the agent ran the up-to-date check, the self-review comment and the merge in one shell command, and the merge
ran although the check printed nothing. From now on the up-to-date check gates the merge (`&&`), and it is re-run
right before the merge, not before the CI wait.
Consequences: `main-guard` turns green again when this merges with a teammate's approval.
References: [REVIEW_PROTOCOL](../agents/REVIEW_PROTOCOL.md) self-merge rule, condition 3; PR #212, #207.

## 2026-10-20 — OP-014 steps 4 and 7: coverage on changed lines; workflow, image and script linting (Trivy included)

Type: implementation
Who: conantkd (+ agent)
Context: phase 15 of the [NEXT-PHASE plan](../tasks/current/NEXT-PHASE-supervised-remediation.md): the gates of
OP-014 before anything can act. Step 4 had paused because the full suite under coverage ran out of memory on a laptop;
step 7 had only pinned the actions.
Decision / result:
- **Step 4 (Python):** the `test` job runs the suite under `pytest-cov` (`argus/`, `services/`), and `diff-cover`
  fails a PR whose changed lines there are under 80 % covered, against `origin/main`. CI only. Vitest coverage waits
  for OP-017.
- **Step 7:** `zizmor` on the workflows (3 medium findings fixed: `persist-credentials: false` on every checkout),
  `hadolint` on the four Dockerfiles (binary checked against its SHA-256; DL3008/DL3018 ignored with the reason in
  `.hadolint.yaml`), `shellcheck -S warning` on `ops/*.sh`. One real finding fixed in `ops/db-backup.sh`
  (`>&"$fd" 2>/dev/null` read as both streams, now `1>&"$fd"`); the rest annotated. Trivy 0.75.0's configuration
  scan (the binary, never the action) at high and critical: its one finding, DS-0002 (root in the container) on the
  target services and the tunnel, is an exception for those two files (`.trivyignore.yaml`, with the reason), since a
  non-root user there is a VM change.
- All are steps of the `test` job: `SELF_MERGE_CHECKS` is unchanged.
Consequences: a PR that adds untested lines in `argus/` or `services/` now fails CI; a workflow, Dockerfile or ops
script finding fails it too, and so does a new Dockerfile running as root. Left in OP-014: the target services and
the tunnel as non-root (step 7, a VM change), the weekly model evaluation (step 8), Vitest coverage.
References: [OPEN_PROBLEMS](../OPEN_PROBLEMS.md) OP-014, OP-017.

## 2026-10-20 — T-0047: what is measured of the built reads, as recorded

Type: documentation
Who: juanbetancurm (+ agent)
Context: conantkd's approval of #202 noted that T-0047 "Before H1" credited EVAL-offers with all five built reads.
EVAL-offers measured `cpu_history`, `disk_history`, `request_path`, `search_logs` and `baseline`; `diagnostic_snapshot`
was EVAL-snapshot (#121); `prior_incidents` was not measured.
Decision / result: "Before H1" lists each measurement with its source and result; H4 names the reads it measures
again, `prior_incidents` only once the replay store holds recorded incidents. No step changes.
Consequences: none beyond the record.
References: #202, #121, [logbook](logbook.md) 2026-10-19 EVAL-offers, 2026-10-13 EVAL-snapshot.

## 2026-10-20 — ACR-0025 accepted: link-state transitions recorded and used by the map, the charts and the investigation

Type: decision
Who: juanbetancurm (+ agent); accepted by the approval of `task/ACR-0025-accepted`
Context: ACR-0025 (area B of the next-phase plan, a live dependency graph) was proposed in #202. `conantkd`'s review
asked for eight changes; with them made, he approved the text as recorded, and both ACRs stayed `proposed`.
Decision / result:
- **Accepted as written:** the scheduler records link-state transitions from the probes the exporter already runs
  (`link_event`, insert-only, the next free migration), skipping a host whose Prometheus cannot be read; host-kind
  dependencies are never probed; the map gets `since` and `required` and a `dependency_broken` problem; the incident
  charts get link events; `network.link_states` is a Level 2 read with its own tag, offered to no class until an
  evaluation batch and a teammate's review.
- No safety principle touched (ACR-0025 §4): one teammate's approval.
Consequences: T-0046 is `ready`. L1 (the link rules in one place and the inventory mapping) applies the ACR to
`ARCHITECTURE.md` with its first code.
References: [ACR-0025](../architecture/changes/ACR-0025-live-dependency-graph.md),
[T-0046](../tasks/current/T-0046-live-dependency-graph.md), #202.

## 2026-10-20 — ACR-0024 accepted: explicit hypotheses and a transparent cause ranking

Type: decision
Who: juanbetancurm (+ agent); accepted by the two approvals of `task/ACR-0024-accepted`
Context: ACR-0024 (area C of the next-phase plan, reasoning and cause ranking) was proposed in #202. `conantkd`'s
review asked for changes; with them made, he approved the text as recorded, and both ACRs stayed `proposed`. It
touches evidence integrity, so it needs a second approval.
Decision / result:
- **Accepted as written:** `conclude`, `escalate` and `use_read_tools` carry up to five hypotheses, each with a
  status and evidence for and against; the harness checks every cited id, a supported cause's own-target evidence and
  the chosen cause (log-only first); a support score from `config/ranking.yaml` (protected) that never changes the
  conclusion; `incident_hypothesis` (insert-only, the next free migration); the incident answer's `hypotheses`;
  `analysis.anomaly_summary`; evaluation labels and the hard check `unsupported_root_cause` = 0.
- Two approvals: one teammate's, plus a second for evidence integrity.
Consequences: T-0047 is `ready`. H1 (the hypothesis format and the checks, log-only) applies the ACR to
`ARCHITECTURE.md` with its first code.
References: [ACR-0024](../architecture/changes/ACR-0024-hypotheses-and-cause-ranking.md),
[T-0047](../tasks/current/T-0047-hypotheses-cause-ranking.md), #202.

## 2026-10-20 — ACR-0027: the policy profile, observation provenance and "unknown is never healthy" written down

Type: architecture
Who: conantkd (+ agent)
Context: the OP-002 review (#212) found three gaps the code already closes as "lab additions" but the architecture
never states: G-001 (the policy profile), G-003 (observation provenance), G-007 (missing data is never healthy).
Decision / result:
- [ACR-0027](../architecture/changes/ACR-0027-built-gaps.md) proposed and applied (ARCHITECTURE 1.8.23): §13.1
  states `profile: lab | production`, required, fail closed; §5.4 and §12.3 replace `observed_at` with `source_time`
  and `collected_at` and add `units`, `partial`, `coverage`, `identities`; §10's `<evidence>` tag says `source_time`
  as the runner writes it; §12.3 gains the rule "unknown is never healthy", and `MetricSnapshot` allows `None`.
- No code change. `tests/test_acr0027_built_gaps.py` pins the text to the code.
- `config/policy.yaml` keeps `profile: production`: the profile changes nothing yet; which profile the lab runs is
  decided in phase 16's ACR-0018 pull request, where separation of duties starts to depend on it.
Consequences: when this merges, G-001, G-003 and G-007 of OP-002 are closed; G-005 and G-006 remain.
References: [OPEN_PROBLEMS](../OPEN_PROBLEMS.md) OP-002, [ACR-0018](../architecture/changes/ACR-0018-operator-access-and-audit.md).

## 2026-10-20 — ACR-0018 accepted: mTLS private path, who holds which permission, the off-host store

Type: decision
Who: conantkd (+ agent); accepted by the two approvals of `task/ACR-0018-accepted`
Context: ACR-0018 (operator access and audit, proposed in #170) is the precondition of phase 16 and of ACR-0019 and
ACR-0020: neither may be built before it is applied and deployed. Three of the NEXT-PHASE open decisions belong to it.
Decision / result:
- **§3 accepted as written:** WebAuthn second factor and step-up, server-side sessions checked by `jti`, EdDSA token
  signing, explicit per-route permissions, separation of duties, a persisted login limiter, the audit hash chain with
  a signed daily digest off Host A, the private path for privileged routes, security alerts.
- **Private path (decision 2):** mTLS client certificates plus an address allowlist on the existing `tcp/443` edge;
  privileged locations answer 404 without both. No VPN: `wg0` belongs to the protected deployment.
- **Permissions (decision 3):** `approve_action` and `place_hold` for `conantkd`, `juanbetancurm`, `juanes6554`;
  `admin` for `conantkd` and `juanbetancurm` (a WebAuthn recovery is done by another administrator);
  `open_terminal:<host>` for nobody until ACR-0020 decides. Separation of duties enforced in production; in the lab a
  self-approval is allowed, recorded and counted.
- **Off-host store (decision 7):** a versioned bucket with a retention lock and a put-only credential, outside both
  VMs; digests 1 year, recordings 90 days. The provider is chosen when phase 16 is deployed; without it the digest
  job fails closed.
- It merges only with both approvals (one teammate's, plus a second for least privilege, secrets and evidence
  integrity).
Consequences: phase 16 may start once this merges: it applies ACR-0018 (ARCHITECTURE, `policies/SECURITY.md`,
`policies/NETWORK.md`) with its first code in one pull request. The client CA and the bucket are new secrets and
infrastructure, created with a lease and `code.bash`.
References: [ACR-0018](../architecture/changes/ACR-0018-operator-access-and-audit.md),
[NEXT-PHASE](../tasks/current/NEXT-PHASE-supervised-remediation.md) open decisions 2, 3, 7, [OPEN_PROBLEMS](../OPEN_PROBLEMS.md) OP-016.

## 2026-10-20 — ACR-0026: one scheme of safety classes (OP-003)

Type: architecture
Who: conantkd (+ agent)
Context: OP-003 (open since 2026-09-30): §12.3 describes capabilities with `risk: low…very_high`, the code with a
two-value `safety_class`, the runbooks with the library's five classes. Phase 17 (`config/risk.yaml`, the action
cards) needs one answer first.
Decision / result:
- [ACR-0026](../architecture/changes/ACR-0026-safety-classes.md) proposed and applied (ARCHITECTURE 1.8.22,
  §12.3 and §13.1): five classes, `READ_ONLY_SAFE`, `READ_ONLY_SENSITIVE`, `MUTATING_LOW_RISK`,
  `MUTATING_HIGH_RISK`, `FORBIDDEN`; `risk` is gone; `permission` and `side_effect` derive from the class;
  `FORBIDDEN` is never registered; the colour per target (ACR-0019) may only raise the class's minimum.
- Found while mapping: `container.detailed_logs` and `container.search_logs` returned log lines as
  `READ_ONLY_SAFE`, unlike `container.logs`. In review (`juanbetancurm`): `analysis.diagnostic_snapshot` carries
  `container.logs` lines, and `host.directory_sizes` returns names found on the host. All four are now
  `READ_ONLY_SENSITIVE`, and a combined read is as sensitive as its most sensitive sub-read (declared in `SUBREADS`,
  tested against the reads it makes). No runtime change (the lab profile allows both read classes).
- `tests/test_acr0026_safety_classes.py`: the registry follows the scheme; red seen on the old catalog.
- Needs a second approval (read-only).
Consequences: OP-003 is in progress. Left: the runbooks' "Safety class" column (54 rows in 19 runbooks differ from
the catalog) rewritten from it with a test; G-006's field allowlists for the sensitive reads; phase 17 adds the
`MUTATING_*` values to the code.
References: [OPEN_PROBLEMS](../OPEN_PROBLEMS.md) OP-003, OP-002 (G-006), [ACR-0019](../architecture/changes/ACR-0019-human-approved-remediation.md) §3.7.

## 2026-10-21 — DEPLOY-215: vm-095 to main b2e3548 (#203, #208's ops scripts)

Type: deployment
Who: conantkd (+ agent, over ssh)
Context: since DEPLOY-B7 (999b5bb), main gained #203 (a failed baseline read is not kept) and #208 (CI gates; a
`db-backup.sh` fix and shellcheck annotations in `ops/`); the rest is CI, Brain and tests.
Decision / result: vm-095 runs `main` `b2e3548`; agent, worker and scheduler rebuilt on one image; no migration
(008 stays the newest); 26/26 database checks, 55/55, write gate closed, `NO INTERFERENCE` on both VMs; the new
`db-backup.sh` made a good backup. vm-166 stays on `bdcd048`. Evidence:
[DEPLOY-215](../execution/history/DEPLOY-215/step-01/evidence.md).
Consequences: `deploy.sh` records the deploy event itself now; the code.bash recorded it a second time (two rows
for this deploy). Later deploy steps drop the manual `argus deploy record`.
References: #203, #208, [DEPLOY-B7](../execution/history/DEPLOY-B7/step-01/evidence.md).

## 2026-10-21 — T-0046 L1: one link-state rule, `{ref, port, required}` dependencies, ACR-0025 applied (1.8.24)

Type: implementation
Who: juanbetancurm (+ agent)
Context: ACR-0025 (a live dependency graph) was accepted in #214. L1 is its first step: the rule that turns a probe
sample into a link state moves to one place, so the topology and the transitions recorded in L3 never disagree, and
an inventory dependency can name its port and whether it is required.
Decision / result:
- `application/links.py`: `link_state(sample, port, warn_ms)`, moved out of `topology.py` unchanged; the topology
  tests stay green.
- `depends_on` accepts `{ref, port, required}` beside a plain ref (`DependencyLink` on `TargetInfo.links`). The loader
  refuses a port the dependency does not list, a `port` on a host ref, a dependency on another host and any other
  key. A plain ref and the same mapping give the same edge.
- Found while applying: `ops/render_target_config.py` builds the exporter's probe list from `depends_on` too, so it
  follows the mapping (a declared port is the only one probed); the rendered config for today's inventory is
  unchanged, and a test keeps it equal to the committed files. And a host dependency is drawn `unknown` ("declared
  dependency"), not `not_checked` as ACR-0025 §3.1 says; ARCHITECTURE says what the code does.
- ARCHITECTURE 1.8.24 describes the whole accepted change (§5.8, §7.1, §7.3, §12.2, §16.1); what later steps build is
  marked with its step (L2 to L4).
Consequences: `config/inventory.yaml` is unchanged; giving a link `required: false` or a port is an inventory change
of its own. Next: L2, `link_event` and its stores.
References: [ACR-0025](../architecture/changes/ACR-0025-live-dependency-graph.md),
[T-0046](../tasks/current/T-0046-live-dependency-graph.md), #214.

## 2026-10-21 — ACR-0028 proposed: field allowlists for the sensitive reads (OP-002 G-006)

Type: architecture
Who: conantkd (+ agent)
Context: OP-002 G-006 (data minimization) was the last gap without an owner. A read's `values` are, in 34 of 49
results, the gateway's JSON answer as it came; the dispatcher redacts patterns and declared literals but keeps every
field, and the model sees the values in each `<evidence>` tag. The gateways minimise at the source, with no check on
Argus's side.
Decision / result: [ACR-0028](../architecture/changes/ACR-0028-field-allowlists.md) proposed: `allowed_fields` on
`CapabilitySpec`, required for every `READ_ONLY_SENSITIVE` read (13 today, after ACR-0026); the dispatcher keeps only
the declared paths before redaction, truncation and storage, and audits the names of the dropped keys; a canary test
per sensitive read. The initial lists come from the gateways' answers on `main`. Rejected: a deny list (fails open),
typed answer models (a new gateway field would turn into a failed read).
Consequences: one implementation PR after ACR-0026 merges; agent image only. Needs a second approval (secrets,
evidence integrity).
References: [OPEN_PROBLEMS](../OPEN_PROBLEMS.md) OP-002, ACR-0026 (#210).

## 2026-10-21 — T-0046 L2: `link_event` (migration 009), insert-only, on both stores

Type: implementation
Who: juanbetancurm (+ agent)
Context: ACR-0025 §3.2. L3's scheduler records link-state transitions, and L4's map and charts read them; both need a
table first. Built on L1 (#219).
Decision / result:
- Migration `009_link_event.sql`: `owner`, `dependency`, `state` (only `ok`, `slow`, `broken`, `unknown`: a table
  check), `latency_ms`, `reason`, `at`; indexed by owner and by dependency. The runtime role gets SELECT and INSERT
  only, as for `deploy_event`.
- `add_link_event` and `link_events(target, start, end)` (the links a target owns or is the dependency of, oldest
  first) on the Postgres and SQLite stores; SQLite refuses UPDATE and DELETE with triggers.
- `argus db check` gains three checks: an insert that must succeed first, then UPDATE and DELETE refused.
Consequences: deploying this needs `db-migrate.sh` (009) before the new image. Nothing writes the table until L3.
References: [ACR-0025](../architecture/changes/ACR-0025-live-dependency-graph.md),
[T-0046](../tasks/current/T-0046-live-dependency-graph.md), #219.

## 2026-10-21 — T-0046 L1 follow-ups; `host.read_file` raised on every successful read

Type: implementation
Who: conantkd (+ agent)
Context: conantkd's review of #219 (T-0046 L1) left two non-blocking notes.
Decision / result:
- The inventory loader refuses a `depends_on` that names the same dependency twice (as a plain ref or with another
  port): `TargetInfo.link()` would keep the first one silently and the map would draw two edges on one port. Red seen
  on the old loader (`tests/test_t0046_l1_links.py`, two new cases).
- `trace_request_path`'s docstring: a dependency on another host is refused by the inventory (ACR-0025); the branch
  that lists one stays as a guard (`test_t0040` feeds one directly).
- **Found while writing ACR-0028's canary test:** `host_read_file` passed `truncated=` to `CapabilityResult`, which
  has no such field, so every successful `host.read_file` raised `TypeError`. The gateway's tests never ran the Argus
  side. It is offered to no class today, so it never fired on the VMs. Now "more lines before" is `partial` with a
  `coverage`, and `tests/test_t0019_batch3b_host_verbs.py` runs the capability (red seen).
Consequences: none for today's inventory (no repeated dependency; it still loads and renders the same).
References: #219, ACR-0025.

## 2026-10-21 — DEPLOY-NIGHT: vm-095 to main 024aa6f (migration 009); OP-004 and OP-008 previewed

Type: deployment
Who: conantkd (+ agent, unattended night session, over ssh)
Context: main gained migration 009 `link_event` (#220), T-0046 L1 (#219) and #221 since DEPLOY-215.
Decision / result: vm-095 runs `main` `024aa6f`; `+ 009_link_event applied`; agent, worker and scheduler on one
image; 29/29 database checks, 55/55, write gate closed, `NO INTERFERENCE` on both VMs; the deploy event recorded once
(the manual `argus deploy record` is gone from the code.bash). vm-166 stays on `bdcd048`. Previews only: OP-004 finds
no checkpoint past 30 days; OP-008 would remove 13 backup sets, none removed (a deletion is a stop condition).
Evidence: [DEPLOY-NIGHT](../execution/history/DEPLOY-NIGHT/step-01/evidence.md).
Consequences: OP-004 and OP-008 wait only for the team's decision on their timers; the backup prune is conantkd's call.
References: #219, #220, #221, OP-004, OP-008.

## 2026-10-21 — Unattended night session: what merged, what waits, what was found

Type: summary
Who: conantkd's agent, unattended (22:45 to 04:00 local, UTC-5), at conantkd's request: "avanzar en las fases de
implementación… pocos PR… al final sacar todos los que se puedan via selfmerge… correr una última vez todo".
Context: the plan was four pull requests (small fixes, ACR-0028 applied, phase 16 step 1, the night's records), a
deploy of main, and a final check of main, the VMs and #210.
Decision / result:
- **Reviewed and merged first (asked):** #220 (T-0046 L2, `link_event`, migration 009), conantkd's approval.
- **Self-merged:** #221 (one link per dependency; `host.read_file` raised `TypeError` on every successful read, found
  by the ACR-0028 canary test); this records pull request.
- **Deployed:** vm-095 to `024aa6f` with migration 009 ([DEPLOY-NIGHT](../execution/history/DEPLOY-NIGHT/step-01/evidence.md)):
  29/29 database checks, 55/55, write gate closed, `NO INTERFERENCE` on both VMs. OP-004 and OP-008 previewed only
  (13 backup sets would be pruned; nothing deleted: a stop condition).
- **Waiting for a teammate (protected paths):** #222 (ACR-0028 applied, 1.8.25), #223 (phase 16 step 1: sessions,
  revocation, persisted login limiter, permissions, the audit hash chain with a scheduled check, EdDSA; 1.8.26,
  migrations 010 and 011), #210 (ACR-0026: approved on an earlier push; a hand-resolved merge needs a re-approval).
- **Found and fixed on the way:** a key-like literal in a database check tripped gitleaks on every PR's CI (the scan
  covers all fetched branches), replaced by `md5('dbcheck')`; two existing UI tests followed the intended changes.
  **A mistake of mine, caught before any merge:** squashing #223 with `git reset --soft origin/main` after #221 had
  merged made its single commit revert #221 (the read_file fix, its tests, its journal); restored, and every PR's
  diff against main re-checked file by file.
  A flaky property test on main (`test_op014_property_based`: a URL user named `passwd` is masked by the key rule,
  in another form; no leak) failed #223's CI once; fixed in #223.
- **Not done, and why:** the `compare_baseline` evaluation for `container_restart_loop` (T-0047; needs constructed
  earlier-window fixtures and OpenAI spend not approved for tonight); phase 16 steps 3 to 5 (WebAuthn needs a library
  choice and the UI; the private path, the off-host store and the alert receiver need team decisions). The plan for
  them is [PHASE-16](../tasks/current/PHASE-16-operator-access.md).
Consequences: next for conantkd: approvals of #222 / #223 / #210 from `juanbetancurm`; then the prepared deploy of
phase 16 step 1 ([code.bash](../execution/history/PHASE-16/step-01/code.bash)); the backup prune is conantkd's call.
References: #210, #220, #221, #222, #223, ACR-0018, ACR-0028, OP-004, OP-008.

## 2026-10-21 — Softened: any team member's approval is the second approval for a safety-principle change

Type: decision
Who: conantkd (proposed), juanbetancurm (approved) (+ agent)
Context: a safety-principle change needs an ACR with a second approval (AGENT_PROTOCOL §4, SECURITY.md). ACR-0018 and
ACR-0024 read that as two teammates other than the author approving the same pull request, and ACR-0012 recorded the
same person approving twice as a conscious deviation. conantkd proposed on #209 to soften it.
Decision / result:
- Agreed: any team member's approval counts as the second approval, the author's included, and one person may give
  both approvals (accepting the ACR and approving the pull request); that is no longer a deviation.
- Unchanged: a safety-principle change still needs an ACR, and every protected path (every ACR is under
  `brain/architecture/`) still needs a teammate's approval on the last push (REVIEW_PROTOCOL).
- AGENT_PROTOCOL §4, REVIEW_PROTOCOL (checklist and protected paths), SECURITY.md and ACR-TEMPLATE.md say so.
Consequences: ACR-0012, #209 (ACR-0018), #215 (ACR-0024) and #218 (ACR-0028) meet the softened rule; #222 rewrites
the ACR-0018 and ACR-0024 tables to match.
References: [AGENT_PROTOCOL §4](../agents/AGENT_PROTOCOL.md), #209, #215, #218, #222.

## 2026-10-21 — ACR-0028 applied: the sensitive reads keep only their declared fields (OP-002 G-006)

Type: implementation
Who: conantkd (+ agent)
Context: ACR-0028 (accepted in #218) asks every `READ_ONLY_SENSITIVE` read to declare the value paths it keeps, and
the dispatcher to drop the rest before redaction and storage.
Decision / result:
- `CapabilitySpec.allowed_fields`; the 13 lists in `ALLOWED_FIELDS` (`argus/capabilities/catalog.py`), read from the
  gateways' answers; the catalog refuses a sensitive read without one, a malformed path, or a list naming no read.
- `argus/domain/minimize.py`: the rule ("a", "a[].b", "a.b"). `Dispatcher.call` and a combined read
  (`InvokeCapability._combined`) apply it; the dropped names go to the `tool.completed` audit detail
  (`dropped_fields`), never to the evidence.
- `tests/test_acr0028_field_allowlists.py`: the rule, the registry checks, and a canary per sensitive read through the
  real dispatcher (a marker at the top, in each row and each object never reaches the values or the model's text).
  The full suite stays green with the lists on, which shows they hold every field a read uses.
- ARCHITECTURE 1.8.25 (§5.4, §12.3, §17.1 layer 4).
- **Correction:** ACR-0018 and ACR-0024 said they "merge only with two approvals". AGENT_PROTOCOL §4 asks for the
  developer's acceptance and one more team member's approval; their tables now record the one approval each got.
Consequences: OP-002 G-006 is closed when this merges and deploys (agent image only). The canary found that
`host.read_file` raised on every successful read (fixed in #221).
References: [ACR-0028](../architecture/changes/ACR-0028-field-allowlists.md), [OPEN_PROBLEMS](../OPEN_PROBLEMS.md) OP-002.

## 2026-10-21 — T-0046 L3: the scheduler records link-state changes (off until deployed)

Type: implementation
Who: juanbetancurm (+ agent)
Context: ACR-0025 §3.1. L2 (#220) added `link_event`; nothing wrote it. ARCHITECTURE §7.3 already describes this step
(1.8.24), so no architecture change.
Decision / result:
- `application/link_transitions.py` (`LinkTransitions`): for every container owner with a declared container
  dependency on its own host, read `dependency_probes(owner)` and derive each link's state with `application/links.py`
  and the owner's `link_warning_ms`. A row and an audit event `link.changed` (actor `scheduler`, the previous and the
  new state) only when the state changes, and once when the process starts. A broken link's reason is the map's.
- A host whose Prometheus cannot be read (`MetricsUnavailable`) is skipped for the tick: no `unknown` burst and no
  recovery burst. A stale read is `unknown`. A host-kind dependency is never probed or recorded.
- `reconcile_firing_alerts.link_states.enabled` in `deploy/scheduler/schedules.yaml`, shipped `false`; refused when the
  reconcile itself is off (it runs on that tick). The scheduler runs it after the alert reconciliation; its failure is
  logged and never stops the alerts.
- Not recorded: the topology's fallback for an owner whose exporter has no per-dependency samples (it shows the
  owner's `dependency_probe_min`); without a per-dependency sample the recorder writes `unknown`.
Consequences: no deploy change while it stays off; L5 turns it on on vm-095 (migration 009 is already applied there).
Next: L4, the map, the charts and the investigation read the table.
References: [ACR-0025](../architecture/changes/ACR-0025-live-dependency-graph.md),
[T-0046](../tasks/current/T-0046-live-dependency-graph.md), #220.

## 2026-10-21 — Phase 16 step 1 (ACR-0018): sessions, revocation, a persisted login limiter, permissions

Type: implementation
Who: conantkd (+ agent, unattended night session)
Context: ACR-0018 (accepted in #209) is the precondition of phase 16 and of ACR-0019 / ACR-0020. Its parts that need
no infrastructure decision come first; WebAuthn, step-up, the audit chain and the private path follow.
Decision / result:
- **Sessions:** every token's `jti` is a row in `auth_session` (migration 010); every request checks it (missing,
  another principal's, or revoked: 401). `POST /api/v1/auth/logout` (allowed to read and investigate tokens too);
  also routed by the public edge (nginx, `contracts/ui-api.json`), and the UI's sign-out calls it before forgetting
  the token (`frontend/src/services/httpAuthAdapter.js`, best effort), so a UI's logout ends the session on the server;
  `argus user add|disable` end a principal's open sessions; `argus session revoke <name> --as <who>` (audited
  `access.sessions_revoked`). The runtime role may set only a session's revocation columns and never deletes one
  (column-level grant; a SQLite trigger in the lab store). A token from before this deploy has no session: one new
  login.
- A correctly signed token whose session is revoked, missing or another principal's is audited as
  `security.session_refused` (a stolen token used after logout shows up); a badly signed one writes nothing.
- A successful login is audited (`access.login`, never the token): until now only failures were.
- **Login limiter** kept in Postgres (`login_failure`): a restart keeps a lockout; each new failure prunes the rows past
  the window (a success clears only its user's). `auth_session` keeps a row per login (small; its owner-run retention is a
  follow-up, like OP-004).
- **Permissions:** routes check `view`, `view_evidence` or `investigate`; roles are bundles; `/me` lists them
  (`contracts/samples/me.json`, `docs/API-FOR-UI.md`). Only built routes' permissions exist.
- **Audit hash chain** (migration 011): each audit row carries `prev_hash` and `hash`; Postgres writes one row at a
  time under an advisory lock, so the agent, worker and scheduler never fork the chain; `argus audit verify` names
  the first row edited, removed or inserted outside the store. Rows from before 011 are counted, not chained. One
  continuous chain instead of the per-day chain of ACR-0018 §3 (recorded in its §6).
  The scheduler verifies it at start and daily (`audit_chain` in `schedules.yaml`) and records a `security` event;
  the alert on a broken chain waits for the team's alert route (none exists: Argus only reads its Alertmanager).
- **EdDSA tokens:** with an Ed25519 key in the secret `jwt_ed25519_key` the API signs and accepts EdDSA only (an
  HS256 token, even one signed with the old key and a live session, is 401); without it, HS256 as before.
  `PyJWT[crypto]`; `policies/SECURITY.md` names the secret. The lab switches in a deploy step.
- **The authorization matrix** (`tests/test_acr0018_authz_matrix.py`): every route × role × token kind against a
  declared table; a new route without a declared permission fails CI (part of phase 16's exit proof).
- `argus db check` gains six checks for 010 (insert first, then the refusals). Tests:
  `tests/test_acr0018_sessions.py`, `tests/test_postgres.py`.
- ARCHITECTURE 1.8.26 (§7.1, §16.1, §17.1 layer 1, §17.3); ACR-0018 §6 records step 1 and what is not built.
Consequences: deploy = `db-migrate.sh` (010, 011) before the image; every open session must log in once. Next (step 2):
WebAuthn and step-up, then the signed daily digest off Host A, then the private path.
References: [ACR-0018](../architecture/changes/ACR-0018-operator-access-and-audit.md),
[IMPLEMENTATION_PLAN](../IMPLEMENTATION_PLAN.md) phase 16.

## 2026-10-21 — OP-017: React Router 7, so what ships in the UI image has no known advisory

Type: implementation
Who: conantkd (+ agent)
Context: OP-017: `npm audit` reported two moderate React Router 6 advisories in the UI image (an open redirect through a
backslash in `<Link>` / `useNavigate`; a constructor injection in SSR hydration, which the UI does not use).
Decision / result:
- `react-router-dom` `^6.26.0` to `^7.18.4` (released 2026-09-15); `package-lock.json` regenerated by `npm install`.
- No code change: the UI uses only the classic API (`BrowserRouter`, `Routes`, `Route`, `Navigate`, `Outlet`, `Link`,
  `NavLink` and the hooks), which 7 keeps.
- Checked locally: ESLint (no errors), Vitest 131 passed, `vite build`, Playwright 21 passed with the read-only guard;
  `npm audit --omit=dev`: 0 vulnerabilities.
Consequences: the UI image needs a rebuild at the next deploy to ship it. The dev-tooling advisories (Vite 5, Vitest
3) stay open in OP-017: their fixes are major upgrades, done together in their own pull request.
References: [OP-017](../OPEN_PROBLEMS.md).

## 2026-10-21 — T-0046 L4: the map, the incident charts and the investigation read the recorded link changes

Type: implementation
Who: juanbetancurm (+ agent)
Context: ACR-0025 §3.3 to §3.5. L3 (#226) records each declared container link's state changes in `link_event`;
nothing read them. ARCHITECTURE (1.8.24) already describes this step, so no architecture change.
Decision / result:
- The map: each dependency edge adds `required` and `since` (its last recorded transition, only when that state is
  the state now; else `null`). A broken required link is a critical `dependency_broken` problem of its owner, except
  when the owner is idle. The overlay of an incident re-judges a box with the same rule. New store read
  `latest_link_events()` (Postgres `DISTINCT ON`, SQLite `MAX(id)`).
- The incident charts: `link_broken`, `link_slow` and `link_recovered` events in the window, for the links of the
  target and of its declared dependencies (same host). `link_recovered` is an `ok` after `broken` or `slow`, judged
  with the state before the window (24 h back); an `ok` after nothing or `unknown`, and `unknown` itself, are no event.
- `network.link_states` (`read_link_states`): Level 2, `READ_ONLY_SAFE`, in-worker (`argus_internal`), tag
  `link_states`, which no class has; `max_per_incident: 2` in `config/policy.yaml`. Per link: the state now (the
  recorder's own rule, `link_transitions.read_links`, on the latest probe), else the last recorded state, `since`,
  and the transitions of the last `minutes` (≤ 240). An unreadable Prometheus gives a partial answer.
- The recorder's per-link logic moved into `read_links`, shared by the recorder and the read.
- `contracts/samples/topology*.json` and `docs/API-FOR-UI.md` show the new fields.
Consequences: the map shows a new critical problem when a required link breaks, and the overview counts that owner
as failed. Offering the read to classes is L6, after an evaluation batch. Next: L5, deploy and measure on vm-095.
References: [ACR-0025](../architecture/changes/ACR-0025-live-dependency-graph.md),
[T-0046](../tasks/current/T-0046-live-dependency-graph.md), #226.

## 2026-10-21 — T-0047 H1: hypotheses on the decisions, the harness checks log-only, ACR-0024 applied (1.8.27)

Type: implementation
Who: juanbetancurm (+ agent)
Context: ACR-0024 (hypotheses and a transparent cause ranking) was accepted in #215. H1 is its first step: a model
strategy states the candidate causes it considered, and the harness checks them without refusing anything yet, so
the evaluation (H4) can show whether enforcing the checks costs accuracy.
Decision / result:
- `domain/model.py`: `Hypothesis`; optional `hypotheses` on `Conclude`, `Escalate` and `UseReadTools`, `chosen` on
  `Conclude`, and `hypothesis_problems` on the three.
- `tooling/model_harness.py`: the `conclude` and `escalate` tools carry `hypotheses` (at most five, ids `h1`–`h5`,
  the target an enum of the scope plus null) and `conclude` carries `chosen`; the system prompt says how to state
  them. `check_hypotheses` and `check_conclusion` implement the §11.3 rows and return each would-be refusal as a
  sentence; the decision stands. A hypothesis that fails its schema is dropped and reported.
- Both runners audit `hypothesis.invalid` (category `decision`: step, decision, at most 10 problems) after the
  decision's own audit.
- Found while applying: the checks need to know what each cited evidence id is about, and `EvidenceRef` did not
  say. It now carries the stored record's `target` and `kind` (set in `invoke_capability.py` and `runner.py`).
- ARCHITECTURE 1.8.27 describes the whole accepted change; what later steps build is marked with its step (H2–H5).
Consequences: deterministic strategies are untouched. A read step has no tool to carry its list, so
`UseReadTools.hypotheses` stays empty until H2 gives the list a place in the context. A model conclusion without
hypotheses is audited (`a conclusion without hypotheses`) but still concludes. Next: H2, storage and the ranking.
References: [ACR-0024](../architecture/changes/ACR-0024-hypotheses-and-cause-ranking.md),
[T-0047](../tasks/current/T-0047-hypotheses-cause-ranking.md), #215.

## 2026-10-21 — DEPLOY-A4479DF: vm-095 to main a4479df (phase 16 step 1, migrations 010 and 011)

Type: deploy
Who: conantkd (+ agent)
Context: main gained nine pull requests since DEPLOY-NIGHT (024aa6f): #210, #222, #223, #225, #226, #227, #228,
#229. Phase 16 step 1 (#223) brings migrations 010 and 011.
Decision / result:
- vm-095 at `a4479df`: backup, deploy, migrations 010 and 011, agent, worker and scheduler on one image, UI image
  rebuilt (React Router 7, the edge routes logout). 35/35 database checks, `AUDIT CHAIN OK`, the scheduler's chain
  check verified, 55/55, `WRITE GATE CLOSED`, `NO INTERFERENCE` on both VMs. vm-166 unchanged (`bdcd048`).
- ACR-0028 checked on real gateway answers: six sensitive reads `ok` through the worker's MCP tools process; the
  declared paths keep the data; only the gateway's envelope (`host`, `role`) is dropped, and the attribution guard
  reads `host` before minimization.
Consequences: every UI session logs in once (pre-010 tokens have no session row). The audit chain starts after 3893
unchained rows. EdDSA stays off until the key is installed (phase 16 step 2).
Next: leave the gateway envelope out of `dropped_fields` (it hides a real new field in the audit); conantkd's logged-in
check (D.3); T-0046 L5 turns `link_states` on.
References: [evidence](../execution/history/DEPLOY-A4479DF/step-01/evidence.md), #223, #222.

## 2026-10-21 — T-0046 L4 follow-up: a scheduler restart is not a link transition

Type: implementation
Who: juanbetancurm (+ agent)
Context: reviewing #227, `conantkd` noted that the recorder writes every link's state once at startup (ARCHITECTURE
§7.3), so each deploy repeated the states it already had: the map's `since` restarted at the deploy, and a link that
stayed broken showed a second `link_broken` on the incident charts. He also noted that the two stores picked the
latest row by different rules (Postgres by time then id, SQLite by id).
Decision / result:
- Fixed where the rows are read, not where they are written: the stores' `link_events` and `latest_link_events` skip
  a row whose state is its link's previous state (a window `LAG` over time, then id), so the map, the charts and
  `network.link_states` all read transitions only. The recorder keeps its startup row, as §7.3 says, so the table
  still shows when a scheduler started; seeding the recorder from the table would have changed §7.3.
- Both stores now order a link's rows by time, then id.
- The L3 test that checks the startup row reads the table directly.
Consequences: no architecture change; ARCHITECTURE §7.1 already defines `since` as the last recorded transition.
References: [T-0046](../tasks/current/T-0046-live-dependency-graph.md), #227.

## 2026-10-21 — The gateway envelope is not a dropped field; T-0046 L5 turns `link_states` on

Type: implementation
Who: conantkd (+ agent)
Context: DEPLOY-A4479DF ran every sensitive read on real gateway answers: each dropped exactly `host` and `role`, the
envelope the read gateway adds to every answer, so the audit's `dropped_fields` could never show a field the gateway
grew. T-0046 L5 turns link recording on once the restart follow-up (#231) is merged.
Decision / result:
- `tooling/dispatch.py`: `GATEWAY_ENVELOPE` (`host`, `role`) is still dropped from a minimized read's values but no
  longer named in `dropped_fields`. The attribution guard reads `host` before minimization, unchanged (test). Red
  seen for the envelope test on the old code.
- T-0046 L5: `reconcile_firing_alerts.link_states.enabled: true` in `deploy/scheduler/schedules.yaml`; the shipped-file
  test now expects it on.
- Dropped from this change: the same restart fix as #231 (started here without seeing it); #231's version filters in
  the stores' reads and is the one kept.
Consequences: the deploy rebuilds the agent image and restarts the scheduler; the first tick writes one row per
declared link. L5's scenario runs (SC-03, SC-07) follow, with conantkd's go.
References: [DEPLOY-A4479DF](../execution/history/DEPLOY-A4479DF/step-01/evidence.md), #222, #231,
[T-0046](../tasks/current/T-0046-live-dependency-graph.md).

## 2026-10-21 — main-guard: a 15-minute limit instead of 5

Type: process
Who: juanbetancurm (+ agent)
Context: the `main-guard` run after #226 (main `f3d831c`) was cancelled at its 5-minute limit while `brain.py
verify-main` waited on GitHub's API; nothing was red. `verify-main` asks GitHub about every merge on `main` (222
first-parent commits today, several calls each), and the runs before took 3.5 to 4.5 minutes, so a slow API is enough
to cross the limit. Run locally the same day, the same calls stalled at random and answered in a second when retried.
Decision / result:
- `.github/workflows/ci.yml`: `main-guard` gets `timeout-minutes: 15`. The rule it checks is unchanged.
Consequences: a cancelled `main-guard` is still not a pass: it is re-run, and a merge waits for it to be green. The run
time grows with every merge; if it nears 15 minutes, `verify-main` could check only the commits since the last green
run, which changes the enforcement and needs its own review.
References: [REVIEW_PROTOCOL](../agents/REVIEW_PROTOCOL.md), #226.

## 2026-10-21 — A flaky overview test: incidents tied on their creation time

Type: fix (tests only)
Who: juanbetancurm (+ agent)
Context: `test_t0045_b6_overview.py::test_open_incidents_are_counted_by_severity_and_the_worst_one_is_the_status`
failed once in a full local run and passed alone. The stores sort incidents by the `opened_at` column, which is
written at creation and never updated; the test created three incidents a moment apart and then changed `opened_at`
only in their stored bodies. When the clock gave two of them the same creation time, the order was the insertion
order (oldest first) and "newest first" failed. Forcing equal creation times reproduces it every time.
Decision / result:
- `tests/test_core.py`: `incident()` takes an optional `opened_at`, so a test can create an incident at its real time.
- `tests/test_t0045_b6_overview.py`: `_inc` passes it instead of changing `opened_at` after the insert.
Consequences: no product change; in Argus an incident's `opened_at` is set once, at creation.
References: T-0045 B6 (`d6ba12a`).

## 2026-10-21 — T-0046 L5: link recording is on in vm-095

Type: deploy
Who: conantkd (+ agent)
Context: ACR-0025 §3.1. L3 built the recorder (off), L4 the readers, #231 made a restart's repeated row no transition,
#234 turned `link_states` on.
Decision / result:
- vm-095 at `2324186` (no migration; agent image). The first tick recorded the 4 declared container links (`api →
  cache` ok; three scenario owners not running: unknown), the next ticks nothing.
- A deliberate scheduler restart wrote one row per link again and left `since` unchanged (18:13:04): #231 holds on
  Postgres. 35/35, the audit chain OK, 55/55, `WRITE GATE CLOSED`, `NO INTERFERENCE` on both VMs.
Consequences: the map's `since`, the chart events and `network.link_states` now read live data on vm-095.
Next: SC-03 and SC-07 once each (lab scenarios; conantkd's go), then L6 offers the read to its classes after an
evaluation batch and a teammate's review.
References: [evidence](../execution/history/T-0046-L5/step-01/evidence.md), #231, #234.

## 2026-10-21 — T-0046 L5: SC-03 and SC-07 with link recording on; SC-01 shows H1's hypotheses live

Type: verification
Who: conantkd (+ agent)
Context: T-0046 L5 asks for SC-03 and SC-07 once each with `link_states` on. SC-01 added to see a model strategy's
hypotheses (T-0047 H1, log-only); `dependency_unavailable` runs the deterministic baseline (D-003).
Decision / result:
- SC-03, SC-07 and SC-01 PASS (runner run by conantkd). SC-03 recorded `api → cache` broken (name not resolved) and
  recovered, shown on the incident's chart. SC-07 left no link row: its fault lasted about 30 s, between two 60 s
  ticks.
- A row's time is the recorder's write time, not the probe sample's: SC-03's `broken` lands 10 s after the incident
  opened, after the errors it caused.
- SC-01: three hypotheses, `chosen` h1 matching the root cause, h2 ruled out, no `hypothesis.invalid`.
Consequences: before L6 offers `network.link_states`, record the sample's time and decide the tick (or measure it in
L6's evaluation batch). H4's labels: a hypothesis with evidence against it should be ruled out, not untested.
References: [evidence](../execution/history/T-0046-L5/step-02/evidence.md),
[T-0046](../tasks/current/T-0046-live-dependency-graph.md), [T-0047](../tasks/current/T-0047-hypotheses-cause-ranking.md).

## 2026-10-21 — T-0047 H2: the hypotheses ranked, stored and carried to the next step (ARCHITECTURE 1.8.28)

Type: implementation
Who: juanbetancurm (+ agent)
Context: H1 (#228) gave the decisions their hypotheses and the harness its log-only checks. H2 is ACR-0024 §3.3-§3.5:
the score and the ranking, the `incident_hypothesis` table and the "Hypotheses under test" slot of the context.
Decision / result:
- `application/ranking.py`: the score by what each cited record is evidence of (own target per record up to
  `max_target_records`; the generic kinds once per kind and side; an unknown id counts for nothing); ties by records
  no other hypothesis cites, then the order given; `ranking_disagrees`. Weights in `config/ranking.yaml` (validated
  at startup, fail closed; the defaults when the file is missing).
- Migration 012 `incident_hypothesis` (insert-only for the runtime role; the db-check proves it) and the same table
  with insert-only triggers in SQLite; `add_hypotheses` and `hypotheses` on both stores.
- Both runners rank and store each decision's hypotheses after its audit; a step already stored is skipped (a run
  resumed after a crash), and a failure to store never stops the run.
- Found while building: §3.1's optional list on `UseReadTools` had no way to arrive, so a read step now states its list
  in one `state_hypotheses` call beside its read calls (not a read; refused alone, twice or beside a decision). The
  context shows the latest list (≤ 1200 characters, about 300 tokens). ARCHITECTURE 1.8.28 says so (§5.5, §11.3).
- The T-0047 H4 step now says to leave out problems on evidence references without `target` / `kind` (#228 review).
Consequences: nothing is shown yet: H3 adds the hypotheses and `ranking_disagrees` to the incident answer. Migration
012 must run before the image that writes the table (`db-migrate.sh`); until then a store without the table logs the
failure and the run goes on.
References: [ACR-0024](../architecture/changes/ACR-0024-hypotheses-and-cause-ranking.md),
[T-0047](../tasks/current/T-0047-hypotheses-cause-ranking.md), #228.

## 2026-10-21 — T-0047 H3: the hypotheses in the incident answer

Type: implementation
Who: juanbetancurm (+ agent)
Context: H2 (#236) stores each decision's hypotheses with their score and rank. H3 is ACR-0024 §3.6: show them in
`GET /api/v1/incidents/{id}`, the slot the UI already had (`"hypotheses": []`). ARCHITECTURE §7.1 already describes
this answer, so the version stays 1.8.28.
Decision / result:
- `incident_view.hypotheses_view`: the final decision's rows, by rank: `{id, statement, cause_class, target, relation,
  status, rank, chosen, support: {score, for, against}}`, plus `ranking_disagrees` (the chosen one is not ranked
  first). Derived from the stored rows; no model call.
- `for` / `against` count the cited records that are stored evidence of the incident, each once (an id cited twice,
  or not stored, is not counted). Operators and approvers also get `support_ids` / `against_ids`; a viewer gets the
  counts only, as for `evidence_highlights`.
- The UI contract's scripted run now concludes with two hypotheses; `contracts/samples/incident.json` gained them by
  hand (the other samples are unchanged). `docs/API-FOR-UI.md` describes the fields.
Consequences: the frontend can show the list and the "the evidence favours <first>" note. H4 measures the ranking.
References: [ACR-0024](../architecture/changes/ACR-0024-hypotheses-and-cause-ranking.md),
[T-0047](../tasks/current/T-0047-hypotheses-cause-ranking.md), #236.

## 2026-10-21 — T-0047 H2/H3 deployed on vm-095 (migration 012)

Type: deploy
Who: conantkd (+ agent)
Context: #236 (H2: ranking, storage, `state_hypotheses`, the context slot) and #237 (H3: the incident answer) merged;
H2 needs migration 012 before its image.
Decision / result:
- vm-095 at `6c83da3`: backup, migration 012 applied, agent image rebuilt; 38/38 database checks, the audit chain OK,
  55/55, `WRITE GATE CLOSED`, `NO INTERFERENCE` on both VMs. vm-166 unchanged.
Consequences: the next model-strategy investigation stores its hypotheses with Argus's score and rank, and the
incident answer shows them. H4 (the evaluation) can now run on stored rows.
References: [evidence](../execution/history/T-0047-H2-deploy/step-01/evidence.md), #236, #237.

## 2026-10-21 — Phase 16: auth_session retention; maintenance audit rows chained

Type: implementation
Who: conantkd (+ agent)
Context: step 1 left `auth_session` growing by one row per login, with its owner-run retention as a follow-up (like
OP-004). Reading OP-004's code for the pattern showed its audit row is a bare `INSERT`: after migration 011 that row
has no hash, and `argus audit verify` (and the scheduler's daily check) would report the chain broken at the first
checkpoint prune that removes anything. None has yet (the last dry run found `threads=0`).
Decision / result:
- `argus db prune-sessions [--days N] [--apply]`: owner-only, preview by default, one transaction, the maintenance
  lock of OP-004; removes rows whose token expired more than 90 days ago (`ARGUS_SESSION_RETENTION_DAYS`), revoked or
  not; audited `maintenance.sessions_pruned` (`access`). The audit keeps each login and refusal.
- `append_chained` (postgres_store): the one way to write an audit row; the store and both maintenance commands use it.
- Tests: `tests/test_session_retention.py`; `tests/test_checkpoint_retention.py` now checks the chain after a prune.
Consequences: no migration and no new grant (the owner deletes). The VM dry run goes with phase 16 step 2's deploy.
ACR-0018 §6 gets its line in step 2's PR (a protected path).
References: [PHASE-16](../tasks/current/PHASE-16-operator-access.md), OP-004.

## 2026-10-21 — OP-017: Vite 8 and Vitest 5; `npm audit` clean on the whole frontend tree

Type: implementation
Who: conantkd (+ agent)
Context: OP-017 left the dev tooling's advisories (Vite 5 / esbuild high, Vitest 3 critical) after React Router 7.
Decision / result:
- `vite` 8.3.5, `@vitejs/plugin-react` 6.1.2 (it needs Vite 8), `vitest` 5.0.5; `@tailwindcss/vite` 4 already accepts
  Vite 8. Node 24 in CI and in the UI image meets every engine range. No code or config change.
- Lint, Vitest (136), the production build and Playwright (21, with the read-only guard) pass locally;
  `npm audit` finds 0 vulnerabilities, dev included.
- The bundle warning (one chunk over 500 kB) is unchanged in kind; Vite 8 now names Rolldown's option for it.
Consequences: the UI image is rebuilt with the next deploy (its build stage only; nginx serves the same static
files). CI's gate on the whole tree (OP-017 fix 3) is a `.github/` change, in its own pull request for review.
References: [OP-017](../OPEN_PROBLEMS.md).

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
References: [OP-014](../OPEN_PROBLEMS.md).

## 2026-10-21 — T-0047 H4 step 1: the evaluation measures the hypotheses

Type: implementation
Who: juanbetancurm (+ agent)
Context: H2 (#236) stores each decision's ranked hypotheses. ACR-0024 §3.8 asks the evaluation for labels, top-1 /
top-3 accuracy over the ranking, ruled-out recall, the `ranking_disagrees` rate and a new hard check. This step
builds the measuring; the batches with the configured model (and the decision to enforce the H1 checks) come next.
Decision / result:
- A case label may name `expected_hypotheses: {supported, ruled_out}` (targets or cause classes); `supported` falls
  back to `root_cause`. 15 cases are labeled, the ones whose cause is not the target (`dep-*`, `nginx-slow-*`,
  `pg-leaker-*`): the cause supported, the victim ruled out.
- A replay keeps the final decision's list (`incident_hypothesis`), `ranking_disagrees`, the H1 problems
  (`hypothesis.invalid`) and the targets it observed.
- The summary adds `hypotheses` (stated share, top-1, top-3, ruled-out recall, disagreement rate, problem rate),
  each over the runs it applies to (`None` for a strategy that states none). The CLI prints them on one line.
- `unsupported_root_cause` (a diagnosis whose root cause the run never observed) counts in the summary's `hard` and
  the CLI's hard line, apart from `hard_violations`: the protected prompt-injection test pins that function's three
  §21.2 rules. Every case still gives 0 with the baseline.
- Found while building: in the `pg-leaker-*` cases nothing reads the leaker itself; the database's sessions name it.
  Read literally ("no observation of its target"), the check flagged 5 correct baseline diagnoses, so a target named
  by an `ok` observation on its host counts as observed. The H1 check on a `supported` hypothesis has the same gap
  (it asks for an observation of its own target); the model batches will show whether it fires on these cases.
Consequences: the next step runs the batches with the configured model (with the H1 checks log-only, then
enforced if accuracy is not lower) and measures the built reads again.
References: [ACR-0024](../architecture/changes/ACR-0024-hypotheses-and-cause-ranking.md),
[T-0047](../tasks/current/T-0047-hypotheses-cause-ranking.md), #236.
