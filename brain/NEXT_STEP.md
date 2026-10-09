# Next step

**OP-005 (2026-10-09, `conantkd`):** the exporter creation metric and young-first `restarts_10m` expression are
implemented on `task/OP-005-young-restarts`. Offline unit and PromQL tests pass. VM verification is still needed:
first resolve PR #38's review and merge, then take the VM lease, probe both hosts, deploy OP-005 from the updated
`main`, and run the SC-01 and old-container checks in [the task file](tasks/current/OP-005-restart-signal.md).
Do not replace vm-166's T-0020 checkout with a branch that predates PR #38.

**Now (2026-10-09, `juanbetancurm`):** PR #36 (T-0021) was merged into `main` (`a9b4df8`) at its earlier head
`289bb0d`, before the review fixes and before the re-review: **`main-guard` is red** and `main` has the OLD
tools-server launcher (a package planted in the worker's folder would run as `argus-tools`). The fix is the
follow-up PR from `task/T-0021-review-fixes`: the launcher runs `cd /` and `python -I` (`isolation_check` probes
it), [ACR-0002](architecture/changes/ACR-0002-tools-uid-sudo-launcher.md) (proposed: the sudo launcher, OD-3 kept
MCP), a hung tools process is replaced, vm-095's compose defaults to `mcp`. **It needs `conantkd`'s review and
his second approval of ACR-0002** (no fast-track: ACR, safety principle). Step 5e is done: vm-095 runs the fixed
launcher (`6f45218`), TOOLS ISOLATION OK ([evidence](execution/history/T-0021/step-05e/evidence.md)).
**Do not deploy `main` on vm-095 until the follow-up merges** (it would bring back the old launcher). vm-166 is
untouched. Next work after it: OP-009, OP-010, OP-004, alerting (T-0022), the end-to-end runner (phase 12).

**Earlier (2026-10-08, end of `juanbetancurm`'s session; lease handed to `conantkd`):** T-0021 (tools in a separate
MCP process under `argus-tools`) is done and verified on vm-095 ([evidence](execution/history/T-0021/step-05/evidence.md)):
TOOLS ISOLATION OK, OD-3 OK. **PR #36 needs a teammate's review** (safety model, no fast-track). vm-095 runs
`task/T-0021-tool-isolation` `a5f330a` with the worker in `mcp` mode: do not deploy `main` there before #36 merges
without the rollback (evidence, block R). vm-166 is untouched on `task/T-0020-sc04-pg-connections`. Owed:
after-merge reviews of #33 and #37; reviews of #34, #35, #36. Next work: T-0020 (SC-04) PR by `conantkd`; OP-004
checkpoint cleanup; alerting (phase 7).

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
