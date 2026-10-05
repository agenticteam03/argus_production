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
