# Current state — the last verified shared state

**As of:** 2026-10-06 (DEPLOY-MAIN by `conantkd`) · **Architecture:** v1.8.0 · **Status:** `verified` on
the VMs; T-0013 (LangGraph + Postgres checkpoints) merged and **deployed: both VMs run `main` `09f5ab1`** (§2) ·
shared-Brain setup B1–B8 under way (three developers).

> The VMs are authoritative for what runs there: run `sudo bash /opt/argus-v18/app/ops/deploy.sh status` (or read
> `/opt/argus-v18/DEPLOYED`) and the state probe before trusting this file.

## 1. In one paragraph

Argus v1.8 runs on the two VMs. The agent on vm-095 diagnoses incidents on both hosts through the per-host gateways
and probes (vm-166 through the restricted SSH tunnel), stores everything in Postgres, and is read-only. Since T-0013 the
investigation skeleton runs as a **LangGraph graph whose state is checkpointed in Postgres** after every node, so an
interrupted investigation resumes instead of starting over. The remaining work: split the single agent container into
api / worker / scheduler (with recovery of interrupted runs), the MCP tools child, the missing scenarios, alerting
and repeated end-to-end runs.

## 2. What runs (OBSERVED 2026-10-06)

| VM | Argus containers | Published ports | Code (`deploy.sh status`) |
|---|---|---|---|
| vm-095 | `argus-v18-agent` (LangGraph runner), `argus-v18-postgres` (healthy), `argus-v18-tunnel`, `argus-v18-read-gateway`, `-host-probe`, `-network-probe`, `-exporter`, `-prometheus`, `argus-lab-api` | `127.0.0.1:18000` only | `main` `2097eb1` — agent rebuilt 2026-10-06 (AFTER-MERGE; the image matches the deployed commit) |
| vm-166 | `argus-v18-read-gateway`, `-host-probe`, `-network-probe`, `-exporter`, `-prometheus`, `argus-lab-api` (healthy), `argus-lab-cache` | `127.0.0.1:18701-18703`, `127.0.0.1:18090` | checkout `58a51c3` (`task/lab-baseline-check`); its services equal `main`'s. **Pending:** move to `main` (`execution/current/code.bash`, ~3 min) |

- `/opt/argus-v18/app` is a **git checkout** on both VMs (read-only deploy key per VM); the old tarball folder is kept
  as `/opt/argus-v18/app.pre-git-<time>`. Only the agent on vm-095 was rebuilt; the other containers still run the
  code they were started with (same behaviour).
- Agent: `ARGUS_RUNNER=langgraph`, Postgres system of record with migrations `001_init` + `002_checkpoints`;
  `argus db check` **15/15**; OpenAI `gpt-5.6-luna` via the Responses API; runbooks shipped inside the image
  (`argus/runbooks/`, library v1.1.0). `/opt/argus-runbooks/056b36e` on vm-095 is no longer used.
- `/opt/argus-v18/hosts.env` on both VMs; the tunnel target matches it.
- Users: `juanbetancurm`, `conantkd`, `juanes6554` (operator, one shared team password); the old personal user is
  disabled. Login test per user (legacy step 12b.2) **done 2026-10-05**: all three log in and get `outcome: HEALTHY`
  on a `--check` of `vm-095/container:argus-lab-api`.
- Last `nonint-check.sh after`: **NO INTERFERENCE** on both VMs (2026-10-06).
- **Latest (OBSERVED 2026-10-06, AFTER-MERGE):** vm-095 `commit=2097eb1…`, `ref=main`, agent rebuilt, `LAB BASELINE OK`,
  NO INTERFERENCE; vm-166's block was not run (still `58a51c3`). Evidence:
  [`execution/history/AFTER-MERGE/step-01/evidence.md`](execution/history/AFTER-MERGE/step-01/evidence.md).
- **Deployed code (OBSERVED earlier on 2026-10-06, `/opt/argus-v18/DEPLOYED`):** both VMs `commit=09f5ab1…`, `ref=main`
  (DEPLOY-MAIN). On vm-095 migrations `001_init` + `002_checkpoints` are applied (no new one) and `argus-v18-agent`
  was rebuilt from `main` and runs with `ARGUS_RUNNER=langgraph`; `argus db check` 15/15.
  Evidence: [`execution/history/DEPLOY-MAIN/step-01/evidence.md`](execution/history/DEPLOY-MAIN/step-01/evidence.md).
- **T-0013 step 5 verified 2026-10-05** (by the reviewer `conantkd`): `argus db check` 15/15, H-1 `HEALTHY`, SC-09
  `UNSUPPORTED → escalated`, SC-01 `DIAGNOSED` (RB-001), every run checkpointed in Postgres, NO INTERFERENCE.
  Evidence: [`execution/history/T-0013-review/step-01/evidence.md`](execution/history/T-0013-review/step-01/evidence.md).

## 3. Phase status

See [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) §1. Done or nearly done: 0, 1, 2, 3, 5, 6, 8, 10.
In progress: 4 (50 %), 7 (50 %), **9 (55 %: LangGraph + checkpoints + OP-006 done; api/worker/scheduler split
next)**, 11 (50 %), 12 (30 %), 13 (35 %). Not started: 14. Phase 10 (90 %) gets a read-only web UI as new scope:
T-0015 (API side) and T-0016 (frontend), planned.

## 4. Scenarios verified on the real VMs

- With the plain runner (2026-10-01/02): H-1/H-2, SC-01, SC-02, the identity proof (SC-01 + SC-02 at once), SC-03,
  SC-09, SC-10, SC-11, SC-12.
- **With the LangGraph runner (2026-10-04):** H-1 (healthy), SC-09 (unsupported → evidence pack), SC-01 (diagnosed,
  RB-001) — every run checkpointed in Postgres.
- **All the plain-runner scenarios now pass on LangGraph (2026-10-06, final `main` agent, one run each):** H-2,
  SC-02, the identity proof, SC-10, SC-11, SC-12 (LGS), plus SC-03 (DEPLOY-MAIN). SC-12 escalates at step 2 (plain
  runner: step 3). Evidence: [`execution/history/LGS/step-01/evidence.md`](execution/history/LGS/step-01/evidence.md).
  Phase 12 still needs ≥ 5 runs per scenario.
- **SC-03 on the LangGraph runner: verified 2026-10-06** on the final `main` code (DEPLOY-MAIN D.5): `DIAGNOSED`,
  root cause `vm-166/container:argus-lab-cache`, confidence high, the api the victim; H-1 `HEALTHY` before (after
  restoring the lab) and after: [`execution/history/DEPLOY-MAIN/step-01/evidence.md`](execution/history/DEPLOY-MAIN/step-01/evidence.md)
  (the 2026-10-05 class demo record: [`execution/history/demo-SC03/step-01/evidence.md`](execution/history/demo-SC03/step-01/evidence.md)).

## 5. Known gaps and decisions pending

- `main-guard` is green: PRs #4 and #9–#13 are recorded exceptions in `policies/main-exceptions.txt`.
- PR #8 (OP-005) was approved by `conantkd` on 2026-10-06 and waits for its author's merge.
- **After-merge reviews of the fast-track PRs #9–#13: all done** by `conantkd` (2026-10-06), no defects. The
  fast-track rule is accepted; the `main-exceptions.txt` header now says fast-track lines are reviewed after the
  merge; OP-006's constants are named (`GraphRunner.FIXED_NODES`, `SAFETY_MARGIN`). **T-0015:** its ACR-0001 pull
  request cannot be fast-tracked (the rule excludes ACRs); its token code should also get a teammate's review.
- **Temporary fast-track until 2026-10-12:** `juanbetancurm` and `conantkd` may merge their own pull requests under the conditions
  of `agents/REVIEW_PROTOCOL.md` ("Temporary fast-track"); each one is listed in `main-exceptions.txt` and reviewed
  by a teammate after the merge.
- Pending team decision **D-001** (cross-host path and alert direction) and open problems OP-001…OP-003:
  [`OPEN_PROBLEMS.md`](OPEN_PROBLEMS.md).
- Differences between the architecture text and the running system: [`architecture/SUMMARY.md`](architecture/SUMMARY.md).
- Nothing resumes an interrupted run automatically yet (no worker recovery loop): that belongs to the
  api/worker/scheduler split.
- Lab baseline: `deploy.sh status` now ends with `LAB BASELINE OK` or names the stopped/unhealthy `argus-lab-*`
  (DEPLOY-MAIN found `argus-lab-cache` stopped for ~7 h; `nonint-check.sh` does not cover Argus objects).
- Postgres backup/restore drill not done. vm-095 says "System restart required" — do not reboot (team decision).

## 6. The shared-Brain setup

| Step | State |
|---|---|
| B1–B5 repository, sanitization, Brain, `brain.py`, CI, hooks | done |
| B6 first push, soft review rules (free plan), deploy keys, `ops/deploy.sh` | done (PRs #1, #2; `deploy.sh init` on both VMs 2026-10-04) |
| B7 pilot T-0013 | done (PR #6) |
| B8 teammates | `conantkd` onboarded (PR #3, first review); `juanes6554` pending — his entry is T-0016 (*"I want to implement the frontend"*) |
| B9 retire the private notes | later |
