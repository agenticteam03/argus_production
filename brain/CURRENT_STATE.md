# Current state — the last verified shared state

**As of:** 2026-10-04 · **Architecture:** v1.8.0 · **Status:** `verified` on the VMs; T-0013 (LangGraph + Postgres
checkpoints) verified on vm-095 · shared-Brain setup B1–B8 under way (two developers active).

> The VMs are authoritative for what runs there: run `sudo bash /opt/argus-v18/app/ops/deploy.sh status` (or read
> `/opt/argus-v18/DEPLOYED`) and the state probe before trusting this file.

## 1. In one paragraph

Argus v1.8 runs on the two VMs. The agent on vm-095 diagnoses incidents on both hosts through the per-host gateways
and probes (vm-166 through the restricted SSH tunnel), stores everything in Postgres, and is read-only. Since T-0013 the
investigation skeleton runs as a **LangGraph graph whose state is checkpointed in Postgres** after every node, so an
interrupted investigation resumes instead of starting over. The remaining work: split the single agent container into
api / worker / scheduler (with recovery of interrupted runs), the MCP tools child, the missing scenarios, alerting
and repeated end-to-end runs.

## 2. What runs (OBSERVED 2026-10-04)

| VM | Argus containers | Published ports | Code (`deploy.sh status`) |
|---|---|---|---|
| vm-095 | `argus-v18-agent` (LangGraph runner), `argus-v18-postgres` (healthy), `argus-v18-tunnel`, `argus-v18-read-gateway`, `-host-probe`, `-network-probe`, `-exporter`, `-prometheus`, `argus-lab-api` | `127.0.0.1:18000` only | branch `task/T-0013-langgraph-skeleton` @ `c87d76c` — redeploy `main` after this PR is merged |
| vm-166 | `argus-v18-read-gateway`, `-host-probe`, `-network-probe`, `-exporter`, `-prometheus`, `argus-lab-api` (healthy), `argus-lab-cache` | `127.0.0.1:18701-18703`, `127.0.0.1:18090` | `main` @ `8eff994` |

- `/opt/argus-v18/app` is a **git checkout** on both VMs (read-only deploy key per VM); the old tarball folder is kept
  as `/opt/argus-v18/app.pre-git-<time>`. Only the agent on vm-095 was rebuilt; the other containers still run the
  code they were started with (same behaviour).
- Agent: `ARGUS_RUNNER=langgraph`, Postgres system of record with migrations `001_init` + `002_checkpoints`;
  `argus db check` **15/15**; OpenAI `gpt-5.6-luna` via the Responses API; runbooks shipped inside the image
  (`argus/runbooks/`, library v1.1.0). `/opt/argus-runbooks/056b36e` on vm-095 is no longer used.
- `/opt/argus-v18/hosts.env` on both VMs; the tunnel target matches it.
- Users: `juanbetancurm`, `conantkd`, `juanes6554` (operator, one shared team password); the old personal user is
  disabled. `juanbetancurm` logged in successfully on 2026-10-04 (T-0013 step 5).
- Last `nonint-check.sh after`: **NO INTERFERENCE** on both VMs (2026-10-04).

## 3. Phase status

See [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) §1. Done or nearly done: 0, 1, 2, 3, 5, 6, 8, 10.
In progress: 4 (50 %), 7 (50 %), **9 (50 %: LangGraph + checkpoints done; api/worker/scheduler split next)**,
11 (50 %), 12 (30 %), 13 (35 %). Not started: 14.

## 4. Scenarios verified on the real VMs

- With the plain runner (2026-10-01/02): H-1/H-2, SC-01, SC-02, the identity proof (SC-01 + SC-02 at once), SC-03,
  SC-09, SC-10, SC-11, SC-12.
- **With the LangGraph runner (2026-10-04):** H-1 (healthy), SC-09 (unsupported → evidence pack), SC-01 (diagnosed,
  RB-001) — every run checkpointed in Postgres. The others are expected to behave the same (parity tests); re-run
  them as part of Phase 12.

## 5. Known gaps and decisions pending

- **`main-guard` is red** since PR #4 was merged without a recorded approval (content reviewed, documentation only):
  `conantkd` approves PR #4 on GitHub, or a reviewed PR adds `pr 4` to `policies/main-exceptions.txt`.
- Pending team decision **D-001** (cross-host path and alert direction) and open problems OP-001…OP-003:
  [`OPEN_PROBLEMS.md`](OPEN_PROBLEMS.md).
- Differences between the architecture text and the running system: [`architecture/SUMMARY.md`](architecture/SUMMARY.md).
- Nothing resumes an interrupted run automatically yet (no worker recovery loop): that belongs to the
  api/worker/scheduler split.
- Postgres backup/restore drill not done. vm-095 says "System restart required" — do not reboot (team decision).

## 6. The shared-Brain setup

| Step | State |
|---|---|
| B1–B5 repository, sanitization, Brain, `brain.py`, CI, hooks | done |
| B6 first push, soft review rules (free plan), deploy keys, `ops/deploy.sh` | done (PRs #1, #2; `deploy.sh init` on both VMs 2026-10-04) |
| B7 pilot T-0013 | done (this PR) |
| B8 teammates | `conantkd` onboarded (PR #3, first review); `juanes6554` pending |
| B9 retire the private notes | later |
