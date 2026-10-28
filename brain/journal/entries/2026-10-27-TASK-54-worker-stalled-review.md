## 2026-10-27 - TASK-54: stalled-worker class review and ACR-0036

Type: review and architecture decision
Who: conantkd (+ Codex)
Context: PR #366 adds the SC-10 `worker_stalled` class and RB-022. Two prior reviews found an unintended vm-095 lab-network join, non-finite detector crashes, a false PostgreSQL dependency, and a stale rendered target config.
Decision / result:
- Reviewed PR head `6a0aecb6` against fetched `main` `446ef51a`. The vm-095 Prometheus network stays isolated, non-finite worker signals are unknown, the worker depends only on Redis, and the rendered vm-166 probe names only Redis.
- Corrected RB-022's scope, the runbook index, and the shared scenario contract to remove the stale PostgreSQL dependency. Bumped RB-022 to version 1.0.1 and the runbook count to 22.
- Accepted ACR-0036 for the new class row in architecture section 1.3; bumped the architecture to 1.8.41 and added its changelog row.
Consequences: deployment and injected-fault behavior on vm-166 remain for a leased integration window; this PR does not deploy or release a write capability.
References: PR #366; [ACR-0036](../../architecture/changes/ACR-0036-stalled-worker-class.md); [shared scenario task](../../tasks/current/DEMO-argus-acts.md).

### Test state

Earlier red evidence: CI on `578c730` failed five rendered-inventory tests because the obsolete database probe remained in `vm-166.json`; commit `6a0aecb6` regenerated that file. CI on `6a0aecb6` then passed its full Python test step but failed the changed-lines coverage gate (48%) because the new baseline plan and diagnosis paths lacked tests. New tests cover the worker/cache read plan and the observed stopped-cache, broken-link, healthy-peer and missing-worker paths; targeted pytest and Ruff pass, and local diff-cover reports 94% on changed lines. `brain.py audit` and `brain.py lint` are clean. The full local pytest run stopped at `tests/skills/test_check_block.py`: its subprocess invokes Windows `bash.EXE`, and WSL cannot find `/bin/bash` (`CreateProcessCommon: execvpe(/bin/bash) failed`). This is a local environment failure; the exact-head Linux CI run remains pending.

### Next step

After PR #366 merges, deploy in the planned leased integration window, verify vm-166's scrape, alert and worker freeze fault, and confirm `NO INTERFERENCE`. Keep the write gate closed until the separate release PR.
