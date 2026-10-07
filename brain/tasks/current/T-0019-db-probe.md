# T-0019 — Phase 3: the database probe (`db-probe`) and `database.health`

| Field | Value |
|---|---|
| Status | `planned` — 2026-10-07 |
| Phase | 3 — target services ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md): "DB probe (with SC-04)") |
| Architecture | no change (no ACR): §4.6 `db-probe`, §12.2 `inspect_database_health` → `database.health` (Level 3) |
| Branch | `task/T-0019-db-probe`, **on top of `task/T-0018-sc07-network`** (PR #27 open; the VMs run its code). Its PR opens after #27 merges, with `main` merged in first |
| Owner | `conantkd` (+ agent) |
| Needs the VM lease | the read-only checks, the deploy and the verification (vm-166 target side, vm-095 agent) |

## Goal (plain language)

Argus can read the health of a PostgreSQL database on the target host: how full its connection slots are, which
clients hold them and in which state, long transactions and lock waits — through a probe that runs **on the target
host** with a **read-only monitoring role** and never reads business rows or SQL text. It is the last missing
target-side service of phase 3 and the evidence SC-04 (connection exhaustion, RB-004) will need.

## Decisions (2026-10-07, `conantkd`)

- **`argus-lab-db` is always on** (lab baseline on vm-166), **for testing only**: it gives the probe something to
  measure and a healthy reference before SC-04. A production deployment does not need it — the probe points at the
  real database instead. This must be stated in the PR (comment) and where the environment is described
  (`infrastructure/environment.md`, `docs/INCIDENTS.md` targets table, the compose file comment).
- **Driver: `pg8000`** (pure Python, no compiler in the Alpine image), version pinned with hashes.
- **Tool levels:** `database.health` is Level 3; `max_tool_level` is already 3 (fixed in PR #27).
- **Branch:** on top of T-0018, as above.

## Design (to confirm step by step)

- **Lab DB:** `argus-lab-db`, `postgres:16-alpine`, profile `base-166`, network `argus-lab-app`, data in tmpfs,
  hard limits, `max_connections=20` (RB-004's lab case), no published port. A role `argus_monitor` with
  `pg_monitor` only (no table privileges); its password generated on vm-166, never printed.
- **Probe:** `ROLE=db_probe` in `services/target/service.py` (one codebase, one role per container), route
  `GET /database/health?name=<allowlisted db>`: max/reserved connections, counts by state and by
  `application_name`, the longest transactions (age, state, wait event — **no query text**), lock waits, usage
  percent. Queries only system views (`pg_stat_activity`, `pg_locks`, `pg_settings`). Token `db_probe`.
- **Deployment:** `argus-v18-db-probe` in `deploy/target/compose.target.yml`, `127.0.0.1:18704` in
  `compose.loopback.yml` (the tunnel already forwards 18704).
- **Agent side:** capability `database.health` (`inspect_database_health`, executor `db_probe`, Level 3), policy
  limit, `db_probe` in `EXECUTOR_KINDS`, inventory (`vm-166/container:argus-lab-db`, executor URL through the
  tunnel), the agent's `db_probe` token (generated on the VMs, never printed). Ordering matters: the agent refuses
  to start when a host executor has no token, so the secrets come before the agent restart.

## Steps

1. Read-only checks on vm-166: PyPI reachable for the image build; nothing on `127.0.0.1:18704`; memory headroom.
2. Tests first, then code (probe, capability, inventory, compose, policy).
3. Secrets (generated on the VMs), deploy, verify: the probe answers for the healthy lab DB, Argus reads it through
   `inspect_database_health`, the answer holds no SQL text and no rows. NO INTERFERENCE.
4. Brain: plan (phase 3 → 100 % for the DB probe), environment, INCIDENTS, journal; PR with the `argus-lab-db`
   "testing only" note as a comment.

## Red seen / evidence

(filled in as the steps run)
