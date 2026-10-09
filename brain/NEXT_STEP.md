# Next step

**OP-008 (2026-10-09, `conantkd`):** snapshot-consistent backup, verified markers, and preview-first backup retention
are implemented on `task/OP-008-backup-retention`. Fifteen tests pass locally, including two with throwaway PostgreSQL
containers and a write during `pg_dump`. Next, when the VM lease is available, check restorable backup evidence and run
`prune` in dry-run mode only. Review the listed sets with a teammate before any live `--apply`; scheduling remains a
separate team decision. See [the task file](tasks/current/OP-008-backup-retention.md).

**Now (2026-10-09, `conantkd`).** `main` has #38 (T-0020), #39 (T-0021 fixes, ACR-0002), #40 (T-0023 runner) and
#41 (OP-005, verified on both VMs). Three branches stacked on `main`, each with `main` merged in:
`task/T-0022-alerting` (phase 7, ACR-0003, **done**: verified on both VMs) → `task/OP-010-reserved-slot` (verified on vm-166) →
`task/T-0024-sc05-disk` (SC-05, **done**: DIAGNOSED on vm-166). Both VMs now run `task/T-0024-sc05-disk` `b049086` (T-0022 + OP-010 + T-0024 + `main`): vm-095 pulls firing alerts
from both Alertmanagers. Both LAB BASELINE OK, NO INTERFERENCE. Open: #42 (OP-004, draft, reviewed), #43 (CI step for OP-005, waits for `juanbetancurm`).

1. **PRs:** T-0022 (needs `juanbetancurm`'s second approval: ACR-0003 touches host isolation), then OP-010, then
   T-0024 (draft until its VM steps). After T-0022 and OP-010 merge, vm-166 goes to `main`.
2. **Done 2026-10-09:** T-0024 steps 2-4: SC-05 DIAGNOSED from the pulled alert (`inc_4d78232433a1`). vm-166 keeps the
   lab filesystem `/srv/argus-lab-fill` (testing only; `ops/lab-fill-mount.sh --remove` takes it away).
3. **Done 2026-10-09:** T-0022 steps 5-6 (alerts pulled from both hosts; SC-03 and SC-02 DIAGNOSED from their alerts).
   OP-010 DIAGNOSED at 100 % from the pulled alert (fixed). After the PRs merge: both VMs to `main`.
   **OP-011:** two alerts on one target open two incidents (§6.4 correlation) — the next code task.
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
