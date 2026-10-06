# Next step

**Now (2026-10-06):** both VMs run `main` `2097eb1` (AFTER-MERGE done). (1) PR #19 (`juanes6554` on the fast-track)
merged (approved by `conantkd`); (2) T-0015: draft ACR-0001 (needs `conantkd`'s approval).

**Pending VM step after the T-0017 PR merges (`conantkd`, 2026-10-06):** vm-095 runs the checkout of
`task/T-0017-pg-backup-drill` (only `ops/db-backup.sh`, tests and the Brain differ from `main`). Once merged,
whoever holds the VM lease puts it back on `main` with the block in `execution/current/code.bash` (~2 min, no
rebuild). vm-166 is already on `main`. Phase 5 is complete (backup/restore drill, T-0017).

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
| **T-0014 — worker + scheduler** (recommended next; `juanbetancurm`) | 9 | split the agent into api / worker / scheduler; the worker claims queued incidents and **resumes interrupted runs from their checkpoint**; the scheduler runs periodic checks and pulls firing alerts | T-0013 merged |
| **T-0015 — read access for user interfaces** (`juanbetancurm`) | 10 | read-only tokens, `GET /api/v1/me`, the UI contract: [`tasks/current/T-0015-ui-read-access.md`](tasks/current/T-0015-ui-read-access.md) | nothing (starts with ACR-0001 for OD-10) |
| **T-0016 — the web frontend** (`juanes6554`; say *"I want to implement the frontend"*) | 10 | his own framework in `frontend/`, test-driven (the agent writes the tests from his guidelines): [`tasks/current/T-0016-frontend.md`](tasks/current/T-0016-frontend.md) | T-0015 steps 1–5 merged |
| SC-07 — network/DNS scenario | 11 | a client and a backend on different Docker networks; Argus must find the network misconfiguration | nothing (independent) |
| MCP tools child | 4 | tool calls through a separate stdio process under its own user | nothing (independent) |

**Priority:** T-0015 unblocks `juanes6554`'s frontend (his tests need its contract and sample data); whoever is
free takes it first. Owners above are suggestions.

Two developers can work in parallel on different rows. The VMs are used by one person at a time (`brain.py start`).
