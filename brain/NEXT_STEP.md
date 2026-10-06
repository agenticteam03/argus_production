# Next step

**First (any developer, 5 minutes):**
1. Teammates: review the fast-track pull requests merged since 2026-10-05 (listed in
   `brain/policies/main-exceptions.txt`), see `agents/REVIEW_PROTOCOL.md` ("Temporary fast-track").
2. `conantkd`: re-review PR #8 (OP-005, updated with your requested changes).
3. At the next VM session, check vm-095 is on `main` (`deploy.sh status`); if it still shows the T-0013 branch:
   `sudo bash /opt/argus-v18/app/ops/deploy.sh main --as <you>` — same code, so nothing needs rebuilding.

**Then — the next tasks:**

| Option | Phase | What | Depends on |
|---|---|---|---|
| **T-0014 — worker + scheduler** (recommended next; `juanbetancurm`) | 9 | split the agent into api / worker / scheduler; the worker claims queued incidents and **resumes interrupted runs from their checkpoint**; the scheduler runs periodic checks and pulls firing alerts | T-0013 merged |
| **T-0015 — read access for user interfaces** (`juanbetancurm`) | 10 | read-only tokens, `GET /api/v1/me`, the UI contract: [`tasks/current/T-0015-ui-read-access.md`](tasks/current/T-0015-ui-read-access.md) | nothing (starts with ACR-0001 for OD-10) |
| **T-0016 — the web frontend** (`juanes6554`; say *"I want to implement the frontend"*) | 10 | his own framework in `frontend/`, test-driven (the agent writes the tests from his guidelines): [`tasks/current/T-0016-frontend.md`](tasks/current/T-0016-frontend.md) | T-0015 steps 1–5 merged |
| SC-07 — network/DNS scenario | 11 | a client and a backend on different Docker networks; Argus must find the network misconfiguration | nothing (independent) |
| MCP tools child | 4 | tool calls through a separate stdio process under its own user | nothing (independent) |

Two developers can work in parallel on different rows. The VMs are used by one person at a time (`brain.py start`).
