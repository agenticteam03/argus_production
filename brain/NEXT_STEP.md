# Next step

**Now (2026-10-10, evening; first roll-up, `conantkd`).** Both VMs run `main` `ebbe9c9` (DEPLOY-MAIN-2); `main` has
moved on to #65–#71. No lease is held.

1. **`main-guard` is red since #68** (merged without an approval of its last push). The fix is PR #72, a retroactive
   line in `policies/main-exceptions.txt`; `juanbetancurm` reviews #68's two last commits there. Merge it first.
2. **E2E-2 step 2 (quality lane, `juanbetancurm`; both leases):** `main` changed `host.disk_usage` and
   `container.status` (#70, #71), so vm-095's agent needs a rebuild: backup, `deploy.sh main`, rebuild agent, worker
   and scheduler, `argus db check`, NO INTERFERENCE; then `ops/e2e/run.py --runs 5 SC-05 SC-07` on vm-166
   ([task](tasks/current/E2E-2-evidence-gaps.md)). Phase 12 so far: SC-01, SC-03, SC-04, SC-06 at 5/5; SC-05 and
   SC-07 6/10 before E2E-2. SC-02 × 5 when vm-095 is free.
3. **Done today, no deploy needed:** T-0031 (phase 8, the standing write-gate test; `ops/write-gate-check.sh`,
   `--host-only` on a Host T: CLOSED on both VMs); T-0032 (phase 13, Prometheus down on one host escalates that host
   only); T-0030 (phase 13, a Postgres restart is a pause); LANES-1 and LANES-2 (a lease per VM; journal entry files
   and `brain.py rollup`: task branches write `journal/entries/`, whoever merges last runs the roll-up).
4. **Open follow-ups:** an alert when a host's own Prometheus is down (T-0032: `ArgusScrapeTargetDown` runs in that
   Prometheus); `brain.py rollup` orders same-day entries by file name, not merge time (fixed by hand in this
   roll-up); OP-002 triage and the OP-003 proposal (as ACR-0006: ACR-0005 is taken); OP-004 and OP-008 `--apply`
   wait for a teammate's review of their previews.

The sections below are older (2026-10-09 and earlier) and kept for the record; the paragraph above supersedes them.

**LANES-2 (2026-10-10, `juanbetancurm`):** task PRs write `journal/entries/` files instead of editing the logbook,
CURRENT_TEST_STATE and NEXT_STEP; the first roll-up follows this merge. See
[the task file](tasks/current/LANES-2-journal-rollup.md).

**OP-008 (2026-10-10, `conantkd`):** snapshot-consistent backup, verified markers and preview-first retention are
implemented and dry-run on vm-095 (`VERIFY OK`, 0 sets to remove with `KEEP=7`). Next: a teammate reviews the
preview before any `prune --apply`; scheduling stays a separate team decision. See
[the task file](tasks/current/OP-008-backup-retention.md).

**OP-004 (2026-10-10, `conantkd`):** `argus db prune-checkpoints` (owner-only, read-only preview by default,
transactional `--apply`, audit row) is implemented and dry-run on vm-095: with the 30-day window nothing is eligible
yet (1-day preview: 88 threads). Next: a teammate reviews the counts before any `--apply`; enabling the daily timer
is a separate team decision. See [the task file](tasks/current/OP-004-checkpoint-retention.md).

**Now (2026-10-09, night, `conantkd`). Phase 7 is complete.** Six branches stacked on `main`, each with the previous
one merged in and `main` up to #53: `task/T-0022-alerting` (#45, ACR-0003) → `task/OP-010-reserved-slot` (#46) →
`task/T-0024-sc05-disk` (#47) → `task/OP-011-correlation` (#48, ACR-0004) → `task/T-0026-alert-resolution` (ACR-0005,
migration 005) → `task/T-0027-blind-spot` (the monitoring blind spot class, RB-014). **Both VMs run
`task/T-0027-blind-spot` `c27546f`**; vm-095's database has migrations 004 and 005 (backups
`argus-20261009T131715Z.dump`, `argus-20261009T183857Z.dump`). LAB BASELINE OK, NO INTERFERENCE. Merged today: #49
(ACR-0002 accepted), #50 (T-0025 evaluation), #53 (OP-009, fast-track). #45 waits for `juanbetancurm`'s second
approval (cAdvisor text fixed). #52 (parallel lanes): changes requested (two text suggestions). **Warning for the
team:** `brain.py start` reports `59ffa39` (PR #44, OP-001) merged into `main` without a non-author approval.

1. **PRs, in order:** T-0022 (needs `juanbetancurm`'s second approval: ACR-0003 touches host isolation), OP-010,
   T-0024, OP-011 #48 (ACR-0004), then T-0026 (ACR-0005) and T-0027. After #45 merges, #46 and #47 (no ACR) can
   be retargeted to `main`, updated and merged by fast-track; #48, T-0026 need a re-approval (ACRs). After they merge, both VMs go to `main` (checkout + rebuild of
   the agent image; migrations 004 and 005 are already applied). Do not deploy `main` before: it would drop the monitoring, the
   reserved slot and the correlation (the table can stay; older code ignores it).
2. **Done 2026-10-09:** OP-011 (step 02 showed the second SC-03 alert pulled after the first incident closed →
   ACR-0004; step 03 one incident `inc_8a4cf92444ae`, occurrences `started` + `attached`). T-0024 steps 2-4 (SC-05
   DIAGNOSED; vm-166 keeps the lab filesystem `/srv/argus-lab-fill`, `ops/lab-fill-mount.sh --remove` takes it away).
   T-0022 steps 5-6 and OP-010.
3. **Done 2026-10-09:** resolved alerts (T-0026, ACR-0005, migration 005; [task file](tasks/current/T-0026-alert-resolution.md)):
   **both VMs run `task/T-0026-alert-resolution` `ea01c68`**; vm-095 has migration 005 (backup
   `argus-20261009T183857Z.dump` before). Its PR goes after #48. **Next code work:** OP-009 is fixed on `task/OP-009-lease-loss`
   (`main` merged in, PR not opened yet); OP-009 before any second worker, OP-004 checkpoint cleanup, SC-06 / SC-08, phase 12 with the
   runner (≥ 5 runs per scenario) and the §21.2 evaluation.
4. **Open question (`conantkd`):** a host incident's scope holds only the host's declared dependents (T-0024 declares
   the filler `depends_on` the host). Opening it to every container of the host (useful for SC-06 CPU) would be an
   ACR (§5 scope rule).

**OP-001 (2026-10-09, `conantkd`):** the 21 runbook `detector` metadata fields and index now match the 20 incident
classes in architecture §1.3 on `task/OP-001-runbook-detectors`. PR #44 passed the local full suite and CI; fast-track
review and merge are next. This metadata update does not enable draft detectors or promote runbooks. See
[the task file](tasks/current/OP-001-runbook-detectors.md).

**Now (2026-10-09, `conantkd`; read as the state after the T-0020 PR merges):** T-0020 (SC-04,
`postgresql_connection_exhaustion`, RB-004) is done: verified on vm-166 (`inc_075fb0006098` DIAGNOSED). #36 (T-0021)
was merged before its re-review; its fixes and ACR-0002 came in **#39, approved by `conantkd` (second approval of
ACR-0002) and merged**: `main-guard` green, `main` has the fixed launcher. **#40** (T-0023, the scenario runner, with
two reviewer fixes) is merged too. Owed by `juanbetancurm`: ACR-0002's status set to `accepted` (small PR).

1. **AFTER-MERGE T-0020 on vm-166** (checkout only, block in `execution/current/code.bash`). vm-095 may now get
   `main` (it has the fixed launcher and defaults to `mcp`); its agent then gets `postgresql_connection_exhaustion`.
2. Next work: alerting (phase 7, T-0022) and OP-010 (the db-probe's reserved slot) are ready on `conantkd`'s
   branches; OP-009 (before any second worker) is fixed on `task/OP-009-lease-loss`, `main` merged in, its PR next; OP-004 checkpoint cleanup; SC-05 (T-0024); phase 12 with the runner:
   SC-02 and SC-07 × 5, then an SC-04 catalogue entry.
3. **Evaluation (§21.2, `tests/eval/`) and phase 12 (≥ 5 runs per scenario):** §3 "Enablement" enables a class only
   when its evaluation passes. The 4 classes enabled so far (including `postgresql_connection_exhaustion`) are
   enabled ahead of it: they have lab runs, not the §21.2 dataset (≥ 5 labeled cases per class, ≥ 5 trials, compared
   with the deterministic baseline). This is the task that closes that gap.

**Earlier (2026-10-08, `juanbetancurm`):** T-0014 (api / worker / scheduler) is done and verified on vm-095
([evidence](execution/history/T-0014/step-05/evidence.md)); PR #33 merged by fast-track (after-merge review by a
teammate owed). vm-095 is back on `main` `5cdfd98` (checkout only; the images already run this code). vm-166
stays on `task/T-0020-sc04-pg-connections` until that task's PR. Next: **T-0021** (MCP tools process under its own
user, draft PR #36): step 4 (compose) now, step 5 on vm-095 with the lease. Open PRs: #34 (CLI ACT width), #35
(T-0015 step 6 record), #36 (T-0021, normal review: safety model).

**Earlier (2026-10-07, `conantkd`):** T-0019 batch 1 (the db-probe and `database.health`) is deployed on both VMs
from `task/T-0019-db-probe`; its PR waits for review (after PR #29, OP-007, which it includes). After the merge:
AFTER-MERGE (both VMs back on `main`, checkout only). Next: **T-0019 batch 2** (host-probe load, io, top
processes, sockets, directory sizes, kernel OOM records; [task file](tasks/current/T-0019-db-probe.md)), or
**SC-04** (`postgresql_connection_exhaustion`, RB-004) which now has its probe. Open PRs: #29 (OP-007), #30
(AFTER-MERGE T-0018 record), #31 (OP-008 proposal).

**Next, agreed by `conantkd`: enable more incident classes** (ARCHITECTURE §3 lists 20, 3 are implemented). A class
is enabled only when its detector exists, its runbook is tested in the lab and the §21.2 evaluation passes (§3
"Enablement"); `query_runbook` lets the scenarios exercise the branch runbooks first. Candidates with a scenario
planned: `dns_network_failure` (RB-009, SC-07 exists), `postgresql_connection_exhaustion` (RB-004, SC-04),
`disk_pressure` (RB-005, SC-05), `cpu_saturation` (RB-006, SC-06), `nginx_upstream_failure` (RB-015, SC-08).

**Earlier (2026-10-06):** both VMs on `main` (vm-095 `f126272`, agent image from `2097eb1`; see below).
Merged today: PR #25 (T-0017), PR #22 (T-0015 steps 1-5, **ACR-0001 accepted** by `conantkd`: UIs read-only in this release) and
PR #24 (T-0016 steps 1-2, the mock-driven UI prototype, approved by `juanbetancurm` and `conantkd`). Next for them:
T-0015 step 6 (deploy on vm-095, after it is back on `main`) and T-0016 step 3 (connect the read parts to the API).

**VMs (2026-10-06, `conantkd`):** PR #25 (T-0017) merged by fast-track; vm-095 is back on `main` `f126272`
(checkout only, NO INTERFERENCE). The agent image is still from `2097eb1`: **T-0015 step 6** (`juanbetancurm`)
rebuilds it and proves a read token is refused on `POST`. vm-166 is on `main`. Phase 5 is complete. PR #25 waits
for its after-merge review by a teammate (fast-track rule).

**Handoff (2026-10-05, from `juanbetancurm`; read the latest journal entry first).** In this order:

1. **Review (start of the session, `agents/REVIEW_PROTOCOL.md`):**
   - **PR #8 — OP-005 proposal**, revised with `conantkd`'s requested changes (creation-time guard, scrape-gap
     test) plus one refinement to judge: the young-container branch goes first, so a container recreated under the
     same name counts from zero. Approve or request changes. Do **not** fast-track it.
   - ~~After-merge review of the fast-track PRs #9–#13~~ **done 2026-10-06** (`conantkd`, PR #16): no defects;
     reports posted as comments on each PR.
2. ~~DEPLOY-MAIN~~ **done 2026-10-06** (`conantkd`): both VMs on `main` `09f5ab1`, agent rebuilt, H-1 `HEALTHY`,
   SC-03 verified on LangGraph, NO INTERFERENCE ([evidence](execution/history/DEPLOY-MAIN/step-01/evidence.md)).

**Then — the next tasks:**

| Option | Phase | What | Depends on |
|---|---|---|---|
| ~~T-0014 — worker + scheduler~~ **done 2026-10-08** (`juanbetancurm`, PR #33) | 9 | split the agent into api / worker / scheduler; the worker claims queued incidents and **resumes interrupted runs from their checkpoint**; the scheduler runs periodic checks and pulls firing alerts | T-0013 merged |
| **T-0015 — read access for user interfaces** (`juanbetancurm`) | 10 | read-only tokens, `GET /api/v1/me`, the UI contract: [`tasks/current/T-0015-ui-read-access.md`](tasks/current/T-0015-ui-read-access.md) | nothing (starts with ACR-0001 for OD-10) |
| **T-0016 — the web frontend** (`juanes6554`; say *"I want to implement the frontend"*) | 10 | his own framework in `frontend/`, test-driven (the agent writes the tests from his guidelines): [`tasks/current/T-0016-frontend.md`](tasks/current/T-0016-frontend.md) | T-0015 steps 1–5 merged |
| ~~SC-07 — network/DNS scenario~~ **done 2026-10-07** (T-0018, `conantkd`) | 11 | verified on vm-166, twice; RB-009 read via `query_runbook` | — |
| MCP tools child | 4 | tool calls through a separate stdio process under its own user | nothing (independent) |
| *Future:* ACR for UI actions | 10 | give the UI the scope its prototype shows (approvals, starting investigations, simulator, scheduler, health data): a new ACR; approvals touch a safety principle and need a second approval (PR #24 comment, ACR-0001 §5) | the API routes the UI would act on exist (approvals, scheduler T-0014, a health read route) |

**Priority:** T-0015 unblocks `juanes6554`'s frontend (his tests need its contract and sample data); whoever is
free takes it first. Owners above are suggestions.

Two developers can work in parallel on different rows. The VMs are used by one person at a time (`brain.py start`).
