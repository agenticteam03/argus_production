# Next step

**First (any developer, 5 minutes):**
1. Review and merge the T-0013 pull request (`task/T-0013-langgraph-skeleton`) — not by its author.
2. Turn `main-guard` green: `conantkd` opens PR #4 → Files changed → Review changes → **Approve**; if GitHub refuses
   on a merged PR, open a small PR adding `pr 4` to `brain/policies/main-exceptions.txt` (reviewed by someone else).
3. After the T-0013 merge, put vm-095 back on `main` (VM lease): `sudo bash /opt/argus-v18/app/ops/deploy.sh main
   --as <you>` — same code, so nothing needs rebuilding.

**Then — the next task (to be created by whoever takes it, as `tasks/current/T-0014-<slug>.md`):**

| Option | Phase | What | Depends on |
|---|---|---|---|
| **T-0014 — worker + scheduler** (recommended next) | 9 | split the agent into api / worker / scheduler; the worker claims queued incidents and **resumes interrupted runs from their checkpoint**; the scheduler runs periodic checks and pulls firing alerts | T-0013 merged |
| SC-07 — network/DNS scenario | 11 | a client and a backend on different Docker networks; Argus must find the network misconfiguration | nothing (independent) |
| MCP tools child | 4 | tool calls through a separate stdio process under its own user | nothing (independent) |

Two developers can work in parallel on different rows. The VMs are used by one person at a time (`brain.py start`).
