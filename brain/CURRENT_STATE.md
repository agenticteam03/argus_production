# Current state — the last verified shared state

**As of:** 2026-10-02 · **Architecture:** v1.8.0 · **Status:** `verified` on the VMs (Tasks 0–12c); the repository
itself is being created (shared-Brain steps B1–B5 done, B6 in progress; `main` = `9ccc61d`).

> The VMs are authoritative for what runs there: check `/opt/argus-v18/DEPLOYED` (from B6) and run the state probe
> before trusting this file.

## 1. In one paragraph

Argus v1.8 runs on the two VMs. The agent on vm-095 diagnoses incidents on both hosts through the per-host gateways
and probes (vm-166 through the restricted SSH tunnel), stores everything in Postgres, and is read-only. Every scenario
runnable today passes on the real VMs. The remaining work replaces the lab mechanics still in the core — the
plain-Python runner (→ LangGraph), the direct tool provider (→ MCP tools child), the single agent container
(→ api / worker / scheduler) — and adds the missing scenarios, alerting and repeated end-to-end runs.

## 2. What runs (OBSERVED 2026-10-02)

| VM | Argus containers | Published ports |
|---|---|---|
| vm-095 | `argus-v18-agent`, `argus-v18-postgres` (healthy), `argus-v18-tunnel`, `argus-v18-read-gateway`, `-host-probe`, `-network-probe`, `-exporter`, `-prometheus`, `argus-lab-api` | `127.0.0.1:18000` only |
| vm-166 | `argus-v18-read-gateway`, `-host-probe`, `-network-probe`, `-exporter`, `-prometheus`, `argus-lab-api` (healthy), `argus-lab-cache` | `127.0.0.1:18701-18703`, `127.0.0.1:18090` |

- Code on the VMs: deployed by laptop tarball from the pre-repository folder (equivalent to this repository's code
  before the B2 sanitization). From B6 on, the VMs pull from Git (`ops/deploy.sh`).
- `/opt/argus-v18/hosts.env` exists on both VMs; the live tunnel target matches it (Task 12c).
- Agent: Postgres system of record (`argus db check` 13/13), OpenAI `gpt-5.6-luna` via the Responses API, runbooks at
  library v1.1.0. In the repository the library now lives in `argus/runbooks/` (D-002); the running agent still reads
  the mounted copy `/opt/argus-runbooks/056b36e` until its next redeploy (same content).
- Users: `juanbetancurm`, `conantkd`, `juanes6554` (operator, one shared team password); the old personal user is
  disabled. **Not yet verified:** a login test per user (legacy step 12b.2).
- Last `nonint-check.sh after`: **NO INTERFERENCE** on both VMs (2026-10-02).

## 3. Phase status

See [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) §1. Done or nearly done: 0, 1, 2, 3, 5, 6, 8, 10.
In progress: 4 (50 %), 7 (50 %), 9 (30 %), 11 (50 %), 12 (30 %), 13 (35 %). Not started: 14.

## 4. Scenarios verified on the real VMs (one run each)

H-1/H-2 (healthy checks), SC-01 (OOM, vm-166), SC-02 (non-OOM crash, vm-095), the identity proof (SC-01 + SC-02 at
once), SC-03 (dependency root cause), SC-09 (unsupported → evidence pack, no model), SC-10 (blind spot →
undiagnosable for one host only), SC-11 (refusals), SC-12 (executor partition → escalation for one host only).

## 5. Known gaps and decisions pending

- Pending team decision **D-001** (cross-host path and alert direction) and open problems OP-001…OP-003:
  [`OPEN_PROBLEMS.md`](OPEN_PROBLEMS.md).
- Differences between the architecture text and the running system: [`architecture/SUMMARY.md`](architecture/SUMMARY.md).
- Postgres backup/restore drill not done. vm-095 says "System restart required" — do not reboot (team decision).

## 6. The shared-Brain setup (in progress)

| Step | State |
|---|---|
| B1 repository + code | done (32/32 tests including Postgres) |
| B2 code sanitization, `hosts.env`, runbook pin (pin later retired by D-002) | done, verified on the VMs |
| B3 stable Brain | written |
| B4 this mutable Brain | written |
| B5 `brain.py` (+15 tests), pre-commit (Brain audit), CI workflow, root shims, `.gitattributes` | done locally; CI runs for the first time at the B6 push |
| B6 audit → first commit → push → review rule → deploy keys + `ops/deploy.sh` | audit clean; `9ccc61d` pushed; `session` branch works; branch protection **refused (free plan)** → soft rules (bootstrap PR #1); deploy keys next |
| B7 pilot T-0013 · B8 teammates · B9 retire the private notes | later |
