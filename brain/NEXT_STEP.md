# Next step

**First (any developer, 5 minutes):**
1. Teammates: review the fast-track pull requests merged since 2026-10-05 (listed in
   `brain/policies/main-exceptions.txt`), see `agents/REVIEW_PROTOCOL.md` ("Temporary fast-track").
2. `juanbetancurm`: update PR #8 (OP-005) with `conantkd`'s requested changes (creation-time guard, scrape-gap test,
   resolve the `OPEN_PROBLEMS.md` conflict).
3. At the next VM session, check vm-095 is on `main` (`deploy.sh status`); if it still shows the T-0013 branch:
   `sudo bash /opt/argus-v18/app/ops/deploy.sh main --as <you>` — same code, so nothing needs rebuilding.

**Then — the next task (to be created by whoever takes it, as `tasks/current/T-0014-<slug>.md`):**

| Option | Phase | What | Depends on |
|---|---|---|---|
| **T-0014 — worker + scheduler** (recommended next) | 9 | split the agent into api / worker / scheduler; the worker claims queued incidents and **resumes interrupted runs from their checkpoint**; the scheduler runs periodic checks and pulls firing alerts | T-0013 merged |
| SC-07 — network/DNS scenario | 11 | a client and a backend on different Docker networks; Argus must find the network misconfiguration | nothing (independent) |
| MCP tools child | 4 | tool calls through a separate stdio process under its own user | nothing (independent) |

Two developers can work in parallel on different rows. The VMs are used by one person at a time (`brain.py start`).
